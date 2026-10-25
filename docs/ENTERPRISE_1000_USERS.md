# Enterprise Architecture: Масштабирование CortexForge до 1000 пользователей

Данный документ описывает архитектуру, механизмы провижининга, управление квотами, шину сообщений, мониторинг и нагрузочное тестирование **CortexForge Enterprise** в конфигурации до **1 000 изолированных инстансов Hermes Agent**.

---

## 1. Обзор архитектуры 1000-User Enterprise

При масштабировании с десятков до 1 000 сотрудников основные узкие места классической Docker Compose-инсталляции лежат в четырёх плоскостях:
1. **Сеть и iptables / bridge-лимиты Linux** — помещение 1 000 контейнеров в один Docker bridge приводит к деградации ARP/broadcast-трафика и исчерпанию лимита портов Linux bridge (по умолчанию 1023 интерфейса на мост).
2. **Конкурентный доступ к SQLite и блокировки HTTP-серверов** — однопоточный `HTTPServer` блокируется на медленных запросах или длинных SSE-стримах, а частые `DELETE` при очистке очередей вызывают `SQLITE_BUSY`.
3. **Онбординг и ротация ключей** — перезапуск центральных сервисов (`quota-proxy`, `message-broker`) при добавлении каждого нового сотрудника недопустим при парке в 1 000 ботов.
4. **Агрегация телеметрии и отчётов** — выгрузка полного списка из 1 000 инстансов в одном HTTP-ответе или запуск 1 000 процессов `docker inspect` в цикле перегружает демон Docker и админ-панель.

### Ключевые архитектурные решения Enterprise-режима

| Подсистема | Решение для 1 000 пользователей |
|---|---|
| **Сетевое шардирование** | Разбиение парка на профили и изолированные bridge-сети `shard-0` .. `shard-9` (по умолчанию по 100 инстансов на шард) |
| **Массовый онбординг** | Утилита `scripts/bulk-users.py` (`make bulk-import`, `make fleet-status`) с `fcntl.flock`, защитой от симлинков и авто-назначением портов |
| **Многопоточные серверы** | Все core-компоненты (`quota-proxy`, `broker`, `service-agent`, `resource-monitor`) переведены на `ThreadingHTTPServer` |
| **Хранилище SQLite** | Режим `WAL`, `synchronous=NORMAL`, `busy_timeout=10000`, `journal_size_limit=1MB`, композитные индексы и `threading.RLock` |
| **Hot-Reload ключей** | Персистентные таблицы `quota_keys` и `broker_keys` в SQLite + API регистрации без рестарта контейнеров |
| **Потоковый учёт SSE** | Построчный парсинг `text/event-stream` (`SSEUsageParser`) в `quota-proxy` на лету без буферизации ответа в памяти |
| **Иерархия квот** | Индивидуальные лимиты инстансов + групповые лимиты департаментов (`department_limits`) |
| **Пагинация и фильтрация** | Поддержка `limit`, `offset`, `department`, `status`, `search`, `sort` во всех отчётных API |

---

## 2. Шардирование парка контейнеров (`shard-0` .. `shard-9`)

### Профили Docker Compose и сетевая топология

При импорте 1 000 пользователей через `scripts/bulk-users.py` каждый сервис `assistant-<name>` в `docker-compose.override.yml` автоматически привязывается к своему шарду:
- Индекс шарда вычисляется как `shard_id = user_index // shard_size` (при `shard_size = 100` создаются шарды `shard-0` .. `shard-9`).
- Каждому инстансу назначаются Compose-профили:
  - `shard-<N>` — для пошардового управления запуском, обновлением и раскладкой по нодам;
  - `all-users` — для одновременного управления всем парком на мощном хосте.
- Для каждого шарда генерируется собственная изолированная сеть `corp-shard-<N>` (`driver: bridge`, `internal: true`), а также метка `corp.assistant.shard: shard-<N>` и `corp.assistant.department: <dept>`.

Пример сгенерированного блока сервиса в `docker-compose.override.yml`:

```yaml
services:
  assistant-user-0001:
    build:
      context: .
      dockerfile: instances/Dockerfile.user
    image: cortex-forge-user:latest
    container_name: corp-user-0001
    restart: unless-stopped
    profiles:
      - "shard-0"
      - "all-users"
    env_file:
      - instances/user-0001/.env
    volumes:
      - ./instances/user-0001/hermes_data:/opt/data
      - ./instances/user-0001/workspace:/opt/data/workspace
      - ./shared/skills:/shared/skills
      - ./shared/docs:/shared/docs
      - ./shared/compliance-data:/shared/compliance-data:ro
    environment:
      - ANTHROPIC_API_KEY=${QUOTA_KEY_USER-0001}
      - OPENAI_API_KEY=${OPENAI_API_KEY:-}
      - SERVICE_API_KEY=${SERVICE_API_KEY}
      - BROKER_URL=http://message-broker:8080
      - BROKER_KEY=${BROKER_KEY_USER-0001}
      - HERMES_UID=1000
      - HERMES_GID=1000
      - HERMES_DASHBOARD=1
    ports:
      - "127.0.0.1:18790:9119"
    networks:
      - corp-internal
      - corp-outbound
      - corp-shard-0
    security_opt:
      - no-new-privileges:true
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 1G
    depends_on:
      quota-proxy:
        condition: service_healthy
      message-broker:
        condition: service_healthy
    labels:
      corp.assistant.role: personal
      corp.assistant.user: user-0001
      corp.assistant.shard: shard-0
      corp.assistant.department: engineering

networks:
  corp-shard-0:
    driver: bridge
    internal: true
```

