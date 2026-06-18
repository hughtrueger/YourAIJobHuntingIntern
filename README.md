# AI Job Hunting Intern

A daily Claude-powered job hunting brief that delivers personalised job listings, calendar prep, and industry news every weekday morning — built as a Claude Code slash command.

---

## How it works

Run `/morning-brief` in any Claude Code session inside this directory. On first run you'll be guided through a short onboarding to build your job profile and optionally connect your email and calendar.

Each morning you get three sections:
- **Job listings** — matched to your profile, sorted by recency then fit score
- **Calendar** — upcoming meetings flagged for prep, conflicts, and logistical reminders
- **Industry news** — scoped to the topics you care about, covering the lookback window since your last brief

---

## Quick Start (Tier 1 — no setup required)

1. Clone this repo
2. Open a Claude Code session in this directory
3. Run `/morning-brief`

Claude uses web search for news and job listings. No Python, no accounts, no dependencies needed.

---

## Full Setup (Tier 2 — Gmail + Google Calendar integration)

Tier 2 unlocks job alert emails from your inbox and a live calendar view. Claude's onboarding will walk you through this interactively, but here's the manual path if you prefer.

### Prerequisites

```bash
pip install -r fetchers/requirements.txt
```

### Connect Google Workspace

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → Enable: **Gmail API**, **Google Calendar API**, **Google Drive API**
3. Create OAuth credentials → Application type: **Desktop app** → Download the JSON file
4. Rename the downloaded file to `credentials.json` and save it to `state/credentials.json`
5. Run the setup (from the project root, inside a Claude Code session):
   ```
   ! python3 fetchers/setup.py --provider google
   ```
   This opens a browser window for sign-in and saves your token to `state/token.json` automatically.

### Connect Microsoft 365

1. Go to [Azure Portal](https://portal.azure.com/) → Azure Active Directory → App registrations
2. New registration → Name: "AI Job Intern" → Supported account types: Personal Microsoft accounts
3. Redirect URI: `http://localhost` (Public client/native)
4. Add API permissions: `Mail.Read`, `Calendars.Read`
5. Copy the Application (client) ID
6. Create `state/ms_config.json`:
   ```json
   { "client_id": "YOUR_CLIENT_ID_HERE" }
   ```
7. Run the setup:
   ```
   ! python3 fetchers/setup.py --provider microsoft
   ```

### Schedule automatic morning data fetch (macOS)

1. Open `launchd/com.aijobintern.plist` and replace `/PATH/TO/ai-job-intern/` with the absolute path to this directory
2. Load the schedule:
   ```bash
   cp launchd/com.aijobintern.plist ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.aijobintern.plist
   ```

Data is fetched at 8am Mon–Fri and cached in `state/`. When you run `/morning-brief`, the brief is built instantly from the cache.

---

## Onboarding walkthrough

On first run, the intern guides you through five steps:

**Step 0 — Pick a personality.** Choose one of five characters — Alfred Pennyworth, Dobby, Renfield, Dexter, or Garth Algar. The intern adopts that character's tone for all responses.

**Step 1 — Connect your productivity suite.** Optionally connect Google or Microsoft for email and calendar. Full step-by-step instructions are provided inline — you run the setup script directly from the Claude Code prompt.

**Step 2 — News preferences.** Pick the industry topics you want covered each morning (AI, fintech, XR, consumer tech, etc.).

**Step 3 — Job profile.** Either answer a few questions or paste your CV — the intern extracts target companies, job functions, and experience level automatically from a CV upload.

**Step 4 — Experience and filters.** Set experience years and seniority keywords (senior, staff, principal, etc.) per job function, plus location and other filters.

After completing setup, the intern silently validates that your profile returns at least 5 job results. If it doesn't, it surfaces a debug menu to broaden the search before running your first brief.

---

## Reducing permission prompts

On first run, the intern will remind you to run `/fewer-permission-prompts`. This scans your session and adds WebSearch and WebFetch to your Claude Code allowlist so you're not prompted on every search. You only need to do this once.

---

## Files

```
ai-job-intern/
├── .claude/
│   └── commands/
│       └── morning-brief.md        ← The Claude skill (the whole product)
├── fetchers/
│   ├── setup.py                    ← One-time OAuth setup
│   ├── fetch_gmail.py              ← Fetch job alert emails
│   ├── fetch_calendar.py           ← Fetch calendar events
│   ├── run_fetchers.py             ← Orchestrator (called by launchd)
│   ├── requirements.txt            ← Python dependencies
│   └── client_secret.example.json ← Template for Google OAuth credentials
├── launchd/
│   └── com.aijobintern.plist       ← macOS schedule template
├── state/
│   └── profile.example.json        ← Profile schema template (copy to profile.json)
└── README.md
```

---

## State file

`state/profile.json` stores your profile between sessions. Copy `state/profile.example.json` to `state/profile.json` to start fresh, or just run `/morning-brief` and onboarding creates it automatically.

| Field | Description |
|---|---|
| `onboarding_complete` | Whether initial setup is done |
| `persona` | Chosen character (e.g. "Alfred Pennyworth") |
| `tier` | 1 (web only) or 2 (OAuth connected) |
| `calendar_type` | `"google"`, `"microsoft"`, or `null` |
| `news_preferences` | Topics for the news section |
| `job_profile.job_functions` | 1–2 target job functions |
| `job_profile.experience_by_function` | Years + level keywords per function |
| `job_profile.target_companies` | Anchor companies for search and scoring |
| `last_run` | ISO date of last brief |

To reset and re-run onboarding: delete `state/profile.json` and run `/morning-brief`.

---

## Privacy

All data stays local. Credentials, tokens, and your personal profile are gitignored and never leave your machine. Gmail and Calendar APIs are accessed read-only.

---

## Requirements

- [Claude Code](https://claude.ai/code) with an active subscription
- Python 3.9+ (Tier 2 only)
- A Google Cloud project with OAuth credentials (Tier 2 Google only)
