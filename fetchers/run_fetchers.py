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


def get_profile() -> dict:
    if not os.path.exists(PROFILE_FILE):
        return {}
    with open(PROFILE_FILE) as f:
        return json.load(f)


def run(script: str) -> bool:
    path = os.path.join(FETCHERS_DIR, script)
    print(f"  Running {script}...")
    result = subprocess.run([sys.executable, path], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ✗ {script} failed:")
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

    if ok:
        print("✓ All fetchers completed successfully.")
    else:
        print("⚠ Some fetchers failed — check state/fetcher-error.log")
        sys.exit(1)


if __name__ == '__main__':
    main()
