# LLM Evaluation Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an additive, LLM-authored semantic layer (project overview, product-vs-vendored classification, per-module descriptions, and cited user/execution flows) to the codebase-mapper report, without disturbing the deterministic scanner/renderer.

**Architecture:** `scan.py` emits a bounded evidence pack alongside the unchanged deterministic `codemap.json`. Claude (in the `map-repo` skill) reads the pack and writes a schema'd sidecar `codemap.enrichment.json`. `render.py` merges the sidecar via an optional `--enrichment` flag and degrades to today's exact output when it is absent.

**Tech Stack:** Python 3.10+ stdlib only (no pip install — tests use stdlib `unittest`). HTML/CSS/SVG output rendered by `render.py`; PDF via headless Chrome.

**Spec:** `docs/superpowers/specs/2026-05-29-llm-evaluation-layer-design.md`

---

## Conventions for this plan

- All script paths are under `plugin/skills/map-repo/scripts/`. This is abbreviated below as `scripts/`.
- Tests live in `scripts/tests/` and run with `python3 -m unittest discover -s plugin/skills/map-repo/scripts/tests -v` from the repo root. (pytest can also run them if preferred.)
- Work happens on branch `llm-evaluation-layer` (already created).
- The module join key between enrichment and the report is the module's **`path`** field (the human-readable string shown on each card, e.g. `g.frame-develop/packages/g.frame.examples`). Task 1 Step 0 confirms this key exists.

---

## File Structure

**Created:**
- `scripts/evidence.py` — builds the bounded evidence pack from the scanned data model + repo. One responsibility: select & truncate high-signal files within a byte budget.
- `scripts/validate_enrichment.py` — validates `codemap.enrichment.json` against the schema and verifies cited files exist. Importable (functions) + runnable (CLI).
- `scripts/tests/__init__.py` — empty, marks the test package.
- `scripts/tests/test_evidence.py` — tests for evidence-pack selection/budget/determinism.
- `scripts/tests/test_validate_enrichment.py` — tests for schema + citation validation.
- `scripts/tests/test_render_enrichment.py` — tests for render degradation + new sections.
- `scripts/tests/fixtures/mini_repo/` — a tiny synthetic repo (a product module + a vendored `*-master` module) used by evidence + render tests.

**Modified:**
- `scripts/scan.py` — add `--evidence-out` arg; call `evidence.build_evidence_pack` and write the pack when requested. No change to `codemap.json` content.
- `scripts/render.py` — add `--enrichment` arg; thread an optional `enrichment` dict through `render_document`; add `render_overview`; demote `render_readme`; product/vendored treatment in `render_modules`; add `render_key_flows`; add CSS.
- `plugin/skills/map-repo/SKILL.md` — add Step 1.5 (LLM evaluation), `--no-llm` arg, and wire `--evidence-out` / `--enrichment` into the pipeline.
- `README.md` — document the evaluation layer + `--no-llm` flag (Phase 1 close-out).

---

# PHASE 1 — Overview, classification, descriptions, and plumbing

## Task 1: Evidence-pack builder (`evidence.py`)

**Files:**
- Create: `scripts/evidence.py`
- Create: `scripts/tests/__init__.py`
- Create: `scripts/tests/test_evidence.py`
- Create fixtures: `scripts/tests/fixtures/mini_repo/...`

- [ ] **Step 0: Confirm the module record shape**

Run: `python3 -c "import json; d=json.load(open('/home/mckechniep/projects/fittalk-monorepo/.codemap/codemap.json')); print(list(d['modules'][0].keys()))"`
Expected: a list including `path`, `loc`, `file_count`, `languages`, `description`. Confirm `path` is present (it is the join key). If a module also has `id`, note it but still key on `path`.

- [ ] **Step 1: Create the fixture repo**

Create these files (exact contents):

`scripts/tests/fixtures/mini_repo/apps/web/package.json`
```json
{ "name": "web", "description": "Customer-facing web app.", "version": "1.0.0" }
```

`scripts/tests/fixtures/mini_repo/apps/web/README.md`
```markdown
# web

[![NPM](https://img.shields.io/badge/npm-x-blue)](https://npm.im/web)

The customer-facing web application. Renders the dashboard.
```

`scripts/tests/fixtures/mini_repo/apps/web/index.ts`
```ts
export function main() { return "web entry"; }
```

`scripts/tests/fixtures/mini_repo/vendor-lib-master/package.json`
```json
{ "name": "vendor-lib", "description": "Third party lib.", "license": "MIT" }
```

`scripts/tests/fixtures/mini_repo/vendor-lib-master/index.js`
```js
module.exports = {};
```

`scripts/tests/fixtures/mini_repo/README.md`
```markdown
# mini

A tiny fixture repo for tests.
```

- [ ] **Step 2: Write the failing test**

`scripts/tests/test_evidence.py`
```python
import json
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scan
import evidence

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mini_repo"


class EvidencePackTest(unittest.TestCase):
    def setUp(self):
        self.data = scan.build_data_model(FIXTURE, "full")

    def test_includes_manifests_and_readmes(self):
        pack = evidence.build_evidence_pack(FIXTURE, self.data, budget_bytes=200_000)
        paths = {f["path"] for f in pack["files"]}
        self.assertIn("apps/web/package.json", paths)
        self.assertIn("apps/web/README.md", paths)
        self.assertIn("README.md", paths)

    def test_includes_entry_points(self):
        pack = evidence.build_evidence_pack(FIXTURE, self.data, budget_bytes=200_000)
        paths = {f["path"] for f in pack["files"]}
        self.assertTrue(any(p.endswith("index.ts") for p in paths))

    def test_carries_module_list_with_path_key(self):
        pack = evidence.build_evidence_pack(FIXTURE, self.data, budget_bytes=200_000)
        self.assertTrue(pack["modules"])
        self.assertIn("path", pack["modules"][0])

    def test_respects_budget_and_reports_omitted(self):
        pack = evidence.build_evidence_pack(FIXTURE, self.data, budget_bytes=50)
        total = sum(len(f["content"].encode("utf-8")) for f in pack["files"])
        self.assertLessEqual(total, 50 + 8000)  # last-file slack only
        self.assertIn("omitted_count", pack["budget"])

    def test_deterministic(self):
        a = evidence.build_evidence_pack(FIXTURE, self.data, budget_bytes=200_000)
        b = evidence.build_evidence_pack(FIXTURE, self.data, budget_bytes=200_000)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
```

`scripts/tests/__init__.py` — create empty (zero bytes).

- [ ] **Step 3: Run the test to verify it fails**

Run: `python3 -m unittest discover -s plugin/skills/map-repo/scripts/tests -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'evidence'`.

- [ ] **Step 4: Implement `evidence.py`**

