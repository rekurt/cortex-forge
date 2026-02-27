# Changelog

All notable changes to corp-assistant will be documented here.

Format follows [Conventional Commits](https://www.conventionalcommits.org/).
Releases are automated via [release-please](https://github.com/googleapis/release-please).

## [0.1.0] — 2026-02-27

### ✨ Новые функции

- Initial infrastructure: quota proxy, message broker, admin instance
- Per-employee token quota limits with SQLite tracking
- Resource monitor with Docker stats + alerts
- Service agent with HTTP API for internal services
- Compliance skill (enrich.py integration)
- MCP server for update management (admin-only)

### 🔒 Безопасность

- Non-root users in all Docker containers
- `corp-admin` network isolation (MCP, quota-proxy)
- Bearer token auth with `hmac.compare_digest`
- Input validation against path traversal in all scripts
- GitHub Actions security pipeline (Semgrep, CodeQL, Trivy, Gitleaks)
