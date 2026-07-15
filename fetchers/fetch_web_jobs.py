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


def matches_job_profile(title: str, job_profile: dict) -> bool:
    """
    Does this listing's title plausibly match the user's job_profile?
    A bare level keyword (e.g. "staff", "principal") is not sufficient on
    its own — those are generic seniority modifiers that apply to any
    discipline ("Research Engineer, Senior Staff+" is not a PM role just
    because it contains "staff"). A match requires either the full function
    phrase, or a level keyword co-occurring with a core word of its function.
    """
    job_functions = job_profile.get('job_functions', []) or []
    if not job_functions:
        return True
    title_lower = title.lower()
    experience = job_profile.get('experience_by_function', {}) or {}
    for fn in job_functions:
        fn_lower = fn.lower()
        if _contains_phrase(title_lower, fn_lower):
            return True
        core_words = _function_core_words(fn)
        level_keywords = (experience.get(fn, {}) or {}).get('level_keywords', []) or []
        for kw in level_keywords:
            kw_lower = kw.lower()
            if _contains_phrase(title_lower, kw_lower) and (
                    kw_lower in fn_lower or any(_contains_phrase(title_lower, w) for w in core_words)):
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

    filtered = [l for l in all_listings if matches_job_profile(l['title'], job_profile)]

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
