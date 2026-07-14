# Cloud Worker Deployment Guide

This guide shows how to deploy the morning brief prewarm worker to a cloud platform, so your morning brief is ready the moment you open Claude—without depending on your Mac being awake or online.

---

## Overview

The prewarm worker:
- runs at 6am every weekday (Mon–Fri)
- fetches fresh Gmail job alerts and calendar events
- builds a compact `morning_report_ready.json` artifact
- stores it persistently
- keeps only derived data, never full mailbox content

The `morning-brief` command checks for this artifact first. If it's fresh and ready, the brief launches in 10–20 seconds. If missing or stale, it falls back to a slower path or requests a refresh.

---

## Architecture: What Gets Stored Where

```
User's Machine         Cloud Platform              Secret Store
================       ==============              ============
state/                 Docker container            OAuth tokens
├─ profile.json ◄──────→ fetchers/                 (encrypted,
├─ token.json ◄─────┐   ├─ fetch_gmail.py         managed)
└─ calendar/*        │   ├─ fetch_calendar.py      
                     │   └─ prewarm_morning_brief.py
                     │
                  Object Storage / Volume
                     │
                  ├─ morning_report_ready.json
                  ├─ gmail_jobs.json
                  └─ calendar.json
```

**Key security principle:** Tokens never leave the cloud platform. They live in a secret manager. Only derived artifacts (compact JSON with no PII) are stored persistently.

---

## Prerequisites

1. **OAuth tokens already set up locally**
   - During onboarding, users connect Google or Microsoft.
   - This creates `state/token.json` (Google) or `state/ms_token.json` (Microsoft).
   - These tokens are already scoped to read-only: `gmail.readonly`, `calendar.readonly`.

2. **A cloud platform account**
   - GCP, Azure, AWS, Fly.io, Railway, Render, or similar.
   - Any platform that supports:
     - scheduled container tasks
     - secret management
     - persistent storage or object storage
     - read-only access to external APIs

3. **Docker installed locally** (for building and testing the image)

---

## Step 1: Prepare the Container Image

### Build the image locally

```bash
cd /path/to/YourAIJobHuntingIntern
docker build -t ai-job-intern-prewarm:latest .
```

### Test locally

If you have `state/token.json` or `state/ms_token.json` locally:

```bash
docker run --rm \
  -v "$PWD/state:/app/state" \
  ai-job-intern-prewarm:latest
```

This should print:
```
Wrote prewarm artifact to state/morning_report_ready.json
Ready=True summary={'job_listing_count': N, 'calendar_event_count': M, ...}
```

---

## Step 2: Store Credentials Securely

### For Google Cloud Platform

1. **Create a Secret Manager secret:**
   ```bash
   gcloud secrets create ai-intern-token --data-file=state/token.json
   ```

2. **Grant the Cloud Run service account access:**
   ```bash
   gcloud secrets add-iam-policy-binding ai-intern-token \
     --member=serviceAccount:<SERVICE-ACCOUNT-EMAIL> \
     --role=roles/secretmanager.secretAccessor
   ```

3. **In your Cloud Run container, fetch the secret at startup:**
   ```python
   from google.cloud import secretmanager
   
   client = secretmanager.SecretManagerServiceClient()
   response = client.access_secret_version(
       request={"name": "projects/PROJECT_ID/secrets/ai-intern-token/versions/latest"}
   )
   token = response.payload.data.decode('utf-8')
   
   with open('state/token.json', 'w') as f:
       f.write(token)
   ```

### For Azure

1. **Store the token in Azure Key Vault:**
   ```bash
   az keyvault secret set --vault-name <VAULT-NAME> --name ai-intern-token --file state/token.json
   ```

2. **Grant the managed identity access:**
   ```bash
   az keyvault set-policy --name <VAULT-NAME> \
     --object-id <MANAGED-IDENTITY-PRINCIPAL-ID> \
     --secret-permissions get
   ```

3. **In your container:**
   ```python
   from azure.identity import DefaultAzureCredential
   from azure.keyvault.secrets import SecretClient
   
   credential = DefaultAzureCredential()
   client = SecretClient(vault_url="https://<VAULT-NAME>.vault.azure.net/", credential=credential)
   token = client.get_secret("ai-intern-token")
   
   with open('state/token.json', 'w') as f:
       f.write(token.value)
   ```

### For AWS Secrets Manager

1. **Store the token:**
   ```bash
   aws secretsmanager create-secret --name ai-intern-token --secret-string file://state/token.json
   ```

2. **Grant the task IAM role access:**
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": "secretsmanager:GetSecretValue",
         "Resource": "arn:aws:secretsmanager:REGION:ACCOUNT:secret:ai-intern-token-*"
       }
     ]
   }
   ```

3. **In your container:**
   ```python
   import boto3
   import json
   
   client = boto3.client('secretsmanager', region_name='REGION')
   response = client.get_secret_value(SecretId='ai-intern-token')
   token = response['SecretString']
   
   with open('state/token.json', 'w') as f:
       f.write(token)
   ```

---

## Step 3: Deploy to Cloud Run (GCP example)

### Push the image to Container Registry

```bash
docker tag ai-job-intern-prewarm:latest gcr.io/PROJECT_ID/ai-job-intern-prewarm:latest
docker push gcr.io/PROJECT_ID/ai-job-intern-prewarm:latest
```

### Create the Cloud Run service

```bash
gcloud run deploy ai-job-intern-prewarm \
  --image gcr.io/PROJECT_ID/ai-job-intern-prewarm:latest \
  --platform managed \
  --region us-central1 \
  --no-allow-unauthenticated \
  --service-account <SERVICE-ACCOUNT-EMAIL> \
  --memory 512Mi \
  --timeout 3600
