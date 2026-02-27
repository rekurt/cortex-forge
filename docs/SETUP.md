# SETUP.md — Установка на чистый сервер

## Требования

- Ubuntu 24.04 LTS
- 2+ CPU, 4+ GB RAM (≈500MB на инстанс)
- Docker 24+
- git

---

## 1. Подготовка сервера

```bash
# Обновление
apt update && apt upgrade -y

# Docker
curl -fsSL https://get.docker.com | bash
usermod -aG docker $USER
newgrp docker

# Проверка
docker --version
docker compose version
```

---

## 2. Клонирование и конфиг

```bash
git clone https://github.com/rekurt/corp-assistant.git /opt/corp-assistant
cd /opt/corp-assistant

cp .env.example .env
nano .env  # Заполнить ANTHROPIC_API_KEY
```

---

## 3. Первый сотрудник

```bash
make add-user NAME=alexey \
              BOT_TOKEN=7000000000:AAxxxx \
              FULL_NAME="Алексей Михайлюк" \
              TG_ID=123456789

# Заполнить личные секреты
nano instances/alexey/.env

make deploy
```

---

## 4. Автозапуск

Docker Compose с `restart: unless-stopped` — контейнеры поднимаются автоматически после ребута.

Для systemd-сервиса:

```bash
cat > /etc/systemd/system/corp-assistant.service << 'EOF'
[Unit]
Description=Corp Assistant
After=docker.service
Requires=docker.service

[Service]
WorkingDirectory=/opt/corp-assistant
ExecStart=docker compose up
ExecStop=docker compose down
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

systemctl enable --now corp-assistant
```

---

## 5. Автобекап (cron)

```bash
# Ежедневно в 2:00
echo "0 2 * * * root cd /opt/corp-assistant && make backup" >> /etc/cron.d/corp-assistant
```
