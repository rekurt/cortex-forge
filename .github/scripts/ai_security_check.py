#!/usr/bin/env python3
"""
AI Security Checker — кастомные проверки специфичные для CortexForge.
Запускается в GitHub Actions. Exit 1 при критических находках.
"""
import re
import sys
import ast
import json
import pathlib
from dataclasses import dataclass, field
from typing import Literal

ROOT = pathlib.Path(__file__).parent.parent.parent

@dataclass
class Finding:
    severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
    rule: str
    file: str
    line: int
    message: str
    fix: str = ""

findings: list[Finding] = []

def find(sev, rule, file, line, msg, fix=""):
    findings.append(Finding(sev, rule, str(file), line, msg, fix))

# ─── Helpers ──────────────────────────────────────────────────────────────────

def read(path: pathlib.Path) -> str:
    try:
        return path.read_text(errors="replace")
    except Exception:
        return ""

def lines(path: pathlib.Path) -> list[str]:
    return read(path).splitlines()

def grep(pattern: str, text: str) -> list[tuple[int, str]]:
    """Вернуть (line_no, line) для всех совпадений."""
    rx = re.compile(pattern)
    return [(i+1, l) for i, l in enumerate(text.splitlines()) if rx.search(l)]

# ─── Check 1: Broker — нельзя читать чужой inbox без авторизации ──────────────

def check_broker_auth():
    broker = ROOT / "broker" / "broker.py"
    if not broker.exists():
        return
    src = read(broker)

    # Проверяем что каждый do_GET handler проверяет auth перед _inbox
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("do_"):
            body_src = ast.get_source_segment(src, node)
            if body_src and "_inbox" in body_src:
                if "_auth" not in body_src and "Unauthorized" not in body_src:
                    find("CRITICAL", "broker-no-auth",
                         broker, node.lineno,
                         f"`{node.name}` обращается к _inbox без вызова _auth()",
                         "Добавь `sender = _auth(self); if not sender: return 403`")

# ─── Check 2: Quota proxy — проверка квоты ДО запроса к upstream ─────────────

def check_quota_order():
    proxy = ROOT / "quota-proxy" / "proxy.py"
    if not proxy.exists():
        return
    src = read(proxy)

    # Ищем функцию _proxy или do_POST — quota check должен быть до urlopen
    for func_name in ["_proxy", "do_POST"]:
        idx_quota = src.find("_get_quota")
        idx_urlopen = src.find("urlopen(")
        if idx_quota == -1 or idx_urlopen == -1:
            continue
        if idx_urlopen < idx_quota:
            find("CRITICAL", "quota-check-after-upstream",
                 proxy, 1,
                 "urlopen() вызывается ДО _get_quota() — можно обойти квоту",
                 "Переставь quota check перед forward-запросом к Anthropic")

# ─── Check 3: MCP server — все инструменты требуют auth ──────────────────────

def check_mcp_auth():
    for mcp_file in ROOT.rglob("server.py"):
        if "mcp-server" not in str(mcp_file):
            continue
        src = read(mcp_file)
        # Проверяем что do_POST вызывает _check_auth
        if "do_POST" in src and "_check_auth" not in src:
            find("HIGH", "mcp-no-auth",
                 mcp_file, 1,
                 "MCP server не проверяет авторизацию в do_POST",
                 "Добавь `if not self._check_auth(): return 401`")

        # Проверяем что ADMIN_TOKEN используется в проверке
        if "ADMIN_TOKEN" in src:
            # Должен использоваться hmac.compare_digest, не ==
            for no, line in grep(r'ADMIN_TOKEN.*==|==.*ADMIN_TOKEN', src):
                find("HIGH", "timing-attack-mcp",
                     mcp_file, no,
                     "Сравнение MCP_ADMIN_TOKEN через == — уязвимо к timing attack",
                     "Используй hmac.compare_digest()")

# ─── Check 4: Service agent — валидация skill name перед subprocess ───────────

def check_service_agent_skill_validation():
    server = ROOT / "service-agent" / "server.py"
    if not server.exists():
        return
    src = read(server)

    # Ищем вызов subprocess без явной проверки whitelist
    for no, line in grep(r'subprocess\.run', src):
        # Проверяем есть ли in TOOL_HANDLERS или allowlist выше
        context_start = max(0, no - 10)
        context = "\n".join(src.splitlines()[context_start:no])
        if "not in" not in context and "allowlist" not in context and "SKILL_HANDLERS" not in context:
            find("HIGH", "service-agent-skill-injection",
                 server, no,
                 f"subprocess.run() без явной проверки whitelist скилла — возможен skill name injection",
                 "Проверяй `skill_name in ALLOWED_SKILLS` перед subprocess.run()")

