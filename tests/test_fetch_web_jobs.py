#!/usr/bin/env python3
"""
Regression tests for the web/career-page job fetcher (fetchers/fetch_web_jobs.py).

Covers the parsing/filtering logic against mocked ATS API responses — no
network calls are made. Runs on the stdlib only:

    python3 -m unittest tests.test_fetch_web_jobs
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'fetchers'))

import fetch_web_jobs as fwj  # noqa: E402

GREENHOUSE_RESPONSE = {
    'jobs': [
        {
            'title': 'Staff Product Manager, Platform',
            'location': {'name': 'Remote - US'},
            'absolute_url': 'https://boards.greenhouse.io/acme/jobs/1',
            'updated_at': '2026-07-14T10:00:00-00:00',
        },
        {
            'title': '',  # malformed — no title, must be skipped
            'location': {'name': 'Remote'},
            'absolute_url': 'https://boards.greenhouse.io/acme/jobs/2',
            'updated_at': '2026-07-14T10:00:00-00:00',
        },
    ]
}

LEVER_RESPONSE = [
    {
        'text': 'Senior Software Engineer',
        'categories': {'location': 'San Francisco'},
        'hostedUrl': 'https://jobs.lever.co/acme/1',
        'createdAt': 1752480000000,
    },
]

JOB_PROFILE = {
    'target_companies': ['Acme'],
    'job_functions': ['Product Manager'],
    'experience_by_function': {
        'Product Manager': {
            'years': 10,
            'level_keywords': ['staff', 'principal'],
        }
    },
}


class SlugifyTests(unittest.TestCase):
    def test_slugify_normalises_company_names(self):
        self.assertEqual(fwj.slugify('Acme'), 'acme')
        self.assertEqual(fwj.slugify('Acme, Inc.'), 'acmeinc')
        self.assertEqual(fwj.slugify('  Acme Corp  '), 'acmecorp')


class ProfileMatchTests(unittest.TestCase):
    def test_matches_job_function(self):
        self.assertTrue(fwj.matches_job_profile('Staff Product Manager, Platform', JOB_PROFILE))

    def test_rejects_unrelated_function(self):
        self.assertFalse(fwj.matches_job_profile('Senior Software Engineer', JOB_PROFILE))

    def test_empty_profile_matches_everything(self):
        self.assertTrue(fwj.matches_job_profile('Anything at all', {}))

    def test_rejects_bare_level_keyword_without_function_core_word(self):
        # Regression: "Industry Principal, Life Sciences" and "Research
        # Engineer (Senior Staff+)" both matched pre-fix because "principal"
        # and "staff" are level keywords for Product Manager, but neither
        # title has anything to do with product management.
        self.assertFalse(fwj.matches_job_profile('Industry Principal, Life Sciences', JOB_PROFILE))
        self.assertFalse(fwj.matches_job_profile('Research Engineer (Senior Staff+)', JOB_PROFILE))

    def test_accepts_level_keyword_with_function_core_word(self):
        self.assertTrue(fwj.matches_job_profile('Principal Product Manager, Growth', JOB_PROFILE))

    def test_word_boundary_prevents_substring_false_positive(self):
        # Regression: "product" is a substring of "productivity" and
        # "manager" would be if a role said "management" — naive `in`
        # checks let "Staff+ Software Engineer, Developer Productivity"
        # match Product Manager. Word-boundary matching must reject it.
        self.assertFalse(fwj.matches_job_profile(
            'Staff+ Software Engineer, Developer Productivity', JOB_PROFILE))


class FetchGreenhouseTests(unittest.TestCase):
    @patch.object(fwj, '_http_get_json', return_value=GREENHOUSE_RESPONSE)
    def test_parses_valid_listing_and_skips_malformed(self, _mock):
        listings = fwj.fetch_greenhouse('Acme')
        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0]['title'], 'Staff Product Manager, Platform')
        self.assertEqual(listings[0]['company'], 'Acme')
        self.assertEqual(listings[0]['source'], 'web_greenhouse')
        self.assertEqual(listings[0]['date_posted'], '2026-07-14')

    @patch.object(fwj, '_http_get_json', return_value=None)
    def test_returns_none_when_company_not_on_greenhouse(self, _mock):
        self.assertIsNone(fwj.fetch_greenhouse('NotOnGreenhouse'))


class FetchLeverTests(unittest.TestCase):
    @patch.object(fwj, '_http_get_json', return_value=LEVER_RESPONSE)
    def test_parses_valid_listing(self, _mock):
        listings = fwj.fetch_lever('Acme')
        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0]['title'], 'Senior Software Engineer')
        self.assertEqual(listings[0]['source'], 'web_lever')

    @patch.object(fwj, '_http_get_json', return_value=None)
    def test_returns_none_when_company_not_on_lever(self, _mock):
        self.assertIsNone(fwj.fetch_lever('NotOnLever'))


class FetchCompanyListingsTests(unittest.TestCase):
    @patch.object(fwj, 'fetch_lever', return_value=None)
    @patch.object(fwj, 'fetch_greenhouse', return_value=[{'title': 'x'}])
    def test_falls_back_from_greenhouse_to_lever(self, mock_gh, mock_lever):
        listings, covered = fwj.fetch_company_listings('Acme')
        self.assertTrue(covered)
        self.assertEqual(listings, [{'title': 'x'}])

    @patch.object(fwj, 'fetch_lever', return_value=None)
    @patch.object(fwj, 'fetch_greenhouse', return_value=None)
    def test_reports_uncovered_when_no_ats_matches(self, mock_gh, mock_lever):
        listings, covered = fwj.fetch_company_listings('NotOnAnyKnownATS')
        self.assertFalse(covered)
        self.assertEqual(listings, [])


class FetchAllTests(unittest.TestCase):
    @patch.object(fwj, 'fetch_company_listings')
    def test_filters_by_profile_and_tracks_coverage(self, mock_fetch):
        mock_fetch.return_value = (
            [
                {'title': 'Staff Product Manager, Platform', 'company': 'Acme',
                 'location': '', 'url': '', 'date_posted': None, 'source': 'web_greenhouse'},
                {'title': 'Senior Software Engineer', 'company': 'Acme',
                 'location': '', 'url': '', 'date_posted': None, 'source': 'web_greenhouse'},
            ],
            True,
        )
        data = fwj.fetch_all(JOB_PROFILE)
        self.assertEqual(data['listing_count'], 1)
        self.assertEqual(data['profile_filtered_count'], 1)
        self.assertEqual(data['covered_companies'], ['Acme'])
        self.assertEqual(data['uncovered_companies'], [])


if __name__ == '__main__':
    unittest.main()
