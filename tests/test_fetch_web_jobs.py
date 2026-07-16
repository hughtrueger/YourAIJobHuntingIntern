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

    def test_rejects_designer_and_tpm_titles_sharing_one_core_word(self):
        # Regression, found live in state/web_jobs.json: requiring just ANY
        # core word let "Staff Product Designer" match on "product" alone
        # and "Principal Technical Program Manager" / "Principal App Store
        # Manager" match on "manager" alone. None of these are Product
        # Manager roles.
        self.assertFalse(fwj.matches_job_profile('Staff Product Designer, Risk', JOB_PROFILE))
        self.assertFalse(fwj.matches_job_profile(
            'Principal Technical Program Manager, Compute', JOB_PROFILE))
        self.assertFalse(fwj.matches_job_profile('Principal App Store Manager', JOB_PROFILE))

    def test_head_of_product_level_keywords_match_their_own_alternate_titles(self):
        # "Director of Product" / "VP of Product" are complete alternate
        # phrasings for the Head of Product function, not seniority
        # modifiers layered on the bare function name -- they must match
        # even though neither contains the literal word "head".
        profile = {
            'job_functions': ['Head of Product'],
            'experience_by_function': {
                'Head of Product': {
                    'years': 10,
                    'level_keywords': ['head of product', 'director of product', 'vp product', 'vp of product'],
                },
            },
        }
        self.assertTrue(fwj.matches_job_profile('Director of Product, Payments', profile))
        self.assertTrue(fwj.matches_job_profile('VP of Product, Platform', profile))
        self.assertTrue(fwj.matches_job_profile('VP Product, Growth', profile))
        self.assertFalse(fwj.matches_job_profile('Director of Engineering', profile))

    def test_company_level_override_replaces_global_level_keywords(self):
        # Title seniority isn't consistent across companies — e.g. Hugh is
        # a Senior PM at Coinbase's level, not a Group PM (Group PM is a
        # level up there). A company override should make an abbreviated
        # "Senior PM" title match for that company even though neither the
        # bare function phrase ("Product Manager") nor the global
        # level_keywords (staff/principal) are present.
        profile = {
            **JOB_PROFILE,
            'company_level_overrides': {
                'Coinbase': {
                    'Product Manager': {'level_keywords': ['senior pm']},
                },
            },
        }
        self.assertTrue(fwj.matches_job_profile(
            'Senior PM, Payments', profile, company='Coinbase'))

    def test_company_level_override_is_scoped_to_that_company(self):
        # The same abbreviated title should NOT match for a company with
        # no override — it doesn't contain the bare "Product Manager"
        # phrase, and "senior" isn't in Acme's (global) level_keywords.
        profile = {
            **JOB_PROFILE,
            'company_level_overrides': {
                'Coinbase': {
                    'Product Manager': {'level_keywords': ['senior pm']},
                },
            },
        }
        self.assertFalse(fwj.matches_job_profile(
            'Senior PM, Payments', profile, company='Acme'))

    def test_company_level_override_excludes_global_keywords_not_reinstated(self):
        # An override replaces the level keywords for that company rather
        # than adding to them -- "Group Product Manager" (which matches
        # the global list) should NOT match at Coinbase once overridden to
        # senior-only, since Group PM is a level above Hugh there.
        profile = {
            **JOB_PROFILE,
            'company_level_overrides': {
                'Coinbase': {
                    'Product Manager': {'level_keywords': ['senior product manager']},
                },
            },
        }
        self.assertFalse(fwj.matches_job_profile(
            'Group Product Manager, Payments', profile, company='Coinbase'))
        # ...but Group PM still matches normally for a company with no override.
        self.assertTrue(fwj.matches_job_profile(
            'Group Product Manager, Payments', {**JOB_PROFILE, 'experience_by_function': {
                'Product Manager': {'years': 10, 'level_keywords': ['group product manager']}}},
            company='Acme'))


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
