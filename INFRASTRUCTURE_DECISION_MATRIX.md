# Infrastructure Decision Matrix

At a glance: which platform to choose based on your situation.

---

## The Cost/Effort Matrix

```
                LOW COST                          HIGH COST
        ┌─────────────────────────────────────────────────────┐
  LOW   │                                                     │
EFFORT  │   ✓ Fly.io (Free/5)   │   Railway ($2/mo)         │
        │   ✓ Render ($7/mo)    │   Heroku-like              │
        │                        │                           │
        ├─────────────────────────────────────────────────────┤
  HIGH  │   GCP/Azure/AWS        │   Premium services        │
EFFORT  │   (0–2/month)          │   (expensive enterprise)   │
        │   BUT: steeper         │                           │
        │   learning curve       │                           │
        └─────────────────────────────────────────────────────┘
```

---

## Quick Decision Tree

**1. First question: Do you want cloud deployment?**

```
YES → Do you already use a cloud platform?
    ├─ GCP? → Use Cloud Run (DEPLOYMENT_CLOUD_WORKER.md)
    ├─ Azure? → Use Container Instances (DEPLOYMENT_CLOUD_WORKER.md)
    ├─ AWS? → Use ECS/Fargate (DEPLOYMENT_CLOUD_WORKER.md)
    └─ None → Use Fly.io or Railway (simplest path, see below)

NO → Use local macOS launchd scheduler (no infrastructure needed)
```

**2. If cloud: Pick based on comfort**

```
├─ Want the simplest setup? (no prior cloud experience)
│  └─ Use Fly.io (20–30 min, $0–5/month) ← RECOMMENDED
│
├─ Familiar with Node.js / npm?
│  └─ Use Railway ($2/month, UI-based)
│
├─ Comfortable with CLI tools and learning?
│  └─ Use GCP Cloud Run (30–45 min, $0–1/month)
│
└─ Heavy AWS user?
   └─ Use ECS/Fargate (45–60 min, $0–2/month)
```

---

## Platform Comparison: Practical Reality

### Fly.io ✓✓✓ RECOMMENDED

**Setup time:** 20–30 minutes  
**Monthly cost:** Free (with optional $1–5/month for persistence)  
**Learning curve:** Very low — mostly UI-driven

**Pros:**
- Simplest possible setup for a Python container job
- Free tier includes 3 shared-cpu VMs
- Persistent volume storage is cheap ($0.15/GB/month)
- No CLI knowledge required (everything web-based)
- Deploy one command: `flyctl deploy`
- Scheduled jobs are a single command

**Cons:**
- Less "enterprise" feel than GCP/Azure/AWS
- Smaller ecosystem of add-ons

**Best for:** First-time cloud users; solo developers; minimal ops

**Try it:** See `DEPLOY_FLY_IO.md`

---

### Railway

**Setup time:** 25–35 minutes  
**Monthly cost:** ~$2–5/month (pay-as-you-go, minimum $5 credit)  
**Learning curve:** Very low — all web UI

**Pros:**
- Even simpler UI than Fly.io
- GitHub integration (just connect repo, auto-deploy)
- No credit card for free tier
- Good for quick prototypes

**Cons:**
- Minimum $5/month spend (even if you use less)
- Fewer advanced features

**Best for:** Developers who like GitHub-first workflows

**Try it:** Sign up at railway.app, connect your repo, create a Docker service

---

### GCP Cloud Run

**Setup time:** 30–45 minutes  
**Monthly cost:** $0–1/month  
**Learning curve:** Medium — CLI tools + cloud concepts

**Pros:**
- Excellent free tier ($0.40/month for this use case)
- Very reliable; used by enterprises
- Great docs and community support
- Easy to scale if needed later
- Cost control is transparent

**Cons:**
- More moving parts (Cloud Scheduler, Secret Manager, Storage)
- CLI setup is required
- Steeper learning curve than Fly.io

**Best for:** Users who want a "real" cloud platform; GCP users

**Try it:** See `DEPLOYMENT_CLOUD_WORKER.md` (GCP section)

---

### Azure Container Instances

**Setup time:** 30–45 minutes  
**Monthly cost:** $0–2/month  
**Learning curve:** Medium — similar to GCP

