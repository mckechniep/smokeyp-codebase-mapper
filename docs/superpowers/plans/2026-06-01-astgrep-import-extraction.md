# ast-grep Import Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace scan.py's regex-based import extraction with tree-sitter-accurate ast-grep extraction, auto-detected with full regex fallback, so the module dependency graph gets sharper edges without adding a hard dependency.

**Architecture:** A new sibling module `astgrep_imports.py` runs ONE batched `ast-grep scan --inline-rules ... --json` subprocess call per scan (verified: 0.084s on a ~97k-file monorepo) and exposes per-language target methods whose return shapes match the existing regex extractors exactly. `build_module_graph` in scan.py asks the bridge first and falls back to the regex extractor per file on any miss. All resolution logic (workspace package names, go.mod prefix stripping, Elixir defmodule index, longest-prefix module matching) is untouched.

**Tech Stack:** Python 3.10+ stdlib only (subprocess + json), ast-grep ≥0.43.0 (optional, auto-detected), unittest.

**Out of scope (deliberately):** Rust as a 6th graph language (ast-grep-only asymmetry — defer); call-graph extraction (Phase B); migrating HTTP-endpoint/ORM regexes.

---

## Verified facts this plan is built on

(From live probing of ast-grep 0.43.0 on 2026-06-01 — see memory `astgrep-integration-research`.)

1. `ast-grep scan --inline-rules "<rules separated by --->" --json=compact <path>` runs all rules for all languages in one invocation. JSON output per match: `ruleId`, `file` (relative to scanned path), `range.start.line` (0-based), `text`, `metaVariables.single.<NAME>.text`.
2. TS/TSX/JS import/export rules MUST use the `kind` + `has` + `field: source` form — the plain pattern `import $C from $SRC` is invalid TS and fails in rule mode (works only in `run` mode).
3. `language: typescript`, `tsx`, and `javascript` are three separate dialects; rules must be duplicated per dialect with unique IDs (duplicate IDs merge silently).
4. Metavariable captures include the quotes for string sources (`SRC` = `'react'`).
5. ast-grep respects .gitignore by default; scan.py's `iter_files` uses its own SKIP_DIRS — so per-file fallback to regex covers any file ast-grep didn't see.
6. Elixir is supported: `alias $MOD` matches both `alias A.B` and `alias A.{B, C}` (capture includes the brace group, expansion happens in Python).

## File structure

| File | Action | Responsibility |
|---|---|---|
| `plugin/skills/map-repo/scripts/astgrep_imports.py` | Create | ast-grep bridge: availability, batched scan, per-language conversion to extractor-compatible shapes |
| `plugin/skills/map-repo/scripts/scan.py` | Modify (`build_module_graph`, lines ~1187–1248) | Ask bridge first, regex fallback per file |
| `plugin/skills/map-repo/scripts/tests/test_imports.py` | Modify | Add pinning tests for `_python_import_targets`, `_go_import_targets`, `_read_go_module_prefix` |
| `plugin/skills/map-repo/scripts/tests/test_astgrep_imports.py` | Create | Bridge unit tests (real ast-grep, skip-decorated) + unavailability test |
| `plugin/skills/map-repo/scripts/tests/fixtures/graph_repo/` | Create | Fixture with real cross-module imports (TS workspace + relative, Python, Go, Elixir) |
| `plugin/skills/map-repo/scripts/tests/test_graph.py` | Create | `build_module_graph` integration: same expected edges in regex mode AND ast-grep mode |

All test commands run from `plugin/skills/map-repo/scripts/`:
```bash
cd /home/mckechniep/ai-llms/claude/mine/smokeyp-codebase-mapper/plugin/skills/map-repo/scripts
```

---

### Task 1: Pin current regex extractor behavior (test-only)

The Python and Go extractors have zero tests. Pin their current behavior BEFORE anything else so the fallback path has a contract.

**Files:**
- Modify: `plugin/skills/map-repo/scripts/tests/test_imports.py`

- [ ] **Step 1: Add the pinning tests**

Append to `tests/test_imports.py`:

