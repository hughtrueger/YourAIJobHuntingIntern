#!/usr/bin/env python3
"""
Link-health eval for job listing URLs.

Job listings go stale between the moment they're fetched/found and the
moment a user clicks the link: roles close, ATS boards recycle job IDs,
and some sources (LinkedIn tracking links, aggregator sites like
RemoteRocketship/NoDesk/WelcomeToTheJungle) were never reliable to begin
with. This checks each listing URL and classifies it honestly rather than
assuming "found = still open":

    live          - 200 (or redirect) landing on what looks like a real job page
    redirected    - redirects to a generic listing/search page rather than a
                    specific job -- the strongest signal of a closed posting
    dead          - 404/410
    error         - 5xx or a network/timeout failure
    unverifiable  - request blocked (403/999) or method not allowed; many
                    ATS providers and LinkedIn reject bot/HEAD traffic even
                    for live postings, so this is NOT the same as "dead" --
                    reporting it as dead would be dishonestly confident
    timeout       - no response within the fast-path's time budget; the
                    check was inconclusive, not a signal either way

No network calls happen in tests; classification logic is unit-tested
against mocked responses (see tests/test_validate_links.py).

Two entry points:
- `check_urls()` / `annotate_listings_file()` -- sequential, thorough,
  used by the prewarm pipeline where wall-clock time doesn't matter.
- `fast_check()` -- concurrent (bounded per-host so it doesn't hammer any
  one career site), returns within ~5s regardless of batch size, used for
  ad-hoc/interactive checks (e.g. gap-fill web-search results found mid
  session, before they're shown to the user). URLs that don't respond in
  time come back as `timeout`, not `dead` -- an inconclusive check is
  reported as inconclusive, never silently upgraded to a verdict.

Usage:
    python3 fetchers/validate_links.py state/web_jobs.json
    python3 fetchers/validate_links.py state/gmail_jobs.json --limit 20
    python3 fetchers/validate_links.py --url https://example.com/jobs/123
    python3 fetchers/validate_links.py --url https://a --url https://b --fast
"""

from __future__ import annotations

import argparse
import json
import re
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

REQUEST_TIMEOUT_SECONDS = 10
USER_AGENT = 'ai-job-hunting-intern-linkcheck/1.0'

# Interactive fast-path defaults: bounded so a batch of gap-fill search
# results can be checked without noticeably stalling a live brief/chat
# turn, regardless of how many URLs or how slow one host is.
FAST_OVERALL_DEADLINE_SECONDS = 5.0
FAST_PER_REQUEST_TIMEOUT_SECONDS = 4.0
FAST_MAX_WORKERS = 10
MAX_PER_HOST_CONCURRENCY = 3  # be polite to any single career site/ATS host

GENERIC_PATH_RE = re.compile(r'(jobs|careers|positions|job-search)/?$', re.IGNORECASE)


@dataclass
class LinkCheckResult:
    url: str
    status: str  # live | redirected | dead | error | unverifiable
    http_status: int | None
    final_url: str | None
    checked_at: str
    detail: str = ""


def _looks_generic(path: str) -> bool:
    return bool(GENERIC_PATH_RE.search(path.rstrip('/')))


def _path_segments(path: str) -> list[str]:
    return [s for s in path.split('/') if s]


def _classify_response(url: str, status: int, final_url: str, now: str) -> LinkCheckResult:
    orig = urlparse(url)
    final = urlparse(final_url)

    if final_url != url:
        # Greenhouse's own "this posting is gone" signal: 302 to
        # /{company}?error=true. Caught this in production -- a closed
        # Reddit posting was redirecting here and being reported as
        # "live" because the path itself doesn't end in jobs/careers/
        # positions, it's just the bare company slug with an error query
        # param. Treat as dead outright rather than merely "redirected",
        # since this is an explicit closed-job marker, not ambiguity.
        if 'error=true' in (final.query or ''):
            return LinkCheckResult(url, 'dead', status, final_url, now,
                                    'redirected to ATS error page (posting closed)')

        orig_segments = _path_segments(orig.path)
        final_segments = _path_segments(final.path)
        # Redirect stripped a specific job identifier down to a shorter/
        # generic path (e.g. /acme/jobs/12345 -> /acme/jobs, or -> /acme)
        # -- the strongest signal short of an explicit error param that
        # the specific posting is gone.
        if len(final_segments) < len(orig_segments) and (
            _looks_generic(final.path) or len(final_segments) <= 1
        ):
            return LinkCheckResult(url, 'redirected', status, final_url, now,
                                    'redirected to a shorter/generic listing page -- likely closed')

    return LinkCheckResult(url, 'live', status, final_url, now)


