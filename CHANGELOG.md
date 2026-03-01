# Changelog

All notable changes to CortexForge will be documented here.

Format follows [Conventional Commits](https://www.conventionalcommits.org/).
Releases are automated via [release-please](https://github.com/googleapis/release-please).

## [0.2.0](https://github.com/rekurt/cortex-forge/compare/v0.1.4...v0.2.0) (2026-03-01)


### Features

* add corp-docs skill, add-user.sh fix, 004 migration ([13250ed](https://github.com/rekurt/cortex-forge/commit/13250edd22da2ede52a84f0168436116f7b9e348))
* add OAuth token rotation script and cleanup migration ([19ac282](https://github.com/rekurt/cortex-forge/commit/19ac282f4117fec9b4b1f6385bff218cfd6f9079))
* add vasily & dmitry instances, fix compose mounts and memory settings ([e7a9d48](https://github.com/rekurt/cortex-forge/commit/e7a9d48435d49b7001bf9fa1522fe4ea1dedda80))
* add vasily & dmitry instances, fix compose mounts and memory settings ([d4e81ef](https://github.com/rekurt/cortex-forge/commit/d4e81ef4c6f305b7b7a0cd9edcbc83f266f717d6))
* context-mode MCP в шаблон ([f66f335](https://github.com/rekurt/cortex-forge/commit/f66f335cc0fe5bdedc9ef69d315935e8fc9f8e2c))
* mount admin-workspace from capuchin repo ([61c2f7f](https://github.com/rekurt/cortex-forge/commit/61c2f7f35563e7daaf988650e14aed6cde7154a5))
* workspace mount из репо для всех инстансов; обновлён add-user.sh ([8b522d0](https://github.com/rekurt/cortex-forge/commit/8b522d04b122b10f520c684c88f9d8035f2139b0))
* актуализация шаблона — models.providers, убрать skills/OPENAI_API_KEY, добавить HEARTBEAT, allowFrom Приора ([1cce655](https://github.com/rekurt/cortex-forge/commit/1cce655b738613e68f14311913eb7fb49da3a297))


### Bug Fixes

* quota-proxy OAuth Bearer + бета заголовки; убрать ANTHROPIC_BASE_URL из compose (конфиг через openclaw.json) ([1032656](https://github.com/rekurt/cortex-forge/commit/10326568f5f8c279cefe124437d58abba8c3bc05))

## [0.1.3](https://github.com/rekurt/cortex-forge/compare/v0.1.2...v0.1.3) (2026-02-27)


### Bug Fixes

* review fixes, doc refresh, network isolation ([ac0bf76](https://github.com/rekurt/cortex-forge/commit/ac0bf7604805010661c4c18b83b911b9487efee2))

## [0.1.2](https://github.com/rekurt/cortex-forge/compare/v0.1.1...v0.1.2) (2026-02-27)


### Bug Fixes

* **service-agent:** add explicit ALLOWED_SKILLS whitelist check before subprocess.run() ([94afea4](https://github.com/rekurt/cortex-forge/commit/94afea460c9cdf5701cf1b29ea6dd895ab164ca9))
* **service-agent:** fix ai_security_check false positives on subprocess.run ([c2ad05c](https://github.com/rekurt/cortex-forge/commit/c2ad05cb8ae5d7ba60b45cf800043b2a4ab7fcce))

## [0.1.1](https://github.com/rekurt/cortex-forge/compare/v0.1.0...v0.1.1) (2026-02-27)


### Bug Fixes

* исправлены падающие GitHub Actions пайплайны ([05dc521](https://github.com/rekurt/cortex-forge/commit/05dc5215d34a99fcebac9fcd44818260eb804d49))

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
