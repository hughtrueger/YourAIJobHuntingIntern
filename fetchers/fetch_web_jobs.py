#!/usr/bin/env python3
"""
Fetch job listings from company career pages via public ATS APIs and write
to state/web_jobs.json.

This closes a structural gap: Section 3 of the morning-brief command asks
for career-page and web-search job sourcing on every run, but that has
always been a *live, prompt-driven* step with no deterministic code behind
it — meaning it silently depends on whichever session happens to run the
command actually doing the work. For a product used by many users, that's
not testable, not schedulable, and not reliable. This script makes the
career-page portion of that sourcing real: deterministic, cacheable, and
covered by tests, exactly like fetch_gmail.py.

Coverage is intentionally honest, not exhaustive: only companies hosted on
a public ATS with a documented, unauthenticated JSON API (currently
Greenhouse and Lever) are covered. Companies with custom/in-house career
sites are reported as "not covered" rather than silently skipped or faked —
see `uncovered_companies` in the output. Extending coverage to more ATS
providers (or to scraping bespoke career pages) is future work; this is the
honest floor, not the ceiling.

Usage: python3 fetchers/fetch_web_jobs.py
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request

STATE_DIR = os.path.join(os.path.dirname(__file__), '..', 'state')
PROFILE_FILE = os.path.join(STATE_DIR, 'profile.json')
OUTPUT_FILE = os.path.join(STATE_DIR, 'web_jobs.json')

REQUEST_TIMEOUT_SECONDS = 15

GREENHOUSE_URL = 'https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true'
LEVER_URL = 'https://api.lever.co/v0/postings/{slug}?mode=json'


def slugify(company: str) -> str:
    """Best-effort guess at a company's ATS board slug from its display name."""
    s = company.lower().strip()
    s = re.sub(r'[^a-z0-9]+', '', s)
    return s


