# Исправление багов и повышение надёжности CortexForge

## Overview

Анализ кодовой базы выявил ряд реальных функциональных багов и уязвимостей, из-за которых система работает непредсказуемо. План фиксирует их по приоритету — от критических (сломана функциональность) до средних (security, надёжность).

## Context

- Files involved:
  - `resource-monitor/monitor.py`
  - `resource-monitor/Dockerfile`
  - `quota-proxy/proxy.py`
  - `service-agent/server.py`
  - `broker/broker.py`
  - `scripts/add-user.sh`
  - `scripts/quota.sh`
- Related patterns: stdlib-only Python, non-root Docker users, hmac.compare_digest() для токенов
- Dependencies: нет внешних

## Development Approach

- **Testing approach**: Regular (код сначала, ручное тестирование через docker compose)
- Каждый таск — один компонент, не смешиваем файлы между тасками
- После каждого таска пересобираем и проверяем поведение вручную
- **CRITICAL: каждый таск завершается проверкой docker compose ps и логов**

## Implementation Steps

### Task 1: Починить парсинг квоты в resource-monitor (квота-алерты никогда не срабатывают)

Баг: monitor.py в функции check_alerts() итерируется по quota.items() как будто там {instance: {used, limit}}, но quota-proxy реально возвращает {"month": "...", "usage": [...], "limits": {...}}. Алерты по квоте физически никогда не срабатывают.

**Files:**
- Modify: `resource-monitor/monitor.py`

- [x] найти функцию check_alerts() в monitor.py, найти блок обработки quota
- [x] исправить парсинг: итерироваться по quota.get("usage", []), брать instance/total_tokens/limit из каждого элемента
- [x] убедиться что структура ответа quota-proxy совпадает с тем что ожидает monitor (сверить proxy.py endpoint /report)
- [x] docker compose build resource-monitor && docker compose restart resource-monitor
- [x] проверить что в логах monitor нет ошибок парсинга

### Task 2: Исправить timing-attack уязвимости в monitor и service-agent

Баг: monitor.py и service-agent/server.py сравнивают токены через == вместо hmac.compare_digest(). В quota-proxy это уже исправлено (proxy.py:281), но в двух других компонентах — нет.

**Files:**
- Modify: `resource-monitor/monitor.py`
- Modify: `service-agent/server.py`

- [x] в monitor.py найти все места сравнения auth-токена через ==, заменить на hmac.compare_digest()
- [x] в service-agent/server.py то же самое
- [x] добавить import hmac если отсутствует
- [x] docker compose build resource-monitor service-agent && docker compose restart resource-monitor service-agent
- [x] проверить что аутентификация всё ещё работает (curl с правильным и неправильным токеном)

### Task 3: Добавить non-root пользователя в resource-monitor Dockerfile

Баг: resource-monitor единственный компонент без non-root пользователя — запускается от root. Все остальные Dockerfiles уже имеют non-root. Нарушает принцип наименьших привилегий.

**Files:**
- Modify: `resource-monitor/Dockerfile`

- [x] добавить создание пользователя app в Dockerfile по образцу broker/Dockerfile
- [x] добавить USER app перед CMD
- [x] убедиться что /data volume доступен пользователю app (chown)
- [x] docker compose build resource-monitor && docker compose restart resource-monitor
- [x] docker compose ps — убедиться что контейнер запустился нормально

### Task 4: Изолировать переменные окружения в service-agent skills

Баг: в server.py скиллы запускаются с env={**os.environ}, то есть наследуют ВСЕ переменные окружения включая DADATA_API_KEY и другие секреты. Скилл может прочитать чужие ключи.

**Files:**
- Modify: `service-agent/server.py`

- [x] найти место запуска subprocess с env в server.py
- [x] определить какие переменные нужны скиллам (PATH, HOME, и специфичные для скилла)
- [x] реализовать whitelist: передавать только безопасные переменные окружения
- [x] скилл-специфичные переменные брать из манифеста skills.json (если нужны)
- [x] проверить что существующие скиллы (compliance/) продолжают работать

### Task 5: Починить утечку памяти в _active_alerts у monitor

Баг: _active_alerts в monitor.py хранит сработавшие алерты вечно — никогда не очищается. После первого срабатывания алерт «замораживается» навсегда в памяти. Для долгоживущего процесса это медленная утечка.

**Files:**
- Modify: `resource-monitor/monitor.py`

- [x] найти _active_alerts и логику cooldown в monitor.py
- [x] добавить очистку записей у которых истёк cooldown (текущее_время - время_срабатывания > ALERT_COOLDOWN_SEC)
- [x] убедиться что очистка происходит при каждом вызове check_alerts()
- [x] проверить что повторный алерт после cooldown снова срабатывает

### Task 6: Исправить вызов _cleanup() в broker — вызывать при отправке, не только при получении

Баг: в broker.py функция _cleanup() вызывается только при /inbox (чтение). Если клиент никогда не читает inbox, но постоянно отправляет, старые сообщения не удаляются. При MAX_INBOX=100 новые сообщения выталкивают старые без очистки по времени.

**Files:**
- Modify: `broker/broker.py`

- [x] в обработчике /send найти место добавления сообщения в очередь
- [x] добавить вызов _cleanup() перед добавлением нового сообщения
- [x] проверить что после перезапуска broker при активной пересылке сообщений очередь не растёт бесконечно

### Task 7: Добавить логирование тихих ошибок в quota-proxy и monitor

Баг: несколько мест молча игнорируют ошибки без логирования — quota-proxy при парсинге ответа Anthropic, monitor при недоступности Docker socket. Это делает отладку невозможной.

**Files:**
- Modify: `quota-proxy/proxy.py`
- Modify: `resource-monitor/monitor.py`

- [x] в proxy.py найти except блок при парсинге usage из ответа upstream — добавить print/log предупреждения
- [x] в monitor.py найти обработку ошибок Docker socket — добавить явное логирование с деталями исключения
- [x] убедиться что логи пишутся в stdout (flush=True) для docker logs

### Task 8: Исправить shell-скрипты — robustness и безопасность

Баг: add-user.sh не обрабатывает пустой glob при копировании workspace. quota.sh интерполирует $INSTANCE напрямую в JSON без экранирования.

**Files:**
- Modify: `scripts/add-user.sh`
- Modify: `scripts/quota.sh`

- [ ] в add-user.sh добавить проверку что директория шаблона существует перед cp
- [ ] добавить nullglob или явную проверку что glob нашёл файлы
- [ ] в quota.sh использовать printf или jq для безопасного формирования JSON вместо прямой интерполяции $INSTANCE
- [ ] проверить что make add-user работает с обычными и граничными именами

### Task 9: Проверка и финализация

- [ ] docker compose down && docker compose up -d --build — полный пересборка
- [ ] docker compose ps — все контейнеры Running
- [ ] проверить логи каждого компонента: docker compose logs quota-proxy broker resource-monitor service-agent
- [ ] make monitor — убедиться что метрики отдаются
- [ ] make service-health — убедиться что service-agent работает
- [ ] make quota-report — убедиться что отчёт формируется корректно
- [ ] обновить CLAUDE.md если изменились паттерны безопасности
- [ ] переместить план в docs/plans/completed/
