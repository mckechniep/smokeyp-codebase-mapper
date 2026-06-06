# Ecto Data-Lineage (Slice C of v0.10.0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the data-lineage section detect Elixir/Ecto schemas (so brevity's ~30 `brevity_schemas` appear against a Postgres store) and stop leaking vendored models, by mirroring the existing Prisma schema-file pass and adding `_vendored_path` filtering.

**Architecture:** Pure scanner change in `scan.py` (render is framework-agnostic — zero render edits). An inline `elif language == "Elixir"` branch in `_scan_data_models_file` emits the existing `{service, framework, model}` shape from a `schema "table" do` regex; `build_data_lineage` adds `"Elixir"` to its language allowlist and a `_vendored_path` guard; `_detect_stores` also reads `config/*.exs` for Postgres.

**Tech Stack:** Python 3.10+ stdlib only, stdlib `unittest`.

**Spec:** `docs/superpowers/specs/2026-06-06-ecto-data-lineage-design.md`

**Test runner:** `cd plugin/skills/map-repo/scripts && python3 -m unittest discover -s tests -t . -q`

---

## Repo gotchas (read before every task)

- **NEVER `git add -A`/`git add .`** — the repo root has untracked junk (char-device dotfiles, etc.). Always `git add` the EXACT paths listed.
- Do NOT amend or force-push. New commits only.
- Run `git add`/`git commit` from the repo root `/home/mckechniep/ai-llms/claude/mine/smokeyp-codebase-mapper`, using `plugin/skills/map-repo/scripts/...` paths. Run the test runner from the scripts dir.
- Harmless `[astgrep_imports] … falling back` lines during scans are NOT failures.
- Baseline suite is **305 tests, all green**. Each task is additive — keep it green.
- **No golden impact:** the golden test (`tests/test_render_enrichment.py`) renders a STATIC fittalk `codemap.json` and does NOT run `build_data_lineage`; fittalk is not Elixir. So scanner changes here cannot move the golden. If the golden ever fails after your change, STOP and report — it means something unexpected.
- Brevity inputs are read-only OK; scan output must go to `/tmp/claude/` (brevity dir is sandbox-write-blocked).

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `plugin/skills/map-repo/scripts/scan.py` | Modify | `ECTO_SCHEMA_RE` constant; `_scan_data_models_file` Elixir branch; `ORM_DEFAULT_STORE["Ecto"]`; `build_data_lineage` Elixir allowlist + `_vendored_path` guard; `_detect_stores` reads `config/*.exs` + postgrex pattern |
| `plugin/skills/map-repo/scripts/tests/test_data_lineage.py` | **Create** | Unit tests: Ecto model scan, end-to-end lineage, vendored exclusion (Ecto + Prisma), config.exs store detection |

---

## Task 1: Ecto schema detection in `_scan_data_models_file`

**Files:**
- Modify: `scripts/scan.py` (add `ECTO_SCHEMA_RE` after line 2178; Elixir branch in `_scan_data_models_file` ~2260; `ORM_DEFAULT_STORE` ~2270)
- Test: `scripts/tests/test_data_lineage.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_data_lineage.py`:

