"""Optional ast-grep (tree-sitter) import extraction for the module graph.

When the `ast-grep` binary is present, scan.py's build_module_graph uses this
bridge for AST-accurate import extraction; when it is absent (or any error
occurs), scan.py falls back to its built-in regex extractors per file. The
bridge therefore never raises — every failure path returns None / empty.

One batched `ast-grep scan --inline-rules ... --json` call covers all
languages and all import forms (~0.1s even on very large repos). Output
shapes returned by the per-language methods MATCH the regex extractors in
scan.py exactly, so all resolution logic stays unchanged.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Same override mechanism as GREPAI_BIN in semantic_index.sh: tests (and
# users with non-PATH installs) can point at a specific binary.
AST_GREP_BIN_ENV = "AST_GREP_BIN"

_TS_DIALECTS = ("typescript", "tsx", "javascript")

# Verified against ast-grep 0.43.0. Notes:
#  * import/export rules use kind + has/field:source — the plain pattern form
#    fails in rule mode (pattern text is not valid standalone TS).
#  * rule IDs must be unique across dialects (duplicates merge silently).
_RULES: list[str] = []
for _d in _TS_DIALECTS:
    _RULES += [
        f"id: {_d}-import\nlanguage: {_d}\nseverity: info\nrule:\n"
        "  kind: import_statement\n  has:\n    field: source\n    pattern: $SRC",
        f"id: {_d}-export-from\nlanguage: {_d}\nseverity: info\nrule:\n"
        "  kind: export_statement\n  has:\n    field: source\n    pattern: $SRC",
        f"id: {_d}-require\nlanguage: {_d}\nseverity: info\nrule:\n"
        "  pattern: require($SRC)",
        f"id: {_d}-dynamic-import\nlanguage: {_d}\nseverity: info\nrule:\n"
        "  pattern: import($SRC)",
    ]
_RULES += [
    "id: py-import\nlanguage: python\nseverity: info\nrule:\n  pattern: import $MOD",
    "id: py-from-import\nlanguage: python\nseverity: info\nrule:\n"
    "  pattern: from $MOD import $$$NAMES",
    "id: go-import\nlanguage: go\nseverity: info\nrule:\n  kind: import_spec",
    "id: elixir-ref\nlanguage: elixir\nseverity: info\nrule:\n  any:\n"
    "    - pattern: alias $MOD\n    - pattern: import $MOD\n"
    "    - pattern: use $MOD\n    - pattern: require $MOD",
    "id: elixir-defmodule\nlanguage: elixir\nseverity: info\nrule:\n"
    "  pattern: defmodule $MOD do $$$BODY end",
]
RULES_YAML = "\n---\n".join(_RULES)

# A match: (rule_id, primary capture text or full match text).
Hit = tuple[str, str]


class AstGrepImports:
    """Per-file import hits from one batched ast-grep scan of a repo root."""

    def __init__(self, root: Path, hits_by_file: dict[Path, list[Hit]]):
        self._root = root
        self._hits = hits_by_file

    def has_file(self, file_path: Path) -> bool:
        try:
            return file_path.resolve() in self._hits
        except (OSError, RuntimeError):
            return False

    def _file_hits(self, file_path: Path) -> list[Hit]:
        try:
            return self._hits.get(file_path.resolve(), [])
        except (OSError, RuntimeError):
            return []


def _find_binary(bin_path: str | None) -> str | None:
    candidate = bin_path or os.environ.get(AST_GREP_BIN_ENV) or "ast-grep"
    return shutil.which(candidate) or (candidate if Path(candidate).is_file() else None)


def collect(root: Path, bin_path: str | None = None) -> AstGrepImports | None:
    """Run the batched scan. Returns None when ast-grep is unavailable or fails."""
    binary = _find_binary(bin_path)
    if not binary:
        return None
    try:
        proc = subprocess.run(
            [binary, "scan", "--inline-rules", RULES_YAML, "--json=compact", "."],
            capture_output=True, text=True, cwd=str(root), timeout=120,
        )
        if proc.returncode != 0:
            print("[astgrep_imports] ast-grep exited "
                  f"{proc.returncode}; falling back to regex extraction", file=sys.stderr)
            return None
        matches = json.loads(proc.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError) as exc:
        print(f"[astgrep_imports] ast-grep failed ({type(exc).__name__}); "
              "falling back to regex extraction", file=sys.stderr)
        return None

    if not isinstance(matches, list):
        print("[astgrep_imports] ast-grep output was not a JSON array; "
              "falling back to regex extraction", file=sys.stderr)
        return None

    hits: dict[Path, list[Hit]] = {}
    for m in matches:
        rule_id = m.get("ruleId", "")
        file_rel = m.get("file", "")
        if not rule_id or not file_rel:
            continue
        single = (m.get("metaVariables") or {}).get("single") or {}
        # The capture of interest is SRC (TS/JS) or MOD (python/elixir);
        # kind-only rules (go-import) have no capture -> use the match text.
        cap = (single.get("SRC") or single.get("MOD") or {}).get("text") or m.get("text", "")
        try:
            key = (root / file_rel).resolve()
        except (OSError, RuntimeError):
            continue
        hits.setdefault(key, []).append((rule_id, cap))
    return AstGrepImports(root, hits)
