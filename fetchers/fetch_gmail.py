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

MONTH_NAMES = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12,
}


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


def parse_date_posted(text: str, email_date: datetime.date) -> str | None:
    """
    Try to extract a posting date from a snippet of text.
    Returns ISO date string (YYYY-MM-DD) or None.
    email_date is used to resolve relative expressions like "3 days ago".
    """
    text = text.strip()
    text_lower = text.lower()

    # Relative: "today", "just posted"
    if text_lower in ('today', 'just posted', 'new', '< 1 day ago'):
        return email_date.isoformat()

    # Relative: "yesterday"
    if text_lower == 'yesterday':
        return (email_date - datetime.timedelta(days=1)).isoformat()

    # Relative: "X days ago", "X day ago"
    m = re.match(r'^(\d+)\s+days?\s+ago$', text_lower)
    if m:
        return (email_date - datetime.timedelta(days=int(m.group(1)))).isoformat()

    # Relative: "X weeks ago"
    m = re.match(r'^(\d+)\s+weeks?\s+ago$', text_lower)
    if m:
        return (email_date - datetime.timedelta(weeks=int(m.group(1)))).isoformat()

    # Explicit: "Posted on M/D/YYYY" or "Posted M/D/YYYY"
    m = re.search(r'posted\s+on\s+(\d{1,2})/(\d{1,2})/(\d{4})', text_lower)
    if m:
        try:
            return datetime.date(int(m.group(3)), int(m.group(1)), int(m.group(2))).isoformat()
        except ValueError:
            pass

    # Explicit: "M/D/YYYY" or "MM/DD/YYYY"
    m = re.search(r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b', text)
    if m:
        try:
            return datetime.date(int(m.group(3)), int(m.group(1)), int(m.group(2))).isoformat()
        except ValueError:
            pass

    # Explicit: "Month D, YYYY" or "Month DD YYYY"
    m = re.search(
        r'\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|'
        r'jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)'
        r'[\s.]+(\d{1,2}),?\s+(\d{4})\b',
        text_lower
    )
    if m:
        month = MONTH_NAMES.get(m.group(1)[:3])
        if month:
            try:
                return datetime.date(int(m.group(3)), month, int(m.group(2))).isoformat()
            except ValueError:
                pass

    # Explicit: "YYYY-MM-DD"
    m = re.search(r'\b(\d{4})-(\d{2})-(\d{2})\b', text)
    if m:
        try:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            pass

    return None


def extract_google_careers_listings(body: str, email_date: datetime.date, sender: str, subject: str) -> list[dict]:
    """
    Parse Google Careers job alert email format.
    Listings appear as: "Job Title\nCompany – Location\nX days ago\n..."
    """
    listings = []
    lines = [l.strip() for l in body.split('\n') if l.strip()]

    # Age patterns that signal a Google Careers listing block
    age_pattern = re.compile(
        r'^(\d+\s+days?\s+ago|today|yesterday|\d+\s+weeks?\s+ago|just posted)$',
        re.I
    )

    i = 0
    while i < len(lines):
        if age_pattern.match(lines[i]):
            age_text = lines[i]
            # Title is typically 2 lines back, company/location 1 line back
            title = lines[i - 2] if i >= 2 else ''
            company_loc = lines[i - 1] if i >= 1 else ''

            # Parse company and location from "Company – Location" or "Company · Location"
            company = company_loc
            location = ''
            for sep in [' – ', ' - ', ' · ', ' | ']:
                if sep in company_loc:
                    parts = company_loc.split(sep, 1)
                    company = parts[0].strip()
                    location = parts[1].strip()
                    break

            # Find the URL in the next few lines
            url = ''
            for j in range(i + 1, min(i + 6, len(lines))):
                if lines[j].startswith('http'):
                    url = lines[j]
                    break

            date_posted = parse_date_posted(age_text, email_date)

            if title and company and len(title) < 120:
                listings.append({
                    'title': title,
                    'company': company,
                    'location': location,
                    'url': url,
                    'date_posted': date_posted,
                    'email_received_date': email_date.isoformat(),
                    'source': 'gmail_google_careers',
                    'sender': sender,
                    'subject': subject,
                })
        i += 1

    return listings


def extract_linkedin_listings(body: str, email_date: datetime.date, sender: str, subject: str) -> list[dict]:
    """
    Parse LinkedIn job alert emails.
    Contains "Posted on M/D/YYYY" and job title blocks.
    """
    listings = []
    lines = [l.strip() for l in body.split('\n') if l.strip()]

    posted_pattern = re.compile(r'posted\s+on\s+(\d{1,2}/\d{1,2}/\d{4})', re.I)

    # LinkedIn snippets often have the posting date at the top of the email
    # and then a single prominent role. Extract date from anywhere in body.
    body_date = None
    for line in lines:
        m = posted_pattern.search(line)
        if m:
            body_date = parse_date_posted(m.group(0), email_date)
            break

    # Try to extract role from subject: "You may be a fit for Company's Role Title role"
    subject_match = re.search(r"fit for (.+?)'s (.+?) role", subject, re.I)
    if subject_match:
        company = subject_match.group(1).strip()
        title = subject_match.group(2).strip()
        url = ''
        for line in lines:
            if 'linkedin.com/jobs' in line:
                url = line
                break
        listings.append({
            'title': title,
            'company': company,
            'location': '',
            'url': url,
            'date_posted': body_date or email_date.isoformat(),
            'email_received_date': email_date.isoformat(),
            'source': 'gmail_linkedin',
            'sender': sender,
            'subject': subject,
        })

    # Also scan for " at " patterns in body
    for i, line in enumerate(lines):
        if ' at ' in line and len(line) < 120 and not line.startswith('http'):
            parts = line.split(' at ', 1)
            if len(parts[0]) > 3 and len(parts[0]) < 80:
                title = parts[0].strip()
                company = parts[1].split(',')[0].strip()
                url = ''
                for j in range(i + 1, min(i + 5, len(lines))):
                    if lines[j].startswith('http') and 'linkedin.com' in lines[j]:
                        url = lines[j]
                        break
                if not any(l['title'] == title and l['company'] == company for l in listings):
                    listings.append({
                        'title': title,
                        'company': company,
                        'location': '',
                        'url': url,
                        'date_posted': body_date or email_date.isoformat(),
                        'email_received_date': email_date.isoformat(),
                        'source': 'gmail_linkedin',
                        'sender': sender,
                        'subject': subject,
                    })

    return listings


def extract_microsoft_listings(body: str, email_date: datetime.date, sender: str, subject: str) -> list[dict]:
    """
    Parse Microsoft Careers job alert emails (sometimes forwarded via Outlook).
    Subject pattern: "X new job(s) at Microsoft for: <search>"
    """
    listings = []
    lines = [l.strip() for l in body.split('\n') if l.strip()]

    url_pattern = re.compile(r'(https?://careers\.microsoft\.com/\S+|https?://microsoft\.com/careers/\S+)', re.I)

    for i, line in enumerate(lines):
        url_match = url_pattern.search(line)
        if url_match:
            url = url_match.group(1)
            title = lines[i - 1] if i >= 1 else ''
            location = ''
            date_posted = None
            # Look for date or location in surrounding lines
            for j in range(max(0, i - 3), min(len(lines), i + 3)):
                d = parse_date_posted(lines[j], email_date)
                if d:
                    date_posted = d
                    break
                if any(word in lines[j].lower() for word in ['remote', 'california', 'redmond', 'seattle', 'san francisco']):
                    location = lines[j]

            if title and not title.startswith('http') and len(title) < 120:
                listings.append({
                    'title': title,
                    'company': 'Microsoft',
                    'location': location,
                    'url': url,
                    'date_posted': date_posted or email_date.isoformat(),
                    'email_received_date': email_date.isoformat(),
                    'source': 'gmail_microsoft_careers',
                    'sender': sender,
                    'subject': subject,
                })

    return listings


def extract_job_listings(subject: str, body: str, sender: str, email_date: datetime.date) -> list[dict]:
    """
    Route to source-specific parsers, fall back to generic extraction.
    """
    sender_lower = sender.lower()

    if 'careers-noreply@google.com' in sender_lower or 'google.com' in sender_lower and 'careers' in subject.lower():
        results = extract_google_careers_listings(body, email_date, sender, subject)
        if results:
            return results

    if 'linkedin.com' in sender_lower:
        results = extract_linkedin_listings(body, email_date, sender, subject)
        if results:
            return results

    if 'microsoft' in sender_lower or ('microsoft' in subject.lower() and 'careers' in subject.lower()):
        results = extract_microsoft_listings(body, email_date, sender, subject)
        if results:
            return results

    # Generic fallback
    listings = []
    url_pattern = re.compile(r'(https?://\S+)')
    lines = [l.strip() for l in body.split('\n') if l.strip()]

    age_pattern = re.compile(
        r'^(\d+\s+days?\s+ago|today|yesterday|\d+\s+weeks?\s+ago|just posted)$', re.I
    )

    i = 0
    while i < len(lines):
        line = lines[i]

        if ' at ' in line and len(line) < 120:
            parts = line.split(' at ', 1)
            if len(parts) == 2 and len(parts[0]) > 3:
                title = parts[0].strip()
                company_loc = parts[1].strip()
                url = ''
                date_posted = None
                location = ''
                for j in range(i + 1, min(i + 6, len(lines))):
                    if lines[j].startswith('http'):
                        url = lines[j]
                        break
                    d = parse_date_posted(lines[j], email_date)
                    if d:
                        date_posted = d
                    elif not location and len(lines[j]) < 80 and not age_pattern.match(lines[j]):
                        location = lines[j]
                listings.append({
                    'title': title,
                    'company': company_loc.split(',')[0].strip(),
                    'location': location or company_loc,
                    'url': url,
                    'date_posted': date_posted or email_date.isoformat(),
                    'email_received_date': email_date.isoformat(),
                    'source': 'gmail_alert',
                    'sender': sender,
                    'subject': subject,
                })

        url_match = url_pattern.search(line)
        if url_match:
            url = url_match.group(1)
            if i >= 2:
                potential_title = lines[i - 2]
                potential_company = lines[i - 1]
                date_posted = None
                for j in range(max(0, i - 4), i):
                    d = parse_date_posted(lines[j], email_date)
                    if d:
                        date_posted = d
                        break
                if (potential_title and len(potential_title) < 100 and
                        potential_company and len(potential_company) < 100 and
                        not potential_title.startswith('http') and
                        not potential_company.startswith('http')):
                    listings.append({
                        'title': potential_title,
                        'company': potential_company,
                        'location': '',
                        'url': url,
                        'date_posted': date_posted or email_date.isoformat(),
                        'email_received_date': email_date.isoformat(),
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
        'product manager', 'pm role', 'pm jobs', 'new job',
        'match your search', 'jobs at ',
    ]
    job_senders = [
        'linkedin.com', 'indeed.com', 'glassdoor.com', 'wellfound.com',
        'lever.co', 'greenhouse.io', 'workday', 'smartrecruiters', 'jobvite',
        'careers@', 'jobs@', 'recruiting@', 'talent@',
        'careers-noreply@google.com', 'jobalerts-noreply@google.com',
        'donotreply@email.careers.microsoft.com',
        'jobs-listings@linkedin.com', 'messages-noreply@linkedin.com',
        'noreply@glassdoor.com',
    ]

    return (
        any(kw in subject_lower for kw in job_keywords) or
        any(s in sender_lower for s in job_senders)
    )


def fetch_job_emails(service, lookback_days: int = 7) -> dict:
    after_date = (datetime.date.today() - datetime.timedelta(days=lookback_days)).strftime('%Y/%m/%d')
    query = (
        f'after:{after_date} ('
        'subject:"job alert" OR subject:"jobs for you" OR subject:"new jobs" OR '
        'subject:"match your search" OR subject:"jobs at" OR subject:"new job" OR '
        'subject:"career" OR subject:"hiring" OR subject:"opportunities" OR '
        'from:linkedin.com OR from:indeed.com OR from:glassdoor.com OR '
        'from:wellfound.com OR from:careers-noreply@google.com OR '
        'from:jobalerts-noreply@google.com OR '
        'from:donotreply@email.careers.microsoft.com'
        ')'
    )

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
        date_str = headers.get('Date', '')

        # Use internalDate (ms since epoch) for precise email timestamp
        internal_ms = int(msg.get('internalDate', 0))
        if internal_ms:
            email_date = datetime.datetime.utcfromtimestamp(internal_ms / 1000).date()
        else:
            email_date = datetime.date.today()

        if not is_job_alert_email(subject, sender):
            continue

        body = decode_body(msg['payload'])
        listings = extract_job_listings(subject, body, sender, email_date)

        raw_emails.append({
            'id': msg_ref['id'],
            'subject': subject,
            'sender': sender,
            'date': email_date.isoformat(),
            'listing_count': len(listings),
        })

        all_listings.extend(listings)

    # Deduplicate by URL, then by title+company
    seen = set()
    deduped = []
    for listing in all_listings:
        url = listing.get('url', '')
        key = url if url else f"{listing['title']}|{listing['company']}"
        if key not in seen:
            seen.add(key)
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
