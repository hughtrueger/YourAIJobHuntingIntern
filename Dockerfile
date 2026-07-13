FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY fetchers/requirements.txt ./fetchers/requirements.txt
RUN pip install --no-cache-dir -r fetchers/requirements.txt

COPY . .

CMD ["python3", "fetchers/prewarm_morning_brief.py"]
