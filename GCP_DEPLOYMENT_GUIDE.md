# GCP Deployment Step-by-Step

Follow these steps in order. Each step builds on the previous one.

---

## Phase 1: GCP Setup (15 minutes)

### Step 1: Create a GCP Project

```bash
# 1. Go to https://console.cloud.google.com/
# 2. Click the project dropdown (top left, next to "Google Cloud")
# 3. Click "NEW PROJECT"
# 4. Name it: "AI Job Intern"
# 5. Click CREATE
# 6. Wait a minute for it to be created

# 7. Verify it's selected (project dropdown should show "AI Job Intern")
```

### Step 2: Install Google Cloud CLI

```bash
# macOS:
brew install --cask google-cloud-sdk

# Initialize it:
gcloud init

# This will open a browser for authentication. Sign in with your Google account.
# When asked "Do you want to configure a default Compute Region and Zone?" → Answer: N
```

### Step 3: Set your project and enable APIs

```bash
# Set the project
gcloud config set project ai-job-intern

# Enable required APIs:
gcloud services enable run.googleapis.com
gcloud services enable cloudscheduler.googleapis.com
gcloud services enable secretmanager.googleapis.com
gcloud services enable artifactregistry.googleapis.com
gcloud services enable compute.googleapis.com

# Verify (should list the services)
gcloud services list --enabled | grep -E "run|scheduler|secret|artifact"
```

### Step 4: Create a Service Account

```bash
# Create the service account
gcloud iam service-accounts create ai-intern-worker \
  --display-name="AI Intern Cloud Worker"

# Verify it was created
gcloud iam service-accounts list
```

### Step 5: Grant permissions to the service account

```bash
# These commands grant the service account permissions to:
# - Run Cloud Run jobs
# - Access secrets
# - Read/write to storage

gcloud projects add-iam-policy-binding ai-job-intern \
  --member=serviceAccount:ai-intern-worker@ai-job-intern.iam.gserviceaccount.com \
  --role=roles/run.invoker

gcloud projects add-iam-policy-binding ai-job-intern \
  --member=serviceAccount:ai-intern-worker@ai-job-intern.iam.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor

gcloud projects add-iam-policy-binding ai-job-intern \
  --member=serviceAccount:ai-intern-worker@ai-job-intern.iam.gserviceaccount.com \
  --role=roles/storage.objectAdmin

# Verify (should list the roles)
gcloud projects get-iam-policy ai-job-intern \
  --flatten="bindings[].members" \
  --filter="bindings.members:ai-intern-worker*"
```

---

## Phase 2: Store Your OAuth Token (5 minutes)

### Step 6: Create a secret for your OAuth token

```bash
# Navigate to your repo where state/token.json lives
cd /path/to/YourAIJobHuntingIntern

# Create the secret in GCP Secret Manager
gcloud secrets create ai-intern-token \
  --replication-policy="automatic" \
  --data-file=state/token.json

# Verify
gcloud secrets list
gcloud secrets describe ai-intern-token
```

### Step 7: Grant the service account access to the secret

```bash
# This allows the Cloud Run worker to read the token
gcloud secrets add-iam-policy-binding ai-intern-token \
  --member=serviceAccount:ai-intern-worker@ai-job-intern.iam.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor

# Verify
gcloud secrets get-iam-policy ai-intern-token
```

---

## Phase 3: Build and Push the Container (10 minutes)

### Step 8: Create a Container Repository

```bash
# This creates a space in GCP to store your Docker images
gcloud artifacts repositories create ai-job-intern-repo \
  --repository-format=docker \
  --location=us-central1 \
  --description="AI Job Intern Worker Images"

# Verify
gcloud artifacts repositories list
```

### Step 9: Configure Docker authentication with GCP

```bash
# This lets your local Docker push images to GCP
gcloud auth configure-docker us-central1-docker.pkg.dev

# When prompted "Add new credentials?", answer: Y
```

### Step 10: Build the Docker image locally

```bash
cd /path/to/YourAIJobHuntingIntern

# Build the image
docker build -t us-central1-docker.pkg.dev/ai-job-intern/ai-job-intern-repo/prewarm:latest .

# Verify
docker images | grep prewarm
```

### Step 11: Push the image to GCP

```bash
# This uploads your container to GCP's registry
docker push us-central1-docker.pkg.dev/ai-job-intern/ai-job-intern-repo/prewarm:latest

# Verify (this may take 1–2 minutes)
gcloud artifacts docker images list us-central1-docker.pkg.dev/ai-job-intern/ai-job-intern-repo
```

---

## Phase 4: Deploy to Cloud Run (10 minutes)

### Step 12: Create the Cloud Run service

