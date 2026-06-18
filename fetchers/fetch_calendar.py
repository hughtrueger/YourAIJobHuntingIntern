#!/usr/bin/env python3
"""
Fetch calendar events for the rest of the current week and write to state/calendar.json.
Usage: python3 fetchers/fetch_calendar.py
"""

import datetime
import json
import os
import sys

STATE_DIR = os.path.join(os.path.dirname(__file__), '..', 'state')
TOKEN_FILE = os.path.join(STATE_DIR, 'token.json')
MS_TOKEN_FILE = os.path.join(STATE_DIR, 'ms_token.json')
MS_CONFIG_FILE = os.path.join(STATE_DIR, 'ms_config.json')
OUTPUT_FILE = os.path.join(STATE_DIR, 'calendar.json')
PROFILE_FILE = os.path.join(STATE_DIR, 'profile.json')


def get_calendar_type() -> str:
    if not os.path.exists(PROFILE_FILE):
        return 'google'
    with open(PROFILE_FILE) as f:
        profile = json.load(f)
    return profile.get('calendar_type', 'google') or 'google'


# ── Google Calendar ────────────────────────────────────────────────────────────

def get_google_service():
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        print("Missing dependencies. Run: pip install -r fetchers/requirements.txt")
        sys.exit(1)

    if not os.path.exists(TOKEN_FILE):
        print("Not authenticated. Run: python3 fetchers/setup.py --provider google")
        sys.exit(1)

    scopes = [
        'https://www.googleapis.com/auth/gmail.readonly',
        'https://www.googleapis.com/auth/calendar.readonly',
        'https://www.googleapis.com/auth/drive.readonly',
    ]

    creds = Credentials.from_authorized_user_file(TOKEN_FILE, scopes)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_FILE, 'w') as f:
                f.write(creds.to_json())
        else:
            print("Token expired. Run: python3 fetchers/setup.py --provider google")
            sys.exit(1)

    return build('calendar', 'v3', credentials=creds)


def fetch_google_events(time_min: datetime.datetime, time_max: datetime.datetime) -> list[dict]:
    service = get_google_service()

    events_result = service.events().list(
        calendarId='primary',
        timeMin=time_min.isoformat() + 'Z',
        timeMax=time_max.isoformat() + 'Z',
        singleEvents=True,
        orderBy='startTime',
        maxResults=100,
    ).execute()

    raw_events = events_result.get('items', [])
    return [normalise_google_event(e) for e in raw_events]


def normalise_google_event(event: dict) -> dict:
    start = event.get('start', {})
    end = event.get('end', {})

    start_dt = start.get('dateTime') or start.get('date', '')
    end_dt = end.get('dateTime') or end.get('date', '')
    all_day = 'date' in start and 'dateTime' not in start

    attendees = [
        a.get('email', '') for a in event.get('attendees', [])
        if not a.get('self', False)
    ]

    return {
        'id': event.get('id', ''),
        'title': event.get('summary', 'Untitled'),
        'description': event.get('description', ''),
        'location': event.get('location', ''),
        'start': start_dt,
        'end': end_dt,
        'all_day': all_day,
        'attendees': attendees,
        'attendee_count': len(event.get('attendees', [])),
        'status': event.get('status', 'confirmed'),
        'organizer': event.get('organizer', {}).get('email', ''),
        'video_link': _extract_video_link(event),
        'source': 'google',
    }


def _extract_video_link(event: dict) -> str:
    # Google Meet link
    entry_points = event.get('conferenceData', {}).get('entryPoints', [])
    for ep in entry_points:
        if ep.get('entryPointType') == 'video':
            return ep.get('uri', '')
    # Check description for Zoom/Teams links
    desc = event.get('description', '')
    for line in desc.split('\n'):
        line = line.strip()
        if 'zoom.us/j/' in line or 'teams.microsoft.com' in line or 'meet.google.com' in line:
            return line
    return ''


# ── Microsoft Calendar ─────────────────────────────────────────────────────────

def get_ms_token() -> str:
    try:
        import msal
    except ImportError:
        print("Missing dependencies. Run: pip install -r fetchers/requirements.txt")
        sys.exit(1)

    if not os.path.exists(MS_CONFIG_FILE):
        print("Microsoft not configured. Run: python3 fetchers/setup.py --provider microsoft")
        sys.exit(1)

    with open(MS_CONFIG_FILE) as f:
        config = json.load(f)

    client_id = config.get('client_id')
    scopes = ['Mail.Read', 'Calendars.Read']
    authority = 'https://login.microsoftonline.com/consumers'
    app = msal.PublicClientApplication(client_id, authority=authority)

    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(scopes, account=accounts[0])
        if result and 'access_token' in result:
            return result['access_token']

    print("Microsoft token expired. Run: python3 fetchers/setup.py --provider microsoft")
    sys.exit(1)