### Команды пошардового управления

```bash
# Запустить только шард 0 (первые 100 пользователей)
docker compose --profile shard-0 up -d

# Перезапустить шард 3
docker compose --profile shard-3 restart

# Запустить все шарды сразу
docker compose --profile all-users up -d
```

В `scripts/sync-instances.sh` проверка живости 1 000 контейнеров оптимизирована за $O(1)$ через единый вызов `docker ps -a --format '{{.Names}}={{.State}}'`, а подъём остановившихся сервисов выполняется батчами по 50 (`xargs -n 50 docker compose up -d`), чтобы не вызывать пиковую перегрузку демона Docker.

---

## 3. Массовый провижининг (`scripts/bulk-users.py`)

CLI-инструмент `scripts/bulk-users.py` автоматизирует онбординг, экспорт и аудит целостности до 1 000+ инстансов без внешних зависимостей (только Python 3.12+ stdlib).

### Поддерживаемые форматы входных файлов

1. **CSV (`users.csv`)**:
   ```csv
   name,bot_token,full_name,tg_id,department,quota_limit,ui_port
   user-0001,7100000001:AAHxxxx1,Иван Петров,100000001,engineering,2000000,18790
   user-0002,7100000002:AAHxxxx2,Мария Сидорова,100000002,sales,1000000,
   ```
2. **JSON (`users.json`)** — список объектов или `{"users": [...]}` с теми же полями (`department`, `quota_limit`, `ui_port` опциональны).

### Гарантии безопасности и атомарности в `bulk-users.py`

- **Строгая валидация полей**:
  - `name`: `^[a-z][a-z0-9_-]{1,31}$` (имя `admin` зарезервировано);
  - `bot_token`: `^[0-9]+:[A-Za-z0-9_-]+$`;
  - `tg_id`: `^[0-9]+(?:,[0-9]+)*$` (обязателен — защита от пустого allowlist);
  - `department`: `^[A-Za-z0-9_.-]{1,64}$`;
  - `ui_port`: диапазон `1024..65535` (исключая админский порт `18789`), автоматическое предотвращение коллизий с уже занятыми портами в `docker-compose.override.yml`.
- **Защита от symlink-атак**: перед чтением шаблона и записью любых файлов проверяется отсутствие символических ссылок (`_verify_tree_no_symlinks`, `_ensure_not_symlink`, `follow_symlinks=False`).
- **Атомарная запись файлов**: функция `_safe_write_file` создаёт временный файл через `tempfile.mkstemp` в целевой директории, выставляет права (`0600` для `.env`, `config.yaml`, `SOUL.md`), вызывает `os.fsync()` и атомарно заменяет целевой файл через `os.replace()`.
- **Межпроцессная блокировка `.env`**: дозапись ключей `BROKER_KEY_*`, `QUOTA_KEY_*`, `QUOTA_LIMIT_*` в корневой `.env` защищена эксклюзивным файловым локом `fcntl.flock(..., fcntl.LOCK_EX)` на `.env.bulk.lock`.
- **Идемпотентность**: уже существующие каталоги `instances/<name>` безопасно пропускаются (`skipped`) без перезаписи пользовательских данных.

### Команды CLI и Makefile

```bash
# Предварительная проверка манифеста без записи на диск (dry-run)
python3 scripts/bulk-users.py import --file users.csv --shard-size 100 --dry-run

# Массовый импорт через Makefile
make bulk-import FILE=users.csv SHARD_SIZE=100

# Проверка состояния парка, распределения по шардам и отсутствия коллизий портов
make fleet-status

# Экспорт манифеста парка (без секретов — 0644, с секретами — 0600)
python3 scripts/bulk-users.py export --output fleet.json
python3 scripts/bulk-users.py export --output fleet-secrets.json --include-secrets
```

---

## 4. Горячая регистрация ключей в `quota-proxy` и `broker`

Для подключения новых ботов или ротации скомпрометированных токенов на лету (без рестарта `corp-quota` и `corp-broker`) оба сервиса хранят ключи в SQLite и синхронизируют их с in-memory хэш-таблицами под защитой `threading.RLock`.