# ─── Check 5: Нет захардкоженных токенов ──────────────────────────────────────

TOKEN_PATTERNS = [
    (r'sk-ant-[A-Za-z0-9\-_]{20,}',  "Anthropic API key"),
    (r'glpat-[A-Za-z0-9\-_]{20,}',   "GitLab PAT"),
    (r'ghp_[A-Za-z0-9]{36}',          "GitHub token"),
    (r'xoxb-[0-9]+-[A-Za-z0-9]+',     "Slack bot token"),
    (r'AKIA[0-9A-Z]{16}',              "AWS Access Key"),
    (r'[0-9]{10}:[A-Za-z0-9\-_]{35}', "Telegram bot token"),
]

EXCLUDE_PATTERNS = re.compile(r'(#|test|example|placeholder|change.me|xxx|\.md$|\.example$)')
TEXT_SECRET_SUFFIXES = {
    ".env", ".example", ".json", ".md", ".py", ".sh", ".txt", ".yaml", ".yml",
    ".toml", ".template", ".lock",
}
SENSITIVE_FILENAMES = {
    ".anthropic_tokens.json",
    "anthropic-oauth.json",
}

def looks_text(path: pathlib.Path) -> bool:
    if path.suffix in TEXT_SECRET_SUFFIXES:
        return True
    if path.name in {"Makefile", "Dockerfile", "CODEOWNERS", "LICENSE", "CHANGELOG"}:
        return True
    return False

def should_skip_secret_path(path: pathlib.Path) -> bool:
    skip_parts = {".git", ".venv", "__pycache__", "node_modules", "openclaw_data", ".openclaw"}
    return bool(skip_parts.intersection(path.parts))

def check_hardcoded_tokens():
    for py_file in ROOT.rglob("*.py"):
        if ".venv" in str(py_file) or ".git" in str(py_file):
            continue
        src = read(py_file)
        for pattern, token_type in TOKEN_PATTERNS:
            for no, line in grep(pattern, src):
                if EXCLUDE_PATTERNS.search(line):
                    continue
                find("CRITICAL", "hardcoded-token",
                     py_file, no,
                     f"Возможный захардкоженный {token_type}",
                     "Перенеси в переменную окружения")

    for sh_file in ROOT.rglob("*.sh"):
        if ".git" in str(sh_file):
            continue
        src = read(sh_file)
        for pattern, token_type in TOKEN_PATTERNS:
            for no, line in grep(pattern, src):
                if EXCLUDE_PATTERNS.search(line):
                    continue
                find("CRITICAL", "hardcoded-token-sh",
                     sh_file, no,
                     f"Возможный захардкоженный {token_type} в bash-скрипте",
                     "Перенеси в .env")

def check_sensitive_token_files():
    oauth_field = re.compile(
        r'(?i)"(?:accessToken|refreshToken|access_token|refresh_token)"\s*:\s*"[^"$<\s][^"]{20,}"'
    )

    for path in ROOT.rglob("*"):
        if not path.is_file() or should_skip_secret_path(path):
            continue

        if path.name in SENSITIVE_FILENAMES:
            find("CRITICAL", "sensitive-token-file",
                 path, 1,
                 f"Чувствительный token-файл `{path.name}` не должен попадать в репозиторий",
                 "Удали файл из git, добавь ignore-правило и ротируй токены")
            continue

        if not looks_text(path):
            continue

        src = read(path)
        if not src:
            continue

        for pattern, token_type in TOKEN_PATTERNS:
            for no, line in grep(pattern, src):
                if EXCLUDE_PATTERNS.search(line):
                    continue
                find("CRITICAL", "hardcoded-token-any-text",
                     path, no,
                     f"Возможный захардкоженный {token_type}",
                     "Перенеси в gitignored .env или секрет-хранилище")

        for no, line in grep(oauth_field.pattern, src):
            if EXCLUDE_PATTERNS.search(line):
                continue
            find("CRITICAL", "oauth-token-json",
                 path, no,
                 "Возможный OAuth access/refresh token в текстовом файле",
                 "Удали файл из git, добавь ignore-правило и ротируй токены")

# ─── Check 6: Docker — сервисы на правильных сетях ───────────────────────────