```python
class PythonImportTest(unittest.TestCase):
    """Pins _python_import_targets — the regex fallback contract."""

    def test_plain_and_dotted_imports_return_first_segment(self):
        text = "import os\nimport os.path\nimport numpy as np\n"
        self.assertEqual(scan._python_import_targets(text),
                         ["os", "os", "numpy"])

    def test_from_imports_return_first_segment(self):
        text = "from collections import defaultdict\nfrom a.b.c import d\n"
        self.assertEqual(scan._python_import_targets(text), ["collections", "a"])

    def test_relative_imports_are_skipped(self):
        text = "from . import sibling\nfrom ..pkg import other\n"
        self.assertEqual(scan._python_import_targets(text), [])

    def test_indented_imports_inside_functions_are_found(self):
        text = "def f():\n    import json\n    return json\n"
        self.assertEqual(scan._python_import_targets(text), ["json"])


class GoImportTest(unittest.TestCase):
    """Pins _go_import_targets + _read_go_module_prefix — the regex fallback contract."""

    GO = (
        'package main\n\n'
        'import "fmt"\n\n'
        'import (\n'
        '\t"context"\n'
        '\t"github.com/myorg/myapp/auth"\n'
        '\tsvc "github.com/myorg/myapp/service"\n'
        ')\n'
    )

    def test_internal_imports_have_prefix_stripped(self):
        targets = scan._go_import_targets(self.GO, "github.com/myorg/myapp")
        self.assertEqual(targets, ["auth", "service"])

    def test_external_imports_are_dropped(self):
        targets = scan._go_import_targets(self.GO, "github.com/myorg/myapp")
        self.assertNotIn("fmt", targets)
        self.assertNotIn("context", targets)

    def test_no_module_prefix_returns_empty(self):
        self.assertEqual(scan._go_import_targets(self.GO, None), [])

    def test_read_go_module_prefix(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "go.mod").write_text("module github.com/x/y\n\ngo 1.21\n")
            self.assertEqual(scan._read_go_module_prefix(root), "github.com/x/y")
            self.assertIsNone(scan._read_go_module_prefix(root / "nope"))
```

Also add `import tempfile` to the imports at the top of `test_imports.py` if not present (it currently imports only `unittest`, `Path`, `sys`, `scan`).

- [ ] **Step 2: Run the new tests — they should PASS (they pin existing behavior)**

```bash
python3 -m unittest tests.test_imports -v
```
Expected: all tests `ok`, including the 8 new ones. If any new test FAILS, the test's expectation is wrong — fix the test to match actual current behavior (these are pinning tests, not change requests). Read the failure, adjust, re-run.

- [ ] **Step 3: Run the full suite**

```bash
python3 -m unittest discover -s tests
```
Expected: `OK` (44 + 8 = 52 tests).

- [ ] **Step 4: Commit**

```bash
git add tests/test_imports.py
git commit -m "test: pin regex import-extractor behavior for Python and Go"
```

---

### Task 2: graph_repo fixture + integration test (regex mode)

A fixture with real cross-module imports, and a test asserting the exact edges `build_module_graph` produces today. This is the safety net for the whole feature: the ast-grep mode must produce the same edges on this fixture.

**Files:**
- Create: `plugin/skills/map-repo/scripts/tests/fixtures/graph_repo/` (8 files below)
- Create: `plugin/skills/map-repo/scripts/tests/test_graph.py`

- [ ] **Step 1: Create the fixture files**

`tests/fixtures/graph_repo/package.json`:
```json
{ "name": "graph-repo", "private": true, "workspaces": ["apps/*", "packages/*"] }
```

`tests/fixtures/graph_repo/apps/web/package.json`:
```json
{ "name": "@graph/web", "version": "1.0.0", "dependencies": { "@graph/shared": "*" } }
```

`tests/fixtures/graph_repo/apps/web/index.ts`:
```typescript
import { helper } from "@graph/shared";
import { local } from "./local";
export function main() { return helper(local); }
```

`tests/fixtures/graph_repo/apps/web/local.ts`:
```typescript
export const local = 1;
```

`tests/fixtures/graph_repo/packages/shared/package.json`:
```json
{ "name": "@graph/shared", "version": "1.0.0" }
```

`tests/fixtures/graph_repo/packages/shared/index.ts`:
```typescript
export function helper(x: number) { return x + 1; }
```

`tests/fixtures/graph_repo/services/api/main.py`:
```python
import core
from core import models

def handler():
    return models.load()
```

`tests/fixtures/graph_repo/services/core/models.py`:
```python
def load():
    return []
```

- [ ] **Step 2: Write the failing integration test**

