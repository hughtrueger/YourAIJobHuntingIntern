# Fly.io Quick Deploy Guide

Deploy the morning brief prewarm worker to Fly.io in ~20 minutes. No credit card needed for the free tier.

---

## Prerequisites

- Fly.io account (free) — [fly.io/sign-up](https://fly.io/sign-up)
- `flyctl` CLI installed
- Docker installed locally (for building the image)
- Your OAuth token already set up (`state/token.json` or `state/ms_token.json`)

---

## Step 1: Install Flyctl

```bash
brew install flyctl
```

Verify:
```bash
flyctl version
```

---

## Step 2: Sign Up and Authenticate

```bash
flyctl auth signup
```

This opens a browser to create your account. You can use GitHub, email, or other providers. **No credit card required** for free tier.

Then authenticate locally:
```bash
flyctl auth login
```

---

## Step 3: Create a Fly App

From your repo directory:

```bash
cd /path/to/YourAIJobHuntingIntern
flyctl launch
```

This guides you through setup:
- **App name?** Enter: `ai-job-intern-prewarm`
- **Select Organization:** Choose the default (your account)
- **Select region:** Pick one close to you (e.g., `sjc` for US West, `ewr` for US East, `iad` for US Central)
- **Would you like to set up a Postgresql database?** Answer: `No`
- **Would you like to set up an Upstash Redis database?** Answer: `No`

This creates a `fly.toml` config file in your repo.

---

## Step 4: Configure Secrets

Store your OAuth token securely in Fly's secret manager.

### For Google:

```bash
flyctl secrets set GOOGLE_TOKEN="$(cat state/token.json)" -a ai-job-intern-prewarm
```

### For Microsoft:

```bash
flyctl secrets set MICROSOFT_TOKEN="$(cat state/ms_token.json)" -a ai-job-intern-prewarm
```

Verify the secret was set:
```bash
flyctl secrets list -a ai-job-intern-prewarm
```

---

## Step 5: Update the Dockerfile

Modify the `Dockerfile` to load the token from the secret at startup:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY fetchers/requirements.txt ./fetchers/requirements.txt
RUN pip install --no-cache-dir -r fetchers/requirements.txt

COPY . .

# Load secrets into files at runtime
RUN mkdir -p state

# This script will be run by the entrypoint
COPY <<EOF /app/entrypoint.sh
#!/bin/bash
set -e

# If Google token is set as secret, write it to state/token.json
if [ -n "$GOOGLE_TOKEN" ]; then
  echo "$GOOGLE_TOKEN" > /app/state/token.json
fi

# If Microsoft token is set as secret, write it to state/ms_token.json
if [ -n "$MICROSOFT_TOKEN" ]; then
  echo "$MICROSOFT_TOKEN" > /app/state/ms_token.json
fi

# Run the prewarm script
exec python3 /app/fetchers/prewarm_morning_brief.py
EOF

chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
```

---

## Step 6: Deploy

```bash
flyctl deploy -a ai-job-intern-prewarm
```

This builds the Docker image locally, pushes it to Fly's registry, and deploys it. You should see:

```
==> Verifying app config
--> Verified app config
==> Building image with Docker
...
==> Pushing image to Fly
...
==> Deploying app
...
```

Once done, verify the app is running:

```bash
flyctl status -a ai-job-intern-prewarm
```

---

## Step 7: Create a Scheduled Job

Fly lets you run the app on a schedule using a machine.

```bash
flyctl machines create \
  --app ai-job-intern-prewarm \
  --schedule cron \
  --cron "0 6 * * 1-5" \
  --image registry.fly.io/ai-job-intern-prewarm:latest
```

This creates a machine that runs at 6am on weekdays (Mon–Fri).

**Cron expressions:**
- `0 6 * * 1-5` = 6am Mon–Fri (default)
- `0 7 * * *` = 7am every day
- `30 6 * * *` = 6:30am every day
- `*/15 * * * *` = every 15 minutes (for testing)

Verify the scheduled machine:

```bash
flyctl machines list -a ai-job-intern-prewarm
```

---

## Step 8: Store the Artifact

The prewarm worker needs to write `morning_report_ready.json` somewhere accessible to your local Claude command.

### Option A: Fly Volume (Recommended)

Attach a persistent volume to store the artifact:

```bash
flyctl volumes create ai_intern_data -a ai-job-intern-prewarm -s 1
```

Mount it in `fly.toml`:

```toml
[[mounts]]
source = "ai_intern_data"
destination = "/app/state"
```

Then redeploy:
```bash
flyctl deploy -a ai-job-intern-prewarm
```

Now the artifact persists across runs.

### Option B: WormholeSh or Similar

Write the artifact to an object storage service and fetch it locally with a simple curl:

In `fetchers/prewarm_morning_brief.py`, after writing the artifact, upload it:

```python
import subprocess

# After writing to state/morning_report_ready.json
subprocess.run([
    'curl', '-F', 'file=@state/morning_report_ready.json',
    'https://your-storage-endpoint.com/upload'
], check=False)
```

Then fetch it locally in the morning-brief command:

```bash
curl -o state/morning_report_ready.json \
  https://your-storage-endpoint.com/latest.json 2>/dev/null || true
```

### Option C: Simple HTTP Endpoint

Add a lightweight Flask app to the Dockerfile that serves the artifact:

```python
from flask import send_file
import json

app = Flask(__name__)

@app.route('/artifact')
def get_artifact():
    with open('state/morning_report_ready.json') as f:
        return send_file(f, mimetype='application/json')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
```

Then fetch it from your local command:

```bash
curl -o state/morning_report_ready.json \
  https://ai-job-intern-prewarm.fly.dev/artifact 2>/dev/null || true
```

---

## Step 9: Test Locally

Run the worker manually to ensure it works:

```bash
flyctl ssh console -a ai-job-intern-prewarm
```

Then inside the machine:

```bash
python3 /app/fetchers/prewarm_morning_brief.py
```

Check the output and verify `state/morning_report_ready.json` is created.

Exit with `exit`.

---

## Step 10: Integrate with Local Command

Update `.claude/commands/morning-brief.md` to fetch the artifact on startup.

If using Fly volume + HTTP endpoint:

```bash
curl -s -o state/morning_report_ready.json \
  https://ai-job-intern-prewarm.fly.dev/artifact 2>/dev/null || true
```

If using Fly private networking (more secure, but requires setup), you can make a direct connection.

---

## Monitoring

### View logs

```bash
flyctl logs -a ai-job-intern-prewarm
```

### Check if the scheduled job ran

```bash
flyctl machines list -a ai-job-intern-prewarm
```

Look for a machine with status `stopped` (it ran and finished) or `running` (currently running).

### View machine details

```bash
flyctl machines show <MACHINE_ID> -a ai-job-intern-prewarm
```

---

## Troubleshooting

### Job never runs

- Verify the cron expression is correct: `flyctl machines list`
- Check if the machine is in the right region
- Restart the scheduled machine: `flyctl machines restart <MACHINE_ID>`

### Token not found

- Verify the secret was set: `flyctl secrets list -a ai-job-intern-prewarm`
- Check the Dockerfile `entrypoint.sh` is writing the token correctly
- View logs: `flyctl logs -a ai-job-intern-prewarm`

### Artifact not persisted

- If using a volume, verify it's mounted: `flyctl volumes list -a ai-job-intern-prewarm`
- If using HTTP, ensure the Flask endpoint is running and accessible

---

## Cost

- **Free tier:** Includes 3 shared-cpu-1x VMs (enough for this use case)
- **Persistent volume:** $0.15 GB/month (1GB = ~$0.15/month for you)
- **Machine runs:** Free on free tier

**Total cost: Free or ~$1/month**

---

## Next: Integration

Once the worker is running:

1. Verify the artifact is generated at 6am.
2. Update your local `morning-brief` command to fetch it.
3. Test by running `/morning-brief` after 6am.
4. The brief should appear in 10–20 seconds instead of 5 minutes.

Done! ✨
