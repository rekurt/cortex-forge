# 🤖 corp-assistant

> **Language / Язык:** English | [Русский](README.ru.md)

Corporate AI assistant infrastructure built on [OpenClaw](https://github.com/openclaw/openclaw).

Each employee gets an **isolated persona** — their own Telegram bot, their own memory, their own character. One server, zero data leakage between users, full token cost control.

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
│            ┌────────▼────────┐                                   │
│            │  quota-proxy    │  corp-internal + corp-admin       │
│            │  :9090          │  + corp-egress (→ internet)       │
│            │  token counter  │                                   │
│            └────────┬────────┘                                   │
│                     │                                            │
│                     ▼  api.anthropic.com  (via corp-egress)      │
│                                                                  │
│  ┌──────────────────────────┐  ┌──────────────────────────────┐  │
│  │  message-broker :8080    │  │  resource-monitor :9091      │  │
│  │  per-instance inbox      │  │  CPU/RAM/disk + alerts       │  │
│  │  auth by key             │  │  HTTP API /metrics /alerts   │  │
│  └──────────────────────────┘  └──────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────┐  ┌──────────────────────────────┐  │
│  │  service-agent :8090     │  │  ADMIN (Prior) 🏛️            │  │
│  │  HTTP API for backends   │  │  sole /infra access          │  │
│  │  skills as subprocesses  │  │  quota / users / docker      │  │
│  └──────────────────────────┘  └──────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### Docker Networks

| Network | `internal` | Connected to | Purpose |
|---|---|---|---|
| `corp-internal` | ✅ yes | all instances, broker, quota-proxy, monitor | main data bus |
| `corp-admin` | ✅ yes | admin, quota-proxy, monitor | quota management & metrics |
| `corp-egress` | ❌ no | quota-proxy only | egress to `api.anthropic.com` |
| `corp-services` | ❌ no | service-agent | calls from backend services |

The `internal: true` flag on `corp-internal` and `corp-admin` means **no direct internet access** for instances — all LLM traffic is routed through `quota-proxy`, which is the only container on the non-internal `corp-egress` network.

---

## Quick Start

```bash
git clone https://github.com/rekurt/corp-assistant.git /opt/corp-assistant
cd /opt/corp-assistant

# 1. Global secrets (API key, management tokens)
cp .env.example .env
nano .env  # ANTHROPIC_API_KEY, QUOTA_ADMIN_TOKEN, BROKER_KEY_ADMIN

# 2. Admin instance secrets (required — docker-compose fails without this file)
mkdir -p instances/admin
cp instances/.env.example instances/admin/.env
nano instances/admin/.env  # TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOW_FROM, BROKER_KEY

# 3. Validate config
make security-check

# 4. Add the first employee
make add-user NAME=alexey BOT_TOKEN=7xxx FULL_NAME="Alexey Mikhailyuk" TG_ID=123456789
nano instances/alexey/.env               # personal tokens (Yandex, GitLab, …)
nano instances/alexey/workspace/SOUL.md  # configure the persona

# 5. Launch
make deploy
```

---

## Commands

### Instance Management

| Command | Description |
|---|---|
| `make add-user NAME=x BOT_TOKEN=y TG_ID=z` | Onboard a new employee |
| `make remove-user NAME=x` | Remove instance (archives workspace first) |
| `make deploy` | Start / rebuild all containers |
| `make restart NAME=x` | Restart a single instance |
| `make logs NAME=x` | Tail logs for an instance |
| `make status` | Status of all containers |
| `make backup` | Back up workspaces to `backups/` |

### Token Quotas

| Command | Description |
|---|---|
| `make quota-report` | Usage report for the current month |
| `make quota-report MONTH=2026-03` | Report for a specific month |
| `make set-limit NAME=x LIMIT=500000` | Set token quota (tokens/month), no restart needed |
| `make quota-reset NAME=x` | Reset current-month counter |

### Monitoring

| Command | Description |
|---|---|
| `make monitor` | Current CPU/RAM/disk metrics |
| `make monitor-alerts` | Active alerts (1h cooldown) |

### Service Agent

| Command | Description |
|---|---|
| `make service-health` | Service-agent healthcheck |
| `make service-skills` | List available skills |
| `make add-service NAME=x PORT=y SKILLS=z` | Add a service-agent replica |

### Security

| Command | Description |
|---|---|
| `make security-check` | Verify `.env` permissions, key presence, gitignore |

---

## Token Quotas

```
📊 Token report (2026-02):

  nikita       823,451 / 1,000,000 tokens  ⚠️ warning  ████████████████
               in=641,203  out=182,248  reqs=1,847

  alexey       312,008 /   500,000 tokens  ✅ ok  ██████
               in=241,500  out=70,508   reqs=892

  dmitry        45,100 /   500,000 tokens  ✅ ok  █
               in=38,200   out=6,900    reqs=203
```

- **⚠️ warning** at 80% — add alerting as needed
- **❌ exceeded** at 100% — instance receives 429, notifies the user
- Limits can be changed **without restart**: `make set-limit NAME=alexey LIMIT=1000000`

---

## Repository Structure

```
corp-assistant/
├── quota-proxy/          # sole holder of ANTHROPIC_API_KEY
│   ├── proxy.py          # HTTP proxy, SQLite quota + audit log
│   └── Dockerfile
├── broker/               # message bus between assistants
│   └── broker.py
├── resource-monitor/     # CPU/RAM/disk monitoring, HTTP API
│   ├── monitor.py
│   └── Dockerfile
├── service-agent/        # HTTP API for backend services
│   ├── server.py         # /v1/run  /v1/skills  /v1/usage
│   ├── skills/           # compliance/ and other skills
│   └── Dockerfile
├── instances/
│   ├── admin/            # Prior — sole instance with /infra access
│   ├── _template/        # new-instance template
│   └── .env.example      # instance .env template
├── shared/
│   └── skills/
│       └── corp-messenger/  # inter-instance messaging skill
├── scripts/
│   ├── add-user.sh       # onboarding: generates keys, copies template
│   ├── remove-user.sh    # remove instance with workspace archive
│   ├── quota.sh          # quota management CLI
│   ├── monitor.sh        # monitoring CLI
│   ├── add-service.sh    # add service-agent replica
│   └── backup.sh         # workspace backup
├── docs/                 # documentation (see below)
├── .github/
│   └── workflows/        # CI: security, release-please, GitHub Releases
└── docker-compose.yml
```

---

## CI / CD

GitHub Actions runs automatically on every push and PR:

| Workflow | What it does |
|---|---|
| `security.yml` | Semgrep SAST + custom AI rules, CodeQL, Trivy, Gitleaks, Hadolint, ShellCheck, pip-audit |
| `release-please.yml` | Opens a Release PR on merge to `master`, updates `CHANGELOG.md` and `VERSION` |
| `release.yml` | Creates a GitHub Release with release notes on `v*.*.*` tag push |
| `lint-commits.yml` | Enforces Conventional Commits on PR titles and commit messages |

Current version: see [VERSION](VERSION) · [CHANGELOG](CHANGELOG.md) · [Releases](https://github.com/rekurt/corp-assistant/releases)

---

## Documentation

| Document | Description |
|---|---|
| [docs/SETUP.md](docs/SETUP.md) | Installation on a clean server (Ubuntu 24.04) |
| [docs/ONBOARDING.md](docs/ONBOARDING.md) | Onboarding a new employee |
| [docs/PERSONAS.md](docs/PERSONAS.md) | Creating personas (SOUL.md / IDENTITY.md) |
| [docs/MESSAGING.md](docs/MESSAGING.md) | Inter-instance messaging |
| [docs/SERVICE_AGENT.md](docs/SERVICE_AGENT.md) | HTTP API for backend services |
| [docs/SECURITY.md](docs/SECURITY.md) | Threat model, patched vulnerabilities, hardening |
