# Infrastructure & Tooling Requirements

## Quick Summary

You need **one** of the following setups. Most are **free or very cheap** ($0–5/month for this use case).

---

## Option 1: Google Cloud Platform (GCP) — Recommended

**Cost:** $0–1/month (mostly free tier)  
**Setup time:** 30–45 minutes  
**Best for:** Most users; excellent free tier; good docs

### What you need to create/buy

| Item | Cost | Where | What to do |
|---|---|---|---|
| GCP Account | Free | [cloud.google.com](https://cloud.google.com) | Sign up with Google account; add billing (won't be charged for free tier) |
| Cloud Run | Free | Built-in to GCP | Deploy your container |
| Cloud Scheduler | Free | Built-in to GCP | Schedule the 6am job |
| Secret Manager | $0.06/month | Built-in to GCP | Store OAuth tokens |
| Cloud Storage | $0.01/month | Built-in to GCP | Store the morning-brief artifact |

### One-time setup

```bash
# 1. Create a GCP project
gcloud projects create ai-job-intern --name="AI Job Intern"
gcloud config set project ai-job-intern

# 2. Enable APIs
gcloud services enable run.googleapis.com
gcloud services enable cloudscheduler.googleapis.com
gcloud services enable secretmanager.googleapis.com
gcloud services enable storage.googleapis.com
gcloud services enable artifactregistry.googleapis.com

# 3. Create a service account
gcloud iam service-accounts create ai-intern-worker \
  --display-name="AI Intern Worker"

# 4. Grant permissions
gcloud projects add-iam-policy-binding ai-job-intern \
  --member=serviceAccount:ai-intern-worker@ai-job-intern.iam.gserviceaccount.com \
  --role=roles/run.invoker

gcloud projects add-iam-policy-binding ai-job-intern \
  --member=serviceAccount:ai-intern-worker@ai-job-intern.iam.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor

gcloud projects add-iam-policy-binding ai-job-intern \
  --member=serviceAccount:ai-intern-worker@ai-job-intern.iam.gserviceaccount.com \
  --role=roles/storage.objectAdmin
```

### What you install locally

```bash
# Install gcloud CLI
# macOS:
brew install --cask google-cloud-sdk

# Then authenticate
gcloud auth login
```

---

## Option 2: Azure — Good Alternative

**Cost:** $0–2/month (generous free tier)  
**Setup time:** 30–45 minutes  
**Best for:** If you already use Microsoft 365 or Azure

### What you need to create/buy

| Item | Cost | Where | What to do |
|---|---|---|---|
| Azure Account | Free | [portal.azure.com](https://portal.azure.com) | Sign up with Microsoft account; add billing (free tier available) |
| Container Registry | ~$0/month | Built-in to Azure | Store your container image |
| Container Instances | ~$0.50/month | Built-in to Azure | Run the container on a schedule |
| Key Vault | Free | Built-in to Azure | Store OAuth tokens |
| Blob Storage | ~$0/month | Built-in to Azure | Store the morning-brief artifact |

### One-time setup

```bash
# 1. Create a resource group
az group create --name ai-intern-rg --location eastus

# 2. Create a container registry
az acr create --resource-group ai-intern-rg \
  --name aiintern --sku Basic

# 3. Create a managed identity
az identity create --resource-group ai-intern-rg --name ai-intern-worker

# 4. Create a Key Vault
az keyvault create --resource-group ai-intern-rg \
  --name ai-intern-kv --location eastus

# 5. Create a storage account
az storage account create --resource-group ai-intern-rg \
  --name aiinternstorage --sku Standard_LRS
```

### What you install locally

```bash
# Install Azure CLI
# macOS:
brew install azure-cli

# Authenticate
az login
```

---

## Option 3: AWS — More Complex but Very Scalable

**Cost:** $0–2/month (free tier covers this)  
**Setup time:** 45–60 minutes  
**Best for:** If you already use AWS or need maximum scalability

### What you need to create/buy

| Item | Cost | Where | What to do |
|---|---|---|---|
| AWS Account | Free | [aws.amazon.com](https://aws.amazon.com) | Sign up; add billing method |
| ECR (Elastic Container Registry) | ~$0/month | Built-in to AWS | Store your container image |
| ECS (Elastic Container Service) | ~$0.50/month | Built-in to AWS | Run the container on a schedule |
| Lambda | Free option | Built-in to AWS | Alternative to ECS |
| Secrets Manager | $0.40/month | Built-in to AWS | Store OAuth tokens |
| S3 | ~$0.02/month | Built-in to AWS | Store the morning-brief artifact |

### One-time setup

```bash
# 1. Create IAM user (if not using root account)
aws iam create-user --user-name ai-intern-worker

# 2. Attach policies
aws iam attach-user-policy --user-name ai-intern-worker \
  --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser

aws iam attach-user-policy --user-name ai-intern-worker \
  --policy-arn arn:aws:iam::aws:policy/SecretsManagerReadWrite

# 3. Create S3 bucket
aws s3 mb s3://ai-intern-artifacts-$(date +%s)

# 4. Create EventBridge rule for scheduling
# (This is easier done via the AWS console or CloudFormation)
```

### What you install locally

```bash
# Install AWS CLI
# macOS:
brew install awscli

# Configure credentials
aws configure
```

---

## Option 4: Fly.io — Simplest & Cheapest

**Cost:** Free tier + $5/month for persistence (optional)  
**Setup time:** 20–30 minutes  
**Best for:** Minimal ops; single developer; very simple setup

### What you need to create/buy

| Item | Cost | Where | What to do |
|---|---|---|---|
| Fly.io Account | Free | [fly.io](https://fly.io) | Sign up with GitHub or email |
| App deployment | Free (first 3 shared-cpu-1x VMs) | Built-in | Deploy your worker |
| Persistent volume | $5/month (optional) | Built-in | Store artifacts |
| Secrets | Free | Built-in | Store OAuth tokens |

### One-time setup

```bash
# Install flyctl
# macOS:
brew install flyctl

# Authenticate
flyctl auth signup  # or flyctl auth login

# Create app
flyctl apps create ai-job-intern

# Deploy (one command)
flyctl deploy
```

### What you install locally

```bash
brew install flyctl
```

---

## Option 5: Railway — Developer Friendly

**Cost:** $5/month minimum credit (basically free for this use case)  
**Setup time:** 25–35 minutes  
**Best for:** GitHub-connected; very simple UI; pay-as-you-go

### What you need to create/buy

| Item | Cost | Where | What to do |
|---|---|---|---|
| Railway Account | Free | [railway.app](https://railway.app) | Sign up with GitHub |
| Deployment | ~$2/month | Built-in | Run the container |
| Persistent storage | ~$1/month | Built-in | Store artifacts |
| Secrets | Free | Built-in | Store OAuth tokens |

### One-time setup

```bash
# 1. Connect your GitHub repo via Railway dashboard
# 2. Create a Docker service
# 3. Add scheduled job via cron service
# (Mostly done through the UI)
```

### What you install locally

```bash
# No CLI needed; configure everything via web UI
# Or install railway CLI:
npm install -g @railway/cli
```

---

## Option 6: Render — Balanced

**Cost:** $7/month (cheapest paid tier)  
**Setup time:** 25–35 minutes  
**Best for:** GitHub-connected; balanced simplicity and features

### What you need to create/buy

| Item | Cost | Where | What to do |
|---|---|---|---|
| Render Account | Free | [render.com](https://render.com) | Sign up with GitHub |
| Cron job | $7/month | Built-in | Schedule your worker |
| Persistent disk | ~$2/month | Built-in | Store artifacts |
| Secrets | Free | Built-in | Store OAuth tokens |

### One-time setup

```bash
# 1. Connect GitHub repo
# 2. Create a Cron job service
# 3. Point to your Dockerfile
# 4. Set schedule and env variables
# (Mostly UI-based)
```

### What you install locally

```bash
# No special CLI needed
# Just push to GitHub and connect via Render dashboard
```

---

## Comparison Table

| Platform | Cost | Setup time | Learning curve | Free tier | Best for |
|---|---|---|---|---|---|
| GCP | $0–1/mo | 30–45m | Medium | Generous | Most users |
| Azure | $0–2/mo | 30–45m | Medium | Generous | Azure/MS365 users |
| AWS | $0–2/mo | 45–60m | High | Generous but complex | AWS users; scaling |
| Fly.io | Free–5/mo | 20–30m | Low | Very generous | Minimal ops |
| Railway | ~$2/mo | 25–35m | Very low | Limited | Developers; quick setup |
| Render | $7/mo | 25–35m | Low | Limited | Balanced; GitHub-first |

---

## My Recommendation for You

**Go with Fly.io or Railway.** Here's why:

1. **Lowest ops burden** — They're designed for this exact use case (small periodic jobs).
2. **GitHub-first** — You already have the repo there.
3. **Cheapest** — Free or $2–5/month.
4. **Fastest setup** — 20–30 minutes from account creation to running.
5. **No vendor lock-in** — The container image is portable; if you move later, it's easy.

### Next: Fly.io Quickstart

If you want to try Fly.io:

```bash
# 1. Sign up at fly.io
# 2. Install flyctl
brew install flyctl

# 3. Authenticate
flyctl auth signup

# 4. Deploy from your repo directory
flyctl deploy

# 5. Set up scheduled job (via dashboard or CLI)
flyctl machines create \
  --schedule cron \
  --cron "0 6 * * 1-5" \
  --app ai-job-intern \
  --image ai-job-intern-prewarm:latest
```

---

## What to Actually Buy/Create

### Step-by-step minimal checklist:

- [ ] Pick a platform (I suggest **Fly.io**)
- [ ] Create account (free)
- [ ] Install local CLI tool (free)
- [ ] Store your OAuth token securely in the platform's secret manager
- [ ] Build and push the Docker image
- [ ] Create a scheduled job (6am, Mon–Fri)
- [ ] Configure artifact output (to object storage or a database)
- [ ] Test locally once
- [ ] Deploy

**Total cost:** $0–5/month (mostly free)  
**Total setup time:** ~1 hour first time

---

## After Deployment

Once the worker is running:

1. The artifact (`morning_report_ready.json`) is generated at 6am daily.
2. Your local `morning-brief` command fetches it on startup.
3. The brief appears in 10–20 seconds instead of 5 minutes.

Done. The morning brief is now truly autonomous and ready when you open Claude.
