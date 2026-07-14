FROM python:3.11-slim

WORKDIR /workspace

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    AI_JOB_INTERN_STATE_DIR=/workspace/state

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY fetchers/requirements.txt ./fetchers/requirements.txt
RUN pip install --no-cache-dir -r fetchers/requirements.txt && \
    pip install --no-cache-dir google-cloud-secret-manager

COPY . .

RUN mkdir -p /workspace/state && \
    chmod +x /workspace/entrypoint.py

ENTRYPOINT ["python3", "/workspace/entrypoint.py"]
