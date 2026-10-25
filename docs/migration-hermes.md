# Миграция CortexForge 2.0: полный переход на Hermes Agent (fresh install)

> Статус: план (v3, реализация) · Дата: 2026-10-25
>
> **Стратегия:** полный переход одной новой версией **v2.0.0**. Никакого импорта старых
> данных и никаких бэкап-церемоний — все инстансы стартуют на Hermes с **чистыми конфигами
> и чистыми воркспейсами**. Персоны, скиллы и правила живут в репозитории и пересоздаются
> из шаблонов; старые сессии/память не переносим (объявляем в релизе как breaking change).
>
> **Принцип нулевого легаси:** в v2.0 в живом коде, конфигах, скриптах и документации
> не остаётся ни одной ссылки на OpenClaw / Clawdbot / Moltbot, старые данные и образы
> удаляются при деплое. Исторический `CHANGELOG.md` — единственное исключение.

---

## 1. Цель

CortexForge переезжает с [OpenClaw](https://github.com/openclaw/openclaw) на
[Hermes Agent](https://hermes-agent.nousresearch.com) (NousResearch). Результат:

- все инстансы (admin + пользовательские) работают на Hermes в релизе v2.0.0;
- `grep -ri "openclaw|clawdbot|moltbot"` по репо (без CHANGELOG и этого документа) → **0**;
- ни одного OpenClaw-контейнера/образа/каталога данных на хосте.

## 2. Целевая архитектура (факты по Hermes)

| Что | Значение |
|---|---|
| Образ | `nousresearch/hermes-agent` — запинен `v0.22.5` (не `stable`/`latest`: плавающий тег + auto-update = неконтролируемый дрейф; обновления вручную) |
| Запуск | `command: ["gateway", "run"]`, ENTRYPOINT `/init` (s6-overlay) — не переопределять |
| Данные | том `…:/opt/data` = `~/.hermes`: `.env`, `config.yaml`, `SOUL.md`, `sessions/`, `memories/`, `skills/`, `home/`, `logs/` |
| Права | env `HERMES_UID`/`HERMES_GID` — s6 ремапит внутреннего пользователя; у нас `1000:1000` (как раньше `node`) |
| Dashboard | порт `9119` (`dashboard --host 127.0.0.1 --no-open`); в контейнере с gateway включается `HERMES_DASHBOARD=1` |
| Gateway API | порт `8642` (OpenAI-совместимый API + health) — нужен для dashboard/внешних инструментов |
| Telegram | env `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS` (через запятую) |
| Gateway-токен | env `HERMES_GATEWAY_TOKEN` |
| Модель | `config.yaml` → `model: {provider, default, base_url, api_mode}`; `api_mode: anthropic_messages` для совместимого эндпоинта |
| Переменные | в `config.yaml` работает подстановка `${VAR}` из окружения |
| Рабочая папка | `terminal.cwd`; сэндбокс — `terminal.backend` / `terminal.docker_image` |
| MCP | `mcp_servers.*` (у нас MCP не используются) |

### Схема инстанса

```
instances/<name>/
  hermes_data/          # маунт → /opt/data  (config.yaml, .env, SOUL.md, memories/, …)
  workspace/            # маунт → /opt/data/workspace, terminal.cwd
  .env                  # секреты инстанса (compose env_file)
```

Порты dashboard: `127.0.0.1:18790+N:9119` (схема локальных портов сохранена).

## 3. Инвентаризация легаси (что зачищаем в v2.0)

`grep -ri "openclaw|clawdbot|moltbot"` по репо:

| Файл | Вхождений | Действие |
|---|---|---|
| `docker-compose.yml` | 6 | образ/маунты/конфиг admin → Hermes |
| `instances/Dockerfile.user`, `instances/admin/Dockerfile` | 1+1 | базовый образ → Hermes + те же слои |
| `instances/admin/openclaw.json`, `_template/openclaw.json.template` | — | заменить на `config.yaml` (+удалить старые) |
| `scripts/add-user.sh` | 10 | переписать под hermes_data/config.yaml |
| `scripts/backup.sh` | 1 | exclude → `hermes_data/sessions` |
| `scripts/fix-permissions.sh` | 1 | `openclaw.json` → `hermes_data/config.yaml` |
| `scripts/migrate-instances.py` | 4 | убрать legacy-fallback `openclaw_data/workspace` |
| `scripts/refresh-oauth.py`, `scripts/update-token.py` | 3+3 | **удалить** — OpenClaw-внутренняя OAuth-механика (Claude Max OAuth живёт в CLIProxyAPI) |
| `scripts/autoupdate.sh` | 1 | pull `nousresearch/hermes-agent` |
| `migrations/004,015,016,021,022 + README` | ~24 | удалить (воркспейсы создаются заново из шаблона) |
| `.gitignore` | 5 | новые игноры |
| `CLAUDE.md`, `README.md`, `README.ru.md`, `docs/SECURITY.md` | 9+5+5+1 | ребрендинг |
| `service-agent/skills/qmd/run.py`, `compliance/enrich.py`, `admin-dashboard/KNOWLEDGE.md` | 2+1+5 | пути/упоминания |
| `shared/skills/qmd/SKILL.md`, `yandex-oauth/*` | 1+3 | упоминания |
| `.github/scripts/ai_security_check.py` | 1 | `skip_parts` → `hermes_data`/`.hermes` |
| `quota-proxy/proxy.py` | 1 | упоминание |
| `CHANGELOG.md` | 1 | **не трогаем** |

## 4. Этапы реализации

1. **Образы и compose** — `Dockerfile.user`, `admin/Dockerfile`, `docker-compose.yml` (этот PR).
2. **Шаблоны конфигов** — `_template/hermes_config.yaml.template`, `admin/config.yaml`, схема `.env`.
3. **Скрипты** — `add-user.sh` и остальные по таблице §3.
4. **Зачистка** — `.gitignore`, CI, skills, migrations, `quota-proxy`.
5. **Документация** — README ×2, `CLAUDE.md`, `docs/SECURITY.md`.
6. **Верификация** — grep → 0, `docker compose config` валиден, `VERSION` → 2.0.0.

## 5. Риски

| # | Риск | Митигация |
|---|---|---|
| R1 | Мульти-провайдер (anthropic через quota-proxy + openai whisper) | Проверить, что `model.base_url` + второй провайдер работают одновременно |
| R2 | Потеря старых сессий/памяти | Осознанное решение (fresh install); объявить в релизе |
| R3 | Порт/healthcheck отличаются от OpenClaw | **Решено:** dashboard 9119 / API 8642 (официальный compose Hermes) |
| R4 | `TELEGRAM_ALLOWED_USERS`-семантика отличается от `allowFrom` | **Решено:** числовые ID через запятую, deny-by-default — семантика совпадает |
| R5 | Квоты: Hermes должен слать `ANTHROPIC_API_KEY=$QUOTA_KEY_*` в quota-proxy | Проверить логи quota-proxy после деплоя |
| R6 | Whisper/голосовые: как Hermes конфигурирует аудио-транскрипцию | **Решено:** `voice.stt.provider` в `config.yaml` (`openai` / `local`); добавлено в шаблон |

## 6. Чек-лист верификации (на каждый инстанс после деплоя)

- [ ] Контейнер стартует, gateway под s6 живой (`docker logs`)
- [ ] `hermes status` внутри контейнера — провайдер авторизован
- [ ] Telegram: сообщение боту → ответ
- [ ] Запрос виден в логах quota-proxy, токены считаются в квоту
- [ ] Персона (SOUL.md) применилась
- [ ] Скиллы из workspace/shared подключены, mcporter работает
- [ ] Голосовое → транскрипция
- [ ] Broker: `/send` между инстансами работает
- [ ] Dashboard на `127.0.0.1:18790+N` открывается

## 7. Rollback

Big-bang без импорта данных: откат = **повторный fresh-install на старой версии**.
`git checkout <прошлый тег> && docker compose up -d` поднимает старый код, но старые
`openclaw_data/` удалены — инстансы нужно пересоздать через `make add-user` с теми же
`BOT_TOKEN`/`TG_ID` (поэтому токены ботов должны храниться во внешнем менеджере секретов,
а не только на сервере — бэкапы `.env`-файлы не включают). Квоты в quota-proxy
(SQLite) не зависят от агента и остаются.

## 8. Runbook деплоя на VPS

1. **Остановить cron автообновления (`autoupdate.sh`)** на время переключения
   (`crontab -e` — закомментировать строку `autoupdate.sh`), иначе каждые 5 минут cron
   будет делать `git pull origin master` и откатывать ветку/контейнеры.
2. **Сохранить токены во внешний менеджер секретов ДО любых удалений**: со старого хоста
   забрать `instances/*/.env` и/или `instances/*/openclaw_data/openclaw.json` (`BOT_TOKEN`,
   `allowFrom`). На самом сервере бэкапы `.env` больше не хранят.
3. Обновить код: `git fetch && git checkout master && git pull` (после мерджа `migrate/hermes`).
4. **Мигрировать существующие каталоги инстансов**: выполнить `make bootstrap`
   (`scripts/provision-hermes-data.sh`). Для каждого существующего `instances/<name>/` скрипт
   создаст `hermes_data/`, скопирует `config.yaml` из шаблона (для user-инстансов),
   сгенерирует `hermes_data/.env` (перенеся `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS`
   из старого `TELEGRAM_ALLOW_FROM`, `HERMES_GATEWAY_TOKEN` из `GATEWAY_TOKEN` и строго
   разделив `ANTHROPIC_API_KEY` для admin vs `QUOTA_KEY_<NAME>` для user-инстансов),
   синхронизирует `SOUL.md` и выставит владельца `1000:1000`.
   *(Команда `make add-user` используется только для добавления новых сотрудников, так как
   отклоняет уже существующие каталоги `instances/<name>`).*
5. Перегенерировать `docker-compose.override.yml` для пользовательских сервисов под схему
   Hermes (маунты `hermes_data:/opt/data`, порт `9119`, `HERMES_UID/GID=1000`) либо
   удалить старые каталоги `instances/<user>` + `override` и пересоздать их через
   `make add-user NAME=… BOT_TOKEN=… TG_ID=…` из сохранённых на шаге 2 токенов.
6. Запустить стек: `make deploy` (выполняет `make bootstrap` + `docker compose up -d --build`).
7. Smoke-тест одного инстанса по чек-листу §6 + обязательные проверки на живом контейнере:
   - `docker compose exec assistant-admin id` → проверить, что `uid=1000(hermes)` (s6 ремап);
   - `docker compose exec assistant-admin hermes status` → провайдер авторизован (интерполяция `${VAR}`);
   - `curl -sI http://127.0.0.1:18789` → dashboard отвечает (если `connection refused`,
     проверить bind-адрес dashboard внутри контейнера);
   - сверить фактический путь/формат файлов в `hermes_data/sessions/` с exclude в `backup.sh`.
8. Удалить старые каталоги `instances/*/openclaw_data/` и образы `ghcr.io/openclaw/*`
   (**не использовать** `docker system prune --volumes`, чтобы не снести `cliproxyapi-auths`
   с OAuth-сессией Claude Max). Разморозить cron `autoupdate.sh`.

## 9. Оценка

| Этап | Оценка |
|---|---|
| Реализация в репо (этапы 1–5) | 2–3 дня |
| Деплой и верификация | 0,5 дня |
| **Итого** | **~3 дня** (простой инстансов: часы, а не дни) |

## 10. Открытые вопросы — закрыты (проверено по докам и Docker Hub registry)

- **Q1** OAuth Claude Max: живёт в CLIProxyAPI (volume `cliproxyapi-auths`); инстансы ходят
  через quota-proxy с quota-key. `refresh-oauth.py`/`update-token.py`/`refresh-anthropic-token.sh`/
  `refresh_token.py` удалены как легаси.
- **Q2** Тег образа: существует `stable` и версионные теги; **выбран и запинен `v0.22.5`**
  (плавающий `stable` + auto-update = неконтролируемый дрейф, см. R-ревью).
- **Q3** Голосовые: транскрибируются gateway автоматически; STT — `voice.stt.provider`
  в `config.yaml` (`openai` / `local` faster-whisper). В шаблон добавлен `openai`.
- **Q4** Сессии: `~/.hermes/sessions/` → exclude в `backup.sh` верный.
- **Q5** Порты: dashboard `9119`, gateway API `8642`.
- **Q6** Telegram: `TELEGRAM_BOT_TOKEN` + `TELEGRAM_ALLOWED_USERS` (числовые ID через запятую)
  в `~/.hermes/.env`; deny-by-default — семантика соответствует старому `allowFrom`.
- **Доп. подтверждения по докам:** интерполяция `${VAR}` в config.yaml — документирована
  (Hermes Configuration, «Environment Variable Substitution»); ремап пользователя через
  `HERMES_UID/GID` (s6-overlay stage2) — описан в официальном docker-compose.yml Hermes.
