# AI Job Hunting Intern — Usage Brief

You are checking the usage telemetry for the AI Job Hunting Intern app. Query PostHog and return a clear summary of how the app is being used.

---

## Step 1: Load credentials

Read `state/posthog.json`. It contains:
```json
{ "personal_api_key": "phx_...", "project_id": "480955" }
```

If the file does not exist, say: "PostHog credentials not found. Create `state/posthog.json` with your personal API key and project ID." and stop.

---

## Step 2: Fetch event counts

Using the `personal_api_key` and `project_id` from the file, run these curl commands in parallel:

```
! curl -s "https://app.posthog.com/api/projects/{project_id}/events/?event=onboarding_started&limit=1000" -H "Authorization: Bearer {personal_api_key}"
! curl -s "https://app.posthog.com/api/projects/{project_id}/events/?event=persona_selected&limit=1000" -H "Authorization: Bearer {personal_api_key}"
! curl -s "https://app.posthog.com/api/projects/{project_id}/events/?event=news_prefs_set&limit=1000" -H "Authorization: Bearer {personal_api_key}"
! curl -s "https://app.posthog.com/api/projects/{project_id}/events/?event=profile_built&limit=1000" -H "Authorization: Bearer {personal_api_key}"
! curl -s "https://app.posthog.com/api/projects/{project_id}/events/?event=integration_connected&limit=1000" -H "Authorization: Bearer {personal_api_key}"
! curl -s "https://app.posthog.com/api/projects/{project_id}/events/?event=onboarding_complete&limit=1000" -H "Authorization: Bearer {personal_api_key}"
! curl -s "https://app.posthog.com/api/projects/{project_id}/events/?event=brief_run&limit=1000" -H "Authorization: Bearer {personal_api_key}"
```

Substitute the actual values from `state/posthog.json` before running.

For each response, count:
- `total_users`: number of unique `distinct_id` values in the results
- `total_events`: total number of result items

Also extract:
- From `integration_connected`: how many users chose google, microsoft, or skipped (from the `provider` property)
- From `persona_selected`: which personas were chosen and how often (from the `persona` property)
- From `brief_run`: how many were tier 1 vs tier 2 (from the `tier` property)

---

## Step 3: Output the report

Present the results in this format:

---

## 📊 Usage Brief — [today's date]

### Funnel

| Stage | Users | Drop-off |
|---|---|---|
| Started onboarding | N | — |
| Picked a persona | N | −X% |
| Set news preferences | N | −X% |
| Built job profile | N | −X% |
| Connected integration | N | −X% |
| Completed onboarding | N | −X% |
| Ran a brief | N | −X% |

Drop-off is calculated relative to the previous stage.

### Personas chosen
List each persona and how many users chose it.

### Integrations
- Google: N users
- Microsoft: N users
- Skipped: N users

### Brief tier breakdown
- Tier 1 (web only): N runs
- Tier 2 (email + calendar): N runs

### Observations
2–3 plain-English observations about where users are dropping off or what's working. Flag anything that stands out.

---

If all event counts are zero, say: "No telemetry data yet — users need to pull the latest code and run /morning-brief for events to start appearing."
