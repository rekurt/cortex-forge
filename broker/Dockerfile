FROM python:3.12-slim
WORKDIR /app
COPY broker.py .
# curl для healthcheck
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
CMD ["python3", "-u", "broker.py"]
