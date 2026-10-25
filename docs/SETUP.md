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
git clone https://github.com/example-org/cortex-forge.git /opt/cortex-forge
cd /opt/cortex-forge
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
| `ANTHROPIC_API_KEY` | API-ключ Anthropic (`sk-ant-…`), обязателен для admin |
| `CLIPROXY_API_KEY` | Ключ авторизации quota-proxy → CLIProxyAPI (`clip-…`) |
| `QUOTA_ADMIN_TOKEN` | Токен управления квотами (мин. 32 символа) |
| `BROKER_KEY_ADMIN` | Ключ admin-инстанса в брокере |
| `BROKER_KEY_SERVICE` | Ключ service-agent в брокере |
| `BROKER_KEY_MONITOR` | Ключ resource-monitor в брокере |
| `MONITOR_ADMIN_TOKEN` | Bearer-токен для API resource-monitor |
| `SERVICE_API_KEY` | Bearer-токен для service-agent (`svc-…`) |

Сгенерировать случайные токены:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
python3 -c "import secrets; print('clip-' + secrets.token_urlsafe(24))"
python3 -c "import secrets; print('svc-' + secrets.token_urlsafe(24))"
```

---

## 4. Admin-инстанс (Admin)

Admin-инстанс обязателен — `docker-compose.yml` требует `instances/admin/.env` и `instances/admin/hermes_data` при старте.

```bash
mkdir -p instances/admin
cp instances/.env.example instances/admin/.env
chmod 600 instances/admin/.env
nano instances/admin/.env
make bootstrap
```

Заполнить в `instances/admin/.env`:

| Ключ | Описание |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен Telegram-бота Admin |
| `TELEGRAM_ALLOWED_USERS` | Telegram ID администратора (числовой, через запятую) |
| `HERMES_GATEWAY_TOKEN` | Токен авторизации Hermes gateway (`secrets.token_urlsafe(32)`) |
| `BROKER_KEY` | Ключ брокера (в compose перекрывается `BROKER_KEY_ADMIN` из корневого `.env`) |

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
- Создаёт `instances/user-2/` (`workspace/` и `hermes_data/`) из шаблона
- Генерирует уникальные `BROKER_KEY`, `QUOTA_KEY` и `HERMES_GATEWAY_TOKEN`
- Добавляет ключи в глобальный `.env` и `instances/user-2/hermes_data/.env`
- Дописывает сервис `assistant-user-2` в `docker-compose.override.yml`

---

## 7. Деплой

```bash
make deploy          # запускает make bootstrap + docker compose up -d --build
```

Проверка:

```bash
make status                  # все контейнеры Up (healthy)
make quota-report            # должно показать инстансы с 0 токенов
make monitor                 # метрики CPU/RAM/диска
curl -sI http://127.0.0.1:18789  # Hermes Dashboard (admin)
```

---

## 8. Автозапуск (systemd)

```bash
cat > /etc/systemd/system/cortexforge.service << 'EOF'
[Unit]
Description=CortexForge Assistant Infrastructure
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/cortex-forge
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now cortexforge.service
```

---

## 9. Автобэкап (cron)

```bash
# Ежедневно в 2:00
echo "0 2 * * * root cd /opt/cortex-forge && make backup >> /var/log/cortexforge-backup.log 2>&1" \
  >> /etc/cron.d/cortexforge
```

Бэкапы сохраняются в `backups/` в виде `.tar.gz`. Рекомендуется настроить синхронизацию на внешнее хранилище.

---

## Обновление

```bash
cd /opt/cortex-forge
git pull origin master
make deploy    # пересобирает изменившиеся образы, перезапускает
```

Воркспейсы сотрудников (`instances/*/workspace/`) не затрагиваются.

---

## Диагностика

```bash
make status                                    # статус всех контейнеров
docker compose logs -f quota-proxy             # логи инфраструктурного сервиса
make logs NAME=admin                           # логи конкретного ассистента (assistant-admin)
make monitor                                   # метрики ресурсов
make monitor-alerts                            # активные алерты
docker compose exec assistant-admin bash       # shell в admin-контейнер
```