`tests/test_graph.py`:
```python
"""Integration tests for build_module_graph on the graph_repo fixture.

The fixture has real cross-module imports:
  - apps/web -> packages/shared   (TS workspace package import "@graph/shared")
  - services/api -> services/core (Python first-segment import "core")

The same expected edges must hold in BOTH extraction modes (regex fallback
and ast-grep). Task 2 pins regex mode; Task 5 adds the ast-grep mode test.
"""

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scan

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "graph_repo"


def build_graph():
    root = FIXTURE.resolve()
    modules = scan.detect_modules(root)
    services = scan.detect_services(root, modules)
    return scan.build_module_graph(root, modules, services)


def edge_set(graph):
    return {(e["source"], e["target"]) for e in graph["edges"]}


class GraphRepoRegexModeTest(unittest.TestCase):
    def test_workspace_package_import_creates_edge(self):
        edges = edge_set(build_graph())
        self.assertIn(("apps/web", "packages/shared"), edges)

    def test_python_first_segment_import_creates_edge(self):
        edges = edge_set(build_graph())
        self.assertIn(("services/api", "services/core"), edges)

    def test_no_self_loops(self):
        for e in build_graph()["edges"]:
            self.assertNotEqual(e["source"], e["target"])


if __name__ == "__main__":
    unittest.main()
```

> **Note on `detect_modules` / `detect_services`:** these are the scan.py functions that produce the `modules` / `services` lists `build_module_graph` consumes. If their actual names differ (check `grep -n "^def detect" scan.py`), use the real names — `build_data_model` (scan.py:2187) shows the exact call sequence to copy. The Python edge expectation also depends on how modules/services are detected for `services/api` and `services/core`; if the Python lookup is service-scoped such that the edge does not appear, adjust the fixture so both Python modules land in the same service (e.g. add `services/api/requirements.txt` and `services/core/requirements.txt` containing `requests\n`), and re-derive the expected edge. The point of this task is to pin WHATEVER the current behavior is — investigate with a debugger/print before changing expectations.

- [ ] **Step 3: Run the test, adjust expectations to current reality**

```bash
python3 -m unittest tests.test_graph -v
```
Expected: tests pass once expectations match current behavior. If `("apps/web", "packages/shared")` is genuinely not produced (e.g. workspace resolution requires a `package.json` field the fixture lacks), fix the FIXTURE (not scan.py) until both edges exist — the fixture's purpose is to exercise the workspace-package and Python resolution paths that fittalk/brevity exercise in production.

- [ ] **Step 4: Run the full suite**

```bash
python3 -m unittest discover -s tests
```
Expected: `OK`. (test_evidence and test_validate_enrichment still use mini_repo — untouched.)

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/graph_repo tests/test_graph.py
git commit -m "test: graph_repo fixture pins module-graph edges end to end"
```

---

### Task 3: astgrep_imports.py — availability + batched collection

**Files:**
- Create: `plugin/skills/map-repo/scripts/astgrep_imports.py`
- Create: `plugin/skills/map-repo/scripts/tests/test_astgrep_imports.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_astgrep_imports.py`:
```python
"""Tests for the ast-grep bridge.

Real-binary tests are skipped when ast-grep is not installed (the bridge is
optional by design). The unavailability test always runs.
"""

import shutil
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import astgrep_imports

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "graph_repo"
HAVE_ASTGREP = shutil.which("ast-grep") is not None


class AvailabilityTest(unittest.TestCase):
    def test_collect_returns_none_when_binary_missing(self):
        # Point the bridge at a binary that does not exist.
        result = astgrep_imports.collect(
            FIXTURE.resolve(), bin_path="/nonexistent/ast-grep")
        self.assertIsNone(result)

    @unittest.skipUnless(HAVE_ASTGREP, "ast-grep not installed")
    def test_collect_returns_bridge_when_available(self):
        result = astgrep_imports.collect(FIXTURE.resolve())
        self.assertIsNotNone(result)


@unittest.skipUnless(HAVE_ASTGREP, "ast-grep not installed")
class CollectionTest(unittest.TestCase):
    def setUp(self):
        self.root = FIXTURE.resolve()
        self.ag = astgrep_imports.collect(self.root)

    def test_finds_hits_in_ts_file(self):
        f = self.root / "apps" / "web" / "index.ts"
        self.assertTrue(self.ag.has_file(f))

    def test_unknown_file_has_no_hits(self):
        f = self.root / "does" / "not" / "exist.ts"
        self.assertFalse(self.ag.has_file(f))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