```python
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scan


class EctoModelScanTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _write(self, rel, text):
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def test_ecto_schema_named_by_module_last_segment(self):
        p = self._write(
            "recommendation.ex",
            'defmodule BrevitySchemas.Recommendation do\n'
            '  use BrevitySchemas.Base\n'
            '  schema "recommendations" do\n'
            '    field :history_lesson, :string\n'
            '    belongs_to :trip, Trip\n'
            '  end\n'
            'end\n',
        )
        out = scan._scan_data_models_file(p, "Elixir", "backend")
        self.assertEqual(
            out, [{"service": "backend", "framework": "Ecto", "model": "Recommendation"}])

    def test_ecto_schema_without_module_falls_back_to_table(self):
        p = self._write(
            "orphan.ex", 'schema "widgets" do\n  field :x, :string\nend\n')
        out = scan._scan_data_models_file(p, "Elixir", "backend")
        self.assertEqual(
            out, [{"service": "backend", "framework": "Ecto", "model": "widgets"}])

    def test_embedded_schema_not_matched(self):
        # embedded_schema has no DB table; must NOT be emitted.
        p = self._write(
            "addr.ex",
            'defmodule App.Address do\n  embedded_schema do\n    field :zip, :string\n  end\nend\n',
        )
        out = scan._scan_data_models_file(p, "Elixir", "backend")
        self.assertEqual(out, [])

    def test_ecto_default_store_is_postgres(self):
        self.assertEqual(scan.ORM_DEFAULT_STORE.get("Ecto"), "postgres")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_data_lineage.EctoModelScanTest -v`
Expected: FAIL — `_scan_data_models_file` has no Elixir branch (returns `[]`), and `ORM_DEFAULT_STORE` has no `"Ecto"` key.

- [ ] **Step 3: Add `ECTO_SCHEMA_RE`**

In `scan.py`, after the `JPA_ENTITY_RE = ...` line (currently line 2178), add:

```python
ECTO_SCHEMA_RE = re.compile(r'^\s*schema\s+"([^"]+)"\s+do', re.MULTILINE)
```

