#!/usr/bin/env python3
"""Cloud Run entrypoint that loads secrets and starts the HTTP server"""

import os
import sys

# Load secret if needed
GOOGLE_PROJECT = os.getenv('GOOGLE_CLOUD_PROJECT', '')
GOOGLE_SECRET_NAME = os.getenv('GOOGLE_SECRET_NAME', '')

if GOOGLE_PROJECT and GOOGLE_SECRET_NAME:
    try:
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceClient()
        secret_name = f"projects/{GOOGLE_PROJECT}/secrets/{GOOGLE_SECRET_NAME}/versions/latest"
        response = client.access_secret_version(request={"name": secret_name})
        payload = response.payload.data.decode("UTF-8")
        
        state_dir = os.getenv('AI_JOB_INTERN_STATE_DIR', '/workspace/state')
        os.makedirs(state_dir, exist_ok=True)
        
        with open(f"{state_dir}/token.json", "w") as f:
            f.write(payload)
        print("✓ Secret loaded from Secret Manager")
    except Exception as e:
        print(f"⚠ Could not load secret: {e}")

# Start the HTTP server
os.chdir('/workspace')
os.execvp("python3", ["python3", "/workspace/fetchers/cloud_run_server.py"])
