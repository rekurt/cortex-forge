FROM ghcr.io/openclaw/openclaw:latest

USER root

# Устанавливаем docker CLI + make + python3 для скриптов
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg make python3 lsb-release && \
    install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg && \
    chmod a+r /etc/apt/keyrings/docker.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/debian $(lsb_release -cs) stable" > \
        /etc/apt/sources.list.d/docker.list && \
    apt-get update -qq && \
    apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin && \
    rm -rf /var/lib/apt/lists/*

USER node
