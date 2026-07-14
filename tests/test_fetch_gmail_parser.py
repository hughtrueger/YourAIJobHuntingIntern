#!/usr/bin/env python3
"""
Regression tests for the Gmail job-alert parser (fetchers/fetch_gmail.py).

These guard against the "cached morning brief looks broken" bug where the
URL/anchor-based extractors emitted UI chrome, social cruft and raw CSS
fragments as job listings. Runs on the stdlib only:

    python3 -m unittest tests.test_fetch_gmail_parser
"""

import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'fetchers'))

import fetch_gmail as fg  # noqa: E402

EMAIL_DATE = datetime.date(2026, 7, 14)


class JunkFieldTests(unittest.TestCase):
    def test_rejects_reported_garbage_fragments(self):
        # The exact shapes called out in the bug report.
        self.assertTrue(fg._is_junk_field('Save:'))
        self.assertTrue(fg._is_junk_field('49 connections in common'))
        self.assertTrue(fg._is_junk_field('San Francisco Bay Area \u00b7 49 connections in common'))
        self.assertTrue(fg._is_junk_field('style="background-color:#1A73E8; padding:12px 20px;"'))

    def test_rejects_ui_chrome_and_urls(self):
        for junk in ['Apply now', 'View jobs', 'Unsubscribe', 'Message',
                     'https://linkedin.com/jobs/view/1', '', '   ', '...']:
            self.assertTrue(fg._is_junk_field(junk), junk)

    def test_accepts_real_titles_and_companies(self):
        for good in ['Senior Product Manager', 'Staff Software Engineer',
                     'Google', 'Stripe', 'Data Scientist, Search']:
            self.assertFalse(fg._is_junk_field(good), good)


class ExtractListingsTests(unittest.TestCase):
    def test_linkedin_notification_produces_no_listings(self):
        body = (
            "LinkedIn\n"
            "San Francisco Bay Area\n"
            "49 connections in common\n"
            "Save:\n"
            "Begin learning Japanese, starting with sounds, phrases, and greetings\n"
            "https://www.linkedin.com/comm/jobs/view/123456\n"
            'style="background-color:#1A73E8; padding:12px 20px; color:#fff;"\n'
            "https://www.linkedin.com/comm/l/456\n"
        )
        listings = fg.extract_job_listings(
            "Jobs for you", body, "messages-noreply@linkedin.com", EMAIL_DATE
        )
        self.assertEqual(listings, [])

    def test_valid_google_careers_listings_survive(self):
        body = (
            "Senior Product Manager\n"
            "Google \u2013 Mountain View, CA\n"
            "3 days ago\n"
            "https://careers.google.com/jobs/123\n\n"
            "Staff Engineer\n"
            "Stripe \u00b7 San Francisco, CA\n"
            "today\n"
            "https://stripe.com/jobs/456\n"
        )
        listings = fg.extract_job_listings(
            "New jobs for you", body, "careers-noreply@google.com", EMAIL_DATE
        )
        titles = {(l['title'], l['company']) for l in listings}
        self.assertIn(('Senior Product Manager', 'Google'), titles)
        self.assertIn(('Staff Engineer', 'Stripe'), titles)

    def test_mixed_email_keeps_only_real_listing(self):
        body = (
            "Save:\n"
            "49 connections in common\n"
            "https://www.linkedin.com/comm/1\n"
            "Backend Engineer\n"
            "Airbnb\n"
            "https://www.linkedin.com/comm/jobs/view/789\n"
        )
        listings = fg.extract_job_listings(
            "job alert", body, "jobs-listings@linkedin.com", EMAIL_DATE
        )
        for listing in listings:
            self.assertFalse(fg._is_junk_field(listing['title']), listing)
            self.assertFalse(fg._is_junk_field(listing['company']), listing)


if __name__ == '__main__':
    unittest.main()
