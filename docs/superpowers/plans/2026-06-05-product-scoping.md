# Product-Scoping (Slice B of v0.10.0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every quantitative section (languages/LOC headline, dependencies, directory tree, tier counts) measure the PRODUCT, not vendored code — leading with product-scoped numbers, repo-wide as a secondary "incl. dependencies" line, with render-time refinement from the LLM's classification.

**Architecture:** Deterministic product = repo-wide − vendored, by subtraction. Each module gains per-language `{files, loc}` stats; a pure `build_language_breakdown(languages_all, modules, is_vendored)` subtracts the vendored modules' stats from the complete file-based totals. Dependency caches (`deps/`, `_build/`) join `SKIP_DIRS`. Deps + tree scope by a path-based vendored check. Render leads with product and refines the vendored set from enrichment via the same subtraction helper.

**Tech Stack:** Python 3.10+ stdlib only, stdlib `unittest`, inline JS/CSS in the rendered HTML.

**Spec:** `docs/superpowers/specs/2026-06-05-product-scoping-design.md`

**Test runner:** `cd plugin/skills/map-repo/scripts && python3 -m unittest discover -s tests -t . -q`

---

## File Structure

All paths under `plugin/skills/map-repo/`.

| File | Change | Responsibility |
|---|---|---|
| `scripts/scan.py` | Modify | `_measure_dir` returns per-language `{files,loc}`; modules carry `lang_stats`; `SKIP_DIRS += deps/_build/_checkouts`; `_vendored_path` helper; `build_language_breakdown`; deps product/repo-wide split; `walk_tree` tags dir nodes `vendored`; `build_data_model` emits product + `_all` aggregates. |
| `scripts/render.py` | Modify | Shared `build_language_breakdown` reuse for enrichment-refined product; cover/languages/deps lead with product + secondary repo-wide line; `_tree_node` collapses `vendored` subtrees; tier counts exclude infra/docs via `_is_infra_or_docs`. |
| `scripts/tests/test_product_scoping.py` | **Create** | `_measure_dir` per-language; `build_language_breakdown` subtraction + nested-vendored dedup; SKIP_DIRS deps exclusion; deps scoping; tree collapse; tier exclusion. |
| `scripts/tests/test_render_*.py` | Modify | Cover/languages/deps product lead; tree collapse render; enrichment refinement shifts product headline. |

---

## Task 1: `_measure_dir` returns per-language `{files, loc}`; modules carry `lang_stats`

**Files:**
- Modify: `scripts/scan.py` (`_measure_dir` 474-487; call sites 513, 611, 666, 688)
- Test: `scripts/tests/test_product_scoping.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_product_scoping.py`:

```python
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scan


class MeasureDirTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _write(self, rel, text):
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def test_measure_dir_returns_per_language_stats(self):
        self._write("a.py", "x = 1\ny = 2\n")        # Python, 2 loc
        self._write("b.py", "z = 3\n")                # Python, 1 loc
        self._write("c.ts", "const a = 1\n")          # TypeScript, 1 loc
        fc, loc, langs, lang_stats = scan._measure_dir(self.dir)
        self.assertEqual(fc, 3)
        self.assertEqual(lang_stats["Python"], {"files": 2, "loc": 3})
        self.assertEqual(lang_stats["TypeScript"], {"files": 1, "loc": 1})
        # langs set unchanged; per-language loc sums to the language totals
        self.assertEqual(set(langs), {"Python", "TypeScript"})
        self.assertEqual(sum(s["loc"] for s in lang_stats.values()),
                         sum(v["loc"] for v in lang_stats.values()))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_product_scoping -v`
Expected: FAIL — `_measure_dir` returns a 3-tuple, so unpacking 4 values raises `ValueError: not enough values to unpack`.

- [ ] **Step 3: Implement — add per-language stats to `_measure_dir`**

Replace `_measure_dir` (scan.py:474-487):

```python
def _measure_dir(d: Path) -> tuple[int, int, set[str], dict[str, dict[str, int]]]:
    """Roll up file_count, loc, language set, and per-language {files, loc}."""
    fc = 0
    loc = 0
    langs: set[str] = set()
    lang_stats: dict[str, dict[str, int]] = {}
    for f in iter_files(d):
        if is_binary(f):
            continue
        n = count_lines(f)
        fc += 1
        loc += n
        lang = detect_language(f)
        if lang:
            name = lang[0]
            langs.add(name)
            st = lang_stats.setdefault(name, {"files": 0, "loc": 0})
            st["files"] += 1
            st["loc"] += n
    return (fc, loc, langs, lang_stats)
```

- [ ] **Step 4: Update the four call sites**