`scripts/evidence.py`
```python
"""Build a bounded, deterministic 'evidence pack' from a scanned data
model so an LLM can evaluate a repo without reading all of it.

The pack is a curated slice: the module list, plus truncated contents of
high-signal files (entry points, manifests, READMEs, route/schema files,
a representative file per top module), within a byte budget. Selection is
deterministic so the pack is reproducible.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# Per-file truncation and overall pack budget.
PER_FILE_BYTES = 6000
DEFAULT_BUDGET_BYTES = 200_000

MANIFEST_NAMES = (
    "package.json", "mix.exs", "go.mod", "pyproject.toml", "requirements.txt",
    "docker-compose.yml", "compose.yml", ".env.example", "Gemfile", "pom.xml",
    "build.gradle", "Cargo.toml", "composer.json",
)
README_NAMES = ("README.md", "readme.md", "README")
ROUTE_FILE_RE = re.compile(
    r"(router\.(ex|rb|ts|js)|urls\.py|routes\.rb|schema\.(ex|prisma|graphql|ts)"
    r"|\.graphql$|route\.(ts|js)$)"
)
ARCH_DOC_RE = re.compile(r"(ARCHITECTURE|CODEBASE_MAP)", re.IGNORECASE)


def _read_truncated(path: Path, limit: int = PER_FILE_BYTES) -> str | None:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except OSError:
        return None


def _rel(root: Path, p: Path) -> str:
    try:
        return str(p.relative_to(root))
    except ValueError:
        return str(p)


def _candidate_paths(root: Path, data: dict[str, Any]) -> list[Path]:
    """Deterministically ordered candidate files, most valuable first."""
    seen: set[Path] = set()
    ordered: list[Path] = []

    def add(p: Path) -> None:
        if p.is_file() and p not in seen:
            seen.add(p)
            ordered.append(p)

    # 1. Root README + root manifests + arch docs.
    for name in README_NAMES:
        add(root / name)
    for name in MANIFEST_NAMES:
        add(root / name)
    for p in sorted(root.glob("docs/*")):
        if p.is_file() and ARCH_DOC_RE.search(p.name):
            add(p)

    # 2. Entry points (already detected by the scanner).
    for ep in data.get("entry_points", []):
        f = ep.get("file")
        if f:
            add((root / f))

    # 3. Per-module manifests + READMEs + a representative file.
    for m in data.get("modules", []):
        mpath = m.get("path")
        if not mpath:
            continue
        mdir = root / mpath
        for name in README_NAMES:
            add(mdir / name)
        for name in MANIFEST_NAMES:
            add(mdir / name)

    # 4. Route/schema files anywhere (bounded by sorted walk).
    for p in sorted(root.rglob("*")):
        if len(ordered) > 400:
            break
        if p.is_file() and ROUTE_FILE_RE.search(p.name):
            add(p)

    return ordered


def build_evidence_pack(
    root: Path, data: dict[str, Any], budget_bytes: int = DEFAULT_BUDGET_BYTES
) -> dict[str, Any]:
    """Return a deterministic, budget-capped evidence pack."""
    files: list[dict[str, Any]] = []
    used = 0
    omitted = 0
    for p in _candidate_paths(root, data):
        content = _read_truncated(p)
        if content is None:
            continue
        size = len(content.encode("utf-8"))
        if used and used + size > budget_bytes:
            omitted += 1
            continue
        files.append({"path": _rel(root, p), "content": content})
        used += size

    modules = [
        {
            "path": m.get("path"),
            "loc": m.get("loc"),
            "file_count": m.get("file_count"),
            "languages": m.get("languages", []),
            "current_description": m.get("description") or "",
        }
        for m in data.get("modules", [])
    ]

    return {
        "schema_version": 1,
        "project": data.get("project", {}),
        "modules": modules,
        "files": files,
        "signals_in_codemap": [
            "module_graph", "http_topology", "data_lineage", "deps", "services",
        ],
        "budget": {
            "budget_bytes": budget_bytes,
            "used_bytes": used,
            "omitted_count": omitted,
        },
    }
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m unittest discover -s plugin/skills/map-repo/scripts/tests -v`
Expected: PASS (5 tests in `EvidencePackTest`).

- [ ] **Step 6: Commit**

```bash
git add plugin/skills/map-repo/scripts/evidence.py plugin/skills/map-repo/scripts/tests
git commit -m "feat: bounded evidence-pack builder for LLM evaluation"
```

---

## Task 2: Wire evidence emission into `scan.py`

**Files:**
- Modify: `scripts/scan.py` (`main()`, lines 2105-2123)
- Test: `scripts/tests/test_evidence.py` (add a CLI test)

- [ ] **Step 1: Write the failing test (append to `test_evidence.py`)**

```python
class EvidenceCliTest(unittest.TestCase):
    def test_cli_writes_evidence_when_requested(self):
        import subprocess, tempfile, os
        scripts_dir = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "codemap.json"
            ev = Path(td) / "codemap.evidence.json"
            subprocess.run(
                ["python3", str(scripts_dir / "scan.py"),
                 "--path", str(FIXTURE), "--depth", "full",
                 "--out", str(out), "--evidence-out", str(ev)],
                check=True, capture_output=True,
            )
            self.assertTrue(out.is_file())
            self.assertTrue(ev.is_file())
            pack = json.loads(ev.read_text())
            self.assertIn("files", pack)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest discover -s plugin/skills/map-repo/scripts/tests -v`
Expected: FAIL — `scan.py: error: unrecognized arguments: --evidence-out`.

- [ ] **Step 3: Modify `scan.py`**

At the top of `scan.py`, ensure `import evidence` is added near the other imports (after the existing imports block).

Replace the `main()` body (lines 2105-2123) with:
```python
def main() -> int:
    parser = argparse.ArgumentParser(description="Scan a repository and emit a JSON data model.")
    parser.add_argument("--path", required=True, help="Path to scan.")
    parser.add_argument("--depth", choices=("shallow", "medium", "full"), default="medium")
    parser.add_argument("--out", required=True, help="Output JSON file path.")
    parser.add_argument(
        "--evidence-out",
        default=None,
        help="If set, also write a bounded evidence pack JSON to this path "
             "(for the LLM evaluation layer).",
    )
    args = parser.parse_args()

    root = Path(args.path).expanduser().resolve()
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2

    out = Path(args.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    data = build_data_model(root, args.depth)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"scanned {data['project']['total_files']} files, {data['project']['total_loc']} LOC -> {out}")

    if args.evidence_out:
        ev = Path(args.evidence_out).expanduser().resolve()
        ev.parent.mkdir(parents=True, exist_ok=True)
        pack = evidence.build_evidence_pack(root, data)
        ev.write_text(json.dumps(pack, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"evidence pack ({pack['budget']['used_bytes']} bytes) -> {ev}")

    return 0
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest discover -s plugin/skills/map-repo/scripts/tests -v`
Expected: PASS.

