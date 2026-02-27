# 🐒 CortexForge

<p align="center">
  <img src="assets/banner.jpg" alt="CortexForge — isolated AI personas for every team member" width="1200"/>
</p>

> **Language / Язык:** English | [Русский](README.ru.md)

[![Version](https://img.shields.io/github/v/tag/rekurt/cortex-forge?label=version&color=blue)](https://github.com/rekurt/cortex-forge/releases)
[![CI Security](https://github.com/rekurt/cortex-forge/actions/workflows/security.yml/badge.svg)](https://github.com/rekurt/cortex-forge/actions/workflows/security.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Corporate AI assistant infrastructure built on [OpenClaw](https://github.com/openclaw/openclaw).

Each employee gets an **isolated persona**: their own Telegram bot, their own memory, their own character.  
One server. Zero data leakage between users. Full token cost control.

---

## Why CortexForge?

Most teams share a single AI tool — meaning everyone sees the same context, there are no personal settings, and there is no way to track who is spending what. CortexForge solves this:

| Problem | Solution |
|---|---|
| Shared API key, no cost tracking | Per-instance token quotas in SQLite, real-time report |
| All employees in the same context | Complete isolation — each instance has its own memory and personality |
| One-size-fits-all assistant | Each employee gets a custom persona (name, style, skills) |
| API key leaks via prompts | Key is only in `quota-proxy`; instances never see it |
| No audit trail | Full audit log for every API call, quota change, admin action |
| Hard to onboard / offboard | `make add-user` / `make remove-user` — one command each |

---

## Features

- 🔒 **Zero key exposure** — `ANTHROPIC_API_KEY` lives only in `quota-proxy`; instances get a `QUOTA_KEY` with no API access
- 📊 **Token quotas** — per-instance monthly limits with warning (80%) and hard cutoff (100%); change live without restart
- 🧑‍🤝‍🧑 **Isolated personas** — each employee has their own bot, workspace, memory and character (`SOUL.md`)
- 💬 **Inter-instance messaging** — assistants can send messages to each other via `message-broker`
- 🏛️ **Admin instance (Prior)** — dedicated admin bot with full infrastructure access, quota management and Docker control
- 📈 **Resource monitor** — CPU/RAM/disk metrics with configurable alert thresholds
- 🔌 **Service agent** — HTTP API that lets backend services call skills (e.g. compliance checks) as subprocesses
- 🛡️ **Security pipeline** — Semgrep, CodeQL, Trivy, Gitleaks, Hadolint, ShellCheck on every commit
- 🔄 **Release automation** — release-please auto-generates changelogs and GitHub Releases on merge to `master`
- 🐳 **Pure Docker Compose** — no Kubernetes, no Helm; runs on a single Ubuntu VPS

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         Docker Networks                          │
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                       │
│  │  nikita  │  │  alexey  │  │  dmitry  │  ...  corp-internal   │
│  │ own bot  │  │ own bot  │  │ own bot  │                       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                       │
│       │             │             │                              │
│       └─────────────┼─────────────┘                              │
│                     │  ANTHROPIC_BASE_URL=http://quota-proxy     │
│            ┌────────▼─────────┐                                  │
│            │   quota-proxy    │  corp-internal                   │
│            │   :9090          │  corp-admin                      │
│            │                  │  corp-egress ──► internet        │
│            │  ✓ counts tokens │                                  │
│            │  ✓ enforces caps │                                  │
│            │  ✓ audit log     │                                  │
│            └────────┬─────────┘                                  │
│                     │                                            │
│                     ▼  api.anthropic.com                         │
│                                                                  │
│  ┌───────────────────────┐   ┌──────────────────────────────┐   │
│  │  message-broker :8080 │   │  resource-monitor :9091      │   │
│  │  per-instance inbox   │   │  CPU / RAM / disk            │   │
│  │  auth by key          │   │  alerts + HTTP API           │   │
│  └───────────────────────┘   └──────────────────────────────┘   │
│                                                                  │
│  ┌───────────────────────┐   ┌──────────────────────────────┐   │
│  │  service-agent :8090  │   │  ADMIN — Prior 🏛️            │   │
│  │  /v1/run  /v1/skills  │   │  /infra access               │   │
│  │  skills as subprocess │   │  quota / users / docker      │   │
│  └───────────────────────┘   └──────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

### How a request flows

1. Employee sends a message to their Telegram bot
2. OpenClaw inside the container receives it and calls Anthropic API — but `ANTHROPIC_BASE_URL` points to `quota-proxy`, not Anthropic directly
3. `quota-proxy` checks the token quota, updates the counter in SQLite, then forwards the request to `api.anthropic.com` via the `corp-egress` network
4. If the quota is exceeded, `quota-proxy` returns HTTP 429 immediately — no real API call is made

### Docker Networks

| Network | `internal` | Connected to | Purpose |
|---|---|---|---|
| `corp-internal` | ✅ yes | all instances, broker, quota-proxy, monitor | main data bus — no direct internet |
| `corp-admin` | ✅ yes | admin, quota-proxy, monitor | quota management & metrics — no direct internet |
| `corp-egress` | ❌ no | quota-proxy **only** | sole path to `api.anthropic.com` |
| `corp-services` | ❌ no | service-agent | backend service calls |

Instances sit on `corp-internal` only — they cannot reach the internet directly, cannot reach `corp-admin`, and cannot see `service-agent`. `quota-proxy` is the only container that bridges the internal networks and the internet.

---

## Requirements

| Component | Minimum | Recommended |
|---|---|---|
| OS | Ubuntu 22.04 LTS | Ubuntu 24.04 LTS |
| CPU | 2 cores | 4+ cores |
| RAM | 4 GB | 8+ GB (~500 MB per instance) |
| Disk | 20 GB | 50+ GB |
| Docker | 24+ | latest |
| Docker Compose | 2.x | latest |

---

## Quick Start

### 1. Clone and configure global secrets

```bash
git clone https://github.com/rekurt/cortex-forge.git /opt/CortexForge
cd /opt/CortexForge

cp .env.example .env
chmod 600 .env
nano .env
```

The only required fields to get started:

```bash
ANTHROPIC_API_KEY=sk-ant-...          # your Anthropic key
QUOTA_ADMIN_TOKEN=<random-32-chars>   # admin API token for quota-proxy
BROKER_KEY_ADMIN=<random-32-chars>    # admin broker key
MONITOR_ADMIN_TOKEN=<random-32-chars> # resource monitor API token
SERVICE_API_KEY=<random-32-chars>     # service-agent bearer token
```

Generate random tokens:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2. Create the admin instance (Prior)

The admin instance is **mandatory** — `docker-compose.yml` references `instances/admin/.env` at startup. Without it, `docker compose config` will fail.

```bash
mkdir -p instances/admin
cp instances/.env.example instances/admin/.env
chmod 600 instances/admin/.env
nano instances/admin/.env
```

Required fields:

```bash
TELEGRAM_BOT_TOKEN=7000000000:AAxxxx  # Prior's bot token (from @BotFather)
TELEGRAM_ALLOW_FROM=123456789         # your Telegram ID (from @userinfobot)
BROKER_KEY=<same as BROKER_KEY_ADMIN> # must match the global .env value
```

### 3. Validate configuration

```bash
make security-check
```

All items should show ✅. Fix any ❌ before proceeding.

### 4. Add the first employee

```bash
make add-user NAME=alexey \
              BOT_TOKEN=7000000000:AAxxxx \
              FULL_NAME="Alexey Mikhailyuk" \
              TG_ID=123456789
```

This script automatically:
- Creates `instances/alexey/` from the template
- Generates unique `BROKER_KEY` and `QUOTA_KEY`
- Appends keys and a 1M token/month limit to `.env`
- Prints the YAML block to add to `docker-compose.yml`

Then optionally fill in personal credentials:
```bash
nano instances/alexey/.env               # Yandex OAuth, GitLab token, etc.
nano instances/alexey/workspace/SOUL.md  # persona style and character
```

### 5. Launch

```bash
make deploy
make status    # all containers should be Up (healthy)
```

---

## Configuration Reference

### Global `.env`

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | Anthropic API key — only read by `quota-proxy` |
| `QUOTA_ADMIN_TOKEN` | ✅ | Bearer token for quota management API |
| `QUOTA_DEFAULT_MONTHLY` | — | Default token limit per month (default: `1000000`) |
| `BROKER_KEY_ADMIN` | ✅ | Admin broker key |
| `MONITOR_ADMIN_TOKEN` | ✅ | Bearer token for resource-monitor API |
| `SERVICE_API_KEY` | ✅ | Bearer token for service-agent API |
| `ENRICH_PY_PATH` | — | Path to `enrich.py` on host for compliance skill |
| `DADATA_API_KEY` | — | DaData API key (for compliance checks) |
| `ALERT_CPU_PCT` | — | CPU alert threshold % (default: `80`) |
| `ALERT_RAM_PCT` | — | RAM alert threshold % (default: `85`) |
| `ALERT_DISK_PCT` | — | Disk alert threshold % (default: `90`) |

### Per-instance `.env` (`instances/<name>/.env`)

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | Telegram bot token (from @BotFather) |
| `TELEGRAM_ALLOW_FROM` | ✅ | Allowed Telegram ID(s), comma-separated |
| `BROKER_KEY` | ✅ | Instance broker key (auto-generated by `add-user.sh`) |
| `YANDEX_OAUTH_TOKEN` | — | Yandex OAuth for mail / Tracker |
| `YANDEX_CALDAV_URL` | — | Yandex Calendar CalDAV URL |
| `YANDEX_USER` | — | Yandex username |
| `YANDEX_APP_PASSWORD` | — | Yandex app password |
| `GITLAB_TOKEN` | — | GitLab Personal Access Token |

---

## Commands

### Instance Management

| Command | Description |
|---|---|
| `make add-user NAME=x BOT_TOKEN=y TG_ID=z` | Onboard a new employee |
| `make remove-user NAME=x` | Remove instance (archives workspace to `backups/` first) |
| `make deploy` | Start / rebuild all containers |
| `make restart NAME=x` | Restart a single instance |
| `make logs NAME=x` | Tail logs for an instance |
| `make status` | Status of all containers |
| `make backup` | Back up all workspaces to `backups/` |

### Token Quotas

| Command | Description |
|---|---|
| `make quota-report` | Usage report for the current month |
| `make quota-report MONTH=2026-03` | Report for a specific month |
| `make set-limit NAME=x LIMIT=500000` | Set token quota (tokens/month), **no restart needed** |
| `make quota-reset NAME=x` | Reset current-month counter for an instance |

### Monitoring

| Command | Description |
|---|---|
| `make monitor` | Current CPU / RAM / disk metrics |
| `make monitor-alerts` | Active alerts (1h cooldown per alert type) |

### Service Agent

| Command | Description |
|---|---|
| `make service-health` | Service-agent healthcheck |
| `make service-skills` | List available skills with parameters |
| `make add-service NAME=x PORT=y SKILLS=z` | Add a service-agent replica |

### Security

| Command | Description |
|---|---|
| `make security-check` | Verify `.env` permissions, key presence, gitignore status |

---

## Token Quotas

Quotas are enforced by `quota-proxy` before any request reaches Anthropic — even if a model requests more tokens, the proxy blocks it.

```
📊 Token report (2026-02):

  nikita       823,451 / 1,000,000 tokens  ⚠️ warning  ████████████████
               in=641,203  out=182,248  reqs=1,847

  alexey       312,008 /   500,000 tokens  ✅ ok  ██████
               in=241,500  out=70,508   reqs=892

  dmitry        45,100 /   500,000 tokens  ✅ ok  █
               in=38,200   out=6,900    reqs=203
```

- **✅ ok** — below 80%
- **⚠️ warning** — 80–99% — inform the admin
- **❌ exceeded** — 100% — quota-proxy returns HTTP 429; instance tells the user
- Quota resets on the 1st of every month (or manually with `make quota-reset`)
- Limits can be changed **without restart**: `make set-limit NAME=alexey LIMIT=1000000`

---

## Personas

Each instance's behavior is defined by two files in `instances/<name>/workspace/`:

**`SOUL.md`** — how the assistant thinks and communicates:
```markdown
You are a precise, no-nonsense analyst.
Give facts, numbers, structure. No guessing.
If data is missing — say so directly.
```

**`IDENTITY.md`** — name, role, emoji:
```markdown
- Name: Vector
- Emoji: 📐
- Vibe: accurate, dry, reliable
```

**`USER.md`** — context about the employee (role, timezone, preferences):
```markdown
- Name: Alexey
- Role: Backend Lead
- Timezone: UTC+3
```

The admin instance is named **Prior** 🏛️ (the head of a Capuchin monastery — he oversees all instances). Prior is the only instance with access to `/infra`, Docker control and quota management.

---

## Repository Structure

```
CortexForge/
├── quota-proxy/          # sole holder of ANTHROPIC_API_KEY
│   ├── proxy.py          # HTTP proxy + SQLite quota & audit log
│   └── Dockerfile
├── broker/               # message bus between assistants
│   └── broker.py         # in-memory inbox per instance, auth by key
├── resource-monitor/     # CPU/RAM/disk monitoring
│   ├── monitor.py        # metrics collection, alert cooldown, HTTP API
│   └── Dockerfile
├── service-agent/        # HTTP API for backend services
│   ├── server.py         # /v1/run  /v1/skills  /v1/health  /v1/usage
│   ├── skills/
│   │   └── compliance/   # compliance risk check (calls enrich.py)
│   └── Dockerfile
├── instances/
│   ├── admin/            # Prior — sole instance with /infra access
│   │   └── workspace/    # IDENTITY.md, SOUL.md, AGENTS.md
│   ├── _template/        # copied by add-user.sh for every new instance
│   └── .env.example      # instance .env template
├── shared/
│   └── skills/
│       └── corp-messenger/  # skill for sending/reading broker messages
├── scripts/
│   ├── add-user.sh       # onboarding: keys, template copy, docker-compose entry
│   ├── remove-user.sh    # remove instance with workspace archive
│   ├── quota.sh          # quota CLI (report / reset / set-limit)
│   ├── monitor.sh        # monitoring CLI
│   ├── add-service.sh    # add service-agent replica
│   └── backup.sh         # workspace backup (tar.gz per instance)
├── docs/
│   ├── SETUP.md          # server installation guide
│   ├── ONBOARDING.md     # employee onboarding guide
│   ├── PERSONAS.md       # persona creation guide
│   ├── MESSAGING.md      # inter-instance messaging reference
│   ├── SERVICE_AGENT.md  # service-agent API reference
│   └── SECURITY.md       # threat model, CVE table, hardening
├── .github/
│   ├── workflows/
│   │   ├── security.yml        # Semgrep, CodeQL, Trivy, Gitleaks, Hadolint
│   │   ├── release-please.yml  # automated release PRs
│   │   ├── release.yml         # GitHub Releases on tag push
│   │   └── lint-commits.yml    # Conventional Commits enforcement
│   ├── semgrep/
│   │   └── ai-security.yml     # 10 custom AI-specific security rules
│   └── scripts/
│       └── ai_security_check.py  # 8 project-specific security checks
├── CHANGELOG.md
├── VERSION
└── docker-compose.yml
```

---

## CI / CD

GitHub Actions runs on every push and PR:

| Workflow | Jobs | What it checks |
|---|---|---|
| `security.yml` | secrets-scan, sast-python, ai-security, codeql, docker-lint, shellcheck, deps-audit, trivy-images | Full security surface |
| `release-please.yml` | release-please | Opens Release PR, updates `CHANGELOG.md` + `VERSION` |
| `release.yml` | github-release | Creates GitHub Release with notes on `v*.*.*` tag |
| `lint-commits.yml` | pr-title, commits, release-ready | Conventional Commits on PR + commit messages |

**Custom AI security rules** (`ai_security_check.py`) check 8 project-specific patterns:
- Broker inbox access without auth check
- Quota check order (must be before upstream request)
- MCP server auth + timing attack on token compare
- Service-agent skill name injection (subprocess before `ALLOWED_SKILLS` check)
- Hardcoded tokens (6 patterns: Anthropic, GitLab, GitHub, Slack, AWS, Telegram)
- Docker network exposure for sensitive services
- Path traversal in `add-user.sh`
- Real secrets in `.env.example`

Current version: [VERSION](VERSION) · [CHANGELOG](CHANGELOG.md) · [Releases](https://github.com/rekurt/cortex-forge/releases)

---

## Security Highlights

- **API key isolation** — `ANTHROPIC_API_KEY` is never mounted into instance containers; they only get a `QUOTA_KEY` scoped to their own quota
- **Network segmentation** — 4 Docker networks; instances on `corp-internal` (internal: true) cannot reach the internet directly
- **Constant-time token comparison** — all Bearer token checks use `hmac.compare_digest`
- **Rate limiting** — leaky bucket per IP on admin endpoints; message size limits on broker
- **Resource limits** — CPU and RAM caps on every container via `deploy.resources`
- **Non-root containers** — all containers run as unprivileged `app` user with `no-new-privileges:true`
- **Read-only mounts** — skill directories and `enrich.py` mounted `:ro`
- **Audit log** — every API call, quota change and admin action logged to SQLite

Full details: [docs/SECURITY.md](docs/SECURITY.md)

---

## Troubleshooting

### `docker compose config` fails with "env file not found"

`instances/admin/.env` is missing. Create it:
```bash
mkdir -p instances/admin
cp instances/.env.example instances/admin/.env
nano instances/admin/.env
```

### Instance container keeps restarting

```bash
make logs NAME=alexey
```

Common causes:
- Invalid `TELEGRAM_BOT_TOKEN` — check with `curl https://api.telegram.org/bot<token>/getMe`
- Missing required field in `.env`

### quota-proxy can't reach api.anthropic.com

Verify `quota-proxy` is on the `corp-egress` network:
```bash
docker inspect corp-quota | grep -A5 Networks
```

Should include `corp-egress`. If not, run `make deploy` to recreate with the current `docker-compose.yml`.

### Token quota exceeded unexpectedly

```bash
make quota-report
```

Increase the limit without restart:
```bash
make set-limit NAME=alexey LIMIT=2000000
```

### service-agent returns "Skill not in allowed list"

The skills whitelist (`_ALLOWED_SKILLS`) is populated at startup from `SKILLS_DIR`. Restart the service-agent container after adding a new skill:
```bash
docker compose restart assistant-service
```

---

## Documentation

| Document | Description |
|---|---|
| [docs/SETUP.md](docs/SETUP.md) | Server installation (Ubuntu 24.04), systemd, cron backup |
| [docs/ONBOARDING.md](docs/ONBOARDING.md) | Full employee onboarding checklist |
| [docs/PERSONAS.md](docs/PERSONAS.md) | Persona creation guide with examples (SOUL.md / IDENTITY.md) |
| [docs/MESSAGING.md](docs/MESSAGING.md) | Inter-instance messaging API reference |
| [docs/SERVICE_AGENT.md](docs/SERVICE_AGENT.md) | Service-agent HTTP API, adding skills, replication |
| [docs/SECURITY.md](docs/SECURITY.md) | Threat model, 17 patched CVEs, CI/CD pipeline, hardening roadmap |

---

## Contributing

1. Fork the repo and create a branch: `git checkout -b feat/your-feature`
2. Follow [Conventional Commits](https://www.conventionalcommits.org): `feat:`, `fix:`, `docs:`, `ci:`, `security:`
3. Run `make security-check` and `python3 .github/scripts/ai_security_check.py` locally before pushing
4. Open a PR against `master` — CI will run all security checks automatically

---

## License

MIT — see [LICENSE](LICENSE)
