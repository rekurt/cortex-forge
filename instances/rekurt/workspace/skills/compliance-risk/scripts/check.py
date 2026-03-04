#!/usr/bin/env python3
"""
compliance-risk/scripts/check.py
Умный запуск проверки контрагента: ИНН, ОГРН, или название компании/ИП.

Использование:
  python3 check.py <ИНН/ОГРН>           — прямая проверка по номеру
  python3 check.py "Название компании"   — поиск + авто-проверка лучшего совпадения
  python3 check.py "ИП Иванов Иван"      — поиск ИП по имени + проверка
  python3 check.py "Сбербанк" --top 3    — показать топ-3 совпадения (не запускать проверку)
  python3 check.py "Рубикс" --pick 2     — выбрать 2й результат поиска и проверить
  python3 check.py "Рубикс" --list       — только список совпадений

Флаги:
  --top N     показать N вариантов и спросить какой проверять (по умолчанию: 5)
  --pick N    автоматически выбрать N-й результат из поиска
  --list      только список совпадений, без проверки
  --format    terminal|telegram (передаётся в enrich.py)
  --json      JSON-вывод
"""

import sys
import os
import re
import subprocess

ENRICH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                      "../../../../../../../shared/skills/compliance-risk/scripts/enrich.py")
# Нормализуем путь
ENRICH = os.path.normpath(ENRICH)
if not os.path.exists(ENRICH):
    ENRICH = "/shared/skills/compliance-risk/scripts/enrich.py"

def is_identifier(s: str) -> bool:
    """True если строка похожа на ИНН (10/12 цифр) или ОГРН (13/15 цифр)."""
    clean = re.sub(r"[\s\-]", "", s)
    return bool(re.fullmatch(r"\d{10}|\d{12}|\d{13}|\d{15}", clean))

def search_by_name(query: str, count: int = 10) -> list[dict]:
    """Вызываем enrich.py --search и парсим вывод."""
    import sys as _sys
    sys.path.insert(0, os.path.dirname(ENRICH))
    
    # Импортируем функцию напрямую из enrich.py
    import importlib.util
    spec = importlib.util.spec_from_file_location("enrich", ENRICH)
    enrich = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(enrich)
    
    return enrich.search_party_by_name(query, count)

def run_check(inn: str, fmt: str = "telegram", as_json: bool = False):
    """Запускаем enrich.py для полной проверки."""
    cmd = [sys.executable, ENRICH, inn, f"--format", fmt]
    if as_json:
        cmd.append("--json")
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode

def print_candidates(results: list[dict], query: str):
    """Вывести список кандидатов."""
    print(f"\n🔍 Результаты поиска по «{query}» ({len(results)} орг.):\n")
    for i, r in enumerate(results, 1):
        status_icon = {"ACTIVE": "✅", "LIQUIDATING": "⚠️", "LIQUIDATED": "❌", "BANKRUPT": "⛔"}.get(r.get("status",""), "❓")
        opf = f"[{r['opf']}] " if r.get("opf") else ""
        region = f" — {r['region']}" if r.get("region") else ""
        print(f"  {i:>2}. {status_icon} {opf}{r['name']}")
        print(f"       ИНН: {r.get('inn','—')}{region}")
    print()

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    # Парсим флаги
    fmt = "telegram"
    as_json = "--json" in args
    list_only = "--list" in args
    top_n = 5
    pick_n = None

    clean_args = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--format" and i+1 < len(args):
            fmt = args[i+1]; i += 2
        elif a == "--top" and i+1 < len(args):
            try: top_n = int(args[i+1])
            except: pass
            i += 2
        elif a == "--pick" and i+1 < len(args):
            try: pick_n = int(args[i+1])
            except: pass
            i += 2
        elif a in ("--json", "--list"):
            i += 1
        else:
            clean_args.append(a)
            i += 1

    query = " ".join(clean_args)
    if not query:
        print("❌ Укажите ИНН, ОГРН или название компании")
        sys.exit(1)

    # Если уже ИНН/ОГРН — сразу проверяем
    if is_identifier(query):
        print(f"🆔 Идентификатор: {query} → запускаем проверку...\n")
        sys.exit(run_check(query, fmt, as_json))

    # Иначе — поиск по названию
    print(f"🔍 Ищем «{query}»...", file=sys.stderr)
    results = search_by_name(query, count=max(top_n, 10))
    
    if not results:
        print(f"❌ По запросу «{query}» ничего не найдено")
        sys.exit(1)

    # Только активные — приоритет
    active = [r for r in results if r.get("status") == "ACTIVE"]
    ranked = active + [r for r in results if r.get("status") != "ACTIVE"]
    ranked = ranked[:top_n]

    if list_only or as_json:
        if as_json:
            import json
            print(json.dumps(ranked, ensure_ascii=False, indent=2))
        else:
            print_candidates(ranked, query)
        sys.exit(0)

    print_candidates(ranked, query)

    # Выбор кандидата
    if pick_n is not None:
        if 1 <= pick_n <= len(ranked):
            chosen = ranked[pick_n - 1]
        else:
            print(f"❌ Нет результата #{pick_n}")
            sys.exit(1)
    elif len(ranked) == 1:
        # Только один вариант — берём без вопросов
        chosen = ranked[0]
        print(f"✅ Единственный вариант: {chosen['name']} (ИНН {chosen['inn']})")
    else:
        # Интерактивный выбор
        try:
            raw = input(f"Выберите номер для проверки (1-{len(ranked)}, Enter = 1, 0 = отмена): ").strip()
            if raw == "0":
                print("Отменено.")
                sys.exit(0)
            n = int(raw) if raw else 1
            if not (1 <= n <= len(ranked)):
                print("❌ Некорректный номер"); sys.exit(1)
            chosen = ranked[n - 1]
        except (EOFError, ValueError):
            # Нет терминала или пустой ввод — берём первый активный
            chosen = ranked[0]
            print(f"↳ Авто-выбор: #{1} {chosen['name']}")

    inn = chosen.get("inn")
    if not inn:
        print("❌ У найденной компании нет ИНН")
        sys.exit(1)

    print(f"\n▶ Запускаем проверку: {chosen['name']} (ИНН {inn})\n")
    sys.exit(run_check(inn, fmt, as_json))

if __name__ == "__main__":
    main()