### Хранение и сравнение ключей

- В памяти и в SQLite (`quota_keys`, `broker_keys`) хранятся **только SHA-256 хэши** ключей.
- Проверка авторизации выполняется за константное время через `hmac.compare_digest()` по снимку списка ключей, взятому под `_keys_lock`, что исключает timing-атаки и `RuntimeError: dictionary changed size during iteration` при параллельной регистрации.
- При ротации ключа старый хэш того же инстанса автоматически удаляется из памяти и перезаписывается в SQLite (`ON CONFLICT(instance) DO UPDATE`).

### API `quota-proxy` (порт `9090`, авторизация `Bearer <QUOTA_ADMIN_TOKEN>`)

1. **`POST /quota/register-key`** — зарегистрировать или обновить ключ инстанса, департамент и индивидуальный лимит:
   ```bash
   curl -s -X POST http://127.0.0.1:9090/quota/register-key \
     -H "Authorization: Bearer ${QUOTA_ADMIN_TOKEN}" \
     -H "Content-Type: application/json" \
     -d '{
       "instance": "user-0001",
       "quota_key": "quota-user-0001-xxxx",
       "department": "engineering",
       "limit": 2000000
     }'
   ```
   *(Также поддерживается передача готового SHA-256 хэша в поле `"key_hash"` вместо `"quota_key"`).*

2. **`POST /quota/reload-keys`** — перечитать ключи из переменных окружения и таблицы `quota_keys`:
   ```bash
   curl -s -X POST http://127.0.0.1:9090/quota/reload-keys \
     -H "Authorization: Bearer ${QUOTA_ADMIN_TOKEN}"
   ```

### API `message-broker` (порт `8080`, авторизация `Bearer <BROKER_KEY_ADMIN>`)

1. **`POST /admin/register-key`** — горячая регистрация ключа инстанса в шине сообщений:
   ```bash
   curl -s -X POST http://message-broker:8080/admin/register-key \
     -H "Authorization: Bearer ${BROKER_KEY_ADMIN}" \
     -H "Content-Type: application/json" \
     -d '{
       "instance": "user-0001",
       "broker_key": "brk-xxxx"
     }'
   ```

2. **`POST /admin/reload-keys`** — горячая перезагрузка таблицы `broker_keys` и env:
   ```bash
   curl -s -X POST http://message-broker:8080/admin/reload-keys \
     -H "Authorization: Bearer ${BROKER_KEY_ADMIN}"
   ```

---

## 5. Потоковый учёт SSE-стримов (`SSEUsageParser`)

В базовой версии `quota-proxy` учитывал токены только для обычных JSON-ответов, пропуская `Content-Type: text/event-stream`. В Enterprise-режиме реализован потоковый перехват и учёт токенов для SSE без задержки первого токена (TTFT) и без буферизации всего потока в RAM.

### Как работает `_stream_sse` и `SSEUsageParser`

1. При получении от upstream заголовка `Content-Type: text/event-stream` метод `_proxy()` передаёт соединение в `_stream_sse()`.
2. Чтение из upstream выполняется построчно (`upstream_resp.readline()`) и немедленно пересылается клиенту (`self.wfile.write(line)` + `self.wfile.flush()`).
3. Каждая строка передаётся в `SSEUsageParser.feed_line(line)`:
   - **Формат Anthropic SSE**:
     - из события `message_start` извлекается `message.usage.input_tokens` (и начальный `output_tokens`);
     - из финального события `message_delta` извлекается итоговый `usage.output_tokens` (и обновлённый `input_tokens`, если передан).
   - **Формат OpenAI / совместимых прокси**:
     - из чанков `data: {...}` с полем `usage` извлекаются `prompt_tokens` / `input_tokens` и `completion_tokens` / `output_tokens`.
4. В блоке `finally` (даже если клиент оборвал соединение `BrokenPipeError` / `ConnectionResetError` до конца генерации) накопленные `input_tokens` и `output_tokens` атомарно записываются в таблицу `usage` через `_record_usage_log()`.

---

## 6. Департаментные квоты (`department_limits`)

Помимо индивидуальных лимитов каждого сотрудника, `quota-proxy` поддерживает квотирование на уровне подразделений (`engineering`, `sales`, `legal`, `support` и т.д.).

### Логика проверки (`_check_quota`)

Перед отправкой запроса в upstream проверяются два условия:
1. **Индивидуальная квота инстанса**: если `usage[instance] >= limits[instance]`, возвращается `HTTP 429` (`quota_exceeded`).
2. **Квота департамента**: определяется департамент инстанса (из таблицы `quota_keys` или переменной `QUOTA_DEPT_<NAME>`). Если для департамента задан лимит `department_limits[dept] > 0` и суммарный расход всех инстансов этого департамента за текущий месяц достиг лимита, запрос блокируется с `HTTP 429` (`Квота департамента <dept> исчерпана`).

