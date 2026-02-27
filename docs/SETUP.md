# SETUP.md — Установка на чистый сервер

## Требования

| | Минимум | Рекомендуется |
|---|---|---|
| ОС | Ubuntu 22.04 LTS | Ubuntu 24.04 LTS |
| CPU | 2 ядра | 4+ ядра |
| RAM | 4 GB | 8+ GB (~500 MB на инстанс) |
| Диск | 20 GB | 50+ GB |
| Docker | 24+ | latest |

---

## 1. Подготовка сервера

```bash
apt update && apt upgrade -y

# Docker (официальный скрипт)
curl -fsSL https://get.docker.com | bash
usermod -aG docker $USER
newgrp docker

# Проверка
docker --version          # Docker version 27.x
docker compose version    # Docker Compose version 2.x
```

---

## 2. Клонирование репозитория

```bash
git clone https://github.com/example-org/corp-assistant.git /opt/corp-assistant
cd /opt/corp-assistant
```

---

## 3. Глобальная конфигурация

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

Обязательные ключи в `.env`:

| Ключ | Описание |
|---|---|
| `ANTHROPIC_API_KEY` | API-ключ Anthropic (`sk-ant-…`) |
| `QUOTA_ADMIN_TOKEN` | Токен управления квотами (мин. 32 символа) |
| `BROKER_KEY_ADMIN` | Ключ admin-инстанса в брокере |
| `MONITOR_API_KEY` | Bearer-токен для API resource-monitor |
| `SERVICE_API_KEY` | Bearer-токен для service-agent |

Сгенерировать случайные токены:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 4. Admin-инстанс (Admin)

Admin-инстанс обязателен — `docker-compose.yml` требует `instances/admin/.env` при старте.

```bash
mkdir -p instances/admin
cp instances/.env.example instances/admin/.env
chmod 600 instances/admin/.env
nano instances/admin/.env
```

Заполнить в `instances/admin/.env`:

| Ключ | Описание |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен Telegram-бота Adminа (от @BotFather) |
| `TELEGRAM_ALLOW_FROM` | Telegram ID администратора |
| `BROKER_KEY` | То же значение что `BROKER_KEY_ADMIN` в `.env` |

---

## 5. Проверка конфигурации

```bash
make security-check
```

Должно показать ✅ для всех пунктов. Исправь все ❌ перед деплоем.

---

## 6. Первый сотрудник

```bash
make add-user NAME=user-2 \
              BOT_TOKEN=7000000000:AAxxxx \
              FULL_NAME="Example User" \
              TG_ID=123456789

# Заполнить личные секреты (Яндекс, GitLab, etc.)
nano instances/user-2/.env
```

Скрипт автоматически:
- Создаёт `instances/user-2/` из шаблона
- Генерирует уникальные `BROKER_KEY` и `QUOTA_KEY`
- Добавляет ключи в глобальный `.env`
- Выводит блок для `docker-compose.yml`

---

## 7. Деплой

```bash
make deploy
```

Проверка:

```bash
make status          # все контейнеры Up (healthy)
make quota-report    # должно показать инстансы с 0 токенов
make monitor         # метрики CPU/RAM/диска
```

---

## 8. Автозапуск (systemd)

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
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now corp-assistant
```

---

## 9. Автобэкап (cron)

```bash
# Ежедневно в 2:00
echo "0 2 * * * root cd /opt/corp-assistant && make backup >> /var/log/corp-backup.log 2>&1" \
  >> /etc/cron.d/corp-assistant
```

Бэкапы сохраняются в `backups/` в виде `.tar.gz`. Рекомендуется настроить синхронизацию на внешнее хранилище.

---

## Обновление

```bash
cd /opt/corp-assistant
git pull origin master
make deploy    # пересобирает изменившиеся образы, перезапускает
```

Воркспейсы сотрудников (`instances/*/workspace/`) не затрагиваются.

---

## Диагностика

```bash
make status                          # статус всех контейнеров
make logs NAME=quota-proxy           # логи конкретного сервиса
make monitor                         # метрики ресурсов
make monitor-alerts                  # активные алерты
docker compose exec corp-admin bash  # shell в admin-контейнер
```
