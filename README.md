# AI Job Hunting Intern

Your AI job hunting assistant — powered by Claude. Every weekday morning, your AI intern will make sure you start your day focused on the best, most active job listings, up to date on the most important industry news, and ready for every meeting in your calendar.

Run `/morning-brief` and your assistant goes to work: scanning job boards and career pages for roles matched to your profile, reviewing your calendar for anything that needs prep, and pulling the headlines relevant to the companies and sectors you care about. Then it brings it all back to you in one focused brief — delivered by a character of your choosing, from a devoted butler to an anxious genius drummer.

---

## What you get each morning

- **Job listings** — matched to your profile, ranked by recency and fit, with a line on why each one made the cut
- **Calendar** — upcoming meetings flagged for prep, conflicts surfaced, anything logistical you shouldn't walk into cold
- **Industry news** — the headlines that matter for your search, scoped to your sectors and covering everything since your last brief

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

## Quick Start (Tier 1 — no setup required)

Claude uses web search for news and job listings. No Python, no accounts, no dependencies needed beyond Claude Code itself.

### 1. Connect to this repo

**Option A — using Git** (if you have it):
```bash
git clone https://github.com/hughtrueger/YourAIJobHuntingIntern.git
```

**Option B — no Git needed:**
1. Click the green **Code** button at the top of this GitHub page
2. Select **Download ZIP**
3. Unzip the folder somewhere you'll remember (e.g. your Documents folder)

### 2. Get Claude Code

Claude Code is Anthropic's AI coding tool — it's what runs the intern. You'll need an account and an active Pro or Max subscription.

1. Go to [claude.ai/code](https://claude.ai/code) and create an Anthropic account
2. Subscribe to Pro or Max (Claude Code requires a paid plan)
3. Download the **desktop app** for [Mac or Windows](https://claude.ai/code) — this is the easiest way to get started

> **Comfortable with a terminal?** You can also install the CLI with `npm install -g @anthropic-ai/claude-code` and run `claude` from any folder.

### 3. Open the project in Claude Code

**Desktop app:** Open Claude Code, click **Open Folder**, and select the `YourAIJobHuntingIntern` folder you just downloaded.

**Terminal:** Navigate to the project folder and run `claude`.

---

**New to terminals?** A terminal is a text-based way to give your computer instructions. Here's how to open one and get to the right folder.

**Opening a terminal:**
- **Mac:** Press `Cmd + Space`, type `Terminal`, press Enter.
- **Windows:** Search for **PowerShell** in the Start menu and open it.

**Navigating to the project folder:**

The command `cd` means "change directory" — it moves you into a folder. You need to tell it the full path to wherever you saved the project.

The easiest way to get the correct path:

- **Mac:** Open Finder, find the `YourAIJobHuntingIntern` folder, then drag and drop it directly onto the Terminal window after typing `cd ` (with a space). The full path fills in automatically. Press Enter.
- **Windows:** Open File Explorer, navigate to the folder, click the address bar at the top, and copy the path shown. In PowerShell, type `cd ` then paste the path and press Enter.

If you unzipped it to Documents, it's probably:
```bash
# Mac
cd ~/Documents/YourAIJobHuntingIntern

# Windows
cd C:\Users\YourName\Documents\YourAIJobHuntingIntern
```

**Check it worked** — type `ls` (Mac) or `dir` (Windows) and press Enter. You should see files like `README.md` and a `fetchers` folder listed. If you do, you're in the right place.

**Common problems:**

- *"No such file or directory"* — the path is wrong or the folder name is slightly different. Check the exact folder name (it might be `YourAIJobHuntingIntern-main` if you downloaded a ZIP). Try the drag-and-drop method above to get the exact path.
- *"Permission denied"* — try closing and reopening the terminal, then try again.
- *Not sure where you are?* — type `pwd` (Mac) or `cd` with no arguments (Windows) and press Enter. It prints your current location.

---

### 4. Run the brief

Once you're in a Claude Code session inside the project folder, type:

```
/morning-brief
```

That's it. Onboarding runs automatically and guides you through everything.

---

## Onboarding walkthrough

On first run, the intern guides you through five steps:

**Step 0 — Pick a personality.** Choose one of four characters — Garth Algar, Dobby, Alfred Pennyworth, or Renfield. The intern adopts that character's tone for all responses.

**Step 1 — News preferences.** Pick the industry topics you want covered each morning (AI, fintech, XR, consumer tech, etc.).

**Step 2 — Job profile.** Either answer a few questions or paste your CV — the intern extracts target companies, job functions, and experience level automatically from a CV upload.

**Step 3 — Experience and filters.** Set experience years and seniority keywords (senior, staff, principal, etc.) per job function, plus location and other filters.

**Step 4 — Connect your productivity suite.** Connect Google or Microsoft for email and calendar. Full step-by-step instructions are provided inline — you run the setup script directly from the Claude Code prompt.

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
| `telemetry_enabled` | `true` by default — set to `false` to opt out of anonymous usage data |
| `telemetry_id` | Auto-generated anonymous UUID — never linked to personal data |

To reset and re-run onboarding: delete `state/profile.json` and run `/morning-brief`.

---

## Privacy

All data stays local. Credentials, tokens, and your personal profile are gitignored and never leave your machine. Gmail and Calendar APIs are accessed read-only.

---

## Requirements

- [Claude Code](https://claude.ai/code) with an active Pro or Max subscription
- Python 3.9+ (Tier 2 only)
- A Google Cloud project with OAuth credentials (Tier 2 Google only)