```bash
# Deploy the container as a Cloud Run service
gcloud run deploy ai-job-intern-prewarm \
  --image=us-central1-docker.pkg.dev/ai-job-intern/ai-job-intern-repo/prewarm:latest \
  --platform=managed \
  --region=us-central1 \
  --service-account=ai-intern-worker@ai-job-intern.iam.gserviceaccount.com \
  --no-allow-unauthenticated \
  --memory=512Mi \
  --timeout=3600 \
  --set-env-vars="AI_JOB_INTERN_STATE_DIR=/workspace/state"

# This will output a URL like:
# Service URL: https://ai-job-intern-prewarm-abc123.run.app

# Save this URL (you'll need it)
```

### Step 13: Update the Dockerfile to load secrets at runtime

The current Dockerfile needs to load the token from Secret Manager. Update it:

```bash
cd /path/to/YourAIJobHuntingIntern

# Replace the Dockerfile with this version:
cat > Dockerfile << 'EOF'
FROM python:3.11-slim

WORKDIR /workspace

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install Google Cloud SDK (for secret access)
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

RUN curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add - && \
    apt-get update && apt-get install -y google-cloud-secret-manager && \
    rm -rf /var/lib/apt/lists/*

COPY fetchers/requirements.txt ./fetchers/requirements.txt
RUN pip install --no-cache-dir -r fetchers/requirements.txt

COPY . .

# Entrypoint script to load secrets
RUN mkdir -p /workspace/state

COPY <<'ENTRYPOINT' /workspace/entrypoint.sh
#!/bin/bash
set -e

# Load secret from GCP Secret Manager
if [ -n "$GOOGLE_SECRET_NAME" ]; then
  echo "Loading secret from Google Secret Manager..."
  gcloud secrets versions access latest --secret=$GOOGLE_SECRET_NAME > /workspace/state/token.json
  echo "✓ Secret loaded"
fi

# Run the prewarm script
exec python3 /workspace/fetchers/prewarm_morning_brief.py
ENTRYPOINT

chmod +x /workspace/entrypoint.sh

ENTRYPOINT ["/workspace/entrypoint.sh"]
EOF

# Rebuild the image
docker build -t us-central1-docker.pkg.dev/ai-job-intern/ai-job-intern-repo/prewarm:latest .

# Push it again
docker push us-central1-docker.pkg.dev/ai-job-intern/ai-job-intern-repo/prewarm:latest

# Redeploy to Cloud Run (same command as before, but with the new image)
gcloud run deploy ai-job-intern-prewarm \
  --image=us-central1-docker.pkg.dev/ai-job-intern/ai-job-intern-repo/prewarm:latest \
  --platform=managed \
  --region=us-central1 \
  --service-account=ai-intern-worker@ai-job-intern.iam.gserviceaccount.com \
  --no-allow-unauthenticated \
  --memory=512Mi \
  --timeout=3600 \
  --set-env-vars="AI_JOB_INTERN_STATE_DIR=/workspace/state,GOOGLE_SECRET_NAME=ai-intern-token"
```

---

## Phase 5: Set Up Cloud Scheduler (5 minutes)

### Step 14: Create the scheduled job

```bash
# This creates a job that triggers Cloud Run at 6am Mon–Fri
gcloud scheduler jobs create http ai-job-intern-prewarm-6am \
  --schedule="0 6 * * 1-5" \
  --http-method=POST \
  --location=us-central1 \
  --uri=https://ai-job-intern-prewarm-abc123.run.app \
  --oidc-service-account-email=ai-intern-worker@ai-job-intern.iam.gserviceaccount.com \
  --oidc-token-audience=https://ai-job-intern-prewarm-abc123.run.app

# Replace the URL with your actual Cloud Run URL from Step 12
```

**Note:** If you get an error about location, try:
```bash
gcloud scheduler jobs create http ai-job-intern-prewarm-6am \
  --schedule="0 6 * * 1-5" \
  --http-method=POST \
  --location=us-central1 \
  --uri=https://YOUR-CLOUD-RUN-URL \
  --oidc-service-account-email=ai-intern-worker@ai-job-intern.iam.gserviceaccount.com \
  --oidc-token-audience=https://YOUR-CLOUD-RUN-URL
```

### Step 15: Verify the scheduled job

```bash
# List all scheduler jobs
gcloud scheduler jobs list --location=us-central1

# Describe the job
gcloud scheduler jobs describe ai-job-intern-prewarm-6am --location=us-central1

# You should see:
# - Schedule: "0 6 * * 1-5" (6am Mon–Fri)
# - State: ENABLED
```

---

## Phase 6: Store the Artifact in Cloud Storage (5 minutes)

### Step 16: Create a Cloud Storage bucket

```bash
# Create a bucket for the artifact
gsutil mb gs://ai-job-intern-artifacts-$(date +%s)/

# Or use a simpler name:
gsutil mb gs://ai-job-intern-artifacts/

# Verify
gsutil ls
```

### Step 17: Update the prewarm script to upload the artifact

Edit `fetchers/prewarm_morning_brief.py` and add this at the end of the `main()` function (after writing the artifact):

