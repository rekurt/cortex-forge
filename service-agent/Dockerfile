FROM python:3.12-slim

# System deps for enrich.py (curl for HTTP calls to DaData/Egrul APIs)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY server.py .
COPY skills/ ./skills/

RUN mkdir -p /data
VOLUME /data

ENV SERVICE_PORT=8090
ENV SKILL_TIMEOUT=120
ENV MAX_CONCURRENT_TASKS=5

CMD ["python3", "-u", "server.py"]