(Note: `^\s*schema\s+"..."` — the leading `schema` keyword. This does NOT match `embedded_schema` because `\s+` after `schema` requires whitespace, and `embedded_schema` has no `schema "table"` form; the `^\s*schema` anchor with the quoted table is Ecto's DB-backed schema macro.)

- [ ] **Step 4: Add the Elixir branch in `_scan_data_models_file`**

In `_scan_data_models_file`, after the `elif language in ("Java", "Kotlin"):` block (currently ends ~line 2262, right before `return out`), add:

```python
    elif language == "Elixir":
        # Ecto schemas: `schema "table" do`. Name each model after the
        # enclosing module's last segment (BrevitySchemas.Recommendation ->
        # "Recommendation"); fall back to the table name if no defmodule.
        defmods = [(m.start(), m.group(1)) for m in ELIXIR_DEFMODULE_RE.finditer(text)]
        for sm in ECTO_SCHEMA_RE.finditer(text):
            mod = None
            for start, name in defmods:
                if start < sm.start():
                    mod = name
                else:
                    break
            emit("Ecto", mod.split(".")[-1] if mod else sm.group(1))
```

(`ELIXIR_DEFMODULE_RE` is already defined at scan.py:1232 and `emit` is the local helper in this function.)

- [ ] **Step 5: Add `ORM_DEFAULT_STORE["Ecto"]`**

In the `ORM_DEFAULT_STORE` dict (currently ~2270), add the `"Ecto"` entry:

```python
ORM_DEFAULT_STORE: dict[str, str] = {
    "Prisma": "postgres",
    "SQLAlchemy": "postgres",
    "Mongoose": "mongodb",
    "Django ORM": "postgres",
    "ActiveRecord": "postgres",
    "Spring Data JPA": "postgres",
    "Ecto": "postgres",
}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python3 -m unittest tests.test_data_lineage.EctoModelScanTest -v`
Expected: PASS (4 tests).

- [ ] **Step 7: Run the full suite**

Run: `python3 -m unittest discover -s tests -t . -q`
Expected: OK (309 = 305 + 4 new). The Elixir branch is only reached when called with `language == "Elixir"`; nothing else calls it that way yet (Task 2 wires it into `build_data_lineage`).

- [ ] **Step 8: Commit**

```bash
cd /home/mckechniep/ai-llms/claude/mine/smokeyp-codebase-mapper
git add plugin/skills/map-repo/scripts/scan.py plugin/skills/map-repo/scripts/tests/test_data_lineage.py
git commit -m "feat: detect Ecto schemas in data-lineage model scan"
```
Verify with `git status` that exactly those two files are staged.

---

## Task 2: Wire Elixir into `build_data_lineage`

**Files:**
- Modify: `scripts/scan.py` (`build_data_lineage` language allowlist ~2297)
- Test: `scripts/tests/test_data_lineage.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_data_lineage.py`:

```python
class BuildDataLineageEctoTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def test_ecto_models_appear_in_lineage(self):
        self._write(
            "backend/lib/brevity_schemas/trip.ex",
            'defmodule BrevitySchemas.Trip do\n'
            '  schema "trips" do\n'
            '    field :name, :string\n'
            '  end\n'
            'end\n',
        )
        services = [{"id": "backend", "name": "backend", "kind": "backend"}]
        lin = scan.build_data_lineage(self.root, services)
        ecto = {m["model"] for m in lin["models"] if m["framework"] == "Ecto"}
        self.assertIn("Trip", ecto)
        # Ecto -> postgres store (synthesized from ORM default if not detected)
        self.assertTrue(any(s["kind"] == "postgres" for s in lin["stores"]))
        # backend -> postgres edge carrying the model
        self.assertTrue(any(
            e["target_store"] == "postgres" and "Trip" in e["models"]
            for e in lin["edges"]))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_data_lineage.BuildDataLineageEctoTest -v`
Expected: FAIL — `build_data_lineage`'s language allowlist excludes `"Elixir"`, so `Trip` never enters `models` (the `ecto` set is empty → `assertIn` fails).

- [ ] **Step 3: Add `"Elixir"` to the allowlist**

In `build_data_lineage` (scan.py ~2297), change:

```python
        if lname not in ("TypeScript", "JavaScript", "Python", "Ruby", "Java", "Kotlin"):
            continue
```
to:
```python
        if lname not in ("TypeScript", "JavaScript", "Python", "Ruby", "Java", "Kotlin", "Elixir"):
            continue
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_data_lineage.BuildDataLineageEctoTest -v`
Expected: PASS. (The `postgres` store appears via the placeholder-synthesis path at scan.py:2337-2344 — `ORM_DEFAULT_STORE["Ecto"]` = postgres, and the edge builder synthesizes the store when it isn't already detected.)

- [ ] **Step 5: Run the full suite**

Run: `python3 -m unittest discover -s tests -t . -q`
Expected: OK (310). Golden unaffected (fittalk has no Elixir files; the golden renders a static codemap anyway).

- [ ] **Step 6: Commit**

```bash
cd /home/mckechniep/ai-llms/claude/mine/smokeyp-codebase-mapper
git add plugin/skills/map-repo/scripts/scan.py plugin/skills/map-repo/scripts/tests/test_data_lineage.py
git commit -m "feat: scan Elixir files for Ecto models in build_data_lineage"
```

---

## Task 3: Product-scope the lineage (`_vendored_path` guard)

**Files:**
- Modify: `scripts/scan.py` (`build_data_lineage` per-file loop ~2292 + `schema.prisma` rglob ~2305)
- Test: `scripts/tests/test_data_lineage.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_data_lineage.py`:

```python
class LineageVendoredFilterTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def test_vendored_ecto_schema_excluded(self):
        self._write(
            "backend/lib/trip.ex",
            'defmodule App.Trip do\n  schema "trips" do\n    field :x, :string\n  end\nend\n')
        self._write(
            "g.frame-develop/lib/foo.ex",
            'defmodule Foo do\n  schema "foos" do\n    field :y, :string\n  end\nend\n')
        services = [{"id": "backend", "name": "backend", "kind": "backend"}]
        lin = scan.build_data_lineage(self.root, services)
        names = {m["model"] for m in lin["models"]}
        self.assertIn("Trip", names)
        self.assertNotIn("Foo", names)  # vendored (-develop) excluded

    def test_vendored_prisma_schema_excluded(self):
        self._write(
            "app/prisma/schema.prisma", 'model Account {\n  id Int @id\n}\n')
        self._write(
            "blues-stack-main/prisma/schema.prisma", 'model User {\n  id Int @id\n}\n')
        services = [{"id": "app", "name": "app", "kind": "backend"}]
        lin = scan.build_data_lineage(self.root, services)
        names = {m["model"] for m in lin["models"]}
        self.assertIn("Account", names)
        self.assertNotIn("User", names)  # vendored (-main) prisma excluded
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_data_lineage.LineageVendoredFilterTest -v`
Expected: FAIL — no `_vendored_path` filtering yet, so `Foo` and `User` (under `g.frame-develop/` and `blues-stack-main/`) leak into `models`; both `assertNotIn` fail.

- [ ] **Step 3: Guard the per-file model loop**

In `build_data_lineage`, the per-file loop (scan.py ~2292-2300) currently is:

```python
    for f in iter_files(root):
        lang = detect_language(f)
        if not lang or is_binary(f):
            continue
        lname = lang[0]
        if lname not in ("TypeScript", "JavaScript", "Python", "Ruby", "Java", "Kotlin", "Elixir"):
            continue
        service_id = _file_to_service_id(f, root, services)
        raw_models.extend(_scan_data_models_file(f, lname, service_id))
```
Add a `_vendored_path` guard right after the language check:

```python
        if lname not in ("TypeScript", "JavaScript", "Python", "Ruby", "Java", "Kotlin", "Elixir"):
            continue
        if _vendored_path(str(f.relative_to(root))):
            continue
        service_id = _file_to_service_id(f, root, services)
        raw_models.extend(_scan_data_models_file(f, lname, service_id))
```

- [ ] **Step 4: Guard the `schema.prisma` rglob**

The Prisma pass (scan.py ~2305-2317) currently is:

```python
    for f in root.rglob("schema.prisma"):
        if any(part in SKIP_DIRS for part in f.parts):
            continue
        text = safe_read(f, limit=64 * 1024)
```
Add the `_vendored_path` check alongside the `SKIP_DIRS` check:

```python
    for f in root.rglob("schema.prisma"):
        if any(part in SKIP_DIRS for part in f.parts):
            continue
        if _vendored_path(str(f.relative_to(root))):
            continue
        text = safe_read(f, limit=64 * 1024)
```

(`_vendored_path` is defined at scan.py:128 — no import needed; it's in the same module.)

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m unittest tests.test_data_lineage.LineageVendoredFilterTest -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `python3 -m unittest discover -s tests -t . -q`
Expected: OK (312). No existing test exercises `build_data_lineage` with vendored fixtures, so this is additive.

- [ ] **Step 7: Commit**

```bash
cd /home/mckechniep/ai-llms/claude/mine/smokeyp-codebase-mapper
git add plugin/skills/map-repo/scripts/scan.py plugin/skills/map-repo/scripts/tests/test_data_lineage.py
git commit -m "fix: product-scope data-lineage (exclude vendored-path schemas + prisma)"
```

---

## Task 4: Detect Postgres from Elixir `config/*.exs`

**Files:**
- Modify: `scripts/scan.py` (`_detect_stores` source list ~2190 + subdir loop ~2196; `STORE_PATTERNS` ~2152)
- Test: `scripts/tests/test_data_lineage.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_data_lineage.py`:

```python
class StoreFromConfigTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def test_postgres_from_root_config_exs(self):
        self._write(
            "config/config.exs",
            'config :app, App.Repo,\n  adapter: Ecto.Adapters.Postgres\n')
        stores = scan._detect_stores(self.root)
        self.assertTrue(any(s["kind"] == "postgres" for s in stores))

    def test_postgres_from_service_config_exs(self):
        self._write(
            "backend/config/runtime.exs",
            'config :brevity, Brevity.Repo, adapter: Ecto.Adapters.Postgres\n')
        stores = scan._detect_stores(self.root)
        self.assertTrue(any(s["kind"] == "postgres" for s in stores))

    def test_postgrex_dep_maps_to_postgres(self):
        self._write("config/dev.exs", 'config :app, deps: [:postgrex]\n')
        stores = scan._detect_stores(self.root)
        self.assertTrue(any(s["kind"] == "postgres" for s in stores))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_data_lineage.StoreFromConfigTest -v`
Expected: FAIL — `_detect_stores` doesn't read `config/*.exs`, so no postgres store from them. (`test_postgrex_dep_maps_to_postgres` also needs the new postgrex pattern.)

- [ ] **Step 3: Add a `postgrex` store pattern**

In `STORE_PATTERNS` (scan.py ~2154), add a postgrex line right after the postgres line (so the Elixir Postgres driver maps to a postgres store; note `\bpostgres\b` does NOT match "postgrex"):

```python
    (r"\bpostgres(?:ql)?\b", "postgres", "PostgreSQL"),
    (r"\bpostgrex\b", "postgres", "PostgreSQL"),
```

- [ ] **Step 4: Read `config/*.exs` at root and in service subdirs**

In `_detect_stores`, the root source list (scan.py ~2190) currently is:

```python
    for name in (".env", ".env.example", ".env.local", "config/database.yml"):
        p = root / name
        if p.is_file():
            sources.append((name, safe_read(p, limit=64 * 1024)))
```
Extend the tuple with the Elixir config files:

```python
    for name in (".env", ".env.example", ".env.local", "config/database.yml",
                 "config/config.exs", "config/dev.exs", "config/runtime.exs"):
        p = root / name
        if p.is_file():
            sources.append((name, safe_read(p, limit=64 * 1024)))
```

Then the service-subdir loop (scan.py ~2196-2201) currently is:

```python
    for d in root.iterdir() if root.is_dir() else []:
        if d.is_dir() and d.name not in SKIP_DIRS and not d.name.startswith("."):
            for name in (".env", ".env.example"):
                p = d / name
                if p.is_file():
                    sources.append((f"{d.name}/{name}", safe_read(p, limit=64 * 1024)))
```
Extend its inner tuple with the config files:

```python
    for d in root.iterdir() if root.is_dir() else []:
        if d.is_dir() and d.name not in SKIP_DIRS and not d.name.startswith("."):
            for name in (".env", ".env.example",
                         "config/config.exs", "config/dev.exs", "config/runtime.exs"):
                p = d / name
                if p.is_file():
                    sources.append((f"{d.name}/{name}", safe_read(p, limit=64 * 1024)))
```

(`Ecto.Adapters.Postgres` lowercased is `ecto.adapters.postgres`; the existing `\bpostgres(?:ql)?\b` pattern matches `postgres` after the `.` word boundary, so reading the file is sufficient for the adapter case. The postgrex pattern covers `:postgrex` dependency references.)

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m unittest tests.test_data_lineage.StoreFromConfigTest -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Run the full suite**

Run: `python3 -m unittest discover -s tests -t . -q`
Expected: OK (315). Additive — no existing fixture has `config/*.exs`.

- [ ] **Step 7: Commit**

```bash
cd /home/mckechniep/ai-llms/claude/mine/smokeyp-codebase-mapper
git add plugin/skills/map-repo/scripts/scan.py plugin/skills/map-repo/scripts/tests/test_data_lineage.py
git commit -m "feat: detect Postgres store from Elixir config/*.exs + postgrex"
```

---

## Task 5: Brevity acceptance verification

**Files:** none (verification only — no code, no commit unless a fix is needed).

- [ ] **Step 1: Re-scan brevity (full depth) to /tmp**

```bash
cd /home/mckechniep/ai-llms/claude/mine/smokeyp-codebase-mapper
python3 plugin/skills/map-repo/scripts/scan.py --path /home/mckechniep/projects/brevity --depth full --out /tmp/claude/brevity.json
```
Expected: scan completes (harmless astgrep fallback lines OK).

- [ ] **Step 2: Verify the lineage acceptance criteria**

```bash
python3 - <<'PY'
import json
d = json.load(open('/tmp/claude/brevity.json'))
lin = d.get('data_lineage', {})
stores = lin.get('stores', [])
models = lin.get('models', [])
ecto = [m for m in models if m['framework'] == 'Ecto']
prisma = [m for m in models if m['framework'] == 'Prisma']
print("stores:", [(s['kind'], s['name']) for s in stores])
print("Ecto model count:", len(ecto))
print("sample Ecto models:", sorted({m['model'] for m in ecto})[:8])
print("Prisma model count (should be 0 — vendored Remix tutorial excluded):", len(prisma))
print("edges:", [(e['source_service'], e['target_store'], e['weight']) for e in lin.get('edges', [])])
ok = (any(s['kind'] == 'postgres' for s in stores)
      and len(ecto) >= 20
      and len(prisma) == 0)
print("ACCEPTANCE:", "PASS" if ok else "FAIL")
PY
```
Expected (REQUIRED to verify): a `postgres` store present; Ecto model count ≈ 30 (the `brevity_schemas`); **Prisma model count 0** (the vendored `blues-stack-main` tutorial no longer leaks); a `backend → postgres` edge with weight ≈ 30. If Ecto count is 0 or Prisma count > 0, STOP and report — the feature isn't taking effect.

- [ ] **Step 3: (optional) eyeball the rendered lineage section**

```bash
python3 plugin/skills/map-repo/scripts/render.py --in /tmp/claude/brevity.json --out /tmp/claude/brevity.html
python3 -c "t=open('/tmp/claude/brevity.html').read(); m=t[t.index('<main>'):t.index('</main>')]; print('Ecto pill present:', 'Ecto' in m); print('postgres store present:', 'postgres' in m.lower())"
```
Expected: `Ecto` framework pill present; postgres store present in the rendered lineage section.

---

## Self-Review

**Spec coverage** (against `2026-06-06-ecto-data-lineage-design.md`):
- §2a enumerate schemas → Task 1 (parser) + Task 2 (wiring). ✓
- §2b `ECTO_SCHEMA_RE`, Elixir branch, `ORM_DEFAULT_STORE["Ecto"]`, allowlist, model-name = module-last-segment with table fallback → Tasks 1, 2. ✓
- §2c store detection from `config/*.exs` + postgrex → Task 4. ✓
- §2d product-scoping `_vendored_path` guard (per-file loop + prisma rglob) → Task 3. ✓
- §2e render no changes → confirmed (no render task). ✓
- §3 testing (Ecto scan, fallback, end-to-end, vendored exclusion, prisma-leak regression, config store) → Tasks 1-4 tests; `embedded_schema` negative + postgrex covered. ✓
- §4 brevity acceptance → Task 5. ✓
- §5 limitations (embedded_schema excluded) → Task 1 `test_embedded_schema_not_matched`. ✓

**Placeholder scan:** every code step shows real code; verification step has the actual script + expected output. No TBD/TODO.

**Type consistency:** the Elixir branch emits the same `{service, framework, model}` dict shape as every other branch in `_scan_data_models_file` (consumed unchanged by `build_data_lineage`'s dedup/edge code). `ECTO_SCHEMA_RE` group(1) = table name; `ELIXIR_DEFMODULE_RE` group(1) = module name — both already-established. `ORM_DEFAULT_STORE["Ecto"] = "postgres"` matches the store kind used by `_detect_stores`/`STORE_PATTERNS` ("postgres"). `_vendored_path(str(f.relative_to(root)))` — identical call form to its other uses in scan.py.

**Risk note:** Task 5 may reveal the brevity Ecto count differs slightly from ~30 (handoff said 31, exploration found 30); the acceptance gate uses `>= 20` to tolerate that while still proving the feature works. Golden is untouched throughout (static-codemap render).
