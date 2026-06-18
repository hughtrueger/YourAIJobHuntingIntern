#!/usr/bin/env python3
"""
One-time OAuth setup for AI Job Hunting Intern.
Usage: python3 fetchers/setup.py --provider google
       python3 fetchers/setup.py --provider microsoft
"""

import argparse
import json
import os
import sys

STATE_DIR = os.path.join(os.path.dirname(__file__), '..', 'state')
CREDENTIALS_FILE = os.path.join(STATE_DIR, 'credentials.json')
TOKEN_FILE = os.path.join(STATE_DIR, 'token.json')


def setup_google():
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except ImportError:
        print("Missing dependencies. Run: pip install -r fetchers/requirements.txt")
        sys.exit(1)

    scopes = [
        'https://www.googleapis.com/auth/gmail.readonly',
        'https://www.googleapis.com/auth/calendar.readonly',
        'https://www.googleapis.com/auth/drive.readonly',
    ]

    if not os.path.exists(CREDENTIALS_FILE):
        print("\n── Google OAuth Setup ─────────────────────────────────────────────")
        print("You need a Google OAuth credentials file to proceed.")
        print("\nSteps:")
        print("  1. Go to https://console.cloud.google.com/")
        print("  2. Create a project (or select an existing one)")
        print("  3. Enable these APIs: Gmail, Google Calendar, Google Drive")
        print("  4. Go to APIs & Services → Credentials → Create Credentials → OAuth client ID")
        print("  5. Application type: Desktop app")
        print("  6. Download the JSON file and save it to:")
        print(f"     {CREDENTIALS_FILE}")
        print("\nOnce you've saved the file, run this command again.")
        print("──────────────────────────────────────────────────────────────────\n")
        sys.exit(1)

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, scopes)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, scopes)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, 'w') as f:
            f.write(creds.to_json())

    print("✓ Google account connected successfully.")
    print(f"  Token saved to: {TOKEN_FILE}")
    print("\nConnected scopes:")
    print("  • Gmail (read-only)")
    print("  • Google Calendar (read-only)")
    print("  • Google Drive (read-only)")

    _update_profile('google')


def setup_microsoft():
    try:
        import msal
    except ImportError:
        print("Missing dependencies. Run: pip install -r fetchers/requirements.txt")
        sys.exit(1)

    config_file = os.path.join(STATE_DIR, 'ms_config.json')

    if not os.path.exists(config_file):
        print("\n── Microsoft OAuth Setup ──────────────────────────────────────────")
        print("You need to register an Azure app to proceed.")
        print("\nSteps:")
        print("  1. Go to https://portal.azure.com/")
        print("  2. Navigate to Azure Active Directory → App registrations → New registration")
        print("  3. Name: 'AI Job Intern' | Supported account types: Personal Microsoft accounts")
        print("  4. Redirect URI: http://localhost (type: Public client/native)")
        print("  5. Under API permissions, add: Mail.Read, Calendars.Read")
        print("  6. Copy the Application (client) ID")
        print(f"\nThen create the file {config_file} with this content:")
        print(json.dumps({"client_id": "YOUR_CLIENT_ID_HERE"}, indent=2))
        print("\nOnce saved, run this command again.")
        print("──────────────────────────────────────────────────────────────────\n")
        sys.exit(1)

    with open(config_file) as f:
        config = json.load(f)

    client_id = config.get('client_id')
    if not client_id or client_id == 'YOUR_CLIENT_ID_HERE':
        print(f"Error: Please set your client_id in {config_file}")
        sys.exit(1)

    scopes = ['Mail.Read', 'Calendars.Read']
    authority = 'https://login.microsoftonline.com/consumers'

    token_file = os.path.join(STATE_DIR, 'ms_token.json')
    app = msal.PublicClientApplication(client_id, authority=authority)

    # Try silent auth first
    accounts = app.get_accounts()
    result = None
    if accounts:
        result = app.acquire_token_silent(scopes, account=accounts[0])

    if not result:
        flow = app.initiate_device_flow(scopes=scopes)
        if 'user_code' not in flow:
            print("Error initiating device flow:", flow.get('error_description'))
            sys.exit(1)

        print("\n── Microsoft sign-in ──────────────────────────────────────────────")
        print(f"  1. Open https://microsoft.com/devicelogin")
        print(f"  2. Enter code: {flow['user_code']}")
        print("──────────────────────────────────────────────────────────────────\n")
        result = app.acquire_token_by_device_flow(flow)

    if 'access_token' not in result:
        print("Authentication failed:", result.get('error_description', 'unknown error'))
        sys.exit(1)

    with open(token_file, 'w') as f:
        json.dump(result, f, indent=2)

    print("✓ Microsoft account connected successfully.")
    print(f"  Token saved to: {token_file}")
    print("\nConnected scopes:")
    print("  • Mail (read-only)")
    print("  • Calendar (read-only)")

    _update_profile('microsoft')


def _update_profile(provider: str):
    profile_file = os.path.join(STATE_DIR, 'profile.json')
    if not os.path.exists(profile_file):
        return

    with open(profile_file) as f:
        profile = json.load(f)

    profile['calendar_type'] = provider
    profile['tier'] = 2

    with open(profile_file, 'w') as f:
        json.dump(profile, f, indent=2)

    print(f"\n✓ Profile updated: tier=2, calendar_type={provider}")
    print("  Return to your morning brief and type 'done' to continue.")


def main():
    parser = argparse.ArgumentParser(description='Set up OAuth for AI Job Hunting Intern')
    parser.add_argument('--provider', choices=['google', 'microsoft'], required=True,
                        help='Which provider to connect')
    args = parser.parse_args()

    os.makedirs(STATE_DIR, exist_ok=True)

    if args.provider == 'google':
        setup_google()
    elif args.provider == 'microsoft':
        setup_microsoft()


if __name__ == '__main__':
    main()
