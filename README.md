# 🐒 CortexForge — toy project, not production-safe

<p align="center">
  <img src="assets/banner.jpg" alt="CortexForge — isolated AI personas for every team member" width="1200"/>
</p>

> **Experimental / entertainment project. Do not use in production.**
> CortexForge is a Docker Compose playground for trying isolated AI assistant instances, quota proxies, message routing, and personal personas. It is **not audited**, **not hardened enough for real employee data**, and includes intentionally powerful local-admin capabilities such as Docker socket access and project write mounts. Treat it as a lab, not an enterprise security product.
>
> **Language / Язык:** English | [Русский](README.ru.md)

[![Version](https://img.shields.io/github/v/tag/example-org/cortex-forge?label=version&color=blue)](https://github.com/example-org/cortex-forge/releases)
[![CI Security](https://github.com/example-org/cortex-forge/actions/workflows/security.yml/badge.svg)](https://github.com/example-org/cortex-forge/actions/workflows/security.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

CortexForge is an experimental AI-assistant infrastructure sandbox built on [OpenClaw](https://github.com/openclaw/openclaw).

The idea is simple: run several isolated Telegram-bot assistant instances on one host, each with its own workspace, persona, token quota, and message inbox.

---

## What This Project Is

This repository is useful for:

- experimenting with per-user AI assistant containers
- testing quota enforcement in front of model APIs
- trying a simple broker for inter-assistant messages
- exploring persona/workspace-based assistant behavior
- prototyping internal automation skills behind a small HTTP service

This repository is **not** suitable for:

- production employee assistants
- regulated data, secrets, customer data, or confidential documents
- multi-tenant deployments with real trust boundaries
- environments where Docker socket access, broad bind mounts, or OAuth proxy experiments are unacceptable

---

## Components

CortexForge is split into a few small services:

| Component | Description |
|---|---|
| **OpenClaw instances** | One admin instance plus optional generated user instances |
| **CLIProxyAPI** | Optional OAuth proxy for Codex/Claude Max style access; stores its own OAuth session in a Docker volume |
| **quota-proxy** | Quota, rate-limit and audit proxy in front of the upstream model endpoint |
| **message-broker** | SQLite-backed inbox/message bus between instances |
| **resource-monitor** | Docker/container metrics and quota alerts |
| **service-agent** | Local HTTP API that runs approved skills as subprocesses |

---

## Why It Exists

The project started as a playful way to see what an "AI office full of little personal bots" could look like. It focuses on operational mechanics rather than polished product security:

| Experiment | Implementation |
|---|---|
| Per-instance context | Separate workspace, memory, Telegram token, and persona files |
| Quota accounting | `quota-proxy` stores monthly counters in SQLite |
| Admin control plane | Admin OpenClaw instance mounts the repo as `/infra` and can inspect Docker |
| Bot-to-bot messaging | `message-broker` exposes `/send`, `/inbox`, and admin inbox views |
| Skill execution | `service-agent` loads skill manifests and runs allowlisted subprocesses |

---

## Features

- 🔒 **Quota proxy pattern** — user instances receive `QUOTA_KEY_*` values and call the local `quota-proxy`
- 📊 **Token quotas** — per-instance monthly limits with warning (80%) and hard cutoff (100%); change live without restart
- 🧑‍🤝‍🧑 **Isolated personas** — each generated instance has its own bot, workspace, memory and character (`SOUL.md`)
- 💬 **Message broker** — inter-instance messages with per-instance inboxes
- 🏛️ **Admin instance** — intentionally powerful admin bot with `/infra` and Docker access
- 📈 **Resource monitor** — CPU/RAM/disk metrics with configurable alert thresholds
- 🔌 **Service agent** — HTTP API that lets backend services call skills (e.g. compliance checks) as subprocesses
- 🛡️ **Security checks** — Gitleaks, Semgrep, Bandit, Trivy, Hadolint, ShellCheck and custom AI checks in CI
- 🔄 **Release automation** — release-please auto-generates changelogs and GitHub Releases on merge to `master`
- 🐳 **Pure Docker Compose** — no Kubernetes, no Helm; runs on a single Ubuntu VPS

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         Docker Networks                          │
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                       │
│  │  user-1  │  │  user-2  │  │  user-3  │  ...  corp-internal   │
│  │ own bot  │  │ own bot  │  │ own bot  │                       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                       │
│       │             │             │                              │
│       └─────────────┼─────────────┘                              │
│                     │  openclaw.json baseUrl=http://quota-proxy  │
│            ┌────────▼─────────┐                                  │
│            │  CortexForge     │  corp-internal                   │
│            │  Proxy :9090     │  corp-admin                      │
│            │                  │  corp-egress ──► internet        │
│            │  ✓ counts tokens │                                  │
│            │  ✓ enforces caps │                                  │
│            │  ✓ audit log     │                                  │
│            └────────┬─────────┘                                  │
│                     │                                            │
│                     ▼  CLIProxyAPI or api.anthropic.com          │
│                                                                  │
│  ┌───────────────────────┐   ┌──────────────────────────────┐   │
│  │  CortexForge Broker   │   │  resource-monitor :9091      │   │
│  │  per-instance inbox   │   │  CPU / RAM / disk            │   │
│  │  auth by key          │   │  alerts + HTTP API           │   │
│  └───────────────────────┘   └──────────────────────────────┘   │
│                                                                  │
│  ┌───────────────────────┐   ┌──────────────────────────────┐   │
│  │  service-agent :8090  │   │  ADMIN — Admin 🏛️            │   │
│  │  /v1/run  /v1/skills  │   │  /infra access               │   │
│  │  skills as subprocess │   │  quota / users / docker      │   │
│  └───────────────────────┘   └──────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

### How a request flows

1. Employee sends a message to their Telegram bot
2. OpenClaw inside the container receives it and calls the provider configured in `openclaw.json`; user templates point `baseUrl` to `http://quota-proxy:9090`
3. `quota-proxy` checks the token quota, updates the counter in SQLite, then forwards the request to CLIProxyAPI by default (`http://cliproxyapi:8317`) or to a direct upstream if configured
4. If the quota is exceeded, `quota-proxy` returns HTTP 429 immediately — no real API call is made

### Docker Networks

| Network | `internal` | Connected to | Purpose |
|---|---|---|---|
| `corp-internal` | ✅ yes | admin, generated instances, broker, quota-proxy, monitor, service-agent | internal data bus — no direct internet |
| `corp-admin` | ✅ yes | admin, quota-proxy, monitor | quota management and metrics — no direct internet |
| `corp-egress` | ❌ no | quota-proxy, CLIProxyAPI | upstream model/OAuth egress |
| `corp-services` | ❌ no | service-agent | backend service calls |
| `corp-outbound` | ❌ no | admin and generated instances | Telegram and other non-model external APIs |

Generated user instances are not placed on `corp-admin` and do not mount `/infra`. They do have `corp-outbound` for Telegram and other external calls, so this is **not** a strict air-gapped or production-grade isolation model.

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
| Python | 3.12+ | 3.12+ |
| ShellCheck | optional locally | required for full local lint |

---

## Quick Start

### 1. Clone and configure local secrets

```bash
git clone https://github.com/example-org/cortex-forge.git /opt/CortexForge
cd /opt/CortexForge

cp .env.example .env
chmod 600 .env
nano .env
```

Minimum local values:

```bash
ANTHROPIC_API_KEY=sk-ant-...          # used by the admin instance directly
CLIPROXY_API_KEY=clip-...             # quota-proxy -> CLIProxyAPI auth
QUOTA_ADMIN_TOKEN=<random-32-chars>   # quota-proxy admin API token
BROKER_KEY_ADMIN=<random-32-chars>    # admin broker key
BROKER_KEY_SERVICE=<random-32-chars>  # service-agent broker key
BROKER_KEY_MONITOR=<random-32-chars>  # monitor broker key
MONITOR_ADMIN_TOKEN=<random-32-chars> # resource-monitor API token
SERVICE_API_KEY=svc-...               # service-agent bearer token
```

Generate random tokens:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
python3 -c "import secrets; print('clip-' + secrets.token_urlsafe(24))"
python3 -c "import secrets; print('svc-' + secrets.token_urlsafe(24))"
```

### 2. Bootstrap CLIProxyAPI OAuth, or change upstream mode

`docker-compose.yml` currently points `quota-proxy` at CLIProxyAPI:

```yaml
UPSTREAM_URL=http://cliproxyapi:8317
UPSTREAM_API_KEY=${CLIPROXY_API_KEY}
```

That means CLIProxyAPI needs an OAuth credential stored in the `cliproxyapi-auths` Docker volume before normal user instances can call models through the proxy. The full headless login procedure is documented in [CLAUDE.md](CLAUDE.md). Without that OAuth state, the CLIProxyAPI container can restart cleanly but still be unusable for real model calls.

For a simpler local experiment, change `UPSTREAM_URL` to a direct provider endpoint and provide a compatible upstream key. Do not commit real credentials.

### 3. Create the admin instance (Admin)

The admin instance is **mandatory** — `docker-compose.yml` references `instances/admin/.env` at startup. Without it, `docker compose config` will fail.

```bash
mkdir -p instances/admin
cp instances/.env.example instances/admin/.env
chmod 600 instances/admin/.env
nano instances/admin/.env
```

Required fields:

```bash
TELEGRAM_BOT_TOKEN=0000000000:CHANGE_ME_BOT_TOKEN
TELEGRAM_ALLOW_FROM=000000000         # your Telegram user ID
BROKER_KEY=<same as BROKER_KEY_ADMIN> # must match the global .env value
```

### 4. Validate configuration

```bash
make security-check
```

All items should show ✅. Fix any ❌ before proceeding.

### 5. Add the first generated instance

```bash
make add-user NAME=user-2 \
              BOT_TOKEN=7000000000:AAxxxx \
              FULL_NAME="Example User" \
              TG_ID=123456789
```

This script automatically:
- Creates `instances/user-2/` from the template
- Generates unique `BROKER_KEY` and `QUOTA_KEY`
- Appends keys and a 1M token/month limit to `.env`
- Appends the generated service to `docker-compose.override.yml` (gitignored)

Then optionally fill in personal credentials:
```bash
nano instances/user-2/.env               # Yandex OAuth, GitLab token, etc.
nano instances/user-2/workspace/SOUL.md  # persona style and character
```

### 6. Launch

```bash
make deploy
make status    # all containers should be Up (healthy)
```

---

## Configuration Reference

### Global `.env`

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | Anthropic API key used by the admin instance directly; generated instances should use quota keys through `quota-proxy` |
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
| `TELEGRAM_BOT_TOKEN` | ✅ | Telegram bot token placeholder |
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

Quotas are enforced by `quota-proxy` before a generated instance reaches the configured upstream (CLIProxyAPI by default, or direct API if reconfigured).

```
📊 Token report (2026-02):

  user-1       823,451 / 1,000,000 tokens  ⚠️ warning  ████████████████
               in=641,203  out=182,248  reqs=1,847

  user-2       312,008 /   500,000 tokens  ✅ ok  ██████
               in=241,500  out=70,508   reqs=892

  user-3        45,100 /   500,000 tokens  ✅ ok  █
               in=38,200   out=6,900    reqs=203
```

- **✅ ok** — below 80%
- **⚠️ warning** — 80–99% — inform the admin
- **❌ exceeded** — 100% — quota-proxy returns HTTP 429; instance tells the user
- Quota resets on the 1st of every month (or manually with `make quota-reset`)
- Limits can be changed **without restart**: `make set-limit NAME=user-2 LIMIT=1000000`

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
- Name: Example User
- Role: Backend Lead
- Timezone: UTC+3
```

The admin instance is named **Admin** 🏛️ (the head of a Capuchin monastery — he oversees all instances). Admin is the only instance with access to `/infra`, Docker control and quota management.

---

## Repository Structure

```
CortexForge/
├── cliproxyapi/          # CLIProxyAPI config and entrypoint for OAuth proxy mode
├── quota-proxy/          # quota/rate-limit/audit proxy for generated instances
│   ├── proxy.py          # HTTP proxy + SQLite quota & audit log
│   └── Dockerfile
├── broker/               # message bus between assistants
│   └── broker.py         # SQLite-persistent inbox per instance, auth by key
├── resource-monitor/     # CPU/RAM/disk monitoring
│   ├── monitor.py        # metrics collection, alert cooldown, HTTP API
│   └── Dockerfile
├── service-agent/        # HTTP API for backend services
│   ├── server.py         # /v1/run  /v1/skills  /v1/health  /v1/usage
│   ├── skills/
│   │   └── compliance/   # compliance risk check (calls enrich.py)
│   └── Dockerfile
├── instances/
│   ├── admin/            # Admin — sole instance with /infra access
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
│   │   ├── security.yml        # Gitleaks, Semgrep, Bandit, Trivy, Hadolint, ShellCheck
│   │   ├── release-please.yml  # automated release PRs
│   │   ├── release.yml         # GitHub Releases on tag push
│   │   └── lint-commits.yml    # Conventional Commits enforcement
│   ├── semgrep/
│   │   └── ai-security.yml     # 14 custom AI/security rules
│   └── scripts/
│       └── ai_security_check.py  # 9 project-specific security checks
├── CHANGELOG.md
├── VERSION
└── docker-compose.yml
```

---

## CI / CD

GitHub Actions runs on every push and PR:

| Workflow | Jobs | What it checks |
|---|---|---|
| `security.yml` | secrets-scan, sast-python, ai-security, docker-lint, shellcheck, deps-audit, trivy-images | Secret scanning, Python SAST, custom AI checks, container lint/scans |
| `release-please.yml` | release-please | Opens Release PR, updates `CHANGELOG.md` + `VERSION` |
| `release.yml` | github-release | Creates GitHub Release with notes on `v*.*.*` tag |
| `lint-commits.yml` | pr-title, commits, release-ready | Conventional Commits on PR + commit messages |

**Custom Python checks** (`ai_security_check.py`) cover 9 project-specific patterns:
- Broker inbox access without auth check
- Quota check order (must be before upstream request)
- MCP server auth + timing attack on token compare
- Service-agent skill name injection (subprocess before `ALLOWED_SKILLS` check)
- Hardcoded tokens (6 patterns: Anthropic, GitLab, GitHub, Slack, AWS, Telegram)
- Sensitive OAuth/token files and token-like values in text files
- Docker network exposure for sensitive services
- Path traversal in `add-user.sh`
- Real secrets in `.env.example`

`.github/semgrep/ai-security.yml` currently defines 14 Semgrep-style AI/security rules.

Current version: [VERSION](VERSION) · [CHANGELOG](CHANGELOG.md) · [Releases](https://github.com/example-org/cortex-forge/releases)

---

## Security Notes

CortexForge has several useful security experiments, but they are not a production security model:

- **Quota key pattern** — generated user instances use `QUOTA_KEY_*` values instead of a direct upstream API key
- **Network segmentation** — `corp-internal` and `corp-admin` are internal Docker networks, while `corp-outbound` allows Telegram/external calls
- **Constant-time token comparison** — bearer token checks use `hmac.compare_digest`
- **Rate limiting and message limits** — implemented in the proxy/broker paths
- **Resource limits** — CPU and RAM caps are configured through Compose `deploy.resources`
- **Dangerous admin power by design** — the admin instance mounts the whole project at `/infra` and has Docker socket access
- **Audit and quota data** — SQLite storage is used for quota, broker, monitor and service-agent state

Use [docs/SECURITY.md](docs/SECURITY.md) as a threat-model note, not as a certification or production hardening guarantee.

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
make logs NAME=user-2
```

Common causes:
- Invalid `TELEGRAM_BOT_TOKEN` — check with `curl https://api.telegram.org/bot<token>/getMe`
- Missing required field in `.env`

### quota-proxy / CLIProxyAPI upstream calls fail

Verify `quota-proxy` and CLIProxyAPI are on the `corp-egress` network:
```bash
docker inspect corp-quota | grep -A5 Networks
docker inspect corp-cliproxyapi | grep -A5 Networks
```

Both should include `corp-egress`. If CLIProxyAPI has no OAuth credential in its volume, complete the OAuth bootstrap first. If networks are wrong, run `make deploy` to recreate with the current `docker-compose.yml`.

### Token quota exceeded unexpectedly

```bash
make quota-report
```

Increase the limit without restart:
```bash
make set-limit NAME=user-2 LIMIT=2000000
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