def _classify_http_error(url: str, e: urllib.error.HTTPError, now: str) -> LinkCheckResult:
    if e.code in (404, 410):
        return LinkCheckResult(url, 'dead', e.code, None, now, 'not found')
    if e.code in (403, 999):
        return LinkCheckResult(url, 'unverifiable', e.code, None, now, 'blocked bot/HEAD traffic')
    if 500 <= e.code < 600:
        return LinkCheckResult(url, 'error', e.code, None, now, 'server error')
    return LinkCheckResult(url, 'unverifiable', e.code, None, now, 'unexpected status')


def classify(url: str, timeout: float = REQUEST_TIMEOUT_SECONDS) -> LinkCheckResult:
    now = datetime.now(timezone.utc).isoformat()
    req = urllib.request.Request(url, method='HEAD', headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return _classify_response(url, resp.status, resp.geturl(), now)
    except urllib.error.HTTPError as e:
        if e.code == 405:
            # HEAD not allowed by this server -- retry with GET.
            try:
                req2 = urllib.request.Request(url, method='GET', headers={'User-Agent': USER_AGENT})
                with urllib.request.urlopen(req2, timeout=timeout) as resp:
                    return _classify_response(url, resp.status, resp.geturl(), now)
            except urllib.error.HTTPError as e2:
                return _classify_http_error(url, e2, now)
            except Exception as e2:  # noqa: BLE001
                return LinkCheckResult(url, 'error', None, None, now, str(e2))
        return _classify_http_error(url, e, now)
    except Exception as e:  # noqa: BLE001
        return LinkCheckResult(url, 'error', None, None, now, str(e))


def score_summary(results: list[LinkCheckResult]) -> dict:
    total = len(results)
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    live = counts.get('live', 0)
    return {
        'total': total,
        'counts': counts,
        'score': f"{live}/{total} verified live" if total else "0/0 verified live",
    }


def check_urls(urls: list[str], delay: float = 0.3) -> list[LinkCheckResult]:
    results = []
    for i, u in enumerate(urls):
        if i > 0:
            time.sleep(delay)
        results.append(classify(u))
    return results


class _HostThrottle:
    """Caps concurrent in-flight requests per host so a batch full of the
    same domain (e.g. 29 Stripe listings) doesn't fire dozens of requests
    at one server simultaneously, while still allowing full concurrency
    across *different* hosts.
    """

    def __init__(self, max_per_host: int = MAX_PER_HOST_CONCURRENCY):
        self._lock = threading.Lock()
        self._sems: dict[str, threading.Semaphore] = defaultdict(
            lambda: threading.Semaphore(max_per_host)
        )

    def run(self, url: str, timeout: float) -> LinkCheckResult:
        host = urlparse(url).netloc
        with self._lock:
            sem = self._sems[host]
        sem.acquire()
        try:
            return classify(url, timeout=timeout)
        finally:
            sem.release()


def fast_check(
    urls: list[str],
    overall_deadline: float = FAST_OVERALL_DEADLINE_SECONDS,
    per_request_timeout: float = FAST_PER_REQUEST_TIMEOUT_SECONDS,
    max_workers: int = FAST_MAX_WORKERS,
) -> list[LinkCheckResult]:
    """Check a batch of URLs concurrently and return within `overall_deadline`
    seconds no matter how many URLs there are or how slow any single host
    is. Meant for interactive use (e.g. checking live-web-search results
    before showing them in a brief/chat turn) where a slow/unresponsive
    site must not stall the whole turn.

    URLs still in flight when the deadline hits come back as `timeout`
    (inconclusive) rather than being force-labelled dead or live -- we
    simply detach from those background requests and move on.
    """
    if not urls:
        return []

    throttle = _HostThrottle()
    now_iso = datetime.now(timezone.utc).isoformat()

    # Deliberately not a `with` block: ThreadPoolExecutor.__exit__ calls
    # shutdown(wait=True), which would block on exit until every straggler
    # thread finishes -- defeating the whole point of a bounded deadline.
    # We shut down with wait=False instead and let any still-running
    # requests finish in the background (they're bounded by
    # per_request_timeout regardless) without the caller waiting on them.
    executor = ThreadPoolExecutor(max_workers=max_workers)
    try:
        future_to_url = {
            executor.submit(throttle.run, u, per_request_timeout): u for u in urls
        }
        done, not_done = wait(future_to_url, timeout=overall_deadline)

        results_by_url: dict[str, LinkCheckResult] = {}
        for fut in done:
            url = future_to_url[fut]
            try:
                results_by_url[url] = fut.result()
            except Exception as e:  # noqa: BLE001
                results_by_url[url] = LinkCheckResult(url, 'error', None, None, now_iso, str(e))
        for fut in not_done:
            url = future_to_url[fut]
            fut.cancel()  # best-effort: won't interrupt an in-flight request, just stops waiting on it
            results_by_url[url] = LinkCheckResult(
                url, 'timeout', None, None, now_iso,
                f'no response within {overall_deadline}s budget',
            )
    finally:
        executor.shutdown(wait=False)

    return [results_by_url[u] for u in urls]


def annotate_listings_file(path, delay: float = 0.3, limit: int | None = None) -> dict:
    """Check every listing URL in a web_jobs.json/gmail_jobs.json-shaped file,
    write a `link_status` field back onto each listing plus an aggregate
    `link_health_score`/`link_health_checked_at` on the file, and return the
    summary dict. Used by both the CLI and prewarm_morning_brief.py.
    """
    with open(path) as f:
        data = json.load(f)

    listings = data.get('listings', []) or []
    urls = [l['url'] for l in listings if l.get('url')]
    if limit:
        urls = urls[:limit]

    results = check_urls(urls, delay=delay)
    summary = score_summary(results)

    by_url = {r.url: asdict(r) for r in results}
    for l in listings:
        if l.get('url') in by_url:
            l['link_status'] = by_url[l['url']]
    data['listings'] = listings
    data['link_health_checked_at'] = datetime.now(timezone.utc).isoformat()
    data['link_health_score'] = summary

    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', nargs='?', help='JSON file with a "listings" array of {url: ...}')
    parser.add_argument('--url', action='append', help='Check one or more URLs directly')
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--delay', type=float, default=0.3, help='Seconds between requests (sequential mode)')
    parser.add_argument('--fast', action='store_true',
                         help='Concurrent, ~5s-bounded check instead of the sequential default')
    parser.add_argument('--json', action='store_true',
                         help='Print {"results": [...], "summary": {...}} instead of text -- for machine consumption')
    args = parser.parse_args()

    if args.fast and args.url:
        urls = list(args.url)
        if args.limit:
            urls = urls[:args.limit]
        results = fast_check(urls)
        summary = score_summary(results)
        if args.json:
            print(json.dumps({'results': [asdict(r) for r in results], 'summary': summary}, indent=2))
        else:
            for r in results:
                print(f"[{r.status:12s}] {r.http_status or '-':>3} {r.url}")
            print(f"\nLink health: {summary['score']}  {summary['counts']}")
        return

    if args.file:
        summary = annotate_listings_file(args.file, delay=args.delay, limit=args.limit)
        with open(args.file) as f:
            data = json.load(f)
        for l in data.get('listings', []):
            status = (l.get('link_status') or {}).get('status', '?')
            http_status = (l.get('link_status') or {}).get('http_status', '-')
            print(f"[{status:12s}] {http_status or '-':>3} {l.get('url', '')}")
        print(f"\nLink health: {summary['score']}  {summary['counts']}")
        return

    urls = list(args.url or [])
    if args.limit:
        urls = urls[:args.limit]
    results = check_urls(urls, delay=args.delay)
    for r in results:
        print(f"[{r.status:12s}] {r.http_status or '-':>3} {r.url}")
    summary = score_summary(results)
    print(f"\nLink health: {summary['score']}  {summary['counts']}")


if __name__ == '__main__':
    main()
