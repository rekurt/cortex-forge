FROM python:3.14-slim
RUN useradd -r -s /usr/sbin/nologin app
WORKDIR /app
COPY broker.py .
# curl для healthcheck
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /data && chown app:app /data
VOLUME /data
USER app
CMD ["python3", "-u", "broker.py"]
