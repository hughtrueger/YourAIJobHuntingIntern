#!/usr/bin/env python3
"""Cloud Run entrypoint that loads secrets and starts the HTTP server"""

import os
import sys

GOOGLE_PROJECT = os.getenv('GOOGLE_CLOUD_PROJECT', '')
GOOGLE_SECRET_NAME = os.getenv('GOOGLE_SECRET_NAME', '')
PREWARM_API_TOKEN_SECRET = os.getenv("PREWARM_API_TOKEN_SECRET", "")
PREWARM_API_TOKEN = os.getenv("PREWARM_API_TOKEN", "")
GOOGLE_TOKEN_INLINE = os.getenv("GOOGLE_TOKEN", "").strip()
MICROSOFT_TOKEN_INLINE = os.getenv("MICROSOFT_TOKEN", "").strip()


def load_secret(project: str, secret_name: str) -> str:
    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()
    version_name = f"projects/{project}/secrets/{secret_name}/versions/latest"
    response = client.access_secret_version(request={"name": version_name})
    return response.payload.data.decode("UTF-8")


if GOOGLE_SECRET_NAME:
    if not GOOGLE_PROJECT:
        print("ERROR: GOOGLE_CLOUD_PROJECT is required when GOOGLE_SECRET_NAME is set", file=sys.stderr)
        sys.exit(1)
    try:
        payload = load_secret(GOOGLE_PROJECT, GOOGLE_SECRET_NAME)
        state_dir = os.getenv('AI_JOB_INTERN_STATE_DIR', '/workspace/state')
        os.makedirs(state_dir, exist_ok=True)
        token_path = f"{state_dir}/token.json"
        with open(token_path, "w") as f:
            f.write(payload)
        os.chmod(token_path, 0o600)
        print("Loaded OAuth token from Secret Manager")
    except Exception as e:
        print(f"ERROR: Could not load OAuth secret: {e}", file=sys.stderr)
        sys.exit(1)

state_dir = os.getenv('AI_JOB_INTERN_STATE_DIR', '/workspace/state')
os.makedirs(state_dir, exist_ok=True)

if GOOGLE_TOKEN_INLINE:
    token_path = f"{state_dir}/token.json"
    with open(token_path, "w") as f:
        f.write(GOOGLE_TOKEN_INLINE)
    os.chmod(token_path, 0o600)

if MICROSOFT_TOKEN_INLINE:
    ms_token_path = f"{state_dir}/ms_token.json"
    with open(ms_token_path, "w") as f:
        f.write(MICROSOFT_TOKEN_INLINE)
    os.chmod(ms_token_path, 0o600)

if PREWARM_API_TOKEN_SECRET:
    if not GOOGLE_PROJECT:
        print("ERROR: GOOGLE_CLOUD_PROJECT is required when PREWARM_API_TOKEN_SECRET is set", file=sys.stderr)
        sys.exit(1)
    try:
        PREWARM_API_TOKEN = load_secret(GOOGLE_PROJECT, PREWARM_API_TOKEN_SECRET).strip()
        os.environ["PREWARM_API_TOKEN"] = PREWARM_API_TOKEN
        print("Loaded prewarm API token from Secret Manager")
    except Exception as e:
        print(f"ERROR: Could not load prewarm API token secret: {e}", file=sys.stderr)
        sys.exit(1)

if not os.getenv("PREWARM_API_TOKEN", "").strip():
    print("ERROR: PREWARM_API_TOKEN (or PREWARM_API_TOKEN_SECRET) must be set", file=sys.stderr)
    sys.exit(1)

# Start the HTTP server
os.chdir('/workspace')
os.execvp("python3", ["python3", "/workspace/fetchers/cloud_run_server.py"])