```bash
python3 -m unittest tests.test_astgrep_imports -v
```
Expected: FAIL/ERROR with `ModuleNotFoundError: No module named 'astgrep_imports'`.

- [ ] **Step 3: Write the bridge core**

`astgrep_imports.py`:
```python
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
            return None
        matches = json.loads(proc.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError):
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
```

- [ ] **Step 4: Run the tests**

```bash
python3 -m unittest tests.test_astgrep_imports -v
```
Expected: all 4 tests `ok` (or 2 `ok` + 2 `skipped` if ast-grep is not installed on the machine running them).

- [ ] **Step 5: Run the full suite, then commit**

```bash
python3 -m unittest discover -s tests
git add astgrep_imports.py tests/test_astgrep_imports.py
git commit -m "feat: ast-grep bridge — availability detection and batched import collection"
```

---

### Task 4: Per-language conversion methods

Add the four conversion methods to `AstGrepImports`, each matching the corresponding regex extractor's contract exactly.

**Files:**
- Modify: `plugin/skills/map-repo/scripts/astgrep_imports.py`
- Modify: `plugin/skills/map-repo/scripts/tests/test_astgrep_imports.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_astgrep_imports.py` (inside the file, after CollectionTest). Note the fixture additions: this task also adds Go and Elixir files to graph_repo so every conversion has real input.

New fixture files (create in this step):

`tests/fixtures/graph_repo/services/gosvc/go.mod`:
```
module github.com/graph/gosvc

go 1.21
```

`tests/fixtures/graph_repo/services/gosvc/main.go`:
```go
package main

import "fmt"

import (
	"github.com/graph/gosvc/auth"
)

func main() { fmt.Println(auth.Token()) }
```

`tests/fixtures/graph_repo/services/gosvc/auth/auth.go`:
```go
package auth

func Token() string { return "t" }
```

`tests/fixtures/graph_repo/apps/exapp/lib/exapp.ex`:
```elixir
defmodule Exapp do
  alias Exapp.{Repo, Worker}
  import Exapp.Helpers
  use GenServer

  def start, do: Repo.init()
end
```

`tests/fixtures/graph_repo/apps/exapp/lib/repo.ex`:
```elixir
defmodule Exapp.Repo do
  def init, do: :ok
end
```

Test classes to append:

```python
@unittest.skipUnless(HAVE_ASTGREP, "ast-grep not installed")
class PythonConversionTest(unittest.TestCase):
    def setUp(self):
        self.root = FIXTURE.resolve()
        self.ag = astgrep_imports.collect(self.root)

    def test_python_targets_match_regex_contract(self):
        f = self.root / "services" / "api" / "main.py"
        # main.py has: `import core` and `from core import models`
        # -> first segments, same as scan._python_import_targets
        self.assertEqual(sorted(self.ag.python_targets(f)), ["core", "core"])

    def test_python_targets_for_unseen_file_is_empty(self):
        self.assertEqual(self.ag.python_targets(self.root / "nope.py"), [])


@unittest.skipUnless(HAVE_ASTGREP, "ast-grep not installed")
class JstsConversionTest(unittest.TestCase):
    def setUp(self):
        self.root = FIXTURE.resolve()
        self.ag = astgrep_imports.collect(self.root)

    def test_jsts_targets_split_paths_and_bare(self):
        f = self.root / "apps" / "web" / "index.ts"
        paths, bare = self.ag.jsts_targets(f)
        # "./local" resolves relative to the file's parent
        self.assertIn((f.parent / "./local").resolve(), [p.resolve() for p in paths])
        # "@graph/shared" is a bare workspace specifier
        self.assertIn("@graph/shared", bare)

    def test_quotes_are_stripped(self):
        f = self.root / "apps" / "web" / "index.ts"
        _, bare = self.ag.jsts_targets(f)
        for spec in bare:
            self.assertFalse(spec.startswith("'") or spec.startswith('"'), spec)


@unittest.skipUnless(HAVE_ASTGREP, "ast-grep not installed")
class GoConversionTest(unittest.TestCase):
    def setUp(self):
        self.root = FIXTURE.resolve()
        self.ag = astgrep_imports.collect(self.root)

    def test_go_internal_targets_strip_prefix(self):
        f = self.root / "services" / "gosvc" / "main.go"
        targets = self.ag.go_internal_targets(f, "github.com/graph/gosvc")
        self.assertEqual(targets, ["auth"])

    def test_go_external_imports_dropped(self):
        f = self.root / "services" / "gosvc" / "main.go"
        targets = self.ag.go_internal_targets(f, "github.com/graph/gosvc")
        self.assertNotIn("fmt", targets)

    def test_go_no_prefix_returns_empty(self):
        f = self.root / "services" / "gosvc" / "main.go"
        self.assertEqual(self.ag.go_internal_targets(f, None), [])


@unittest.skipUnless(HAVE_ASTGREP, "ast-grep not installed")
class ElixirConversionTest(unittest.TestCase):
    def setUp(self):
        self.root = FIXTURE.resolve()
        self.ag = astgrep_imports.collect(self.root)

    def test_elixir_refs_include_multi_alias_expansion(self):
        f = self.root / "apps" / "exapp" / "lib" / "exapp.ex"
        refs = self.ag.elixir_reference_targets(f)
        self.assertIn("Exapp.Repo", refs)
        self.assertIn("Exapp.Worker", refs)
        self.assertIn("Exapp.Helpers", refs)
        self.assertIn("GenServer", refs)

    def test_elixir_defmodules(self):
        f = self.root / "apps" / "exapp" / "lib" / "repo.ex"
        self.assertEqual(self.ag.elixir_defmodules(f), ["Exapp.Repo"])
```

