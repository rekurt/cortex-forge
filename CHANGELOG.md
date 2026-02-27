# Changelog

All notable changes to corp-assistant will be documented here.

Format follows [Conventional Commits](https://www.conventionalcommits.org/).
Releases are automated via [release-please](https://github.com/googleapis/release-please).

## [0.1.2](https://github.com/rekurt/corp-assistant/compare/v0.1.1...v0.1.2) (2026-02-27)


### Bug Fixes

* **service-agent:** add explicit ALLOWED_SKILLS whitelist check before subprocess.run() ([94afea4](https://github.com/rekurt/corp-assistant/commit/94afea460c9cdf5701cf1b29ea6dd895ab164ca9))
* **service-agent:** fix ai_security_check false positives on subprocess.run ([c2ad05c](https://github.com/rekurt/corp-assistant/commit/c2ad05cb8ae5d7ba60b45cf800043b2a4ab7fcce))

## [0.1.1](https://github.com/rekurt/corp-assistant/compare/v0.1.0...v0.1.1) (2026-02-27)


### Bug Fixes

* исправлены падающие GitHub Actions пайплайны ([05dc521](https://github.com/rekurt/corp-assistant/commit/05dc5215d34a99fcebac9fcd44818260eb804d49))

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
