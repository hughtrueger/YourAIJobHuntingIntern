#!/usr/bin/env python3
"""
Anonymous telemetry for AI Job Hunting Intern.
Uses only stdlib — no pip install required.
Silently no-ops if offline or opted out.
"""

import argparse
import json
import os
import sys
import uuid
import urllib.request

POSTHOG_HOST = "https://us.i.posthog.com"
POSTHOG_API_KEY = "phc_s8Mh3sS2tmxnoDPeBhXabL8gnSxC3BJKBmcrmnw2y8sm"

STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "state")
PROFILE_FILE = os.path.join(STATE_DIR, "profile.json")


def _read_profile():
    if not os.path.exists(PROFILE_FILE):
        return {}
    with open(PROFILE_FILE) as f:
        return json.load(f)


def _write_profile(profile):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(PROFILE_FILE, "w") as f:
        json.dump(profile, f, indent=2)


def _get_or_create_id(profile):
    if not profile.get("telemetry_id"):
        profile["telemetry_id"] = str(uuid.uuid4())
        _write_profile(profile)
    return profile["telemetry_id"]


def send(event_name, properties=None):
    profile = _read_profile()

    if not profile.get("telemetry_enabled", True):
        return

    distinct_id = _get_or_create_id(profile)

    payload = {
        "api_key": POSTHOG_API_KEY,
        "event": event_name,
        "distinct_id": distinct_id,
        "properties": {
            "$lib": "youraijobhuntingintern",
            **(properties or {}),
        },
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{POSTHOG_HOST}/capture/",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="Send a telemetry event")
    parser.add_argument("--event", required=True, help="Event name")
    parser.add_argument("--props", default="{}", help="JSON properties string")
    args = parser.parse_args()

    try:
        props = json.loads(args.props)
    except json.JSONDecodeError:
        props = {}

    send(args.event, props)


if __name__ == "__main__":
    main()
