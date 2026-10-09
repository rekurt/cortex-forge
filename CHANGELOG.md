# Changelog

All notable changes to CortexForge will be documented here.

Format follows [Conventional Commits](https://www.conventionalcommits.org/).
Releases are automated via [release-please](https://github.com/googleapis/release-please).

## [0.6.0](https://github.com/rekurt/cortex-forge/compare/v0.5.1...v0.6.0) (2026-10-09)


### Features

* **site:** publish project website ([1ef96d5](https://github.com/rekurt/cortex-forge/commit/1ef96d52f9b542585e1a3e3c260d79802f29d3a1))

## [0.5.1](https://github.com/example-org/cortex-forge/compare/v0.5.0...v0.5.1) (2026-06-10)


### Documentation

* clarify that CortexForge is an experimental toy project and is not production-safe
* refresh README and README.ru with current CLIProxyAPI, Docker network, and security-check details

## [0.5.0](https://github.com/example-org/cortex-forge/compare/v0.4.0...v0.5.0) (2026-03-19)


### Features

* add 6 shared skills as submodules ([1238aaa](https://github.com/example-org/cortex-forge/commit/1238aaa684a84fcd5694f569a9b58f2d928b105b))
* add gitlab-release-monitor as shared skill, update ONBOARDING.md ([6fee05c](https://github.com/example-org/cortex-forge/commit/6fee05c475f31f22c62aaaf386f6bc851482cd4f))
* add gitlab-release-monitor to skills table in all AGENTS.md + template ([e176aba](https://github.com/example-org/cortex-forge/commit/e176aba034a96722e6e9e0fae922529fbe632e78))
* add user-5 instance, update user-1 USER.md, add compliance-risk skill to user-1 ([149d9f5](https://github.com/example-org/cortex-forge/commit/149d9f5d5d89c202176b7bc985d85c6426a2583e))
* add new documentation files for agent infrastructure and update identity details ([0f6c77d](https://github.com/example-org/cortex-forge/commit/0f6c77decdd2060309635bce47acea77bff04557))
* add sast-priority as shared skill submodule ([baa3d0d](https://github.com/example-org/cortex-forge/commit/baa3d0d862d0f6145dff90ab9b978df7d1b7c53d))
* **admin:** expose docker socket rw + docker group ([289be2d](https://github.com/example-org/cortex-forge/commit/289be2d2830975703db2f94dec49c6adb15886f6))
* **admin:** mount docker CLI binary from host ([438c3a8](https://github.com/example-org/cortex-forge/commit/438c3a878d118acc3f0500a1f9635b3039555fe7))
* enhance OAuth credential handling and update documentation ([7ca0290](https://github.com/example-org/cortex-forge/commit/7ca0290d2be97b01fe43c167b5c8797926c2fb6b))
* migration 024 — add 7 new shared skills to AGENTS.md ([b1f7ecc](https://github.com/example-org/cortex-forge/commit/b1f7ecc730d0478142797855b29709949e5cb8a9))
* update workspace paths to be within instance directories ([198150a](https://github.com/example-org/cortex-forge/commit/198150ae3eaa2dc8de97c29464b7ffa195fd4224))


### Bug Fixes

* **ci:** fix commitlintrc trailing comma and trivy db mirror ([8ef81fe](https://github.com/example-org/cortex-forge/commit/8ef81fe9011e9a638267b2520858b987137d9895))

## [0.4.0](https://github.com/example-org/cortex-forge/compare/v0.3.0...v0.4.0) (2026-03-03)


### Features

* add CLIProxyAPI as Docker service for Claude Max OAuth ([a63da83](https://github.com/example-org/cortex-forge/commit/a63da83e9c35a051c80afc18dfbc97cd5a2df7b1))
* configurable upstream for quota-proxy (CLIProxyAPI support) ([debf04c](https://github.com/example-org/cortex-forge/commit/debf04c63d5f0c912e6efd6d0bf9aa703850d58b))
* update monkey personality with warmth and workaround-thinking ([0e7e6ff](https://github.com/example-org/cortex-forge/commit/0e7e6ff0b25c7c75aea40a7dd6db869453d2e760))
* verify acceptance criteria for CLIProxyAPI and personality updates ([c0fd05e](https://github.com/example-org/cortex-forge/commit/c0fd05e38e0fb22c582e1c2ffda9eff7817e0fb9))


### Bug Fixes

* address code review findings ([50b140b](https://github.com/example-org/cortex-forge/commit/50b140b7e1e42c6df8b6ecb69c363133d32e1522))
* address code review findings ([99fa73d](https://github.com/example-org/cortex-forge/commit/99fa73d7d2b87069a43d289f64f56ce8ef1b9624))
* address code review findings ([d711d51](https://github.com/example-org/cortex-forge/commit/d711d5172a332c06f980b709d768f0299cee5a4a))
* address code review findings ([d3453dd](https://github.com/example-org/cortex-forge/commit/d3453ddf734c4775e8354339fe0e3cfaeae91cbc))
* address code review findings ([869fc79](https://github.com/example-org/cortex-forge/commit/869fc79fcca16a25b8e52f960f67953e45ff99c8))
* address code review findings ([fb3a3f2](https://github.com/example-org/cortex-forge/commit/fb3a3f2bc12a9881f5a8d8e17133ae59caa38689))
* address code review findings ([3c31d3a](https://github.com/example-org/cortex-forge/commit/3c31d3ae8330644ba9a776f65487729fb4745604))
* address code review findings ([9e8702e](https://github.com/example-org/cortex-forge/commit/9e8702eb7ed390b5d8c7ce23409e7b57f8358a21))
* address code review findings ([28c49d7](https://github.com/example-org/cortex-forge/commit/28c49d7cdbf9122541244d3b26b674d9ae3d2a61))
* use service names and auto-discover compose files in sync-instan… ([#11](https://github.com/example-org/cortex-forge/issues/11)) ([50b140b](https://github.com/example-org/cortex-forge/commit/50b140b7e1e42c6df8b6ecb69c363133d32e1522))

## [0.3.0](https://github.com/example-org/cortex-forge/compare/v0.2.0...v0.3.0) (2026-03-02)


### Features

* **infra:** reliability improvements and new skills from bugfix-reliability ([e7eb834](https://github.com/example-org/cortex-forge/commit/e7eb834cf91ce85df6bdaa95b4122a2430be8c36))

## [0.2.0](https://github.com/example-org/cortex-forge/compare/v0.1.4...v0.2.0) (2026-03-01)


### Features

* add corp-docs skill, add-user.sh fix, 004 migration ([13250ed](https://github.com/example-org/cortex-forge/commit/13250edd22da2ede52a84f0168436116f7b9e348))
* add OAuth token rotation script and cleanup migration ([19ac282](https://github.com/example-org/cortex-forge/commit/19ac282f4117fec9b4b1f6385bff218cfd6f9079))
* add user-4 & user-3 instances, fix compose mounts and memory settings ([e7a9d48](https://github.com/example-org/cortex-forge/commit/e7a9d48435d49b7001bf9fa1522fe4ea1dedda80))
* add user-4 & user-3 instances, fix compose mounts and memory settings ([d4e81ef](https://github.com/example-org/cortex-forge/commit/d4e81ef4c6f305b7b7a0cd9edcbc83f266f717d6))
* context-mode MCP в шаблон ([f66f335](https://github.com/example-org/cortex-forge/commit/f66f335cc0fe5bdedc9ef69d315935e8fc9f8e2c))
* mount admin-workspace from capuchin repo ([61c2f7f](https://github.com/example-org/cortex-forge/commit/61c2f7f35563e7daaf988650e14aed6cde7154a5))
* workspace mount из репо для всех инстансов; обновлён add-user.sh ([8b522d0](https://github.com/example-org/cortex-forge/commit/8b522d04b122b10f520c684c88f9d8035f2139b0))
* актуализация шаблона — models.providers, убрать skills/OPENAI_API_KEY, добавить HEARTBEAT, allowFrom Admin ([1cce655](https://github.com/example-org/cortex-forge/commit/1cce655b738613e68f14311913eb7fb49da3a297))


### Bug Fixes

* quota-proxy OAuth Bearer + бета заголовки; убрать ANTHROPIC_BASE_URL из compose (конфиг через openclaw.json) ([1032656](https://github.com/example-org/cortex-forge/commit/10326568f5f8c279cefe124437d58abba8c3bc05))

## [0.1.3](https://github.com/example-org/cortex-forge/compare/v0.1.2...v0.1.3) (2026-02-27)


### Bug Fixes

* review fixes, doc refresh, network isolation ([ac0bf76](https://github.com/example-org/cortex-forge/commit/ac0bf7604805010661c4c18b83b911b9487efee2))

## [0.1.2](https://github.com/example-org/cortex-forge/compare/v0.1.1...v0.1.2) (2026-02-27)


### Bug Fixes

* **service-agent:** add explicit ALLOWED_SKILLS whitelist check before subprocess.run() ([94afea4](https://github.com/example-org/cortex-forge/commit/94afea460c9cdf5701cf1b29ea6dd895ab164ca9))
* **service-agent:** fix ai_security_check false positives on subprocess.run ([c2ad05c](https://github.com/example-org/cortex-forge/commit/c2ad05cb8ae5d7ba60b45cf800043b2a4ab7fcce))

## [0.1.1](https://github.com/example-org/cortex-forge/compare/v0.1.0...v0.1.1) (2026-02-27)


### Bug Fixes

* исправлены падающие GitHub Actions пайплайны ([05dc521](https://github.com/example-org/cortex-forge/commit/05dc5215d34a99fcebac9fcd44818260eb804d49))

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