def _http_get_json(url: str):
    """GET a URL and parse JSON. Returns None on any failure (404, timeout, bad JSON)."""
    req = urllib.request.Request(url, headers={'User-Agent': 'ai-job-hunting-intern/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            if resp.status != 200:
                return None
            body = resp.read().decode('utf-8', errors='replace')
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def fetch_greenhouse(company: str) -> list[dict] | None:
    slug = slugify(company)
    data = _http_get_json(GREENHOUSE_URL.format(slug=slug))
    if not data or 'jobs' not in data:
        return None

    listings = []
    for job in data.get('jobs', []):
        title = (job.get('title') or '').strip()
        if not title:
            continue
        location = ((job.get('location') or {}).get('name') or '').strip()
        url = (job.get('absolute_url') or '').strip()
        updated_at = job.get('updated_at') or job.get('first_published') or ''
        date_posted = updated_at[:10] if updated_at else None
        listings.append({
            'title': title,
            'company': company,
            'location': location,
            'url': url,
            'date_posted': date_posted,
            'source': 'web_greenhouse',
        })
    return listings


def fetch_lever(company: str) -> list[dict] | None:
    slug = slugify(company)
    data = _http_get_json(LEVER_URL.format(slug=slug))
    if not data or not isinstance(data, list):
        return None

    listings = []
    for job in data:
        title = (job.get('text') or '').strip()
        if not title:
            continue
        categories = job.get('categories') or {}
        location = (categories.get('location') or '').strip()
        url = (job.get('hostedUrl') or '').strip()
        created_at_ms = job.get('createdAt')
        date_posted = None
        if isinstance(created_at_ms, (int, float)):
            date_posted = datetime.datetime.fromtimestamp(
                created_at_ms / 1000, tz=datetime.timezone.utc
            ).date().isoformat()
        listings.append({
            'title': title,
            'company': company,
            'location': location,
            'url': url,
            'date_posted': date_posted,
            'source': 'web_lever',
        })
    return listings


def fetch_company_listings(company: str) -> tuple[list[dict], bool]:
    """
    Try each known ATS for a company. Returns (listings, covered) — covered
    is False when no ATS responded, so callers can report it honestly
    instead of silently treating "no results" as "no jobs right now".
    """
    for fetcher in (fetch_greenhouse, fetch_lever):
        result = fetcher(company)
        if result is not None:
            return result, True
    return [], False


_FUNCTION_STOPWORDS = {'of', 'the', 'a', 'and'}


def _function_core_words(function_name: str) -> set[str]:
    return {w for w in function_name.lower().split() if w not in _FUNCTION_STOPWORDS}


def _contains_phrase(text_lower: str, phrase_lower: str) -> bool:
    """
    Word-boundary phrase match — plain substring search would let "product"
    match inside "productivity", or "manager" inside "management". re.escape
    handles phrases containing regex-special characters (e.g. "vp+").
    """
    return re.search(r'\b' + re.escape(phrase_lower) + r'\b', text_lower) is not None


def _company_level_override(fn: str, job_profile: dict, company: str | None) -> dict | None:
    if not company:
        return None
    overrides = job_profile.get('company_level_overrides', {}) or {}
    company_override = overrides.get(company, {}) or {}
    return company_override.get(fn)


def matches_job_profile(title: str, job_profile: dict, company: str | None = None) -> bool:
    """
    Does this listing's title plausibly match the user's job_profile?
    A bare level keyword (e.g. "staff", "principal") is not sufficient on
    its own — those are generic seniority modifiers that apply to any
    discipline ("Research Engineer, Senior Staff+" is not a PM role just
    because it contains "staff"). A match requires either the full function
    phrase, or a level keyword co-occurring with a core word of its function.

    `company`, if given, is checked against `company_level_overrides` first.
    Title seniority conventions aren't consistent across companies — the
    same scope of work can be "Senior PM" at one company and "Group PM" at
    another, so a global level-keyword list either over-surfaces roles that
    are actually a level up, or silently excludes correct-level roles that
    are titled differently at that company. When an override exists for
    (company, function), it fully replaces the matching rule for that
    function — including the bare-function-phrase shortcut below — because
    "Group Product Manager" contains the phrase "Product Manager" and would
    otherwise match regardless of the override; the whole point of an
    override is that the company's title conventions don't line up with
    the bare function name.
    """
    job_functions = job_profile.get('job_functions', []) or []
    if not job_functions:
        return True
    title_lower = title.lower()
    for fn in job_functions:
        override = _company_level_override(fn, job_profile, company)
        if override is not None:
            for kw in override.get('level_keywords', []) or []:
                if _contains_phrase(title_lower, kw.lower()):
                    return True
            continue  # overridden for this company -- no fallback to the global rule below

        fn_lower = fn.lower()
        if _contains_phrase(title_lower, fn_lower):
            return True
        core_words = _function_core_words(fn)
        level_keywords = (job_profile.get('experience_by_function', {}) or {}).get(fn, {}).get('level_keywords', []) or []
        for kw in level_keywords:
            kw_lower = kw.lower()
            kw_words = set(kw_lower.split())
            if kw_words & core_words:
                # This level keyword already names the discipline itself
                # (e.g. "director of product" / "vp of product" for the
                # "Head of Product" function both contain "product") -- it's
                # a complete alternate phrasing, not a bare seniority
                # modifier, so a phrase match on it alone is sufficient.
                if _contains_phrase(title_lower, kw_lower):
                    return True
                continue
            # Regression: requiring just ANY core word co-occurring with a
            # *bare* seniority modifier ("staff", "principal", "group pm" --
            # words that say nothing about discipline on their own) let
            # "Staff Product Designer" match on "product", "Principal
            # Technical Program Manager" match on "manager", and "Principal
            # App Store Manager" match on "manager" too -- none are Product
            # Manager roles. Require ALL core words present (not just one),
            # so a paraphrased-but-real match like "Manager, Product --
            # Staff" still works without those false positives.
            if _contains_phrase(title_lower, kw_lower) and core_words and all(
                    _contains_phrase(title_lower, w) for w in core_words):
                return True
    return False


def get_job_profile() -> dict:
    if not os.path.exists(PROFILE_FILE):
        return {}
    with open(PROFILE_FILE) as f:
        profile = json.load(f)
    return profile.get('job_profile', {}) or {}


def fetch_all(job_profile: dict) -> dict:
    target_companies = job_profile.get('target_companies', []) or []

    all_listings = []
    covered_companies = []
    uncovered_companies = []

    for company in target_companies:
        listings, covered = fetch_company_listings(company)
        if covered:
            covered_companies.append(company)
        else:
            uncovered_companies.append(company)
        all_listings.extend(listings)

    filtered = [l for l in all_listings if matches_job_profile(l['title'], job_profile, company=l.get('company'))]

    return {
        'fetched_at': datetime.datetime.now().isoformat(),
        'companies_queried': len(target_companies),
        'covered_companies': covered_companies,
        'uncovered_companies': uncovered_companies,
        'listing_count': len(filtered),
        'profile_filtered_count': len(all_listings) - len(filtered),
        'listings': filtered,
    }


def main():
    job_profile = get_job_profile()
    if not job_profile.get('target_companies'):
        print("No target_companies in job_profile — nothing to fetch.")
        sys.exit(0)

    print(f"Fetching web job listings for {len(job_profile['target_companies'])} target companies...")
    data = fetch_all(job_profile)

    os.makedirs(STATE_DIR, exist_ok=True)
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"✓ Found {data['listing_count']} listings from {len(data['covered_companies'])}/"
          f"{data['companies_queried']} companies with ATS coverage "
          f"({data['profile_filtered_count']} filtered out as off-profile)")
    if data['uncovered_companies']:
        print(f"  No ATS coverage for: {', '.join(data['uncovered_companies'])}")
    print(f"  Written to: {OUTPUT_FILE}")


if __name__ == '__main__':
    main()