- [ ] **Step 5: Verify `codemap.json` is unchanged by this task**

Run:
```bash
python3 plugin/skills/map-repo/scripts/scan.py --path /home/mckechniep/projects/fittalk-monorepo --depth full --out /tmp/t1.json
git stash; python3 plugin/skills/map-repo/scripts/scan.py --path /home/mckechniep/projects/fittalk-monorepo --depth full --out /tmp/t0.json; git stash pop
diff <(grep -v scanned_at /tmp/t0.json) <(grep -v scanned_at /tmp/t1.json) && echo "IDENTICAL (modulo timestamp)"
```
Expected: `IDENTICAL (modulo timestamp)`.

- [ ] **Step 6: Commit**

```bash
git add plugin/skills/map-repo/scripts/scan.py plugin/skills/map-repo/scripts/tests/test_evidence.py
git commit -m "feat: scan.py --evidence-out emits the evidence pack"
```

---

## Task 3: Enrichment validator (`validate_enrichment.py`)

**Files:**
- Create: `scripts/validate_enrichment.py`
- Create: `scripts/tests/test_validate_enrichment.py`

- [ ] **Step 1: Write the failing test**

`scripts/tests/test_validate_enrichment.py`
```python
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import validate_enrichment as ve

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mini_repo"


def _valid():
    return {
        "schema_version": 1,
        "overview": {
            "what_it_is": "x", "what_it_does": "y", "how_it_works": "z",
            "primary_stack": ["TypeScript"], "confidence": "high", "caveats": [],
        },
        "classification": {
            "products": [{"module_id": "apps/web", "role": "frontend", "why": "w"}],
            "vendored": [{"module_id": "vendor-lib-master", "kind": "vendored-framework",
                          "source": "github.com/x", "why": "w"}],
        },
        "module_descriptions": [
            {"module_id": "apps/web", "description": "d", "is_product": True}
        ],
        "flows": [
            {"name": "f", "kind": "request", "trigger": "t", "narration": "n",
             "terminates": "end",
             "steps": [{"label": "main", "file": "apps/web/index.ts",
                        "symbol": "main", "note": "entry"}]},
        ],
    }


class ValidateTest(unittest.TestCase):
    def test_valid_passes(self):
        errors = ve.validate(_valid(), repo_root=FIXTURE)
        self.assertEqual(errors, [])

    def test_missing_overview_field_fails(self):
        d = _valid(); del d["overview"]["what_it_is"]
        self.assertTrue(any("what_it_is" in e for e in ve.validate(d, repo_root=FIXTURE)))

    def test_flow_step_requires_file_and_symbol(self):
        d = _valid(); del d["flows"][0]["steps"][0]["symbol"]
        self.assertTrue(any("symbol" in e for e in ve.validate(d, repo_root=FIXTURE)))

    def test_broken_citation_detected(self):
        d = _valid(); d["flows"][0]["steps"][0]["file"] = "nope/missing.ts"
        self.assertTrue(any("missing.ts" in e for e in ve.validate(d, repo_root=FIXTURE)))

    def test_drop_invalid_flows_keeps_valid(self):
        d = _valid()
        d["flows"].append({"name": "bad", "kind": "request", "trigger": "t",
                           "narration": "n", "terminates": "e",
                           "steps": [{"label": "x", "file": "nope.ts",
                                      "symbol": "y", "note": "z"}]})
        cleaned = ve.drop_invalid_flows(d, repo_root=FIXTURE)
        self.assertEqual(len(cleaned["flows"]), 1)
        self.assertEqual(cleaned["flows"][0]["name"], "f")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest discover -s plugin/skills/map-repo/scripts/tests -v`
Expected: FAIL — `No module named 'validate_enrichment'`.

- [ ] **Step 3: Implement `validate_enrichment.py`**

`scripts/validate_enrichment.py`
```python
"""Validate a codemap.enrichment.json sidecar: structural schema checks
plus verification that every flow-step citation points at a real file.

Importable (validate / drop_invalid_flows) and runnable as a CLI that
exits non-zero on structural errors.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

CONFIDENCE = {"high", "medium", "low"}
FLOW_KINDS = {"request", "background", "scheduled", "state-machine", "pipeline", "bootstrap"}


def _require(obj: dict, key: str, where: str, errors: list[str]) -> bool:
    if key not in obj or obj[key] in (None, ""):
        errors.append(f"{where}: missing required '{key}'")
        return False
    return True


def validate(enr: dict[str, Any], repo_root: Path) -> list[str]:
    """Return a list of structural + citation errors ([] means valid)."""
    errors: list[str] = []
    if enr.get("schema_version") != 1:
        errors.append("schema_version must be 1")

    ov = enr.get("overview")
    if not isinstance(ov, dict):
        errors.append("overview: missing or not an object")
    else:
        for k in ("what_it_is", "what_it_does", "how_it_works"):
            _require(ov, k, "overview", errors)
        if ov.get("confidence") not in CONFIDENCE:
            errors.append("overview.confidence must be high|medium|low")

    cls = enr.get("classification", {})
    if not isinstance(cls, dict):
        errors.append("classification: missing or not an object")

    for i, f in enumerate(enr.get("flows", [])):
        where = f"flows[{i}]"
        for k in ("name", "kind", "trigger", "terminates"):
            _require(f, k, where, errors)
        if f.get("kind") not in FLOW_KINDS:
            errors.append(f"{where}: kind must be one of {sorted(FLOW_KINDS)}")
        steps = f.get("steps")
        if not isinstance(steps, list) or not steps:
            errors.append(f"{where}: must have a non-empty steps list")
            continue
        for j, s in enumerate(steps):
            sw = f"{where}.steps[{j}]"
            _require(s, "file", sw, errors)
            _require(s, "symbol", sw, errors)
            cited = s.get("file")
            if cited and not (repo_root / cited).is_file():
                errors.append(f"{sw}: cited file not found: {cited}")
    return errors


def drop_invalid_flows(enr: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    """Return a copy of enr with flows whose citations don't resolve removed."""
    kept = []
    for f in enr.get("flows", []):
        steps = f.get("steps") or []
        if steps and all(
            s.get("file") and (repo_root / s["file"]).is_file() and s.get("symbol")
            for s in steps
        ):
            kept.append(f)
    out = dict(enr)
    out["flows"] = kept
    return out


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="Validate codemap.enrichment.json")
    p.add_argument("--enrichment", required=True)
    p.add_argument("--repo", required=True, help="Repo root for citation checks")
    args = p.parse_args()
    enr = json.loads(Path(args.enrichment).read_text(encoding="utf-8"))
    errors = validate(enr, Path(args.repo).expanduser().resolve())
    if errors:
        for e in errors:
            print(f"INVALID: {e}", file=sys.stderr)
        return 1
    print("enrichment OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest discover -s plugin/skills/map-repo/scripts/tests -v`
