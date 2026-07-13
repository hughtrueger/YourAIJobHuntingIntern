#!/usr/bin/env python3
"""
Generate a compact morning-brief prewarm artifact that can be consumed quickly
by the morning-brief command or a cloud worker.

This script is intentionally lightweight and container-friendly:
- it reads the local profile and cached fetcher outputs
- it can optionally run the existing Gmail/Calendar fetchers
- it writes a compact JSON artifact to state/morning_report_ready.json
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
STATE_DIR = Path(os.environ.get("AI_JOB_INTERN_STATE_DIR", ROOT_DIR / "state"))
PROFILE_FILE = STATE_DIR / "profile.json"
OUTPUT_FILE = STATE_DIR / "morning_report_ready.json"
FETCHERS_DIR = Path(os.environ.get("AI_JOB_INTERN_FETCHERS_DIR", ROOT_DIR / "fetchers"))


def get_profile() -> dict[str, Any]:
    if not PROFILE_FILE.exists():
        return {}
    with PROFILE_FILE.open() as fh:
        return json.load(fh)


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with path.open() as fh:
            return json.load(fh)
    except json.JSONDecodeError:
        return None


def run_fetcher(script_name: str) -> tuple[bool, str]:
    script_path = FETCHERS_DIR / script_name
    if not script_path.exists():
        return False, f"missing script: {script_name}"

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            env={**os.environ, "AI_JOB_INTERN_STATE_DIR": str(STATE_DIR)},
            cwd=str(ROOT_DIR),
        )
    except OSError as exc:
        return False, str(exc)

    output = (result.stdout or "").strip()
    if result.returncode != 0:
        error = (result.stderr or "").strip() or output or "unknown error"
        return False, error

    return True, output


def summarize_jobs(gmail_data: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not gmail_data:
        return []

    listings = gmail_data.get("listings", []) or []
    items = []
    for listing in listings[:5]:
        items.append(
            {
                "title": listing.get("title", ""),
                "company": listing.get("company", ""),
                "location": listing.get("location", ""),
                "url": listing.get("url", ""),
                "date_posted": listing.get("date_posted", ""),
                "source": listing.get("source", ""),
            }
        )
    return items


def summarize_calendar(calendar_data: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not calendar_data:
        return []

    events = calendar_data.get("events", []) or []
    items = []
    for event in events[:5]:
        items.append(
            {
                "title": event.get("title", ""),
                "start": event.get("start", ""),
                "location": event.get("location", ""),
                "source": event.get("source", ""),
                "has_conflict": bool(event.get("has_conflict", False)),
            }
        )
    return items


def build_artifact(profile: dict[str, Any]) -> dict[str, Any]:
    onboarding_complete = bool(profile.get("onboarding_complete"))
    tier = int(profile.get("tier", 1) or 1)
    calendar_type = profile.get("calendar_type")

    gmail_path = STATE_DIR / "gmail_jobs.json"
    calendar_path = STATE_DIR / "calendar.json"
    gmail_data = load_json(gmail_path)
    calendar_data = load_json(calendar_path)

    if onboarding_complete and tier >= 2 and calendar_type:
        refresh_needed = True
        if gmail_data and calendar_data:
            refreshed = gmail_data.get("fetched_at") or calendar_data.get("fetched_at")
            if refreshed:
                refresh_needed = False
        if refresh_needed:
            fetch_results = []
            if tier >= 2:
                ok_gmail, out_gmail = run_fetcher("fetch_gmail.py")
                fetch_results.append(("gmail", ok_gmail, out_gmail))
                ok_calendar, out_calendar = run_fetcher("fetch_calendar.py")
                fetch_results.append(("calendar", ok_calendar, out_calendar))
                gmail_data = load_json(gmail_path)
                calendar_data = load_json(calendar_path)
            else:
                fetch_results = []
    else:
        fetch_results = []

    ready = bool(onboarding_complete and tier >= 2 and calendar_type and gmail_data and calendar_data)
    generated_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    expires_at = (datetime.utcnow() + timedelta(hours=12)).replace(microsecond=0).isoformat() + "Z"

    artifact = {
        "schema_version": 1,
        "generated_at": generated_at,
        "expires_at": expires_at,
        "ready": ready,
        "source": "cloud-worker-prewarm",
        "onboarding_complete": onboarding_complete,
        "tier": tier,
        "calendar_type": calendar_type,
        "profile_summary": {
            "persona": profile.get("persona"),
            "news_preferences": profile.get("news_preferences", []),
            "target_companies": (profile.get("job_profile") or {}).get("target_companies", []),
            "job_functions": (profile.get("job_profile") or {}).get("job_functions", []),
        },
        "summary": {
            "job_listing_count": (gmail_data or {}).get("listing_count", 0) if gmail_data else 0,
            "calendar_event_count": (calendar_data or {}).get("event_count", 0) if calendar_data else 0,
            "ready_for_launch": ready,
        },
        "highlights": {
            "jobs": summarize_jobs(gmail_data),
            "calendar": summarize_calendar(calendar_data),
        },
        "fetch_results": [
            {
                "name": name,
                "ok": ok,
                "message": message[:400] if message else "",
            }
            for name, ok, message in fetch_results
        ],
        "data_files": {
            "gmail_jobs": str(gmail_path.relative_to(ROOT_DIR)) if gmail_path.exists() else None,
            "calendar": str(calendar_path.relative_to(ROOT_DIR)) if calendar_path.exists() else None,
        },
    }

    return artifact


def main() -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    profile = get_profile()

    try:
        artifact = build_artifact(profile)
    except Exception as exc:  # noqa: BLE001
        artifact = {
            "schema_version": 1,
            "generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "expires_at": (datetime.utcnow() + timedelta(hours=6)).replace(microsecond=0).isoformat() + "Z",
            "ready": False,
            "source": "cloud-worker-prewarm",
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }

    with OUTPUT_FILE.open("w") as fh:
        json.dump(artifact, fh, indent=2)
        fh.write("\n")

    print(f"Wrote prewarm artifact to {OUTPUT_FILE}")
    print(f"Ready={artifact.get('ready')} summary={artifact.get('summary', {})}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
