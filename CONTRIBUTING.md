# Contributing to corp-assistant

Thank you for your interest in contributing! This guide covers everything you need to get started.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How to Contribute](#how-to-contribute)
- [Development Setup](#development-setup)
- [Commit Convention](#commit-convention)
- [Pull Request Process](#pull-request-process)
- [Security Issues](#security-issues)

---

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). By participating, you agree to uphold it.

---

## How to Contribute

### Reporting Bugs

1. Search [existing issues](https://github.com/rekurt/corp-assistant/issues) first
2. If not found — open a [bug report](https://github.com/rekurt/corp-assistant/issues/new?template=bug_report.yml)
3. Include: version, OS, steps to reproduce, expected vs actual behaviour

### Suggesting Features

Open a [feature request](https://github.com/rekurt/corp-assistant/issues/new?template=feature_request.yml).
Describe the problem you're solving, not just the solution.

### Contributing Code

1. Fork the repo
2. Create a branch: `git checkout -b feat/your-feature`
3. Make changes, write tests
4. Run checks (see below)
5. Open a PR against `master`

---

## Development Setup

**Requirements:** Docker 24+, Docker Compose 2.x, Python 3.12+

```bash
git clone https://github.com/rekurt/corp-assistant.git
cd corp-assistant

# Global config
cp .env.example .env
# Edit .env: set ANTHROPIC_API_KEY and other tokens

# Admin instance (required)
mkdir -p instances/admin
cp instances/.env.example instances/admin/.env
# Edit instances/admin/.env: set TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOW_FROM

# Launch
make deploy
make status
```

### Running security checks locally

```bash
# Project-specific AI security checks
python3 .github/scripts/ai_security_check.py

# Shell scripts
shellcheck scripts/*.sh

# Basic config check
make security-check
```

### Running tests

```bash
# Tests are being added — see open issues tagged 'tests'
# pytest tests/ -v
```

### Adding a skill to service-agent

1. Create `service-agent/skills/<your-skill>/`
2. Add `run.py` (reads JSON from stdin, writes JSON to stdout):
   ```python
   import sys, json
   params = json.load(sys.stdin)
   # ... do work ...
   print(json.dumps({"result": "done"}))
   ```
3. Add `skills.json` manifest (see `compliance/skills.json` as reference)
4. Rebuild: `docker compose build assistant-service`

---

## Commit Convention

This project uses [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short description>

[optional body]
[optional footer]
```

**Allowed types:** `feat`, `fix`, `docs`, `ci`, `security`, `perf`, `refactor`, `chore`, `test`, `build`, `revert`

**Examples:**
```
feat(broker): add DELETE /inbox endpoint
fix(quota-proxy): fix SIGTERM race condition
docs(readme): add architecture diagram
security(service-agent): add ALLOWED_SKILLS whitelist
ci(security): add Trivy image scanning
```

Commits that don't follow this convention will be rejected by CI.

---

## Pull Request Process

1. **One PR = one concern.** Don't mix refactoring with new features.
2. **Update documentation** if behaviour changes.
3. **Pass all CI checks** — the PR cannot be merged with red security checks.
4. **Fill in the PR template** completely.
5. **Request review** from [@rekurt](https://github.com/rekurt).

PRs are merged via **squash merge** to keep `master` history clean.

---

## Security Issues

**Do not open a public issue for security vulnerabilities.**

See [SECURITY.md](SECURITY.md) for responsible disclosure instructions.
