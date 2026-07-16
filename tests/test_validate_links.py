#!/usr/bin/env python3
"""
Regression tests for the link-health eval (fetchers/validate_links.py).

Covers the classification logic against mocked HTTP responses -- no
network calls are made.

    python3 -m unittest tests.test_validate_links
"""

import os
import sys
import time
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'fetchers'))

import validate_links as vl  # noqa: E402


def _mock_response(status: int, final_url: str):
    resp = MagicMock()
    resp.status = status
    resp.geturl.return_value = final_url
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


class ClassifyTests(unittest.TestCase):
    def test_live_job_page(self):
        url = 'https://boards.greenhouse.io/acme/jobs/12345'
        with patch('urllib.request.urlopen', return_value=_mock_response(200, url)):
            result = vl.classify(url)
        self.assertEqual(result.status, 'live')
        self.assertEqual(result.http_status, 200)

    def test_redirect_to_generic_listing_is_flagged(self):
        url = 'https://boards.greenhouse.io/acme/jobs/12345'
        final = 'https://boards.greenhouse.io/acme/jobs'
        with patch('urllib.request.urlopen', return_value=_mock_response(200, final)):
            result = vl.classify(url)
        self.assertEqual(result.status, 'redirected')

    def test_greenhouse_error_redirect_is_dead(self):
        # Real bug caught in production: Greenhouse 302s a closed posting to
        # /{company}?error=true -- the path is just the bare company slug,
        # so it doesn't end in jobs/careers/positions and was previously
        # misclassified as "live".
        url = 'https://job-boards.greenhouse.io/reddit/jobs/6721235'
        final = 'https://job-boards.greenhouse.io/reddit?error=true'
        with patch('urllib.request.urlopen', return_value=_mock_response(200, final)):
            result = vl.classify(url)
        self.assertEqual(result.status, 'dead')

    def test_redirect_stripped_to_bare_company_slug_is_flagged(self):
        url = 'https://boards.greenhouse.io/acme/jobs/12345'
        final = 'https://boards.greenhouse.io/acme'  # no error=true, but still shorter/generic
        with patch('urllib.request.urlopen', return_value=_mock_response(200, final)):
            result = vl.classify(url)
        self.assertEqual(result.status, 'redirected')

    def test_redirect_between_two_specific_job_pages_is_live(self):
        # e.g. a permalink that 301s to a canonical URL for the *same* job
        url = 'https://boards.greenhouse.io/acme/jobs/12345'
        final = 'https://boards.greenhouse.io/acme/jobs/12345-staff-pm'
        with patch('urllib.request.urlopen', return_value=_mock_response(200, final)):
            result = vl.classify(url)
        self.assertEqual(result.status, 'live')

    def test_404_is_dead(self):
        url = 'https://boards.greenhouse.io/acme/jobs/99999'
        err = urllib.error.HTTPError(url, 404, 'Not Found', None, None)
        with patch('urllib.request.urlopen', side_effect=err):
            result = vl.classify(url)
        self.assertEqual(result.status, 'dead')
        self.assertEqual(result.http_status, 404)

    def test_403_is_unverifiable_not_dead(self):
        # e.g. LinkedIn blocking bot/HEAD traffic on a link that may well be live
        url = 'https://www.linkedin.com/comm/jobs/view/12345/'
        err = urllib.error.HTTPError(url, 403, 'Forbidden', None, None)
        with patch('urllib.request.urlopen', side_effect=err):
            result = vl.classify(url)
        self.assertEqual(result.status, 'unverifiable')

    def test_5xx_is_error_not_dead(self):
        url = 'https://example.com/jobs/1'
        err = urllib.error.HTTPError(url, 503, 'Service Unavailable', None, None)
        with patch('urllib.request.urlopen', side_effect=err):
            result = vl.classify(url)
        self.assertEqual(result.status, 'error')

    def test_405_retries_with_get(self):
        url = 'https://example.com/jobs/1'
        err = urllib.error.HTTPError(url, 405, 'Method Not Allowed', None, None)
        with patch('urllib.request.urlopen', side_effect=[err, _mock_response(200, url)]):
            result = vl.classify(url)
        self.assertEqual(result.status, 'live')

    def test_timeout_is_error(self):
        url = 'https://example.com/jobs/1'
        with patch('urllib.request.urlopen', side_effect=TimeoutError('timed out')):
            result = vl.classify(url)
        self.assertEqual(result.status, 'error')


class ScoreSummaryTests(unittest.TestCase):
    def test_score_counts_and_ratio(self):
        results = [
            vl.LinkCheckResult('u1', 'live', 200, 'u1', 'now'),
            vl.LinkCheckResult('u2', 'live', 200, 'u2', 'now'),
            vl.LinkCheckResult('u3', 'dead', 404, None, 'now'),
            vl.LinkCheckResult('u4', 'unverifiable', 403, None, 'now'),
        ]
        summary = vl.score_summary(results)
        self.assertEqual(summary['total'], 4)
        self.assertEqual(summary['counts']['live'], 2)
        self.assertEqual(summary['score'], '2/4 verified live')

    def test_empty_results(self):
        summary = vl.score_summary([])
        self.assertEqual(summary['score'], '0/0 verified live')


class FastCheckTests(unittest.TestCase):
    def test_empty_input_returns_immediately(self):
        self.assertEqual(vl.fast_check([]), [])

    def test_fast_responses_all_classified_correctly(self):
        urls = ['https://a.example/jobs/1', 'https://b.example/jobs/2']

        def fake_urlopen(req, timeout=None):
            return _mock_response(200, req.full_url)

        with patch('urllib.request.urlopen', side_effect=fake_urlopen):
            results = vl.fast_check(urls, overall_deadline=2, per_request_timeout=1)

        self.assertEqual([r.status for r in results], ['live', 'live'])
        # order matches input order, not completion order
        self.assertEqual([r.url for r in results], urls)

    def test_slow_host_times_out_without_blocking_the_batch(self):
        urls = ['https://slow.example/jobs/1', 'https://fast.example/jobs/2']

        def fake_urlopen(req, timeout=None):
            if 'slow' in req.full_url:
                time.sleep(2)  # longer than the overall deadline below
                return _mock_response(200, req.full_url)
            return _mock_response(200, req.full_url)

        start = time.monotonic()
        with patch('urllib.request.urlopen', side_effect=fake_urlopen):
            results = vl.fast_check(urls, overall_deadline=0.3, per_request_timeout=5)
        elapsed = time.monotonic() - start

        by_url = {r.url: r for r in results}
        self.assertEqual(by_url['https://slow.example/jobs/1'].status, 'timeout')
        self.assertEqual(by_url['https://fast.example/jobs/2'].status, 'live')
        # the whole batch returns close to the deadline, not after the slow host finishes
        self.assertLess(elapsed, 1.0)

    def test_dead_link_among_fast_batch(self):
        urls = ['https://a.example/jobs/1', 'https://a.example/jobs/gone']

        def fake_urlopen(req, timeout=None):
            if 'gone' in req.full_url:
                raise urllib.error.HTTPError(req.full_url, 404, 'Not Found', None, None)
            return _mock_response(200, req.full_url)

        with patch('urllib.request.urlopen', side_effect=fake_urlopen):
            results = vl.fast_check(urls, overall_deadline=2, per_request_timeout=1)

        by_url = {r.url: r for r in results}
        self.assertEqual(by_url['https://a.example/jobs/1'].status, 'live')
        self.assertEqual(by_url['https://a.example/jobs/gone'].status, 'dead')


if __name__ == '__main__':
    unittest.main()
