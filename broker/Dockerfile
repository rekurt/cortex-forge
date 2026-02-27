FROM python:3.12-slim
RUN useradd -r -s /usr/sbin/nologin app
WORKDIR /app
COPY broker.py .
# curl для healthcheck
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
USER app
CMD ["python3", "-u", "broker.py"]