- [ ] **Step 2: Run to verify failures**

```bash
python3 -m unittest tests.test_astgrep_imports -v
```
Expected: new tests ERROR with `AttributeError: 'AstGrepImports' object has no attribute 'python_targets'` (etc.). Existing tests still pass. Note: test_graph.py from Task 2 must also still pass — the new fixture files add modules but the asserted edges remain.

- [ ] **Step 3: Implement the conversion methods**

Add to the `AstGrepImports` class in `astgrep_imports.py`:

```python
    @staticmethod
    def _strip_quotes(s: str) -> str:
        s = s.strip()
        if len(s) >= 2 and s[0] in "'\"" and s[-1] == s[0]:
            return s[1:-1]
        return s

    # --- Python: contract of scan._python_import_targets -----------------
    def python_targets(self, file_path: Path) -> list[str]:
        """First-segment package names; relative imports skipped."""
        out: list[str] = []
        for rule_id, cap in self._file_hits(file_path):
            if rule_id not in ("py-import", "py-from-import"):
                continue
            mod = cap.strip()
            if not mod or mod.startswith("."):
                continue  # relative import
            # `import numpy as np` captures "numpy as np" -> take the module part
            mod = mod.split()[0]
            first = mod.split(".")[0]
            if first:
                out.append(first)
        return out

    # --- JS/TS: contract of scan._jsts_import_targets --------------------
    def jsts_targets(self, file_path: Path) -> tuple[list[Path], list[str]]:
        """(resolved relative/absolute path imports, bare specifiers)."""
        paths: list[Path] = []
        bare: list[str] = []
        jsts_rules = tuple(
            f"{d}-{kind}" for d in _TS_DIALECTS
            for kind in ("import", "export-from", "require", "dynamic-import")
        )
        parent = file_path.parent
        for rule_id, cap in self._file_hits(file_path):
            if rule_id not in jsts_rules:
                continue
            spec = self._strip_quotes(cap)
            if not spec:
                continue
            if spec.startswith(".") or spec.startswith("/"):
                try:
                    paths.append((parent / spec).resolve())
                except (OSError, RuntimeError):
                    continue
            else:
                bare.append(spec)
        return paths, bare

    # --- Go: contract of scan._go_import_targets -------------------------
    def go_internal_targets(self, file_path: Path, module_prefix: str | None) -> list[str]:
        """Internal package paths with the go.mod module prefix stripped."""
        if not module_prefix:
            return []
        out: list[str] = []
        prefix = module_prefix.rstrip("/") + "/"
        for rule_id, cap in self._file_hits(file_path):
            if rule_id != "go-import":
                continue
            # import_spec text: `"fmt"` or `alias "github.com/x/y"`
            quoted = cap.strip()
            if '"' in quoted:
                quoted = quoted.split('"')[1]
            if quoted == module_prefix:
                out.append("")
            elif quoted.startswith(prefix):
                out.append(quoted[len(prefix):])
        return out

    # --- Elixir: contracts of scan._elixir_reference_targets / _elixir_defmodules
    def elixir_reference_targets(self, file_path: Path) -> list[str]:
        """Module names referenced via alias/import/use/require, multi-alias expanded."""
        out: list[str] = []
        for rule_id, cap in self._file_hits(file_path):
            if rule_id != "elixir-ref":
                continue
            ref = cap.strip()
            if "{" in ref and ref.endswith("}"):
                base, _, group = ref.partition(".{")
                for part in group.rstrip("}").split(","):
                    part = part.strip()
                    if part:
                        out.append(f"{base}.{part}")
            elif ref:
                out.append(ref.rstrip("."))
        return out

    def elixir_defmodules(self, file_path: Path) -> list[str]:
        """Module names declared via defmodule in this file."""
        return [
            cap.strip() for rule_id, cap in self._file_hits(file_path)
            if rule_id == "elixir-defmodule" and cap.strip()
        ]
```