Expected: PASS (all `ValidateTest` cases).

- [ ] **Step 5: Commit**

```bash
git add plugin/skills/map-repo/scripts/validate_enrichment.py plugin/skills/map-repo/scripts/tests/test_validate_enrichment.py
git commit -m "feat: enrichment schema + citation validator"
```

---

## Task 4: `render.py` loads `--enrichment` and degrades gracefully

**Files:**
- Modify: `scripts/render.py` (`render_document` line 5023; `main()` line 5067)
- Create: `scripts/tests/test_render_enrichment.py`

- [ ] **Step 1: Capture the pre-change golden output**

Run:
```bash
python3 plugin/skills/map-repo/scripts/render.py --in /home/mckechniep/projects/fittalk-monorepo/.codemap/codemap.json --out /tmp/golden.html
cp /tmp/golden.html plugin/skills/map-repo/scripts/tests/fixtures/golden_fittalk.html
```
This frozen file is the "no enrichment must equal today" baseline.

- [ ] **Step 2: Write the failing test**

`scripts/tests/test_render_enrichment.py`
```python
import json
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import render

FIX = Path(__file__).resolve().parent / "fixtures"
FITTALK = Path("/home/mckechniep/projects/fittalk-monorepo/.codemap/codemap.json")


class DegradationTest(unittest.TestCase):
    def test_no_enrichment_matches_golden(self):
        data = json.loads(FITTALK.read_text())
        html = render.render_document(data)            # no enrichment arg
        golden = (FIX / "golden_fittalk.html").read_text()
        self.assertEqual(html, golden)

    def test_none_enrichment_matches_golden(self):
        data = json.loads(FITTALK.read_text())
        html = render.render_document(data, enrichment=None)
        golden = (FIX / "golden_fittalk.html").read_text()
        self.assertEqual(html, golden)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run to verify it fails**

Run: `python3 -m unittest plugin.skills.map-repo.scripts.tests.test_render_enrichment -v` (or the discover command)
Expected: FAIL — `render_document() got an unexpected keyword argument 'enrichment'`.

- [ ] **Step 4: Modify `render_document` signature (line 5023)**

Change:
```python
def render_document(data: dict[str, Any]) -> str:
    project_name = escape(data["project"]["name"])
    body = (
        render_cover(data)
        + render_readme(data)
```
to:
```python
def render_document(data: dict[str, Any], enrichment: dict[str, Any] | None = None) -> str:
    project_name = escape(data["project"]["name"])
    body = (
        render_cover(data)
        + render_overview(data, enrichment)
        + render_readme(data, enrichment)
```
(Leave the rest of the body assembly unchanged for now. `render_overview` and the new `render_readme` signature are added in Tasks 5-6; for this task only, add a temporary no-op `render_overview` so the module imports — see Step 5.)

- [ ] **Step 5: Add a no-op `render_overview` and update `render_readme` signature**

Immediately above `render_readme` (line ~4940), add:
```python
def render_overview(data: dict[str, Any], enrichment: dict[str, Any] | None = None) -> str:
    """Prominent LLM-authored 'what this is' opener. Renders only when
    enrichment is present; otherwise empty (deterministic-only report)."""
    if not enrichment or not enrichment.get("overview"):
        return ""
    return ""  # filled in Task 5
```
Change `def render_readme(data: dict[str, Any]) -> str:` to
`def render_readme(data: dict[str, Any], enrichment: dict[str, Any] | None = None) -> str:`
(The body is unchanged in this task — the `enrichment` param is accepted but unused until Task 6.)

- [ ] **Step 6: Update `main()` to accept `--enrichment` (line 5067)**

Replace `main()` with:
```python
def main() -> int:
    parser = argparse.ArgumentParser(description="Render a codemap HTML report from JSON.")
    parser.add_argument("--in", dest="inp", required=True, help="Path to codemap.json")
    parser.add_argument("--out", required=True, help="Path to output HTML file")
    parser.add_argument("--enrichment", default=None, help="Optional codemap.enrichment.json")
    args = parser.parse_args()

    inp = Path(args.inp).expanduser().resolve()
    if not inp.is_file():
        print(f"error: not a file: {inp}", file=sys.stderr)
        return 2
    try:
        data = json.loads(inp.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"error: invalid JSON in {inp}: {e}", file=sys.stderr)
        return 2

    enrichment = None
    if args.enrichment:
        ep = Path(args.enrichment).expanduser().resolve()
        if ep.is_file():
            try:
                enrichment = json.loads(ep.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                print(f"warning: ignoring invalid enrichment {ep}: {e}", file=sys.stderr)
        else:
            print(f"warning: enrichment not found, rendering without it: {ep}", file=sys.stderr)

    html = render_document(data, enrichment)
    out = Path(args.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"rendered -> {out}")
    return 0
```

- [ ] **Step 7: Run to verify degradation tests pass**

Run: `python3 -m unittest discover -s plugin/skills/map-repo/scripts/tests -v`
Expected: PASS (the golden still matches because `render_overview` returns `""` and `render_readme` is unchanged).

- [ ] **Step 8: Commit**

```bash
git add plugin/skills/map-repo/scripts/render.py plugin/skills/map-repo/scripts/tests/test_render_enrichment.py plugin/skills/map-repo/scripts/tests/fixtures/golden_fittalk.html
git commit -m "feat: render.py accepts optional --enrichment, degrades to baseline"
```

---

## Task 5: Overview section render

**Files:**
- Modify: `scripts/render.py` (`render_overview`, the no-op from Task 4)
- Modify: `scripts/render.py` (`CSS` string — add overview styles)
- Test: `scripts/tests/test_render_enrichment.py` (add `OverviewTest`)

- [ ] **Step 1: Write the failing test (append)**

```python
def _enr():
    return {
        "schema_version": 1,
        "overview": {
            "what_it_is": "A travel recommendation service.",
            "what_it_does": "Curates trips and serves them via GraphQL.",
            "how_it_works": "Elixir backend plus a React Native app.",
            "primary_stack": ["Elixir/Phoenix", "React Native"],
            "confidence": "high",
            "caveats": ["The root README is a roadmap, not a description."],
        },
        "classification": {"products": [], "vendored": []},
        "module_descriptions": [],
        "flows": [],
    }


class OverviewTest(unittest.TestCase):
    def test_overview_renders_narrative(self):
        html = render.render_overview({"project": {"name": "x"}}, _enr())
        self.assertIn("A travel recommendation service.", html)
        self.assertIn("Elixir/Phoenix", html)
        self.assertIn("roadmap, not a description", html)

    def test_overview_empty_without_enrichment(self):
        self.assertEqual(render.render_overview({"project": {"name": "x"}}, None), "")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest discover -s plugin/skills/map-repo/scripts/tests -v`
Expected: FAIL on `test_overview_renders_narrative` (asserts text not present — current no-op returns "").

- [ ] **Step 3: Implement `render_overview`**

Replace the Task-4 no-op body with:
```python
def render_overview(data: dict[str, Any], enrichment: dict[str, Any] | None = None) -> str:
    """Prominent LLM-authored 'what this is' opener. Renders only when
    enrichment is present; otherwise empty (deterministic-only report)."""
    if not enrichment or not enrichment.get("overview"):
        return ""
    ov = enrichment["overview"]
    stack = "".join(
        f'<span class="tag">{escape(s)}</span>' for s in ov.get("primary_stack", [])
    )
    caveats = ov.get("caveats", [])
    caveat_html = ""
    if caveats:
        items = "".join(f"<li>{escape(c)}</li>" for c in caveats)
        caveat_html = f'<div class="overview-caveats"><div class="group-label">Caveats</div><ul>{items}</ul></div>'
    conf = escape(ov.get("confidence", ""))
    return f"""
<section class="overview">
  <h2>What this codebase is</h2>
  <p class="overview-lede">{escape(ov.get('what_it_is', ''))}</p>
  <div class="overview-body">
    <p>{escape(ov.get('what_it_does', ''))}</p>
    <p>{escape(ov.get('how_it_works', ''))}</p>
  </div>
  <div class="overview-stack"><span class="group-label">Stack</span> {stack}</div>
  {caveat_html}
  <p class="overview-conf">Assessed from the source by an LLM · confidence: {conf}</p>
</section>
"""
```

- [ ] **Step 4: Add Overview CSS**

Find the `CSS = """..."""` string in `render.py` (the large stylesheet) and append these rules before its closing `"""`:
```css
.overview { margin: var(--space-5) 0; }
.overview-lede { font-size: 1.4rem; font-weight: 600; line-height: 1.3; color: var(--text); margin: 0 0 var(--space-3); }
.overview-body p { margin: 0 0 var(--space-2); color: var(--text); }
.overview-stack { margin: var(--space-3) 0; display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.overview-caveats { margin: var(--space-3) 0; padding: var(--space-2) var(--space-3); border-left: 3px solid var(--accent); background: var(--bg); }
.overview-caveats ul { margin: 4px 0 0; padding-left: 18px; }
.overview-conf { font-size: 0.82rem; color: var(--muted); font-family: var(--font-mono); margin-top: var(--space-2); }
```
(If a token like `--space-5` is absent, use the nearest existing spacing token — grep `:root` in `render.py` to confirm available tokens before writing.)

- [ ] **Step 5: Run to verify it passes**

Run: `python3 -m unittest discover -s plugin/skills/map-repo/scripts/tests -v`
Expected: PASS. The degradation golden test still passes (overview empty without enrichment).

- [ ] **Step 6: Commit**

```bash
git add plugin/skills/map-repo/scripts/render.py plugin/skills/map-repo/scripts/tests/test_render_enrichment.py
git commit -m "feat: LLM overview section (renders only with enrichment)"
```

---

## Task 6: README demotion + product/vendored module treatment

**Files:**
- Modify: `scripts/render.py` (`render_readme` line ~4940, `render_modules` line 1885)
- Modify: `scripts/render.py` (`CSS` — vendored card styles)
- Test: `scripts/tests/test_render_enrichment.py` (add `ModulesTest`)

- [ ] **Step 1: Write the failing test (append)**

```python
class ModulesTest(unittest.TestCase):
    def _data(self):
        return {"modules": [
            {"path": "apps/web", "file_count": 3, "loc": 100,
             "languages": ["TypeScript"], "description": "scanner guess"},
            {"path": "vendor-lib-master", "file_count": 2, "loc": 5000,
             "languages": ["JavaScript"], "description": "vendor guess"},
        ]}

    def _enr(self):
        return {
            "schema_version": 1,
            "overview": {"what_it_is": "x", "what_it_does": "y", "how_it_works": "z",
                         "primary_stack": [], "confidence": "low", "caveats": []},
            "classification": {
                "products": [{"module_id": "apps/web", "role": "frontend", "why": "w"}],
                "vendored": [{"module_id": "vendor-lib-master",
                              "kind": "vendored-framework", "source": "x", "why": "w"}],
            },
            "module_descriptions": [
                {"module_id": "apps/web", "description": "The web dashboard.", "is_product": True}
            ],
            "flows": [],
        }

    def test_product_uses_llm_description_and_sorts_first(self):
        html = render.render_modules(self._data(), self._enr())
        self.assertIn("The web dashboard.", html)
        self.assertLess(html.index("apps/web"), html.index("vendor-lib-master"))

    def test_vendored_is_badged(self):
        html = render.render_modules(self._data(), self._enr())
        self.assertIn("vendored", html.lower())

    def test_modules_unchanged_without_enrichment(self):
        html = render.render_modules(self._data(), None)
        self.assertIn("scanner guess", html)
        self.assertNotIn("The web dashboard.", html)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest discover -s plugin/skills/map-repo/scripts/tests -v`
Expected: FAIL — `render_modules() takes 1 positional argument but 2 were given`.

- [ ] **Step 3: Rewrite `render_modules` (lines 1885-1910)**

```python
def render_modules(data: dict[str, Any], enrichment: dict[str, Any] | None = None) -> str:
    mods = data.get("modules", [])
    if not mods:
        return ""

    # Build classification + description lookups from enrichment (keyed by path).
    vendored_ids: dict[str, dict] = {}
    desc_by_id: dict[str, str] = {}
    if enrichment:
        for v in enrichment.get("classification", {}).get("vendored", []):
            if v.get("module_id"):
                vendored_ids[v["module_id"]] = v
        for d in enrichment.get("module_descriptions", []):
            if d.get("module_id") and d.get("description"):
                desc_by_id[d["module_id"]] = d["description"]

    def is_vendored(m: dict) -> bool:
        return m.get("path") in vendored_ids

    def card(m: dict) -> str:
        path = m.get("path", "")
        vend = is_vendored(m)
        desc = desc_by_id.get(path) or (m.get("description") if not vend else "")
        kind = vendored_ids.get(path, {}).get("kind", "")
        badge = f'<span class="vendored-badge">vendored{(" · " + escape(kind)) if kind else ""}</span>' if vend else ""
        desc_html = ('<p class="desc">' + escape(desc) + '</p>') if desc else ""
        return f"""
        <div class="card{' is-vendored' if vend else ''}">
          <div class="head">
            <div class="name">{escape(path)}{badge}</div>
            <div class="meta">{fmt_num(m['file_count'])} files · {fmt_num(m['loc'])} LOC</div>
          </div>
          {desc_html}
          <div class="langs">
            {''.join(f'<span class="tag">{escape(l)}</span>' for l in m.get('languages', []))}
          </div>
        </div>
        """

    # Products first (original order), vendored last — only when classified.
    if enrichment:
        products = [m for m in mods if not is_vendored(m)]
        vendored = [m for m in mods if is_vendored(m)]
        ordered = products + vendored
    else:
        ordered = mods

    cards = "".join(card(m) for m in ordered)
    return f"""
<section>
  <h2>Top-level modules</h2>
  {section_intro("modules")}
  <div class="card-grid">{cards}</div>
</section>
"""
```

- [ ] **Step 4: Demote `render_readme` when enrichment present (line ~4958)**

Replace the return block of `render_readme` with:
```python
    heading = "What the README says" if enrichment and enrichment.get("overview") else f"From {escape(r['file'])}"
    aside_class = " readme-demoted" if enrichment and enrichment.get("overview") else ""
    return f"""
<section class="readme-section{aside_class}">
  <h2>{heading}</h2>
  {section_intro("readme")}
  <blockquote class="readme-quote">{escape(first_para)}</blockquote>
</section>
"""
```

- [ ] **Step 5: Add vendored + demotion CSS** (append to the `CSS` string)

```css
.vendored-badge { font-size: 0.7rem; font-family: var(--font-mono); color: var(--muted); border: 1px solid var(--border); border-radius: 4px; padding: 1px 6px; margin-left: 8px; vertical-align: middle; }
.card.is-vendored { opacity: 0.62; }
.card.is-vendored .name { color: var(--muted); }
.readme-demoted { opacity: 0.85; }
.readme-demoted .readme-quote { font-size: 0.92rem; }
```

- [ ] **Step 6: Run to verify it passes**

Run: `python3 -m unittest discover -s plugin/skills/map-repo/scripts/tests -v`
Expected: PASS. The degradation golden still matches (no enrichment ⇒ original module order, original heading).

- [ ] **Step 7: Commit**

```bash
git add plugin/skills/map-repo/scripts/render.py plugin/skills/map-repo/scripts/tests/test_render_enrichment.py
git commit -m "feat: README demotion + product/vendored module treatment"
```

---

## Task 7: SKILL.md Step 1.5 orchestration + `--no-llm`

**Files:**
- Modify: `plugin/skills/map-repo/SKILL.md`

This task is documentation/orchestration (instructions Claude follows), not code — no unit test. Validate by reading and by the Task 8 acceptance run.

- [ ] **Step 1: Add `--no-llm` to argument parsing (SKILL.md "Argument parsing" section)**

Add after the `--out` bullet:
```markdown
5. **`--no-llm`** (alias `--fast`) — skip the LLM evaluation step (Step 1.5)
   and produce the deterministic-only report. Defaults to running the
   evaluation.
```

- [ ] **Step 2: Change Step 1 (Scan) to also emit the evidence pack**

Update the scan command (unless `--no-llm`) to:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/map-repo/scripts/scan.py" \
  --path "<resolved-path>" \
  --depth "<shallow|medium|full>" \
  --out "<out-dir>/codemap.json" \
  --evidence-out "<out-dir>/codemap.evidence.json"
```
(When `--no-llm`, omit `--evidence-out`.)

- [ ] **Step 3: Insert new "Step 1.5 — LLM evaluation" between Scan and Render**

```markdown
### Step 1.5 — LLM evaluation (skip if `--no-llm`)

Read `<out-dir>/codemap.evidence.json`. It contains the module list and
truncated contents of high-signal files (entry points, manifests,
READMEs, route/schema files). You may additionally `Read`/`Grep` up to
~20 more files in the target repo to confirm flows and citations — do not
read the whole repo.

Produce a `codemap.enrichment.json` at `<out-dir>/` with this shape
(schema in `validate_enrichment.py`):

- `overview`: what_it_is / what_it_does / how_it_works (plain English,
  grounded in the code you read, NOT the README), primary_stack[],
  confidence (high|medium|low), caveats[] (call out a misleading README).
- `classification`: products[] and vendored[]. Treat as **vendored** any
  module that is a dependency/reference clone: paths under `vendor/` or
  `node_modules/`, directory names ending `-master`/`-develop`/`-main`
  (git-archive clones), a third-party LICENSE or repo URL in its
  package.json, or a path-dependency. Everything that is the actual
  product is a **product** (give each a role + one-line why).
- `module_descriptions`: for each PRODUCT module, an accurate one-line
  description (fill gaps the scanner left empty, e.g. Elixir modules).
- `flows`: 3 flows at `--depth medium`, up to 6 at `full`. Each is an
  end-to-end story (signup, a domain state machine, a scheduled job, a
  data pipeline, app bootstrap). **Every step must cite a real
  `file` + `symbol` you actually saw.** No uncited steps.

Then validate before rendering:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/map-repo/scripts/validate_enrichment.py" \
  --enrichment "<out-dir>/codemap.enrichment.json" \
  --repo "<resolved-path>"
```
If it reports structural errors, fix the JSON and re-validate. (Flows with
broken citations are dropped automatically at render time, but fix them if
you can.) If you cannot produce valid enrichment, skip it and render the
deterministic-only report.
```

- [ ] **Step 4: Update Step 2 (Render) to pass enrichment**

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/map-repo/scripts/render.py" \
  --in "<out-dir>/codemap.json" \
  --out "<out-dir>/codemap.html" \
  --enrichment "<out-dir>/codemap.enrichment.json"
```
(When `--no-llm`, omit `--enrichment`.)

- [ ] **Step 5: Commit**

```bash
git add plugin/skills/map-repo/SKILL.md
git commit -m "docs(skill): add Step 1.5 LLM evaluation + --no-llm gating"
```

---

## Task 8: Phase 1 acceptance (brevity + fittalk + degradation)

**Files:** none (verification task). If a check fails, fix in the relevant task's files.

- [ ] **Step 1: Full unit suite**

Run: `python3 -m unittest discover -s plugin/skills/map-repo/scripts/tests -v`
Expected: all PASS.

- [ ] **Step 2: Deterministic degradation end-to-end**

```bash
python3 plugin/skills/map-repo/scripts/render.py --in /home/mckechniep/projects/fittalk-monorepo/.codemap/codemap.json --out /tmp/deg.html
diff /tmp/deg.html plugin/skills/map-repo/scripts/tests/fixtures/golden_fittalk.html && echo "DEGRADATION OK"
```
Expected: `DEGRADATION OK`.

- [ ] **Step 3: Evidence pack on brevity is bounded**

```bash
python3 plugin/skills/map-repo/scripts/scan.py --path /home/mckechniep/projects/brevity --depth full --out /tmp/brev.json --evidence-out /tmp/brev.evidence.json
python3 -c "import json; p=json.load(open('/tmp/brev.evidence.json')); print('used', p['budget']['used_bytes'], 'omitted', p['budget']['omitted_count'], 'files', len(p['files']))"
```
Expected: `used_bytes` ≤ ~208000; a sane file count; command exits 0.

- [ ] **Step 4: Author a real enrichment for brevity by hand-running Step 1.5**

Acting as the skill, read `/tmp/brev.evidence.json` (+ a few files), write `/tmp/brev.enrichment.json`, then:
```bash
python3 plugin/skills/map-repo/scripts/validate_enrichment.py --enrichment /tmp/brev.enrichment.json --repo /home/mckechniep/projects/brevity && echo "ENRICHMENT VALID"
```
Expected: `ENRICHMENT VALID`. Acceptance content checks: overview names the Elixir/Phoenix backend + React Native app; `google_ads-master` and the g.frame packages appear under `classification.vendored`.

- [ ] **Step 5: Render brevity with enrichment and eyeball it**

```bash
python3 plugin/skills/map-repo/scripts/render.py --in /tmp/brev.json --out /tmp/brev.html --enrichment /tmp/brev.enrichment.json
bash plugin/skills/map-repo/scripts/to-pdf.sh /tmp/brev.html /tmp/brev.pdf
```
Convert the Overview page and the Top-level modules page to PNG (`pdftoppm`) and confirm: Overview narrative is accurate and prominent; README is demoted; vendored modules are badged/dimmed and sorted last.

- [ ] **Step 6: Tag Phase 1 complete**

```bash
git commit --allow-empty -m "chore: phase 1 (overview/classification/descriptions) acceptance passed"
```

---

# PHASE 2 — Key flows section (hybrid SVG spine + HTML text)

## Task 9: `render_key_flows` (hybrid render)

**Files:**
- Modify: `scripts/render.py` (add `render_key_flows`; insert into `render_document` after `render_critical_paths_section`)
- Modify: `scripts/render.py` (`CSS` — flow card styles)
- Test: `scripts/tests/test_render_enrichment.py` (add `FlowsTest`)

- [ ] **Step 1: Write the failing test (append)**

```python
class FlowsTest(unittest.TestCase):
    def _enr(self):
        return {"schema_version": 1, "overview": {}, "classification": {},
                "module_descriptions": [],
                "flows": [
                    {"name": "User signup", "kind": "request",
                     "trigger": "GraphQL mutation signUp", "narration": "Creates an account.",
                     "terminates": "auth token returned",
                     "steps": [
                        {"label": "sign_up/2", "file": "backend/lib/x.ex",
                         "symbol": "sign_up/2", "line": 28, "note": "validates + delegates"},
                        {"label": "Repo.transact", "file": "backend/lib/y.ex",
                         "symbol": "create_account/1", "note": "inserts account"},
                     ]},
                ]}

    def test_flows_render_with_citations(self):
        html = render.render_key_flows({}, self._enr())
        self.assertIn("User signup", html)
        self.assertIn("sign_up/2", html)
        self.assertIn("backend/lib/x.ex", html)
        self.assertIn("GraphQL mutation signUp", html)

    def test_no_flows_no_section(self):
        self.assertEqual(render.render_key_flows({}, None), "")
        self.assertEqual(render.render_key_flows({}, {"flows": []}), "")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest discover -s plugin/skills/map-repo/scripts/tests -v`
Expected: FAIL — `module 'render' has no attribute 'render_key_flows'`.

- [ ] **Step 3: Implement `render_key_flows`** (add near the other section renderers, e.g. after `render_critical_paths_section`)

```python
# Flow-kind chips reuse the editorial palette without new accent colors.
FLOW_KIND_LABELS = {
    "request": "REQUEST", "background": "BACKGROUND", "scheduled": "SCHEDULED",
    "state-machine": "STATE MACHINE", "pipeline": "PIPELINE", "bootstrap": "BOOTSTRAP",
}


def _render_flow_card(flow: dict[str, Any]) -> str:
    steps = flow.get("steps", [])
    n = len(steps)
    # SVG spine: a vertical line with a numbered node per step. Text lives in
    # HTML rows aligned to each node (hybrid). Row pitch must match CSS.
    ROW = 56  # px per step row; keep in sync with .flow-step height
    spine_h = max(ROW * n, ROW)
    nodes = []
    for i in range(n):
        cy = i * ROW + ROW / 2
        nodes.append(
            f'<circle cx="11" cy="{cy:.0f}" r="9" fill="var(--bg)" '
            f'stroke="var(--accent)" stroke-width="2"/>'
            f'<text x="11" y="{cy + 3:.0f}" text-anchor="middle" '
            f'font-size="10" font-family="var(--font-mono)" fill="var(--text)">{i + 1}</text>'
        )
    spine = (
        f'<svg class="flow-spine" width="22" height="{spine_h}" '
        f'viewBox="0 0 22 {spine_h}" aria-hidden="true">'
        f'<line x1="11" y1="9" x2="11" y2="{spine_h - 9}" stroke="var(--border)" stroke-width="2"/>'
        f'{"".join(nodes)}</svg>'
    )
    rows = []
    for s in steps:
        cite = escape(s.get("file", ""))
        sym = escape(s.get("symbol", ""))
        line = f':{escape(str(s["line"]))}' if s.get("line") else ""
        note = escape(s.get("note", ""))
        rows.append(
            f'<div class="flow-step">'
            f'<div class="flow-step-label">{escape(s.get("label", sym))}</div>'
            f'<div class="flow-step-cite"><code>{cite}{line}</code> · <code>{sym}</code></div>'
            f'{f"<div class=flow-step-note>{note}</div>" if note else ""}'
            f'</div>'
        )
    kind = FLOW_KIND_LABELS.get(flow.get("kind", ""), escape(flow.get("kind", "").upper()))
    return f"""
    <div class="flow-card">
      <div class="flow-head">
        <span class="flow-kind">{kind}</span>
        <span class="flow-name">{escape(flow.get('name', ''))}</span>
      </div>
      <div class="flow-trigger"><strong>Trigger:</strong> {escape(flow.get('trigger', ''))}</div>
      <div class="flow-narration">{escape(flow.get('narration', ''))}</div>
      <div class="flow-body">
        {spine}
        <div class="flow-steps">{''.join(rows)}</div>
      </div>
      <div class="flow-terminates"><strong>Ends:</strong> {escape(flow.get('terminates', ''))}</div>
    </div>
    """


def render_key_flows(data: dict[str, Any], enrichment: dict[str, Any] | None = None) -> str:
    """Render LLM-derived end-to-end flows. Empty without flows."""
    flows = (enrichment or {}).get("flows") or []
    if not flows:
        return ""
    cards = "".join(_render_flow_card(f) for f in flows)
    return f"""
<section class="key-flows">
  <h2>Key flows</h2>
  {section_intro("flows") if "flows" in SECTION_INTROS else ""}
  <div class="flow-list">{cards}</div>
</section>
"""
```
Note: if `section_intro` requires a registered key, add a `"flows"` entry to the section-intro source (grep `def section_intro` / `SECTION_INTROS` to find it) describing "End-to-end paths through the code, derived from the source." If `SECTION_INTROS` is not the symbol name, adapt the guard to match the codebase; otherwise drop the `section_intro("flows")` line.

- [ ] **Step 4: Insert into `render_document`** (after `render_critical_paths_section(data)`, line ~5039)

```python
        + render_critical_paths_section(data)
        + render_key_flows(data, enrichment)
```

- [ ] **Step 5: Add flow CSS** (append to `CSS`)

```css
.key-flows { margin: var(--space-5) 0; }
.flow-list { display: flex; flex-direction: column; gap: var(--space-4); }
.flow-card { border: 1px solid var(--border); border-radius: 8px; padding: var(--space-3); background: var(--surface); }
.flow-head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 6px; }
.flow-kind { font-size: 0.68rem; font-family: var(--font-mono); letter-spacing: 0.08em; color: var(--accent); border: 1px solid var(--accent); border-radius: 4px; padding: 1px 6px; }
.flow-name { font-size: 1.1rem; font-weight: 600; }
.flow-trigger, .flow-terminates { font-size: 0.9rem; color: var(--text); margin: 4px 0; }
.flow-narration { color: var(--muted); margin: 4px 0 10px; }
.flow-body { display: grid; grid-template-columns: 22px 1fr; gap: 14px; }
.flow-spine { display: block; }
.flow-steps { display: flex; flex-direction: column; }
.flow-step { min-height: 56px; padding-bottom: 8px; }
.flow-step-label { font-weight: 600; font-size: 0.95rem; }
.flow-step-cite { font-size: 0.8rem; color: var(--muted); }
.flow-step-cite code { font-family: var(--font-mono); }
.flow-step-note { font-size: 0.85rem; color: var(--text); }
```

- [ ] **Step 6: Run to verify it passes**

Run: `python3 -m unittest discover -s plugin/skills/map-repo/scripts/tests -v`
Expected: PASS. Degradation golden still matches (no flows ⇒ no section).

- [ ] **Step 7: Commit**

```bash
git add plugin/skills/map-repo/scripts/render.py plugin/skills/map-repo/scripts/tests/test_render_enrichment.py
git commit -m "feat: Key flows section (hybrid SVG spine + HTML text)"
```

---

## Task 10: Flow print CSS (paginate at step/card boundaries)

**Files:**
- Modify: `scripts/render.py` (`@media print` block, ~line 1460-1560)

- [ ] **Step 1: Add print rules** (inside the existing `@media print { ... }` block)

```css
  .flow-card { break-inside: avoid; page-break-inside: avoid; }
  .key-flows h2 { break-after: avoid; page-break-after: avoid; }
```

- [ ] **Step 2: Verify a flow-bearing report prints without splitting a card mid-step**

```bash
python3 plugin/skills/map-repo/scripts/render.py --in /tmp/brev.json --out /tmp/brevflow.html --enrichment /tmp/brev.enrichment.json
bash plugin/skills/map-repo/scripts/to-pdf.sh /tmp/brevflow.html /tmp/brevflow.pdf
```
Find the "Key flows" page(s) (`pdftotext` per-page grep), rasterize with `pdftoppm`, and confirm each flow card stays intact (spine numbers aligned to step rows, no card split mid-card).

- [ ] **Step 3: Commit**

```bash
git add plugin/skills/map-repo/scripts/render.py
git commit -m "feat: print rules keep flow cards intact across pages"
```

---

## Task 11: Phase 2 acceptance + README update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Brevity flow acceptance**

Confirm `/tmp/brev.enrichment.json` (from Task 8) has ≥3 flows and that:
```bash
python3 plugin/skills/map-repo/scripts/validate_enrichment.py --enrichment /tmp/brev.enrichment.json --repo /home/mckechniep/projects/brevity && echo OK
```
returns `OK` (every cited file exists). Visually confirm the rendered "Key flows" section reads as real end-to-end stories (e.g. the trip state machine).

- [ ] **Step 2: Full suite + degradation once more**

Run: `python3 -m unittest discover -s plugin/skills/map-repo/scripts/tests -v`
Then: `diff <(python3 plugin/skills/map-repo/scripts/render.py --in /home/mckechniep/projects/fittalk-monorepo/.codemap/codemap.json --out /dev/stdout) plugin/skills/map-repo/scripts/tests/fixtures/golden_fittalk.html && echo "DEGRADATION OK"`
Expected: all PASS + `DEGRADATION OK`.

- [ ] **Step 3: Document the layer in README.md**

Under "What's in a report", add a bullet:
```markdown
- **Overview & Key flows** *(LLM evaluation, on by default)* — an accurate, code-derived summary of what the project is and does (the README is demoted to a secondary aside), vendored/reference code flagged and de-emphasised, and several end-to-end execution flows with file:symbol citations. Pass `--no-llm` for a fast deterministic-only report.
```
Add to the arguments table:
```markdown
| `--no-llm` | off | Skip the LLM evaluation step; produce the deterministic-only report |
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document the LLM evaluation layer and --no-llm"
```

---

## Self-review notes (spec coverage)

- Evidence pack → Tasks 1-2. Enrichment schema + validation → Task 3. Sidecar data flow + degradation → Task 4. Overview + README demotion → Tasks 5-6. Product/vendored treatment → Task 6. Skill Step 1.5 + `--no-llm` → Task 7. Flows (hybrid) → Tasks 9-10. Acceptance (brevity/fittalk/degradation) → Tasks 8, 11.
- Determinism invariant enforced by the golden-file degradation test (Tasks 4, 8, 11).
- Anti-hallucination (cited flows) enforced by `validate_enrichment.py` citation checks (Task 3) and `drop_invalid_flows` at render time.
- Out of scope per spec: deterministic Elixir/workspace import parsing; enrichment caching.