In scan.py, update each `_measure_dir` unpack and store `lang_stats` on the module where applicable:
- **Line 513** (`emit_module` in `_modules_within`): change `fc, loc, langs = _measure_dir(d)` to `fc, loc, langs, lang_stats = _measure_dir(d)`, and add `"lang_stats": lang_stats,` to the module dict it appends.
- **Line 611** (monorepo service container): change to `fc, loc, langs, _ls = _measure_dir(container)` (service records don't need lang_stats; discard with `_ls`).
- **Line 666** (loose top-level dir): change to `fc, loc, langs, lang_stats = _measure_dir(loose)` and add `"lang_stats": lang_stats,` to that module dict (it is a module record — read the dict it builds and add the field alongside `"languages"`).
- **Line 688** (single-service root): change `fc, loc, _ = _measure_dir(root)` to `fc, loc, _langs, _ls = _measure_dir(root)`.

Read each site first to place the `lang_stats` field correctly (only the two that build a *module* record — 513 and 666 — store it).

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m unittest tests.test_product_scoping -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `python3 -m unittest discover -s tests -t . -q`
Expected: OK (the 4-tuple change is internal; module dicts gain a field, which is additive).

- [ ] **Step 7: Commit**

```bash
git add scripts/scan.py scripts/tests/test_product_scoping.py
git commit -m "feat: _measure_dir returns per-language {files,loc}; modules carry lang_stats"
```
Use exact paths; never `git add -A` (the tree has unrelated untracked junk).

---

## Task 2: Exclude dependency caches (`deps/`, `_build/`) from `SKIP_DIRS`

**Files:**
- Modify: `scripts/scan.py:87-99` (`SKIP_DIRS`)
- Test: `scripts/tests/test_product_scoping.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_product_scoping.py`:

```python
class SkipDirsTest(unittest.TestCase):
    def test_dependency_caches_are_skipped(self):
        for name in ("deps", "_build", "_checkouts"):
            self.assertIn(name, scan.SKIP_DIRS)

    def test_deps_dir_excluded_from_languages(self):
        import shutil, tempfile
        d = Path(tempfile.mkdtemp())
        try:
            (d / "lib").mkdir()
            (d / "lib" / "app.ex").write_text("defmodule App do\nend\n")
            (d / "deps").mkdir()
            (d / "deps" / "phoenix").mkdir()
            (d / "deps" / "phoenix" / "lib.ex").write_text("x\n" * 500)
            langs = scan.aggregate_languages(d)
            elixir = next((l for l in langs if l["name"] == "Elixir"), None)
            self.assertIsNotNone(elixir)
            self.assertEqual(elixir["files"], 1)  # only lib/app.ex, not deps/
        finally:
            shutil.rmtree(d, ignore_errors=True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_product_scoping.SkipDirsTest -v`
Expected: FAIL — `deps`/`_build`/`_checkouts` not in `SKIP_DIRS`; the `deps/phoenix/lib.ex` is counted (elixir files == 2).

- [ ] **Step 3: Implement**

In `scan.py`, add to the `SKIP_DIRS` frozenset (after `"vendor",` on line 98):

```python
    "vendor",
    "deps", "_build", "_checkouts",   # Elixir hex cache + build artifacts
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_product_scoping.SkipDirsTest -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `python3 -m unittest discover -s tests -t . -q`
Expected: OK (no fixture has a `deps/` dir; fittalk is TS, unaffected).

- [ ] **Step 6: Commit**

```bash
git add scripts/scan.py scripts/tests/test_product_scoping.py
git commit -m "feat: exclude Elixir deps/_build dependency caches from all aggregates"
```

---

## Task 3: `_vendored_path` helper + `build_language_breakdown` (product = all − vendored)

**Files:**
- Modify: `scripts/scan.py` (refactor `_vendored_guess` to use `_vendored_path`; add `build_language_breakdown`)
- Test: `scripts/tests/test_product_scoping.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_product_scoping.py`:

```python
class LanguageBreakdownTest(unittest.TestCase):
    def _mod(self, path, vendored, stats):
        return {"path": path, "vendored_guess": vendored, "lang_stats": stats}

    def test_vendored_path(self):
        self.assertTrue(scan._vendored_path("google_ads-master/lib/x.ex"))
        self.assertTrue(scan._vendored_path("a/third_party/b.py"))
        self.assertFalse(scan._vendored_path("backend/lib/app.ex"))

    def test_product_is_all_minus_vendored(self):
        languages_all = [
            {"name": "Elixir", "color": "#6e4a7e", "files": 10, "loc": 1000},
            {"name": "HTML", "color": "#e34c26", "files": 5, "loc": 700},
        ]
        modules = [
            self._mod("backend", False, {"Elixir": {"files": 8, "loc": 800}}),
            self._mod("g.frame-develop", True, {"HTML": {"files": 5, "loc": 700}}),
        ]
        prod = scan.build_language_breakdown(languages_all, modules,
                                             lambda m: m["vendored_guess"])
        by = {l["name"]: l for l in prod}
        # HTML was entirely vendored -> gone; Elixir kept whole (vendored module
        # had no Elixir, and loose Elixir files survive)
        self.assertNotIn("HTML", by)
        self.assertEqual(by["Elixir"], {"name": "Elixir", "color": "#6e4a7e",
                                        "files": 10, "loc": 1000})

    def test_nested_vendored_not_double_subtracted(self):
        languages_all = [{"name": "JS", "color": "#f1e05a", "files": 10, "loc": 1000}]
        modules = [
            self._mod("ads-master", True, {"JS": {"files": 10, "loc": 1000}}),
            # nested under ads-master: its files are already in the parent's stats
            self._mod("ads-master/sub-master", True, {"JS": {"files": 4, "loc": 400}}),
        ]
        prod = scan.build_language_breakdown(languages_all, modules,
                                             lambda m: m["vendored_guess"])
        # only the top-level vendored module is subtracted (10), not 10+4
        self.assertEqual(prod, [])  # JS fully vendored, dropped (not negative)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_product_scoping.LanguageBreakdownTest -v`
Expected: FAIL — `_vendored_path` and `build_language_breakdown` don't exist.

- [ ] **Step 3: Implement `_vendored_path` (refactor `_vendored_guess`)**

In `scan.py`, add before `_vendored_guess` (line 127):

```python
def _vendored_path(rel_path: str) -> bool:
    """Path-only vendored signal: a git-archive clone suffix on any segment, or
    a conventional vendor segment. The cheap half of _vendored_guess, reusable
    where only a path is available (deps manifests, tree nodes)."""
    parts = [p.lower() for p in Path(rel_path).parts]
    if any(p in VENDORED_PATH_SEGMENTS for p in parts):
        return True
    if any(p.endswith(VENDORED_DIR_SUFFIXES) for p in parts):
        return True
    return False
```

Then change `_vendored_guess` (lines 135-138) to delegate its path checks:

```python
    if _vendored_path(rel_path):
        return True
    pkg = module_dir / "package.json"
    if pkg.is_file():
```
(Remove the now-duplicated `parts =`/`if any(...)` lines that `_vendored_path` replaces — read the current body and keep the package.json check intact below.)

- [ ] **Step 4: Implement `build_language_breakdown`**

Add near `aggregate_languages` in `scan.py`:

```python
def _is_under(child: str, parent: str) -> bool:
    """True if child path is strictly inside parent path."""
    return child != parent and (child + "/").startswith(parent.rstrip("/") + "/")


def build_language_breakdown(languages_all, modules, is_vendored):
    """Product per-language list = repo-wide minus the vendored modules' stats.

    Subtracts each TOP-LEVEL vendored module's per-language {files, loc} from the
    complete file-based ``languages_all`` (nested vendored modules are skipped so
    their measurements aren't double-subtracted). A language reduced to nothing
    is dropped. Pure: ``is_vendored(module) -> bool`` is the only classification
    input, so render can pass an enrichment-refined predicate."""
    vendored = [m for m in modules if is_vendored(m)]
    top = [m for m in vendored
           if not any(o is not m and _is_under(m.get("path", ""), o.get("path", ""))
                      for o in vendored)]
    sub: dict[str, dict[str, int]] = {}
    for m in top:
        for lang, st in (m.get("lang_stats") or {}).items():
            agg = sub.setdefault(lang, {"files": 0, "loc": 0})
            agg["files"] += st.get("files", 0)
            agg["loc"] += st.get("loc", 0)
    out = []
    for lang in languages_all:
        s = sub.get(lang["name"], {})
        files = lang["files"] - s.get("files", 0)
        loc = lang["loc"] - s.get("loc", 0)
        if files > 0 or loc > 0:
            out.append({**lang, "files": files, "loc": loc})
    return sorted(out, key=lambda b: b["loc"], reverse=True)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m unittest tests.test_product_scoping.LanguageBreakdownTest -v`
Expected: PASS.

- [ ] **Step 6: Wire into `build_data_model`**

In `build_data_model`, after `languages = aggregate_languages(root)` (line 2462) and after `modules` are built, compute product + repo-wide aggregates. Rename the repo-wide and add product:

```python
    languages_all = aggregate_languages(root)
    languages = build_language_breakdown(languages_all, modules,
                                         lambda m: bool(m.get("vendored_guess")))
    total_files_all = sum(l["files"] for l in languages_all)
    total_loc_all = sum(l["loc"] for l in languages_all)
    total_files = sum(l["files"] for l in languages)
    total_loc = sum(l["loc"] for l in languages)
```

In the returned dict (the `project` block ~2498 and top-level ~2503), emit both:
- `project.total_files` / `total_loc` = product (the lead); add `project.total_files_all` / `total_loc_all` = repo-wide.
- top-level `"languages": languages` (product) and `"languages_all": languages_all`.

(Read the exact `modules` variable name in `build_data_model` — it must be the full module list with `lang_stats`. Compute the breakdown AFTER modules exist.)

- [ ] **Step 7: Run the full suite**

Run: `python3 -m unittest discover -s tests -t . -q`
Expected: a `test_render_enrichment` golden body failure is LIKELY (the deterministic cover numbers now product-scope on fittalk; if fittalk has any `-master`/`-develop` module or vendored module, the numbers shift). If it fails, DO NOT regenerate the golden yet — that happens in Task 9 after all scanner changes land. Note the failure and proceed; if it passes (fittalk has no vendored modules so product == repo-wide), even better. Report which.

- [ ] **Step 8: Commit**

```bash
git add scripts/scan.py scripts/tests/test_product_scoping.py
git commit -m "feat: product-scoped language/LOC aggregates (product = repo-wide minus vendored)"
```

---

## Task 4: Deps product/repo-wide scoping

**Files:**
- Modify: `scripts/scan.py` (`find_dependencies` 834-878; `build_data_model` deps emit)
- Test: `scripts/tests/test_product_scoping.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_product_scoping.py`:

```python
class DepsScopingTest(unittest.TestCase):
    def test_vendored_manifest_excluded_from_product_deps(self):
        import shutil, tempfile
        d = Path(tempfile.mkdtemp())
        try:
            (d / "backend").mkdir()
            (d / "backend" / "mix.exs").write_text(
                'defp deps do\n  [{:phoenix, "~> 1.6"}]\nend\n')
            (d / "google_ads-master").mkdir()
            (d / "google_ads-master" / "mix.exs").write_text(
                'defp deps do\n  [{:grpc, "~> 0.5"}, {:google_protos, "~> 0.1"}]\nend\n')
            product = scan.find_dependencies(d, None, product_only=True)
            repo_wide = scan.find_dependencies(d, None, product_only=False)
            hex_product = next((e for e in product if e["ecosystem"] == "hex"), None)
            hex_all = next((e for e in repo_wide if e["ecosystem"] == "hex"), None)
            prod_names = {p["name"] for p in hex_product["packages"]}
            all_names = {p["name"] for p in hex_all["packages"]}
            self.assertIn("phoenix", prod_names)
            self.assertNotIn("grpc", prod_names)       # vendored manifest excluded
            self.assertIn("grpc", all_names)            # present repo-wide
        finally:
            shutil.rmtree(d, ignore_errors=True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_product_scoping.DepsScopingTest -v`
Expected: FAIL — `find_dependencies` has no `product_only` parameter (TypeError).

- [ ] **Step 3: Implement — add `product_only` to `find_dependencies`**

In `scan.py`, change the `find_dependencies` signature and skip vendored-path manifests when `product_only`:

```python
def find_dependencies(root: Path, max_per_ecosystem: int | None,
                      product_only: bool = False) -> list[dict[str, Any]]:
```
Inside its file loop, after computing the manifest's rel path and before parsing it, add:
```python
        rel = str(f.relative_to(root))
        if product_only and _vendored_path(rel):
            continue
```
(Read the loop to find where `f` and its rel path are available; `iter_files` already excludes `SKIP_DIRS`, so `deps/` manifests are never seen. The `product_only` skip only drops the `-master`/`-develop` clone manifests.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_product_scoping.DepsScopingTest -v`
Expected: PASS.

- [ ] **Step 5: Wire into `build_data_model`**

Where deps are built (search `find_dependencies(` in `build_data_model`), produce both:
```python
    deps = find_dependencies(root, max_deps, product_only=True)
    deps_all = find_dependencies(root, max_deps, product_only=False)
```
Emit `"deps": deps` (product lead) and `"deps_all": deps_all` in the returned dict.

- [ ] **Step 6: Run the full suite**

Run: `python3 -m unittest discover -s tests -t . -q`
Expected: OK (or the same Task-3 golden note; do not regenerate yet).

- [ ] **Step 7: Commit**

```bash
git add scripts/scan.py scripts/tests/test_product_scoping.py
git commit -m "feat: product-scoped dependencies (exclude vendored-clone manifests)"
```

---

## Task 5: Tier counts exclude infra/docs

**Files:**
- Modify: `scripts/render.py` (`_sysmap_select` band assignment ~2872; `_is_infra_or_docs` new)
- Test: `scripts/tests/test_render_system_map.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_render_system_map.py` (it has `synthetic_data()` and imports `render`):

```python
class TierExclusionTest(unittest.TestCase):
    def test_is_infra_or_docs(self):
        for p in ("docs", "docs/guide", "infra/terraform", ".github/workflows", "ops"):
            self.assertTrue(render._is_infra_or_docs(p), p)
        for p in ("backend/lib", "apps/web", "services/api"):
            self.assertFalse(render._is_infra_or_docs(p), p)

    def test_docs_module_not_counted_as_backend(self):
        data = synthetic_data()
        # add a docs module/service with no real code role
        data["services"].append({"id": "docs", "name": "docs", "kind": "unknown",
            "loc": 200, "file_count": 5, "color": "#888", "primary_language": "Markdown"})
        data["module_graph"]["nodes"].append({"id": "docs/guide", "name": "guide",
            "service": "docs", "loc": 200, "files": 5, "primary_language": "Markdown",
            "color": "#888", "vendored_guess": False})
        sel = render._sysmap_select(data, None)
        backend_ids = {n["id"] for n in sel["bands"]["backend"]}
        self.assertNotIn("docs/guide", backend_ids)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_render_system_map.TierExclusionTest -v`
Expected: FAIL — `_is_infra_or_docs` doesn't exist; `docs/guide` currently lands in the backend band.

- [ ] **Step 3: Implement**

In `render.py`, add near `SYSMAP_FRONTEND_KINDS` (line 2759):

```python
_INFRA_DOCS_SEGMENTS = frozenset({
    "docs", "doc", "documentation", "infra", "infrastructure",
    "ops", "deploy", "deployment", "ci", ".github",
})


def _is_infra_or_docs(path: str) -> bool:
    """A module path that is documentation or infrastructure, not a service tier."""
    parts = [p.lower() for p in path.split("/") if p]
    return any(p in _INFRA_DOCS_SEGMENTS for p in parts)
```

In `_sysmap_select`, where nodes are bucketed into bands (the loop at ~2872-2878), skip infra/docs nodes:
```python
    for n in visible:
        if _is_infra_or_docs(n.get("id", "")):
            continue
        svc = services.get(n.get("service")) or {}
        ...
```
(Read the exact loop; add the `_is_infra_or_docs` guard at its top so those nodes never enter `frontend`/`backend` bands or their counts.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_render_system_map.TierExclusionTest -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `python3 -m unittest discover -s tests -t . -q`
Expected: OK — `synthetic_data()` has no docs/infra modules, so existing band tests are unchanged. (Golden note as Task 3.)

- [ ] **Step 6: Commit**

```bash
git add scripts/render.py scripts/tests/test_render_system_map.py
git commit -m "feat: exclude docs/infra modules from tier (frontend/backend) counts"
```

---

## Task 6: Directory tree — tag + collapse vendored subtrees

**Files:**
- Modify: `scripts/scan.py` (`walk_tree` 237-291 — tag dir nodes `vendored`); `scripts/render.py` (`_tree_node` ~2632 — collapse)
- Test: `scripts/tests/test_product_scoping.py` + `scripts/tests/test_render_*` (tree)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_product_scoping.py`:

```python
class TreeVendoredTest(unittest.TestCase):
    def test_walk_tree_tags_vendored_dirs(self):
        import shutil, tempfile
        d = Path(tempfile.mkdtemp())
        try:
            (d / "backend").mkdir()
            (d / "backend" / "app.ex").write_text("x\n")
            (d / "google_ads-master").mkdir()
            (d / "google_ads-master" / "x.ex").write_text("y\n" * 100)
            tree = scan.walk_tree(d, None)
            kids = {c["name"]: c for c in tree["children"]}
            self.assertTrue(kids["google_ads-master"].get("vendored"))
            self.assertFalse(kids["backend"].get("vendored", False))
        finally:
            shutil.rmtree(d, ignore_errors=True)
```

And a render test — add to `tests/test_render_system_map.py` (or wherever `render_tree` is tested; create a small class):

```python
class TreeCollapseTest(unittest.TestCase):
    def test_vendored_subtree_collapses_to_summary(self):
        data = {"tree": {"name": "root", "type": "dir", "file_count": 200,
                         "loc": 100000, "children": [
            {"name": "backend", "type": "dir", "file_count": 10, "loc": 2000,
             "children": [{"name": "app.ex", "type": "file", "language": "Elixir",
                           "loc": 50}]},
            {"name": "google_ads-master", "type": "dir", "file_count": 190,
             "loc": 98000, "vendored": True, "children": [
                {"name": "x.ex", "type": "file", "language": "Elixir", "loc": 500}]},
        ]}}
        html = render.render_tree(data)
        self.assertIn("vendored", html)              # the collapse marker
        self.assertNotIn(">x.ex<", html)             # vendored child not expanded
        self.assertIn("app.ex", html)                # product child still shown
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_product_scoping.TreeVendoredTest tests.test_render_system_map.TreeCollapseTest -v`
Expected: FAIL — `walk_tree` doesn't tag `vendored`; `_tree_node` expands all children.

- [ ] **Step 3: Implement — tag dir nodes in `walk_tree`**

In `scan.py` `walk_tree`, where a directory node dict is built (the normal-path branch ~259-288), add a `vendored` flag from the node's path. The walk has the dir path available; compute the rel path from root and set:
```python
        node["vendored"] = _vendored_path(str(node_path.relative_to(root)))
```
(Read `walk_tree` to find the node-construction point and the available `node_path`/`root`. Set `vendored` only on dir nodes. `root` may need threading into the recursive `_walk` — if `_walk` is a closure over `root`, use it directly.)

- [ ] **Step 4: Implement — collapse in `_tree_node`**

In `render.py` `_tree_node` (~2632), before recursing into a dir node's children, branch on `vendored`:
```python
    if node.get("type") == "dir" and node.get("vendored"):
        fc = node.get("file_count", 0)
        loc = node.get("loc", 0)
        return (f'<div class="tree-vendored">▸ {escape(node["name"])}/ — '
                f'{fmt_num(fc)} files · {fmt_num(loc)} LOC · '
                f'<span class="tree-vendored-tag">vendored (hidden)</span></div>')
```
(Place this as the first branch inside `_tree_node` after the file-node handling but before normal dir expansion. Use the file `fmt_num`/`escape` helpers already imported. Add a small `.tree-vendored` / `.tree-vendored-tag` CSS rule near the other tree CSS — muted color, monospace.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_product_scoping.TreeVendoredTest tests.test_render_system_map.TreeCollapseTest -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `python3 -m unittest discover -s tests -t . -q`
Expected: OK (golden note as Task 3).

- [ ] **Step 7: Commit**

```bash
git add scripts/scan.py scripts/render.py scripts/tests/test_product_scoping.py scripts/tests/test_render_system_map.py
git commit -m "feat: collapse vendored subtrees in the directory tree to a summary line"
```

---

## Task 7: Render leads with product; repo-wide secondary; labeled counts

**Files:**
- Modify: `scripts/render.py` (cover, `render_languages`, `render_deps`)
- Test: `scripts/tests/test_render_*`

- [ ] **Step 1: Write the failing test**

Add to a render test file (e.g. `tests/test_render_enrichment.py` or a new `tests/test_render_product.py` — create it):

```python
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import render


def _data():
    return {
        "project": {"name": "p", "total_files": 100, "total_loc": 12000,
                    "total_files_all": 700, "total_loc_all": 1300000,
                    "primary_language": "Elixir"},
        "languages": [{"name": "Elixir", "color": "#6e4a7e", "files": 100, "loc": 12000}],
        "languages_all": [{"name": "HTML", "color": "#e34c26", "files": 600, "loc": 1288000},
                          {"name": "Elixir", "color": "#6e4a7e", "files": 100, "loc": 12000}],
        "deps": [{"ecosystem": "hex", "file": "mix.exs", "count": 1,
                  "packages": [{"name": "phoenix", "version": "~> 1.6"}]}],
        "deps_all": [{"ecosystem": "hex", "file": "mix.exs ×84", "count": 119,
                      "packages": [{"name": "phoenix", "version": "~> 1.4"}]}],
    }


class ProductLeadTest(unittest.TestCase):
    def test_cover_leads_with_product_loc(self):
        html = render.render_cover(_data())
        self.assertIn("12,000", html)            # product LOC leads
        self.assertIn("incl. dependencies", html)  # repo-wide secondary line
        self.assertIn("1,300,000", html)           # repo-wide secondary number

    def test_languages_section_leads_product(self):
        html = render.render_languages(_data())
        # product languages drive the bars; repo-wide shown as a secondary aside
        self.assertIn("Elixir", html)
        self.assertIn("incl. dependencies", html)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_render_product -v`
Expected: FAIL — cover/languages don't yet emit the "incl. dependencies" secondary line or lead with the product number.

- [ ] **Step 3: Implement**

Read `render_cover`, `render_languages`, and `render_deps` in `render.py`. For each:
- Lead with the product fields (`data["project"]["total_loc"]`, `data["languages"]`, `data["deps"]`) which are now product-scoped.
- Add a muted secondary line using the `_all` fields: `incl. dependencies: {total_loc_all} lines across {total_files_all} files` on the cover; an aside on the languages section; and for deps, a `incl. dependencies (N)` note linking to `deps_all`.
- Where the cover currently labels the headline (e.g. "Primary language X · N lines"), keep the product number as the lead and add the secondary line beneath. Label the cover's file/LOC as **code** (it counts known-language files) to explain any residual difference from the tree's all-files count (Task 6 / §2f).

Use the existing `fmt_num`/markup helpers. Keep additions enrichment-independent (these are deterministic product fields).

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_render_product -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `python3 -m unittest discover -s tests -t . -q`
Expected: the golden body test fails (deterministic cover/languages/deps output changed — intended). Do NOT regenerate yet (Task 9). Other tests pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/render.py scripts/tests/test_render_product.py
git commit -m "feat: cover/languages/deps lead with product, repo-wide as 'incl. dependencies'"
```

---

## Task 8: Render-time enrichment refinement of the product aggregates

**Files:**
- Modify: `scripts/render.py` (`_apply_enrichment_overrides` or sibling; import `build_language_breakdown` from scan)
- Test: `scripts/tests/test_render_overrides.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_render_overrides.py`:

```python
class ProductRefinementTest(unittest.TestCase):
    def _data(self):
        return {
            "project": {"name": "p", "total_files": 10, "total_loc": 1700,
                        "total_files_all": 10, "total_loc_all": 1700,
                        "primary_language": "Elixir"},
            "languages": [{"name": "Elixir", "color": "#6e4a7e", "files": 10, "loc": 1700}],
            "languages_all": [{"name": "Elixir", "color": "#6e4a7e", "files": 10, "loc": 1700}],
            "modules": [
                {"path": "backend", "vendored_guess": False,
                 "lang_stats": {"Elixir": {"files": 3, "loc": 200}}},
                {"path": "copied-lib", "vendored_guess": False,
                 "lang_stats": {"Elixir": {"files": 7, "loc": 1500}}},
            ],
        }

    def test_enrichment_vendored_reclassification_shrinks_product(self):
        # The LLM marks 'copied-lib' vendored (the heuristic missed it).
        enr = {"classification": {"products": [],
               "vendored": [{"module_id": "copied-lib", "kind": "vendored-lib",
                             "source": "x", "why": "y"}]}}
        out = render._apply_enrichment_overrides(self._data(), enr)
        # product Elixir loc drops from 1700 to 200 (copied-lib subtracted)
        elixir = next(l for l in out["languages"] if l["name"] == "Elixir")
        self.assertEqual(elixir["loc"], 200)
        self.assertEqual(out["project"]["total_loc"], 200)

    def test_no_enrichment_leaves_deterministic_product(self):
        d = self._data()
        out = render._apply_enrichment_overrides(d, None)
        self.assertEqual(out["project"]["total_loc"], 1700)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_render_overrides.ProductRefinementTest -v`
Expected: FAIL — `_apply_enrichment_overrides` doesn't re-derive product languages from enrichment classification.

- [ ] **Step 3: Implement**

In `render.py`, import the shared helper at the top: `from scan import build_language_breakdown` (scan is a sibling module; render already runs with the scripts dir on `sys.path`). In `_apply_enrichment_overrides` (the pure transform added in v0.9.0), after the existing kind/edge overrides, add product re-derivation when enrichment has classification:

```python
    cls = (enrichment or {}).get("classification") or {}
    vendored_ids = {v.get("module_id") for v in (cls.get("vendored") or []) if v.get("module_id")}
    product_ids = {p.get("module_id") for p in (cls.get("products") or []) if p.get("module_id")}
    modules = data.get("modules") or []
    languages_all = data.get("languages_all") or data.get("languages") or []
    if (vendored_ids or product_ids) and modules and languages_all:
        def is_vendored(m):
            mid = m.get("path")
            if mid in product_ids:
                return False          # LLM rescue
            if mid in vendored_ids:
                return True            # LLM catch
            return bool(m.get("vendored_guess"))
        new_langs = build_language_breakdown(languages_all, modules, is_vendored)
        new = dict(new)  # 'new' is the copy already being built in this function
        new["languages"] = new_langs
        proj = dict(new.get("project") or {})
        proj["total_files"] = sum(l["files"] for l in new_langs)
        proj["total_loc"] = sum(l["loc"] for l in new_langs)
        new["project"] = proj
```
(Integrate with the existing `_apply_enrichment_overrides` structure — it already builds a `new = dict(data)` copy and returns it. Add this block before the return, operating on `new`. Read the current function to merge cleanly; ensure the early `if not enrichment: return data` short-circuit still wins so `test_no_enrichment_leaves_deterministic_product` passes.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_render_overrides.ProductRefinementTest -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `python3 -m unittest discover -s tests -t . -q`
Expected: golden body still failing from Task 7 (deterministic) — that's Task 9. The override tests pass; no-enrichment path unchanged.

- [ ] **Step 6: Commit**

```bash
git add scripts/render.py scripts/tests/test_render_overrides.py
git commit -m "feat: render re-derives product aggregates from enrichment classification"
```

---

## Task 9: Regenerate golden + full brevity verification

**Files:**
- Modify: `scripts/tests/fixtures/golden_fittalk.html`

- [ ] **Step 1: Confirm the only failing tests are the golden body tests**

Run: `python3 -m unittest discover -s tests -t . -q 2>&1 | tail -20`
Expected: failures limited to `test_render_enrichment` golden body (and any render test asserting old cover/deps markup — update those expectations to the product-lead structure). If any NON-golden, NON-display test fails, STOP and report — it indicates a real regression.

- [ ] **Step 2: Inspect the golden body diff before regenerating**

```bash
python3 render.py --in /home/mckechniep/projects/fittalk-monorepo/.codemap/codemap.json --out /tmp/claude/fittalk_new.html
python3 -c "
def body(p):
    t=open(p).read(); return t[t.index('<main>'):t.index('</main>')]
import difflib
old=body('tests/fixtures/golden_fittalk.html').splitlines()
new=body('/tmp/claude/fittalk_new.html').splitlines()
print('\n'.join(l for l in difflib.unified_diff(old,new,lineterm='') if l[:1] in '+-')[:4000])
"
```
Expected: the diff is confined to the cover headline (product LOC + 'incl. dependencies' line), the languages section, the deps section, and any tree-collapse lines — i.e. the product-scoping change and nothing else. Confirm there is no unrelated content change. (fittalk is a TS monorepo; if it has no vendored/`-master` modules, product == repo-wide and the diff is just the new secondary lines + labels.)

- [ ] **Step 3: Regenerate the golden**

```bash
cat /tmp/claude/fittalk_new.html > tests/fixtures/golden_fittalk.html
python3 -m unittest tests.test_render_enrichment -q
```
Expected: OK.

- [ ] **Step 4: Run the entire suite**

Run: `python3 -m unittest discover -s tests -t . -q`
Expected: OK, all green.

- [ ] **Step 5: Brevity smoke verification (deterministic, no LLM)**

```bash
cd /home/mckechniep/ai-llms/claude/mine/smokeyp-codebase-mapper
python3 plugin/skills/map-repo/scripts/scan.py --path /home/mckechniep/projects/brevity --depth full --out /tmp/claude/brevity.json
python3 -c "
import json
d=json.load(open('/tmp/claude/brevity.json'))
p=d['project']
print('product LOC:', p['total_loc'], '| repo-wide LOC:', p.get('total_loc_all'))
print('product primary language:', (d['languages'][0]['name'] if d['languages'] else None))
print('repo-wide primary:', (d['languages_all'][0]['name'] if d.get('languages_all') else None))
print('product hex deps count:', next((e['count'] for e in d['deps'] if e['ecosystem']=='hex'), 0))
print('repo-wide hex deps count:', next((e['count'] for e in d['deps_all'] if e['ecosystem']=='hex'), 0))
"
```
Expected (REQUIRED to verify): product LOC is a small fraction of repo-wide (the 517k deps + vendored clones removed); product primary language is **Elixir** (not HTML); product hex deps count is far below the repo-wide 119. If the product primary language is still HTML or product LOC ≈ repo-wide, STOP and report — product-scoping isn't taking effect.

- [ ] **Step 6: Commit**

```bash
git add plugin/skills/map-repo/scripts/tests/fixtures/golden_fittalk.html
git commit -m "test: regenerate golden for product-scoped cover/languages/deps"
```

---

## Self-Review

**Spec coverage** (against `2026-06-05-product-scoping-design.md`):
- §2/§2b core mechanism (`SKIP_DIRS` += caches, `_vendored_path`, product = all − vendored) → Tasks 2, 3. ✓
- §2a data model (`lang_stats`, `total_*`/`total_*_all`, `languages`/`languages_all`) → Tasks 1, 3. ✓
- §2c deps scoping → Task 4. ✓
- §2d tree collapse → Task 6. ✓
- §2e tiers exclude infra/docs → Task 5. ✓
- §2f count reconciliation (label code-vs-all, both product-scoped) → Task 7 (cover labeled "code") + Task 6 (tree product-scoped via collapse/SKIP_DIRS). ✓
- §3 render leads product + enrichment refinement → Tasks 7, 8. ✓
- §4 golden regenerated with verified diff → Task 9. ✓

**Placeholder scan:** every code step has real code. The render-display tasks (5, 6 collapse, 7) instruct reading the specific named functions (`render_cover`/`render_languages`/`render_deps`/`_tree_node`/`_sysmap_select`) because their exact markup must be matched in place — each provides the new code block + the test that pins behavior, not a vague "update the render."

**Type consistency:** `_measure_dir` 4-tuple with `lang_stats: dict[str, dict[str,int]]` — same shape stored on modules (Task 1) and consumed by `build_language_breakdown` (Task 3) and the render refinement (Task 8). `build_language_breakdown(languages_all, modules, is_vendored)` — identical signature in scan (Task 3 def + deterministic call) and render (Task 8 import + enrichment-predicate call). `find_dependencies(root, max, product_only=False)` — Task 4 def + both call sites. `_vendored_path(rel) -> bool` — Task 3 def, reused in Task 4 (deps) and Task 6 (tree). `_is_infra_or_docs(path) -> bool` — Task 5. Data keys (`languages`/`languages_all`, `total_loc`/`total_loc_all`, `deps`/`deps_all`, node `vendored`) are consistent across scanner emit (Tasks 3,4,6) and render consume (Tasks 7,8, tree).

**Risk note carried:** Task 3's golden break is expected and deferred to Task 9; Tasks 3-8 each say "do not regenerate golden yet." The nested-vendored double-subtraction edge is handled by `build_language_breakdown`'s top-level-only filter (Task 3, tested). The cover-vs-tree residual (code files vs all files) is resolved by labeling, not forced equality (Task 7).