### Установка лимита департамента

```bash
curl -s -X POST http://127.0.0.1:9090/quota/set-department-limit \
  -H "Authorization: Bearer ${QUOTA_ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "department": "engineering",
    "limit": 50000000
  }'
```

В отчёте `GET /quota/report` возвращается секция `departments` со сводкой по каждому подразделению (`input_tokens`, `output_tokens`, `total_tokens`, `requests`, `instances`, `limit`, `used_pct`, `status`).

---

## 7. Шина сообщений, Service-Agent и пагинация API

При 1 000 активных ботов все внутренние API поддерживают пагинацию, фильтрацию и защиту от шумных соседей (noisy neighbor).

### Шина сообщений (`broker/broker.py`)

- **Приоритеты и TTL**: `POST /send` и `POST /broadcast` принимают `priority` (`low`, `normal`, `high`, `urgent`) и `ttl_sec` (индивидуальное время жизни сообщения в секундах).
- **Широковещательная рассылка (`POST /broadcast`)**:
  - Доступна только `admin`;
  - Поле `to` принимает `"*"` (все зарегистрированные инстансы кроме отправителя), массив `["user-1", "user-2"]` или строку через запятую;
  - Вставка выполняется в одной SQLite-транзакции через `conn.executemany()` с удержанием лимита `MAX_INBOX` на каждого получателя.
- **Троттлинг очистки (`_purge_expired`)**: удаление просроченных сообщений выполняется не чаще раза в `BROKER_PURGE_INTERVAL_SEC` (по умолчанию 5 секунд) под неблокирующим `_purge_lock`, что устраняет write-contention при сотнях параллельных чтений `/inbox`.
- **Пагинация и `peek`-режим**:
  - `GET /inbox?limit=50&offset=0&since_id=1200&peek=true` — чтение сообщений с курсором `since_id`; при `peek=true` сообщения не помечаются как `delivered=1`.
  - `GET /inbox/all?limit=100&offset=0` — пагинированная сводка размеров очередей по всем инстансам для `admin`.

### Пагинация и фильтрация остальных сервисов

| Сервис | Эндпоинт | Параметры запроса |
|---|---|---|
| `quota-proxy` | `GET /quota/report` | `month=YYYY-MM`, `department=<dept>`, `status=ok\|warning\|exceeded`, `limit=N`, `offset=M` |
| `service-agent` | `GET /v1/usage` | `caller=<instance>`, `skill=<skill_id>`, `limit=N`, `offset=M` |
| `resource-monitor` | `GET /metrics` | `search=<substr>`, `sort=cpu_pct\|mem_pct\|name`, `order=asc\|desc`, `limit=N`, `offset=M` |
| `resource-monitor` | `GET /alerts`, `/alerts/active` | `instance=<name>`, `limit=N`, `offset=M` |

В `service-agent` дополнительно введён per-caller rate limiter (`CallerRateLimiter`, переменная `SKILL_RATE_LIMIT`, по умолчанию `30` вызовов/мин на одного вызывающего бота) и настраиваемый пул `MAX_CONCURRENT_SKILLS`.

---

## 8. Нагрузочное тестирование (`make benchmark-1k`)

Цель `make benchmark-1k` в `Makefile` запускает нагрузочный бенчмарк для проверки способности `quota-proxy`, `message-broker`, `service-agent` и `resource-monitor` обслуживать 1 000 конкурентных инстансов.

### Запуск тестов и бенчмарка

```bash
# Прогон всех Enterprise unit/integration тестов (160 тестов, включая конкурентные стресс-тесты)
python3 -m unittest discover tests/ -v

# Отдельные тестовые наборы Enterprise-компонентов:
python3 -m unittest tests/test_quota_enterprise.py -v
python3 -m unittest tests/test_broker_enterprise.py -v
python3 -m unittest tests/test_bulk_provisioning.py -v
python3 -m unittest tests/test_service_monitor_enterprise.py -v

# Запуск нагрузочного бенчмарка на 1000 пользователей (при наличии скрипта benchmark-1000-users.py)
make benchmark-1k
```

### Проверяемые инварианты под нагрузкой

1. **Отсутствие `SQLITE_BUSY` и гонок данных**: параллельная регистрация сотен ключей и одновременный учёт токенов/сообщений из 50–100 потоков дают точное совпадение счётчиков в SQLite.
2. **Линейная масштабируемость памяти**: потоковый `SSEUsageParser` обрабатывает длинные ответы константным объёмом памяти (`O(1)` по числу чанков).
3. **Изоляция сбоев**: превышение квоты одного департамента или rate-limit одного бота (`SKILL_RATE_LIMIT`) не влияет на задержки остальных инстансов.