```

### Schedule the job with Cloud Scheduler

```bash
gcloud scheduler jobs create http ai-job-intern-prewarm-6am \
  --schedule "0 6 * * 1-5" \
  --location us-central1 \
  --http-method POST \
  --uri https://<CLOUD-RUN-URL>/prewarm \
  --oidc-service-account-email <SERVICE-ACCOUNT-EMAIL> \
  --oidc-token-audience https://<CLOUD-RUN-URL>
```

---

## Step 4: Store the Artifact

The prewarm worker writes `state/morning_report_ready.json`. You need persistent storage so the local command can fetch it.

### Option A: Cloud Storage (simplest)

The worker uploads to a GCS bucket after building the artifact:

```python
from google.cloud import storage

client = storage.Client()
bucket = client.bucket('ai-intern-artifacts')
blob = bucket.blob('morning_report_ready.json')
blob.upload_from_filename('state/morning_report_ready.json')
```

Then, the local `morning-brief` command fetches it:

```bash
gsutil cp gs://ai-intern-artifacts/morning_report_ready.json state/morning_report_ready.json 2>/dev/null || true
```

### Option B: Shared Database

The worker inserts the artifact into a small database (e.g. Firestore, PostgreSQL):

```python
from google.cloud import firestore

db = firestore.Client()
db.collection('ai_intern').document('current_brief').set({
    'artifact': artifact_dict,
    'generated_at': datetime.utcnow(),
})
```

The local command fetches it via a lightweight API or the SDK.

### Option C: Shared Network Volume

If using Kubernetes or a managed container orchestrator with shared storage, mount a persistent volume to both the worker and any retrieval endpoints.

---

## Step 5: Integrate with the Local Command

The `morning-brief` command now checks for the prewarmed artifact before building from scratch.

### Fetch the artifact (example for GCS)

Add this to `.claude/commands/morning-brief.md` before STEP 1:

```bash
! gsutil -q cp gs://ai-intern-artifacts/morning_report_ready.json state/morning_report_ready.json 2>/dev/null || true
```

This silently fetches the artifact if available. If not, the command continues normally.

---

## Security Checklist

- [ ] OAuth tokens are stored in a managed secret store, never in config files or repos.
- [ ] The cloud worker has read-only scopes: `gmail.readonly`, `calendar.readonly`.
- [ ] The worker never stores full email bodies or raw calendar data—only derived summaries.
- [ ] Only `morning_report_ready.json` (a compact JSON artifact) is persisted long-term.
- [ ] All communication is over HTTPS.
- [ ] The cloud container image is scanned for vulnerabilities before deployment.
- [ ] IAM roles are scoped to the minimum necessary permissions.
- [ ] Secret rotation is configured (automatic refresh every 90 days recommended).
- [ ] Audit logs track secret access and artifact reads.
- [ ] The user can disconnect or revoke access at any time.

---

## Operational Monitoring

### Logs

- Cloud Run logs: `gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=ai-job-intern-prewarm" --limit 50`
- Cloud Scheduler logs: `gcloud logging read "resource.type=cloud_scheduler_job AND resource.labels.job_id=ai-job-intern-prewarm-6am" --limit 50`

### Alerts

Set up alerts for:
- Job fails (non-zero exit code)
- No artifact written in the last 24 hours
- Secret access denied or expired
- Unusual API usage patterns

---

## Troubleshooting

### Token expired

If `fetch_gmail.py` or `fetch_calendar.py` fails with "token expired", refresh the token locally and re-upload:

```bash
python3 fetchers/setup.py --provider google
gcloud secrets versions add ai-intern-token --data-file=state/token.json
```

### No artifact is written

Check the logs:
```bash
gcloud logging read "resource.type=cloud_run_revision" --limit 50
```

Look for errors in `prewarm_morning_brief.py` or the fetcher scripts.

### Artifact is stale

Verify the Cloud Scheduler job ran on schedule. If not, check scheduler logs and permissions.

---

## Cost Estimate

- **Cloud Run invocation**: ~$0.20–0.40 per month (1 daily job, ~30–40s execution)
- **Cloud Storage** (if used): ~$0.01 per month (negligible)
- **Cloud Scheduler**: Free (1 job included per month, standard rate ~$0.10 per job after)
- **Secret Manager**: ~$0.06 per month (1 secret)

**Total: ~$0.30–0.50 per month** — negligible for most users.

---

## Customization

### Change the schedule

Modify the Cloud Scheduler cron expression:
- `0 6 * * 1-5` = 6am Mon–Fri (default)
- `0 7 * * *` = 7am every day
- `*/15 * * * *` = every 15 minutes

### Change the artifact location

Update `OUTPUT_FILE` in `fetchers/prewarm_morning_brief.py` to point to a network path, object storage URL, or database endpoint.

### Add more data to the artifact

Edit `build_artifact()` in `prewarm_morning_brief.py` to include additional summaries (e.g., industry news, company research).

---

## Next Steps

1. Choose your cloud platform (GCP, Azure, AWS, etc.).
2. Follow the deployment steps for your platform.
3. Test locally with a Docker container.
4. Set up secret management and schedule the job.
5. Integrate the artifact fetch into the local `morning-brief` command.
6. Monitor logs and set up alerts.