def fetch_microsoft_events(time_min: datetime.datetime, time_max: datetime.datetime) -> list[dict]:
    try:
        import urllib.request
        import urllib.parse
    except ImportError:
        pass

    token = get_ms_token()

    start_str = time_min.strftime('%Y-%m-%dT%H:%M:%S')
    end_str = time_max.strftime('%Y-%m-%dT%H:%M:%S')

    url = (
        f"https://graph.microsoft.com/v1.0/me/calendarView"
        f"?startDateTime={urllib.parse.quote(start_str)}"
        f"&endDateTime={urllib.parse.quote(end_str)}"
        f"&$orderby=start/dateTime"
        f"&$top=100"
        f"&$select=subject,start,end,location,bodyPreview,attendees,isAllDay,organizer,onlineMeeting"
    )

    import urllib.request as req
    request = req.Request(url, headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
    with req.urlopen(request) as response:
        data = json.loads(response.read().decode())

    return [normalise_ms_event(e) for e in data.get('value', [])]


def normalise_ms_event(event: dict) -> dict:
    start = event.get('start', {}).get('dateTime', '')
    end = event.get('end', {}).get('dateTime', '')
    location = event.get('location', {}).get('displayName', '')
    all_day = event.get('isAllDay', False)

    attendees = [
        a.get('emailAddress', {}).get('address', '')
        for a in event.get('attendees', [])
    ]

    online = event.get('onlineMeeting', {}) or {}
    video_link = online.get('joinUrl', '')

    return {
        'id': event.get('id', ''),
        'title': event.get('subject', 'Untitled'),
        'description': event.get('bodyPreview', ''),
        'location': location,
        'start': start,
        'end': end,
        'all_day': all_day,
        'attendees': attendees,
        'attendee_count': len(attendees),
        'status': 'confirmed',
        'organizer': event.get('organizer', {}).get('emailAddress', {}).get('address', ''),
        'video_link': video_link,
        'source': 'microsoft',
    }


# ── Shared ─────────────────────────────────────────────────────────────────────

def get_week_window() -> tuple[datetime.datetime, datetime.datetime]:
    """Returns (start_of_today, end_of_friday_this_week) in UTC."""
    today = datetime.date.today()
    # End of this Friday (or today if it's Friday/weekend, extend to next Friday)
    days_until_friday = (4 - today.weekday()) % 7
    if days_until_friday == 0 and today.weekday() == 4:
        end_date = today
    elif today.weekday() > 4:
        # Weekend — look at next week
        days_until_friday = 4 + (7 - today.weekday())
        end_date = today + datetime.timedelta(days=days_until_friday)
    else:
        end_date = today + datetime.timedelta(days=days_until_friday)

    time_min = datetime.datetime.combine(today, datetime.time.min)
    time_max = datetime.datetime.combine(end_date, datetime.time(23, 59, 59))
    return time_min, time_max


def detect_conflicts(events: list[dict]) -> list[dict]:
    """Tag events that overlap with another event."""
    timed = []
    for e in events:
        if not e.get('all_day'):
            try:
                start = datetime.datetime.fromisoformat(e['start'].replace('Z', '+00:00'))
                end = datetime.datetime.fromisoformat(e['end'].replace('Z', '+00:00'))
                timed.append((start, end, e))
            except (ValueError, KeyError):
                pass

    for i, (s1, e1, ev1) in enumerate(timed):
        for j, (s2, e2, ev2) in enumerate(timed):
            if i >= j:
                continue
            if s1 < e2 and s2 < e1:
                ev1['has_conflict'] = True
                ev2['has_conflict'] = True

    return events


def main():
    calendar_type = get_calendar_type()
    time_min, time_max = get_week_window()

    print(f"Fetching {calendar_type} calendar ({time_min.date()} → {time_max.date()})...")

    if calendar_type == 'google':
        events = fetch_google_events(time_min, time_max)
    elif calendar_type == 'microsoft':
        events = fetch_microsoft_events(time_min, time_max)
    else:
        print(f"Unknown calendar type: {calendar_type}")
        sys.exit(1)

    events = detect_conflicts(events)

    output = {
        'fetched_at': datetime.datetime.now().isoformat(),
        'calendar_type': calendar_type,
        'window_start': time_min.isoformat(),
        'window_end': time_max.isoformat(),
        'event_count': len(events),
        'events': events,
    }

    os.makedirs(STATE_DIR, exist_ok=True)
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"✓ Fetched {len(events)} events")
    print(f"  Written to: {OUTPUT_FILE}")


if __name__ == '__main__':
    main()
