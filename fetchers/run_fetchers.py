#!/usr/bin/env python3
"""
Orchestrator: run all Tier 2 data fetchers in sequence.
Called by launchd each weekday morning.
"""

import json
import os
import subprocess
import sys
import datetime

STATE_DIR = os.path.join(os.path.dirname(__file__), '..', 'state')
PROFILE_FILE = os.path.join(STATE_DIR, 'profile.json')
FETCHERS_DIR = os.path.dirname(__file__)
PREWARM_SCRIPT = os.path.join(FETCHERS_DIR, 'prewarm_morning_brief.py')
FETCH_TIMEOUT_SECONDS = 600


def get_profile() -> dict:
    if not os.path.exists(PROFILE_FILE):
        return {}
    with open(PROFILE_FILE) as f:
        return json.load(f)


def run(script: str) -> bool:
    path = os.path.join(FETCHERS_DIR, script)
    print(f"  Running {script}...")
    try:
        result = subprocess.run(
            [sys.executable, path],
            capture_output=True,
            text=True,
            timeout=FETCH_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        print(f"  ✗ {script} timed out after {FETCH_TIMEOUT_SECONDS}s")
        return False
    if result.returncode != 0:
        print(f"  ✗ {script} failed:")
        print(result.stderr)
        return False
    print(result.stdout.strip())
    return True


def run_prewarm() -> bool:
    print("  Running prewarm_morning_brief.py...")
    try:
        result = subprocess.run(
            [sys.executable, PREWARM_SCRIPT],
            capture_output=True,
            text=True,
            env={**os.environ, 'AI_JOB_INTERN_STATE_DIR': STATE_DIR},
            cwd=os.path.dirname(FETCHERS_DIR),
            timeout=FETCH_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        print(f"  ✗ prewarm_morning_brief.py timed out after {FETCH_TIMEOUT_SECONDS}s")
        return False
    if result.returncode != 0:
        print("  ✗ prewarm_morning_brief.py failed:")
        print(result.stderr)
        return False
    print(result.stdout.strip())
    return True


def main():
    profile = get_profile()

    if not profile.get('onboarding_complete'):
        print("Onboarding not complete — skipping data fetch.")
        sys.exit(0)

    if profile.get('tier', 1) < 2:
        print("Tier 1 (no OAuth) — skipping data fetch.")
        sys.exit(0)

    calendar_type = profile.get('calendar_type')
    if not calendar_type:
        print("No calendar type set — skipping data fetch.")
        sys.exit(0)

    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}] Running AI Job Intern fetchers...")

    ok = True
    ok &= run('fetch_gmail.py')
    ok &= run('fetch_calendar.py')

    prewarm_ok = run_prewarm()

    if ok and prewarm_ok:
        print("✓ All fetchers completed successfully and the morning brief was prewarmed.")
    elif ok:
        print("⚠ Fetchers completed, but the prewarm artifact could not be written.")
    else:
        print("⚠ Some fetchers failed — check state/fetcher-error.log")
        sys.exit(1)


if __name__ == '__main__':
    main()
