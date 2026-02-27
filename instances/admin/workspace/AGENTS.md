# AGENTS.md — Админ-инстанс

## Стартап

1. Read `SOUL.md`
2. Read `USER.md`
3. Read `memory/YYYY-MM-DD.md`

---

## 🔑 Ключевой принцип

Один корпоративный Anthropic API-ключ хранится **только в quota-proxy**.
Инстансы используют квота-ключи — proxy знает кто есть кто и считает расход.
Все изменения квот — **без рестарта**, через API.

---

## 📊 Управление квотами токенов

### Отчёт по использованию
```bash
cd /infra && bash scripts/quota.sh report
# или за конкретный месяц:
bash scripts/quota.sh report 2026-03
```

### Установить/изменить лимит (мгновенно, без рестарта)
```bash
cd /infra && bash scripts/quota.sh set-limit user-2 500000
bash scripts/quota.sh set-limit user-1 2000000
bash scripts/quota.sh set-limit user-3 0        # 0 = без лимита
```

### Сбросить счётчик (например, вручную в начале месяца)
```bash
cd /infra && bash scripts/quota.sh reset user-2
bash scripts/quota.sh reset user-2 2026-02  # конкретный месяц
```

### Через API напрямую (если нужно из скрипта)
```bash
# Установить лимит
curl -X POST http://quota-proxy:9090/quota/set-limit \
  -H "Authorization: Bearer $QUOTA_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"instance":"user-2","limit":500000}'

# Получить отчёт
curl http://quota-proxy:9090/quota/report \
  -H "Authorization: Bearer $QUOTA_ADMIN_TOKEN"

# Сбросить счётчик
curl -X POST http://quota-proxy:9090/quota/reset \
  -H "Authorization: Bearer $QUOTA_ADMIN_TOKEN" \
  -d '{"instance":"user-2"}'
```

---

## 👤 Управление инстансами

```bash
# Добавить сотрудника
cd /infra && make add-user NAME=x BOT_TOKEN=y FULL_NAME="Имя" TG_ID=z

# Удалить инстанс
cd /infra && make remove-user NAME=x

# Статус / логи
cd /infra && make status
cd /infra && make logs NAME=x

# Перезапустить
cd /infra && make restart NAME=x

# Задеплоить всё
cd /infra && make deploy
```

---

## 🖥️ Сервер

```bash
df -h                              # место на диске
docker stats --no-stream           # нагрузка контейнеров
docker pull ghcr.io/openclaw/openclaw:latest && cd /infra && make deploy  # обновить образ
```

---

## Безопасность

- **НЕ читать** воркспейсы других инстансов без явного запроса владельца
- **НЕ делиться** секретами одного инстанса с другим
- Деструктивные действия — только с подтверждением