**Pros:**
- Generous free tier
- Good for Microsoft 365 / Outlook integration (you're using Microsoft auth)
- Container Instances are simple and quick to set up
- Azure Key Vault is excellent for secrets

**Cons:**
- More steps than Fly.io
- CLI knowledge needed

**Best for:** Microsoft Outlook users; Azure ecosystem users

**Try it:** See `DEPLOYMENT_CLOUD_WORKER.md` (Azure section)

---

### AWS (ECS + Fargate)

**Setup time:** 45–60 minutes  
**Monthly cost:** $0–2/month (free tier covers)  
**Learning curve:** High — many moving parts

**Pros:**
- If you already use AWS, integrates seamlessly
- Maximum flexibility and scalability
- Free tier is very generous

**Cons:**
- Many services to wire together (Lambda, ECS, Secrets Manager, S3, EventBridge)
- Steeper learning curve
- Easy to accidentally spend money if misconfigured

**Best for:** AWS-heavy shops; maximum scalability needs

**Try it:** See `DEPLOYMENT_CLOUD_WORKER.md` (AWS section)

---

## "I Just Want It to Work" Path

**Minimum viable setup (Fly.io, ~20 minutes):**

```bash
# 1. Sign up
# Go to fly.io/sign-up → create account

# 2. Install CLI
brew install flyctl

# 3. Authenticate
flyctl auth signup

# 4. Navigate to repo
cd /path/to/YourAIJobHuntingIntern

# 5. Launch
flyctl launch --name ai-job-intern-prewarm

# 6. Add your token
flyctl secrets set GOOGLE_TOKEN="$(cat state/token.json)" -a ai-job-intern-prewarm

# 7. Deploy
flyctl deploy

# 8. Schedule
flyctl machines create \
  --app ai-job-intern-prewarm \
  --schedule cron \
  --cron "0 6 * * 1-5" \
  --image registry.fly.io/ai-job-intern-prewarm:latest

# Done. The brief is now automated and always ready. ✨
```

That's it. 20 minutes. $0/month.

---

## What Actually Costs Money

| Item | Platform | Cost |
|---|---|---|
| Nothing | Fly.io (default) | $0/month |
| Persistent storage | Fly.io volume | $0.15/month (1GB) |
| Scheduled container | Railway minimum | $5/month |
| Nothing | GCP (within free tier) | $0/month |
| Token storage | GCP Secret Manager | $0.06/month |
| Artifact storage | GCP Cloud Storage | $0.01/month |
| Nothing | Azure (within free tier) | $0/month |
| Nothing | AWS (within free tier) | $0/month |

**Reality:** For this specific use case (one 30s job per day), everything is essentially free.

---

## Local Alternative (No Cloud)

**If you want zero cloud/infrastructure:**

- Use the existing macOS `launchd` scheduler
- It's already set up in `launchd/com.aijobintern.plist`
- Runs at 6am and generates `state/morning_report_ready.json` locally
- Cost: $0
- Setup: 5 minutes (just update the path in the plist)
- Trade-off: Depends on your Mac being awake at 6am

**Setup:**
```bash
# 1. Edit the plist and replace /PATH/TO/ with your actual path
open launchd/com.aijobintern.plist

# 2. Install it
cp launchd/com.aijobintern.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.aijobintern.plist

# 3. Test
launchctl list | grep com.aijobintern
```

This is the "lightest" option if you're always home.

---

## Recommendation Summary

### ✓ For most people: **Fly.io**
- Easiest setup
- Free
- Always reliable
- No vendor lock-in
- Takes ~20 minutes

### ✓ For AWS users: **ECS + Fargate**
- Integrates with your AWS account
- Slightly more complex
- Same cost

### ✓ For GCP/Azure users: **Cloud Run / Container Instances**
- Native to your platform
- Slightly more complex
- Same cost

### ✓ For minimal overhead: **Local macOS launchd**
- $0
- 5 minutes setup
- Trade-off: Mac must be on at 6am

---

## Next Steps

**Pick your path:**

1. **Cloud (recommended):** Go to `DEPLOY_FLY_IO.md` and follow the 20-minute quickstart
2. **Local only:** Update `launchd/com.aijobintern.plist` with your path and load it
3. **Undecided:** Ask me to help you choose based on your setup

**Then:**

1. Test that the prewarm artifact is generated
2. Verify the local command fetches it quickly
3. Enjoy the instant morning brief! ✨

---

## One-Sentence Versions

- **Fly.io:** Copy-paste a few commands, your job runs at 6am forever, costs $0–5/month
- **Local:** Update one config file, runs at 6am if your Mac is on, costs $0
- **GCP/Azure/AWS:** More powerful but more complex; same cost