> **Capture caveat to verify while implementing:** for `py-import`, the `$MOD` capture for `import numpy as np` may be `numpy` (alias outside the capture) or `numpy as np` (alias inside) depending on the grammar's node structure — the `.split()[0]` handles both. Similarly `elixir-ref`'s capture for `alias Exapp.{Repo, Worker}` may or may not include the brace group. The tests in Step 1 assert the OUTcome (correct expansion), so run them, observe the actual capture via `python3 -c "import astgrep_imports; ag = astgrep_imports.collect(...); print(ag._hits)"`, and adjust the conversion (not the test) if the capture shape differs.

- [ ] **Step 4: Run the tests until green**

```bash
python3 -m unittest tests.test_astgrep_imports -v && python3 -m unittest discover -s tests
```
Expected: all `ok` / `OK`.

- [ ] **Step 5: Commit**

```bash
git add astgrep_imports.py tests/test_astgrep_imports.py tests/fixtures/graph_repo
git commit -m "feat: ast-grep per-language conversions matching regex extractor contracts"
```

---

### Task 5: Wire into build_module_graph with per-file fallback

**Files:**
- Modify: `plugin/skills/map-repo/scripts/scan.py` (import block ~line 23, `build_module_graph` ~lines 1187–1248)
- Modify: `plugin/skills/map-repo/scripts/tests/test_graph.py`

- [ ] **Step 1: Write the failing test (ast-grep mode must produce the same edges)**

Append to `tests/test_graph.py`:

```python
import shutil

HAVE_ASTGREP = shutil.which("ast-grep") is not None


@unittest.skipUnless(HAVE_ASTGREP, "ast-grep not installed")
class GraphRepoAstGrepModeTest(unittest.TestCase):
    """The same fixture must produce the same edges via ast-grep extraction."""

    def test_same_edges_as_regex_mode(self):
        graph = build_graph()  # ast-grep auto-detected -> used
        edges = edge_set(graph)
        self.assertIn(("apps/web", "packages/shared"), edges)
        self.assertIn(("services/api", "services/core"), edges)

    def test_extraction_mode_is_reported(self):
        graph = build_graph()
        self.assertEqual(graph.get("extraction"), "ast-grep")


class GraphRepoForcedFallbackTest(unittest.TestCase):
    """With ast-grep unavailable, regex fallback produces the same edges."""

    def test_same_edges_with_fallback(self):
        import os
        os.environ["AST_GREP_BIN"] = "/nonexistent/ast-grep"
        try:
            graph = build_graph()
            edges = edge_set(graph)
            self.assertIn(("apps/web", "packages/shared"), edges)
            self.assertIn(("services/api", "services/core"), edges)
            self.assertEqual(graph.get("extraction"), "regex")
        finally:
            del os.environ["AST_GREP_BIN"]
```

- [ ] **Step 2: Run to verify failure**