```python
# Upload artifact to GCS
try:
    from google.cloud import storage
    client = storage.Client()
    bucket = client.bucket('ai-job-intern-artifacts')
    blob = bucket.blob('morning_report_ready.json')
    blob.upload_from_filename(str(OUTPUT_FILE))
    print(f"✓ Artifact uploaded to gs://ai-job-intern-artifacts/morning_report_ready.json")
except Exception as e:
    print(f"⚠ Could not upload to GCS: {e}")
```

### Step 18: Rebuild and redeploy

```bash
docker build -t us-central1-docker.pkg.dev/ai-job-intern/ai-job-intern-repo/prewarm:latest .
docker push us-central1-docker.pkg.dev/ai-job-intern/ai-job-intern-repo/prewarm:latest

# Cloud Run automatically picks up the new image
```

---

## Phase 7: Test It (5 minutes)

### Step 19: Test manually

```bash
# Trigger the Cloud Run job manually to test
gcloud run services call ai-job-intern-prewarm \
  --region=us-central1 \
  --region=us-central1

# Or use the HTTP endpoint:
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  https://ai-job-intern-prewarm-abc123.run.app

# Check the logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=ai-job-intern-prewarm" \
  --limit=50 \
  --format=json | tail -20
```

### Step 20: Verify the artifact was created

```bash
# List objects in your bucket
gsutil ls gs://ai-job-intern-artifacts/

# Download and inspect the artifact
gsutil cp gs://ai-job-intern-artifacts/morning_report_ready.json /tmp/artifact.json
cat /tmp/artifact.json | jq .
```

---

## Phase 8: Integrate with Local Command (5 minutes)

### Step 21: Update the morning-brief command

Edit `.claude/commands/morning-brief.md` and add this to **STEP 1** (after "Read state"):

```bash
# Fetch the prewarmed artifact from Cloud Storage
if [ -z "$CI" ]; then
  gsutil -q cp gs://ai-job-intern-artifacts/morning_report_ready.json state/morning_report_ready.json 2>/dev/null || true
fi
```

**Note:** You need `gsutil` installed. If not:
```bash
# Install Google Cloud SDK (if not already installed)
brew install --cask google-cloud-sdk

# Authenticate
gcloud auth application-default login
```

---

## Phase 9: Set Up Monitoring (5 minutes)

### Step 22: View logs

```bash
# View real-time logs
gcloud logging read "resource.type=cloud_run_revision" \
  --limit=50 \
  --follow \
  --format=json

# Or view via the console:
# https://console.cloud.google.com/logs
```

### Step 23: Set up alerts (optional)

```bash
# Create an alert for failed jobs
gcloud alpha monitoring policies create \
  --notification-channels=YOUR_CHANNEL_ID \
  --display-name="AI Job Intern: Prewarm Failed" \
  --condition-display-name="Cloud Run error rate > 0" \
  --condition-threshold-value=0 \
  --condition-threshold-comparison=COMPARISON_GT
```

---

## Troubleshooting

### "Project not found"
```bash
gcloud config set project ai-job-intern
```

### "Permission denied"
```bash
# Make sure the service account has the right roles
gcloud projects get-iam-policy ai-job-intern
```

### "Secret not found"
```bash
# Check if the secret exists
gcloud secrets list

# If not, create it:
gcloud secrets create ai-intern-token --data-file=state/token.json
```

### "Artifact not appearing in bucket"
```bash
# Check if Cloud Run service has permissions
gcloud projects get-iam-policy ai-job-intern | grep ai-intern-worker

# Add storage permissions if missing:
gcloud projects add-iam-policy-binding ai-job-intern \
  --member=serviceAccount:ai-intern-worker@ai-job-intern.iam.gserviceaccount.com \
  --role=roles/storage.objectAdmin
```

### "Job never runs at 6am"
```bash
# Check scheduler logs
gcloud logging read "resource.type=cloud_scheduler_job" --limit=50

# Manually test the trigger:
gcloud scheduler jobs run ai-job-intern-prewarm-6am --location=us-central1
```

---

## Cost Estimate

| Service | Monthly Cost |
|---|---|
| Cloud Run (prewarm job) | ~$0.20–0.50 |
| Cloud Storage (artifact) | ~$0.01 |
| Secret Manager (1 secret) | ~$0.06 |
| Cloud Scheduler (1 job) | ~$0.10 |
| **Total** | **~$0.50/month** |

---

## Success Checklist

- [ ] GCP project created
- [ ] APIs enabled
- [ ] Service account created with permissions
- [ ] OAuth token stored in Secret Manager
- [ ] Docker image built and pushed
- [ ] Cloud Run service deployed
- [ ] Cloud Scheduler job created (6am Mon–Fri)
- [ ] Cloud Storage bucket created
- [ ] Prewarm script uploads artifact
- [ ] Manual test succeeds
- [ ] Artifact appears in bucket
- [ ] morning-brief command fetches from bucket
- [ ] ✨ Ready to launch!

---

## Next: Test It

1. Run manual test (Step 19)
2. Verify artifact in bucket (Step 20)
3. Update morning-brief command (Step 21)
4. Wait until tomorrow morning, or manually trigger the job to test
5. Enjoy instant briefs! 🎉
