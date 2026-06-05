"""Deterministic HTTP-handler symbol extraction via ast-grep.

Mirrors astgrep_imports.py: a single batched scan, never raises, returns an
empty dict on any failure. Maps a file's relative path -> list of handler
symbol names. Frameworks not covered contribute nothing; a skeleton with
symbols == [] is valid (the LLM fills the symbol during narration).

Supported frameworks:
- NestJS (@Get/@Post/... decorated controller methods) — TypeScript
- FastAPI / Flask-style (@app.get/@router.post/... decorated functions) — Python
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Same override mechanism as AST_GREP_BIN in astgrep_imports.py.
AST_GREP_BIN_ENV = "AST_GREP_BIN"

# Verified against ast-grep 0.43.0.
# NestJS rule: method_definition that follows a decorator matching HTTP verbs.
# In tree-sitter TS grammar, class-member decorators are sibling nodes that
# appear immediately before the method_definition in the class_body — so
# `follows: {kind: decorator, regex: ...}` is the correct structural match.
#
# Python rule: decorated_definition that contains both a function_definition
# (for the name capture) and a decorator matching route-style patterns.
#
# IMPORTANT: use YAML single-quoted scalars for regex values so that
# backslashes are passed literally to the regex engine — YAML double-quoted
# scalars treat `\(` as an unknown escape and ast-grep rejects the rule.
_RULES_LIST = [
    # NestJS HTTP-verb decorators (@Get, @Post, @Put, @Patch, @Delete, @All,
    # @Head, @Options) — the regex uses \( to match a literal open paren after
    # the verb name, ruling out e.g. @Getter or @GetMetadata.
    "id: nest-handler\n"
    "language: TypeScript\n"
    "severity: info\n"  # else default 'error' can make the scan exit non-zero
    "rule:\n"
    "  kind: method_definition\n"
    "  all:\n"
    "    - has:\n"
    "        field: name\n"
    "        pattern: $NAME\n"
    "    - follows:\n"
    "        kind: decorator\n"
    "        regex: '@(Get|Post|Put|Patch|Delete|All|Head|Options)\\('",
    # FastAPI / Flask-style route decorators (@app.get, @router.post, etc.)
    # The regex \. matches a literal dot so e.g. bare @get('/x') (no object
    # prefix) is excluded; \( ensures we match the opening paren.
    "id: py-route-handler\n"
    "language: Python\n"
    "severity: info\n"
    "rule:\n"
    "  kind: decorated_definition\n"
    "  all:\n"
    "    - has:\n"
    "        kind: function_definition\n"
    "        has:\n"
    "          field: name\n"
    "          pattern: $NAME\n"
    "    - has:\n"
    "        kind: decorator\n"
    "        regex: '\\.(get|post|put|patch|delete|route)\\('",
]

RULES_YAML = "\n---\n".join(_RULES_LIST)

_HANDLER_RULE_IDS = {"nest-handler", "py-route-handler"}


def _find_binary(bin_path: str | None) -> str | None:
    candidate = bin_path or os.environ.get(AST_GREP_BIN_ENV) or "ast-grep"
    return shutil.which(candidate) or (candidate if Path(candidate).is_file() else None)


def collect(root: Path, bin_path: str | None = None) -> dict[str, list[str]]:
    """Return {file_rel_path: [handler symbol names]}. Empty dict on any failure."""
    binary = _find_binary(bin_path)
    if not binary:
        return {}
    try:
        proc = subprocess.run(
            [binary, "scan", "--inline-rules", RULES_YAML, "--json=compact", "."],
            capture_output=True, text=True, cwd=str(root), timeout=120,
        )
        if proc.returncode != 0:
            print(f"[astgrep_handlers] ast-grep exited {proc.returncode}; "
                  "skipping handler symbols", file=sys.stderr)
            return {}
        matches = json.loads(proc.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError) as exc:
        print(f"[astgrep_handlers] ast-grep failed ({type(exc).__name__}); "
              "skipping handler symbols", file=sys.stderr)
        return {}
    if not isinstance(matches, list):
        print("[astgrep_handlers] ast-grep output was not a JSON array; "
              "skipping handler symbols", file=sys.stderr)
        return {}

    out: dict[str, list[str]] = {}
    for m in matches:
        if m.get("ruleId") not in _HANDLER_RULE_IDS:
            continue
        file_rel = m.get("file", "")
        single = (m.get("metaVariables") or {}).get("single") or {}
        name = (single.get("NAME") or {}).get("text")
        if not file_rel or not name:
            continue
        names = out.setdefault(file_rel, [])
        if name not in names:
            names.append(name)
    return out