```bash
python3 -m unittest tests.test_graph -v
```
Expected: `test_extraction_mode_is_reported` and `test_same_edges_with_fallback` FAIL (`graph.get("extraction")` is None — key doesn't exist yet). Edge tests may already pass via regex.

- [ ] **Step 3: Modify scan.py**

Add the import after `import evidence` (line 23):
```python
import astgrep_imports
```

In `build_module_graph`, after `index = _build_module_index(modules, root)` (line ~1136), add:
```python
    # Optional AST-accurate extraction: one batched ast-grep call for the
    # whole repo. None when the binary is absent or anything fails — every
    # use below falls back to the regex extractor per file.
    ag = astgrep_imports.collect(root)
```

Replace the Elixir pre-pass loop body (lines ~1190–1196):
```python
    elixir_module_index: dict[str, Path] = {}
    for m in modules:
        for f in iter_files((root / m["path"]).resolve()):
            if f.suffix.lower() in (".ex", ".exs"):
                if ag and ag.has_file(f):
                    names = ag.elixir_defmodules(f)
                else:
                    etext = safe_read(f, limit=256 * 1024)
                    names = _elixir_defmodules(etext) if etext else []
                for name in names:
                    elixir_module_index.setdefault(name, f)
```

Replace the four dispatch branches (lines ~1220–1248):
```python
            use_ag = ag is not None and ag.has_file(f)

            if lname == "Python":
                targets = ag.python_targets(f) if use_ag else _python_import_targets(text)
                for first in targets:
                    target_id = py_names.get(first)
                    if target_id:
                        _bump_edge(edges, source_id, target_id)
            elif lname in ("JavaScript", "TypeScript"):
                if use_ag:
                    js_paths, js_bare = ag.jsts_targets(f)
                else:
                    js_paths, js_bare = _jsts_import_targets(f, text)
                for abs_target in js_paths:
                    target_id = _module_for(abs_target, index)
                    if target_id:
                        _bump_edge(edges, source_id, target_id)
                for spec in js_bare:
                    pkg = _pkg_name_of_specifier(spec)
                    target_id = workspace_pkg_to_module.get(pkg) if pkg else None
                    if target_id:
                        _bump_edge(edges, source_id, target_id)
            elif lname == "Go":
                if use_ag:
                    internals = ag.go_internal_targets(f, go_prefix)
                else:
                    internals = _go_import_targets(text, go_prefix)
                for internal in internals:
                    candidate = (root / internal).resolve() if internal else root
                    target_id = _module_for(candidate, index)
                    if target_id:
                        _bump_edge(edges, source_id, target_id)
            elif lname == "Elixir":
                if use_ag:
                    refs = ag.elixir_reference_targets(f)
                else:
                    refs = _elixir_reference_targets(text)
                for ref in refs:
                    deffile = elixir_module_index.get(ref)
                    if deffile:
                        target_id = _module_for(deffile, index)
                        if target_id:
                            _bump_edge(edges, source_id, target_id)
```

In the return dict (line ~1267), add the extraction-mode field:
```python
    return {
        "nodes": nodes,
        "edges": edge_list,
        "services": service_summary,
        "languages_parsed": sorted(languages_parsed),
        "languages_unparsed": sorted(languages_unparsed - languages_parsed),
        "extraction": "ast-grep" if ag is not None else "regex",
    }
```

Also update `astgrep_imports.collect()` to honor the env override set in tests — it already does via `_find_binary` reading `AST_GREP_BIN`.

> **JS/TS resolution nuance:** `_jsts_import_targets` resolves `./local` to `<parent>/local` (no extension). `_module_for` then longest-prefix-matches it into a module. The ast-grep path produces the same parent-relative resolution in `jsts_targets`, so behavior is identical. Verify with the fixture test; if the resolved-path forms differ (e.g. `local` vs `local.ts`), normalize inside `jsts_targets` to match the regex extractor (resolve WITHOUT adding extensions — exactly `(parent / spec).resolve()`).

- [ ] **Step 4: Run the graph tests, then the full suite**

```bash
python3 -m unittest tests.test_graph -v && python3 -m unittest discover -s tests
```
Expected: all `ok` / `OK`. The golden fittalk render test is unaffected (it renders a stored codemap.json — scanning behavior is not part of that test).

- [ ] **Step 5: Commit**

```bash
git add plugin/skills/map-repo/scripts/scan.py tests/test_graph.py
git commit -m "feat: AST-accurate import extraction via ast-grep with per-file regex fallback"
```

---

### Task 6: Real-repo verification + release

**Files:**
- Modify: `README.md` (roadmap)
- Modify: `plugin/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `plugin/skills/map-repo/scripts/scan.py:25` (TOOL_VERSION) — release commit only

- [ ] **Step 1: Re-scan fittalk-monorepo in both modes and diff the edges**

```bash
cd /home/mckechniep/ai-llms/claude/mine/smokeyp-codebase-mapper/plugin/skills/map-repo/scripts
python3 scan.py --path ~/projects/fittalk-monorepo --depth medium --out /tmp/fittalk-astgrep.json
AST_GREP_BIN=/nonexistent python3 scan.py --path ~/projects/fittalk-monorepo --depth medium --out /tmp/fittalk-regex.json
python3 - <<'EOF'
import json
ag = json.load(open('/tmp/fittalk-astgrep.json'))['module_graph']
rx = json.load(open('/tmp/fittalk-regex.json'))['module_graph']
ag_e = {(e['source'], e['target']) for e in ag['edges']}
rx_e = {(e['source'], e['target']) for e in rx['edges']}
print(f"extraction modes: {ag.get('extraction')} vs {rx.get('extraction')}")
print(f"edges: ast-grep={len(ag_e)} regex={len(rx_e)}")
print(f"only in ast-grep: {sorted(ag_e - rx_e)}")
print(f"only in regex:    {sorted(rx_e - ag_e)}")
EOF
```

Expected: `extraction modes: ast-grep vs regex`. Edge sets should be identical or ast-grep should have a superset / more accurate set. **Manually review every difference**: each edge only-in-regex is either a regex false positive (good — ast-grep removed noise, e.g. an import inside a comment or string) or an ast-grep miss (bad — investigate before shipping). Record the findings in the commit message.

- [ ] **Step 2: Render both and eyeball the matrix diagram**

```bash
python3 render.py --in /tmp/fittalk-astgrep.json --out /tmp/fittalk-astgrep.html
python3 render.py --in /tmp/fittalk-regex.json --out /tmp/fittalk-regex.html
```
Open both in a browser; the dependency matrix should look equally good or better (more edges = more filled cells).

- [ ] **Step 3: Update the README roadmap**

In `README.md`, replace the `- **v0.7.0** —` line with:
```markdown
- **v0.7.0** *(shipped)* — AST-accurate import extraction: when the `ast-grep` binary is present, the module dependency graph is built from tree-sitter parses (one batched scan, ~0.1s even on large monorepos) instead of regexes — catching `import type`, re-exports, dynamic imports, and multi-line forms the regexes miss. Auto-detected with full regex fallback, so nothing new is required. Groundwork for the v1.0.0 call-graph backend.
- **v0.8.0** — TypeScript path-alias support, Express `app.use('/api', router)` mount following, third-party service detection (external API calls grouped as "outbound services" node)
```
And renumber the existing v0.8.0/v0.9.0 lines to v0.9.0/v0.10.0 (keep v1.0.0 as-is).

- [ ] **Step 4: Confirm release with the user, then bump versions and tag**

Per versioning rules this is a MINOR bump (new feature, pre-1.0): 0.6.1 → 0.7.0. Ask the user to confirm the release, then:

```bash
sed -i 's/TOOL_VERSION = "0.6.1"/TOOL_VERSION = "0.7.0"/' plugin/skills/map-repo/scripts/scan.py
sed -i 's/"version": "0.6.1",/"version": "0.7.0",/' plugin/.claude-plugin/plugin.json
sed -i 's/"version": "0.6.1"/"version": "0.7.0"/' .claude-plugin/marketplace.json
cd plugin/skills/map-repo/scripts && python3 -m unittest discover -s tests && cd -
git add -A && git commit -m "chore(release): 0.7.0" && git tag -a v0.7.0 -m "Release 0.7.0"
```

---

## Self-review

**Spec coverage:** auto-detect ✓ (Task 3 `_find_binary`), regex fallback ✓ (Task 5 per-file `use_ag` conditionals + forced-fallback test), extraction parity ✓ (Tasks 2+5 same-edges tests), no new hard dependency ✓ (every failure path returns None → regex), performance ✓ (one batched call, Task 6 verifies on fittalk), pre-work test gaps ✓ (Task 1).

**Known uncertainties flagged inline:** `detect_modules`/`detect_services` function names (Task 2 note), metavariable capture shapes for Python alias imports and Elixir multi-alias (Task 4 caveat), JS/TS resolved-path normalization (Task 5 nuance). Each has a verification step and an adjust-the-conversion-not-the-test rule.

**Type consistency:** `collect(root, bin_path=None) -> AstGrepImports | None`; `python_targets(Path) -> list[str]`; `jsts_targets(Path) -> tuple[list[Path], list[str]]`; `go_internal_targets(Path, str|None) -> list[str]`; `elixir_reference_targets(Path) -> list[str]`; `elixir_defmodules(Path) -> list[str]`; `has_file(Path) -> bool` — used consistently across Tasks 3–5.
