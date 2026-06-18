#!/usr/bin/env python3
"""
Fetch job alert emails from Gmail and write to state/gmail_jobs.json.
Usage: python3 fetchers/fetch_gmail.py
"""

import base64
import datetime
import json
import os
import re
import sys

STATE_DIR = os.path.join(os.path.dirname(__file__), '..', 'state')
TOKEN_FILE = os.path.join(STATE_DIR, 'token.json')
OUTPUT_FILE = os.path.join(STATE_DIR, 'gmail_jobs.json')
PROFILE_FILE = os.path.join(STATE_DIR, 'profile.json')


def get_gmail_service():
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

    return build('gmail', 'v1', credentials=creds)


def decode_body(payload):
    """Extract plain text body from a Gmail message payload."""
    if payload.get('mimeType') == 'text/plain':
        data = payload.get('body', {}).get('data', '')
        if data:
            return base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')

    if 'parts' in payload:
        for part in payload['parts']:
            result = decode_body(part)
            if result:
                return result

    return ''


def extract_job_listings(subject: str, body: str, sender: str) -> list[dict]:
    """
    Parse job listings from an email body.
    Returns a list of dicts with title, company, url, location, date_posted.
    """
    listings = []

    # LinkedIn job alert format
    linkedin_pattern = re.compile(
        r'([^\n]{10,80})\n([^\n]{5,50})\n(?:([^\n]{5,50})\n)?'
        r'.*?(?:https?://(?:www\.)?linkedin\.com/jobs/view/\S+)',
        re.DOTALL
    )

    # Generic URL extraction with surrounding context
    url_pattern = re.compile(r'(https?://\S+)')

    # Greenhouse / Lever / Workday patterns
    ats_patterns = [
        re.compile(r'greenhouse\.io/[^/]+/jobs/(\d+)', re.I),
        re.compile(r'lever\.co/[^/]+/([a-f0-9-]{36})', re.I),
        re.compile(r'jobs\.lever\.co/[^/]+/([a-f0-9-]{36})', re.I),
        re.compile(r'myworkdayjobs\.com/[^/]+/job/([^/\s]+)', re.I),
    ]

    # Extract job-relevant lines
    lines = [l.strip() for l in body.split('\n') if l.strip()]

    # Look for job alert patterns
    i = 0
    while i < len(lines):
        line = lines[i]

        # LinkedIn-style alerts: "Job Title at Company"
        if ' at ' in line and len(line) < 120:
            parts = line.split(' at ', 1)
            if len(parts) == 2 and len(parts[0]) > 3:
                title = parts[0].strip()
                company_loc = parts[1].strip()

                # Next lines might have location and URL
                url = ''
                location = ''
                for j in range(i + 1, min(i + 5, len(lines))):
                    if lines[j].startswith('http'):
                        url = lines[j]
                        break
                    elif not location and len(lines[j]) < 80:
                        location = lines[j]

                if title and company_loc:
                    listings.append({
                        'title': title,
                        'company': company_loc.split(',')[0].strip(),
                        'location': location or company_loc,
                        'url': url,
                        'source': 'gmail_alert',
                        'sender': sender,
                        'subject': subject,
                    })

        # "Role Title\nCompany Name\nLocation" blocks followed by a URL
        url_match = url_pattern.search(line)
        if url_match:
            url = url_match.group(1)
            # Look backwards for title/company
            if i >= 2:
                potential_title = lines[i - 2] if i >= 2 else ''
                potential_company = lines[i - 1] if i >= 1 else ''
                if (potential_title and len(potential_title) < 100 and
                        potential_company and len(potential_company) < 100 and
                        not potential_title.startswith('http') and
                        not potential_company.startswith('http')):
                    listings.append({
                        'title': potential_title,
                        'company': potential_company,
                        'location': '',
                        'url': url,
                        'source': 'gmail_alert',
                        'sender': sender,
                        'subject': subject,
                    })

        i += 1

    return listings


def is_job_alert_email(subject: str, sender: str) -> bool:
    """Heuristic: is this email a job alert or careers digest?"""
    subject_lower = subject.lower()
    sender_lower = sender.lower()

    job_keywords = [
        'job alert', 'jobs for you', 'new jobs', 'job recommendations',
        'career opportunities', 'job matches', 'hiring', 'job opening',
        'roles for you', 'jobs matching', 'new opportunities',
        'product manager', 'pm role', 'pm jobs',
    ]
    job_senders = [
        'linkedin', 'indeed', 'glassdoor', 'wellfound', 'lever.co',
        'greenhouse.io', 'workday', 'smartrecruiters', 'jobvite',
        'careers@', 'jobs@', 'recruiting@', 'talent@', 'noreply@',
    ]

    return (
        any(kw in subject_lower for kw in job_keywords) or
        any(s in sender_lower for s in job_senders)
    )


def fetch_job_emails(service, lookback_days: int = 7) -> dict:
    after_date = (datetime.date.today() - datetime.timedelta(days=lookback_days)).strftime('%Y/%m/%d')
    query = f'after:{after_date} (subject:"job alert" OR subject:"jobs for you" OR subject:"new jobs" OR subject:"career" OR subject:"hiring" OR subject:"opportunities" OR from:linkedin.com OR from:indeed.com OR from:glassdoor.com OR from:wellfound.com)'

    results = service.users().messages().list(
        userId='me',
        q=query,
        maxResults=50
    ).execute()

    messages = results.get('messages', [])

    all_listings = []
    raw_emails = []

    for msg_ref in messages:
        msg = service.users().messages().get(
            userId='me',
            id=msg_ref['id'],
            format='full'
        ).execute()

        headers = {h['name']: h['value'] for h in msg['payload'].get('headers', [])}
        subject = headers.get('Subject', '')
        sender = headers.get('From', '')
        date = headers.get('Date', '')

        if not is_job_alert_email(subject, sender):
            continue

        body = decode_body(msg['payload'])
        listings = extract_job_listings(subject, body, sender)

        raw_emails.append({
            'id': msg_ref['id'],
            'subject': subject,
            'sender': sender,
            'date': date,
            'listing_count': len(listings),
        })

        all_listings.extend(listings)

    # Deduplicate by URL
    seen_urls = set()
    deduped = []
    for listing in all_listings:
        url = listing.get('url', '')
        key = url if url else f"{listing['title']}|{listing['company']}"
        if key not in seen_urls:
            seen_urls.add(key)
            deduped.append(listing)

    return {
        'fetched_at': datetime.datetime.now().isoformat(),
        'lookback_days': lookback_days,
        'email_count': len(raw_emails),
        'listing_count': len(deduped),
        'listings': deduped,
        'emails_scanned': raw_emails,
    }


def get_lookback_days() -> int:
    if not os.path.exists(PROFILE_FILE):
        return 7
    with open(PROFILE_FILE) as f:
        profile = json.load(f)
    last_run = profile.get('last_run')
    if not last_run:
        return 7
    try:
        last = datetime.date.fromisoformat(last_run)
        days = (datetime.date.today() - last).days
        return min(max(days, 1), 7)
    except (ValueError, TypeError):
        return 7


def main():
    service = get_gmail_service()
    lookback = get_lookback_days()

    print(f"Fetching job alert emails (last {lookback} days)...")
    data = fetch_job_emails(service, lookback_days=lookback)

    os.makedirs(STATE_DIR, exist_ok=True)
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"✓ Found {data['listing_count']} listings across {data['email_count']} emails")
    print(f"  Written to: {OUTPUT_FILE}")


if __name__ == '__main__':
    main()