def check_docker_networks():
    dc = ROOT / "docker-compose.yml"
    if not dc.exists():
        return
    src = read(dc)

    # quota-proxy и capuchin-mcp не должны быть на corp-internal
    # (только на corp-admin)
    sensitive_services = ["quota-proxy", "capuchin-mcp", "resource-monitor"]
    for svc in sensitive_services:
        if svc not in src:
            continue
        # Находим блок сервиса
        svc_match = re.search(
            rf'\n  {re.escape(svc)}:.*?(?=\n  [a-z]|\nvolumes:|\nnetworks:|\Z)',
            src, re.DOTALL
        )
        if svc_match:
            block = svc_match.group()
            networks_in_block = re.findall(r'- (corp-\w+)', block)
            if "corp-internal" in networks_in_block and svc in ["capuchin-mcp"]:
                lineno = src[:svc_match.start()].count('\n') + 1
                find("HIGH", "docker-network-exposure",
                     dc, lineno,
                     f"Сервис `{svc}` подключён к corp-internal — его могут видеть все инстансы",
                     "capuchin-mcp должен быть только на corp-admin сети")

# ─── Check 7: add-user.sh — валидация имени перед использованием в путях ──────

def check_add_user_validation():
    add_user = ROOT / "scripts" / "add-user.sh"
    if not add_user.exists():
        return
    src = read(add_user)

    # Должна быть валидация имени через regex
    if 'grep -qE' not in src and 're.match' not in src:
        find("HIGH", "add-user-no-validation",
             add_user, 1,
             "add-user.sh не валидирует NAME — возможен path traversal",
             "Добавь: `echo \"$NAME\" | grep -qE '^[a-z][a-z0-9_-]{1,31}$'`")

    # Проверяем что mkdir использует $TARGET, не $NAME напрямую
    for no, line in grep(r'mkdir.*\$NAME(?!_)', src):
        find("MEDIUM", "add-user-path-traversal",
             add_user, no,
             "mkdir с $NAME напрямую — должен быть $TARGET = instances/$NAME",
             "Используй $TARGET вместо прямого $NAME")

# ─── Check 8: Проверка .env.example на отсутствие реальных секретов ──────────

def check_env_example():
    for env_file in ROOT.glob("**/.env.example"):
        src = read(env_file)
        for pattern, token_type in TOKEN_PATTERNS:
            for no, line in grep(pattern, src):
                if EXCLUDE_PATTERNS.search(line):
                    continue
                find("HIGH", "real-secret-in-example",
                     env_file, no,
                     f"Реальный {token_type} в .env.example",
                     "Замени на placeholder типа 'change-me-xxx'")

# ─── Запуск всех проверок ────────────────────────────────────────────────────

def run_all():
    check_broker_auth()
    check_quota_order()
    check_mcp_auth()
    check_service_agent_skill_validation()
    check_hardcoded_tokens()
    check_sensitive_token_files()
    check_docker_networks()
    check_add_user_validation()
    check_env_example()

run_all()

# ─── Вывод результатов ────────────────────────────────────────────────────────

SEV_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
SEV_ICON  = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🔵", "INFO": "⚪"}

findings.sort(key=lambda f: SEV_ORDER.get(f.severity, 9))

if not findings:
    print("✅ AI Security: нарушений не найдено")
    sys.exit(0)

critical_count = sum(1 for f in findings if f.severity in ("CRITICAL", "HIGH"))

print(f"\n{'='*60}")
print(f"AI Security Check — {len(findings)} находок ({critical_count} критичных/высоких)")
print(f"{'='*60}\n")

for f in findings:
    icon = SEV_ICON.get(f.severity, "❓")
    print(f"{icon} [{f.severity}] {f.rule}")
    print(f"   📄 {f.file}:{f.line}")
    print(f"   🔎 {f.message}")
    if f.fix:
        print(f"   🔧 {f.fix}")
    print()

# Также выводим в GitHub Actions annotations
for f in findings:
    sev = "error" if f.severity in ("CRITICAL", "HIGH") else "warning"
    print(f"::{sev} file={f.file},line={f.line}::[{f.rule}] {f.message}")

print(f"\n{'='*60}")
if critical_count > 0:
    print(f"❌ Найдено {critical_count} критичных/высоких проблем. Pipeline упадёт.")
    sys.exit(1)
else:
    print(f"⚠️  Найдено {len(findings)} предупреждений. Pipeline продолжается.")
    sys.exit(0)
