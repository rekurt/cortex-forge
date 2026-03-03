#!/usr/bin/env python3
"""
QMD — быстрый полнотекстовый поиск по .md файлам.

Skill для service-agent. Читает JSON из stdin, пишет JSON в stdout.
Рекурсивный обход директорий с поиском по содержимому .md файлов.

Scopes:
  workspace — /home/node/.openclaw/workspace/
  shared    — /shared/docs/ + /shared/skills/
  skills    — /shared/skills/ only
  all       — всё вышеперечисленное

Python stdlib only. No pip.
"""

import json
import os
import re
import sys
import time

# Directories per scope (overridable via env for testing)
_WORKSPACE_DIR = os.environ.get("QMD_WORKSPACE_DIR", "/home/node/.openclaw/workspace/")
_SHARED_DOCS_DIR = os.environ.get("QMD_SHARED_DOCS_DIR", "/shared/docs/")
_SHARED_SKILLS_DIR = os.environ.get("QMD_SHARED_SKILLS_DIR", "/shared/skills/")

SCOPE_DIRS = {
    "workspace": [_WORKSPACE_DIR],
    "shared": [_SHARED_DOCS_DIR, _SHARED_SKILLS_DIR],
    "skills": [_SHARED_SKILLS_DIR],
    "all": [_WORKSPACE_DIR, _SHARED_DOCS_DIR, _SHARED_SKILLS_DIR],
}

MAX_FILE_SIZE = 512 * 1024  # 512 KB — skip huge files
CONTEXT_LINES = 3  # lines around match to include
SEARCH_TIMEOUT = 10  # seconds


def search_md_files(query, scope, max_results):
    """Search .md files in given scope for query. Returns list of matches."""
    dirs = SCOPE_DIRS.get(scope, SCOPE_DIRS["all"])

    # Try to compile as regex; fall back to literal (case-insensitive)
    try:
        pattern = re.compile(query, re.IGNORECASE)
    except re.error:
        pattern = re.compile(re.escape(query), re.IGNORECASE)

    results = []
    files_scanned = 0
    start = time.time()

    for search_dir in dirs:
        if not os.path.isdir(search_dir):
            continue

        for dirpath, _dirnames, filenames in os.walk(search_dir):
            if time.time() - start > SEARCH_TIMEOUT:
                break

            for fname in filenames:
                if not fname.lower().endswith(".md"):
                    continue

                fpath = os.path.join(dirpath, fname)

                try:
                    fsize = os.path.getsize(fpath)
                except OSError:
                    continue
                if fsize > MAX_FILE_SIZE:
                    continue

                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()
                except OSError:
                    continue

                files_scanned += 1
                match_count = 0
                file_matches = []

                for i, line in enumerate(lines):
                    if pattern.search(line):
                        match_count += 1
                        # Context: 3 lines before and after
                        ctx_start = max(0, i - CONTEXT_LINES)
                        ctx_end = min(len(lines), i + CONTEXT_LINES + 1)
                        context = "".join(lines[ctx_start:ctx_end]).rstrip()

                        file_matches.append({
                            "line_number": i + 1,
                            "context": context,
                        })

                if match_count > 0:
                    results.append({
                        "file": fpath,
                        "match_count": match_count,
                        "matches": file_matches[:5],  # limit matches per file
                    })

                if len(results) >= max_results:
                    break

            if len(results) >= max_results:
                break

        if len(results) >= max_results or time.time() - start > SEARCH_TIMEOUT:
            break

    elapsed_ms = int((time.time() - start) * 1000)
    return results, files_scanned, elapsed_ms


def main():
    raw = sys.stdin.read()
    try:
        params = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as e:
        print(json.dumps({"status": "error", "error": f"Invalid JSON input: {e}"}))
        sys.exit(1)

    query = params.get("query", "").strip()
    if not query:
        print(json.dumps({
            "status": "error",
            "error": "Missing 'query' parameter",
        }))
        sys.exit(1)

    scope = params.get("scope", "all").strip().lower()
    if scope not in SCOPE_DIRS:
        print(json.dumps({
            "status": "error",
            "error": f"Unknown scope: {scope}. Use: all, workspace, shared, skills",
        }))
        sys.exit(1)

    max_results = params.get("max_results", 10)
    try:
        max_results = int(max_results)
    except (ValueError, TypeError):
        max_results = 10
    max_results = max(1, min(max_results, 50))  # clamp to [1, 50]

    results, files_scanned, elapsed_ms = search_md_files(query, scope, max_results)

    total_matches = sum(r["match_count"] for r in results)

    print(json.dumps({
        "status": "ok",
        "query": query,
        "scope": scope,
        "results": results,
        "total_files_with_matches": len(results),
        "total_matches": total_matches,
        "files_scanned": files_scanned,
        "elapsed_ms": elapsed_ms,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
