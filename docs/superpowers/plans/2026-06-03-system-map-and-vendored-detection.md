# System Map + Deterministic Vendored Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic `vendored_guess` flag to the scanner and a new "How the system fits together" hero section — a layered-bands map of product modules (frontend → backend → data) wired with import/HTTP/store edges.

**Architecture:** Two-layer change. (1) `scan.py` computes per-module vendored heuristics and propagates them into `module_graph` nodes. (2) `render.py` gains a new deterministic hero section `render_system_map()` placed right after the overview, plus `render_modules()` learns to use the heuristic flag. The renderer stays a pure function of `(codemap.json, enrichment?)`; enrichment refines the vendored filter but is never required.

**Tech Stack:** Python 3.10+ stdlib only (no new dependencies). SVG generated as f-strings. stdlib `unittest` for tests.

**Spec:** `docs/superpowers/specs/2026-06-03-full-coverage-flows-and-system-map-design.md` (Parts 1, 5, 6)

**Working branch:** `feat/0.8.0-flows-and-system-map` (already created)

**Key existing code facts** (verified against current `main`):

| Fact | Location |
|---|---|
| Module dicts built in `emit_module` | `scan.py:410-418` |
| Loose (serviceless) module dicts | `scan.py:542-550` |
| Graph node dicts built | `scan.py:1155-1163` |
| `DEPTH_TIERS` | `scan.py:2195` |
| `TOOL_VERSION = "0.7.0"` | `scan.py:32` |
| CSS string starts | `render.py:22` |
| `@page hero` + print hero rules | `render.py:1525-1570` |
| `SECTION_INTROS` dict | `render.py:1830-1886` |
| `render_modules` (vendored handling) | `render.py:2393-2475` |
| `SERVICE_KIND_COLORS` | `render.py:2482` |
| `_render_observations` | `render.py:2507` |
| `_truncate_label` (MAX_LABEL_CHARS=18) | `render.py:2856` / `render.py:2824` |
| `STORE_KIND_COLORS` | `render.py:4148` |
| `_lineage2_emit_cylinder(x, y, w, h, color)` | `render.py:4879` |
| `render_document` section order | `render.py:5829-5856` |
| Test conventions (`sys.path.insert`, unittest) | `tests/test_render_enrichment.py:1-9` |
| Golden test compares `<main>` body | `tests/test_render_enrichment.py:12-34` |
| Fittalk codemap (test data) | `/home/mckechniep/projects/fittalk-monorepo/.codemap/codemap.json` |
| mini_repo fixture (has `vendor-lib-master/` + `apps/web/`) | `tests/fixtures/mini_repo/` |

**Run all tests:** `cd /home/mckechniep/ai-llms/claude/mine/smokeyp-codebase-mapper && python3 -m unittest discover -s plugin/skills/map-repo/scripts/tests -v`

**Line numbers note:** Line numbers above are accurate at plan-writing time. After Task 1 lands, later line references shift — always locate code by the quoted snippet, not the number.

---

### Task 1: Vendored heuristics in scan.py

The scanner flags modules that look like copied-in third-party code. The flag rides on module dicts AND on module-graph nodes (the map reads nodes, the module cards read modules).

**Files:**
- Modify: `plugin/skills/map-repo/scripts/scan.py`
- Create: `plugin/skills/map-repo/scripts/tests/test_vendored.py`

- [ ] **Step 1: Write the failing test**

Create `plugin/skills/map-repo/scripts/tests/test_vendored.py`:

```python
"""Tests for deterministic vendored-module heuristics.

The mini_repo fixture has a product module (apps/web) and a vendored
git-archive clone (vendor-lib-master). The heuristic must tell them apart
without any LLM involvement, and the flag must propagate to both the
module dicts and the module-graph nodes.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scan

MINI = Path(__file__).resolve().parent / "fixtures" / "mini_repo"


class VendoredHeuristicTest(unittest.TestCase):
    """Unit tests for scan._vendored_guess (pure function)."""

    def test_master_suffix_is_vendored(self):
        self.assertTrue(scan._vendored_guess(
            MINI / "vendor-lib-master", "vendor-lib-master", "mini_repo"))

    def test_develop_suffix_is_vendored(self):
        # Directory need not exist for the path-segment heuristics.
        self.assertTrue(scan._vendored_guess(
            MINI / "g.frame-develop", "g.frame-develop", "mini_repo"))

    def test_vendor_path_segment_is_vendored(self):
        self.assertTrue(scan._vendored_guess(
            MINI / "vendor" / "lib", "vendor/lib", "mini_repo"))

    def test_third_party_segment_is_vendored(self):
        self.assertTrue(scan._vendored_guess(
            MINI / "third_party" / "lib", "third_party/lib", "mini_repo"))

    def test_nested_master_segment_is_vendored(self):
        self.assertTrue(scan._vendored_guess(
            MINI / "google_ads-master" / "lib" / "google",
            "google_ads-master/lib/google", "mini_repo"))

    def test_product_module_is_not_vendored(self):
        self.assertFalse(scan._vendored_guess(
            MINI / "apps" / "web", "apps/web", "mini_repo"))

    def test_main_named_product_dir_is_not_vendored(self):
        # "main" as a directory NAME is fine; only the "-main" SUFFIX flags.
        self.assertFalse(scan._vendored_guess(
            MINI / "src" / "main", "src/main", "mini_repo"))


class VendoredFlagPropagationTest(unittest.TestCase):
    """The flag must appear on module dicts and graph nodes."""

    @classmethod
    def setUpClass(cls):
        cls.services, cls.modules = scan.detect_services_and_modules(MINI)

    def test_modules_carry_vendored_guess_key(self):
        for m in self.modules:
            self.assertIn("vendored_guess", m, f"missing flag on {m['path']}")

    def test_vendor_clone_flagged(self):
        flagged = [m["path"] for m in self.modules if m["vendored_guess"]]
        self.assertTrue(any("vendor-lib-master" in p for p in flagged),
                        f"expected vendor-lib-master flagged, got: {flagged}")

    def test_product_not_flagged(self):
        clean = [m["path"] for m in self.modules if not m["vendored_guess"]]
        self.assertTrue(any("web" in p for p in clean),
                        f"expected web module unflagged, got: {clean}")

    def test_graph_nodes_carry_vendored_guess(self):
        graph = scan.build_module_graph(MINI, self.modules, self.services)
        for n in graph["nodes"]:
            self.assertIn("vendored_guess", n, f"missing flag on node {n['id']}")
        flags = {n["id"]: n["vendored_guess"] for n in graph["nodes"]}
        vendored_nodes = [nid for nid, f in flags.items() if f]
        self.assertTrue(any("vendor-lib-master" in nid for nid in vendored_nodes))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest plugin.skills.map-repo.scripts.tests.test_vendored -v 2>&1 | head -20`

That dotted path won't import (dashes in dirs) — use discovery instead:

Run: `cd plugin/skills/map-repo/scripts && python3 -m unittest tests.test_vendored -v`

Expected: ERROR — `AttributeError: module 'scan' has no attribute '_vendored_guess'`

- [ ] **Step 3: Implement the heuristic function**

In `plugin/skills/map-repo/scripts/scan.py`, add after the `SOURCE_ROOTS` constant (after line 101, before `ENTRY_PATTERNS`):

```python
# -------- vendored-code heuristics --------------------------------------
#
# Deterministic counterpart of the SKILL.md Step 1.5 prose rules: modules
# that look like copied-in third-party code get vendored_guess=True. The
# LLM enrichment can override in BOTH directions at render time
# (classification.products rescues false positives; classification.vendored
# catches what these heuristics miss).

VENDORED_DIR_SUFFIXES: tuple[str, ...] = ("-master", "-develop", "-main")
VENDORED_PATH_SEGMENTS: frozenset[str] = frozenset({
    "vendor", "vendors", "third_party", "third-party", "extern", "external",
})


def _vendored_guess(module_dir: Path, rel_path: str, root_name: str) -> bool:
    """Heuristic: does this module look like vendored third-party code?

    Checks, cheapest first:
      1. A conventional vendor directory segment anywhere in the path.
      2. A git-archive clone suffix (-master/-develop/-main) on any segment.
      3. A package.json whose repository URL doesn't reference this repo.
    """
    parts = [p.lower() for p in Path(rel_path).parts]
    if any(p in VENDORED_PATH_SEGMENTS for p in parts):
        return True
    if any(p.endswith(VENDORED_DIR_SUFFIXES) for p in parts):
        return True
    pkg = module_dir / "package.json"
    if pkg.is_file():
        try:
            meta = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError):
            return False
        if isinstance(meta, dict):
            repo = meta.get("repository")
            if isinstance(repo, dict):
                repo = repo.get("url") or ""
            if isinstance(repo, str) and repo.strip():
                if root_name.lower() not in repo.lower():
                    return True
    return False
```

- [ ] **Step 4: Wire the flag into module dicts**

Three call sites in `scan.py`. First, `emit_module` inside `_modules_within` (currently lines 410-418) — add the flag as the last key:

```python
        out.append({
            "path": str(d.relative_to(root)),
            "name": d.name,
            "service": service_id,
            "file_count": fc,
            "loc": loc,
            "languages": sorted(langs),
            "description": guess_module_description(d),
            "vendored_guess": _vendored_guess(d, str(d.relative_to(root)), root.name),
        })
```

Second, the loose-dirs module dicts in `detect_services_and_modules` (currently lines 542-550):

```python
            modules.append({
                "path": str(loose.relative_to(root)),
                "name": loose.name,
                "service": None,
                "file_count": fc,
                "loc": loc,
                "languages": sorted(langs),
                "description": guess_module_description(loose),
                "vendored_guess": _vendored_guess(loose, str(loose.relative_to(root)), root.name),
            })
```

(The single-service branch at line 581 calls `_modules_within`, so it's covered by the first change.)

Third, propagate to graph nodes in `build_module_graph` (currently lines 1155-1163):

```python
        nodes.append({
            "id": m["path"],
            "name": m["name"],
            "service": m.get("service"),
            "loc": m["loc"],
            "files": m["file_count"],
            "primary_language": lang_name,
            "color": lang_color or "#888888",
            "vendored_guess": bool(m.get("vendored_guess")),
        })
```

- [ ] **Step 5: Run the new tests — verify they pass**

Run: `cd plugin/skills/map-repo/scripts && python3 -m unittest tests.test_vendored -v`

Expected: all tests PASS (OK).

- [ ] **Step 6: Run the FULL suite — verify nothing broke**

Run: `python3 -m unittest discover -s plugin/skills/map-repo/scripts/tests -v 2>&1 | tail -20`

Expected: all existing tests still pass. The golden test (`DegradationTest`) stays green because the fittalk `codemap.json` test data predates the flag (`m.get("vendored_guess")` → `None` → falsy) and `render.py` hasn't changed yet.

- [ ] **Step 7: Commit**

```bash
git add plugin/skills/map-repo/scripts/scan.py plugin/skills/map-repo/scripts/tests/test_vendored.py
git commit -m "feat: deterministic vendored-module heuristics in scanner

Path-segment, git-archive-suffix, and third-party package.json checks
produce a vendored_guess flag on every module dict and graph node.
Mirrors the SKILL.md Step 1.5 prose rules so vendored exclusion no
longer requires LLM enrichment."
```

---

### Task 2: render_modules uses the heuristic flag

The module cards section currently badges/dims/sorts vendored modules only when enrichment classified them. Now it does so from `vendored_guess` too, with enrichment able to override in both directions.

**Files:**
- Modify: `plugin/skills/map-repo/scripts/render.py` (function `render_modules`, currently lines 2393-2475)
- Modify: `plugin/skills/map-repo/scripts/tests/test_render_enrichment.py` (class `ModulesTest`)

- [ ] **Step 1: Write the failing tests**

Add these methods to `ModulesTest` in `plugin/skills/map-repo/scripts/tests/test_render_enrichment.py`:

```python
    def test_heuristic_vendored_without_enrichment(self):
        """vendored_guess alone (no enrichment) badges, dims, and sorts last."""
        data = {"modules": [
            {"path": "glib-master", "file_count": 2, "loc": 9000,
             "languages": ["JavaScript"], "description": "clone",
             "vendored_guess": True},
            {"path": "apps/web", "file_count": 3, "loc": 100,
             "languages": ["TypeScript"], "description": "product",
             "vendored_guess": False},
        ]}
        html = render.render_modules(data, None)
        self.assertIn("vendored", html.lower())
        self.assertIn("is-vendored", html)
        # Product sorts before the (larger) vendored module.
        self.assertLess(html.index("apps/web"), html.index("glib-master"))

    def test_enrichment_product_rescues_heuristic_false_positive(self):
        """classification.products beats vendored_guess=True."""
        data = {"modules": [
            {"path": "tools/build-main", "file_count": 3, "loc": 100,
             "languages": ["TypeScript"], "description": "our build tool",
             "vendored_guess": True},
        ]}
        enr = {
            "schema_version": 1,
            "overview": {"what_it_is": "x", "what_it_does": "y", "how_it_works": "z",
                         "primary_stack": [], "confidence": "low", "caveats": []},
            "classification": {
                "products": [{"module_id": "tools/build-main", "role": "tooling", "why": "ours"}],
                "vendored": [],
            },
            "module_descriptions": [],
            "flows": [],
        }
        html = render.render_modules(data, enr)
        self.assertNotIn("is-vendored", html)

    def test_legacy_data_without_flag_renders_unchanged(self):
        """Module dicts with no vendored_guess key (pre-0.8.0 codemap.json)
        behave exactly as before."""
        data = {"modules": [
            {"path": "apps/web", "file_count": 3, "loc": 100,
             "languages": ["TypeScript"], "description": "product"},
        ]}
        html = render.render_modules(data, None)
        self.assertNotIn("is-vendored", html)
        self.assertNotIn("vendored-badge", html)
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `cd plugin/skills/map-repo/scripts && python3 -m unittest tests.test_render_enrichment.ModulesTest -v`

Expected: `test_heuristic_vendored_without_enrichment` FAILS (no vendored badge without enrichment today). `test_enrichment_product_rescues_heuristic_false_positive` and `test_legacy_data_without_flag_renders_unchanged` PASS already (rescue is vacuous today, legacy path unchanged) — that's fine; they pin behavior against regression in Step 3.

- [ ] **Step 3: Implement**

In `render_modules` (render.py), replace the lookup block (currently lines 2398-2410):

```python
    # Build classification + description lookups from enrichment (keyed by path).
    vendored_ids: dict[str, dict] = {}
    product_ids: set[str] = set()
    desc_by_id: dict[str, str] = {}
    if enrichment:
        cls = enrichment.get("classification") or {}
        for v in cls.get("vendored", []) or []:
            if v.get("module_id"):
                vendored_ids[v["module_id"]] = v
        for p in cls.get("products", []) or []:
            if p.get("module_id"):
                product_ids.add(p["module_id"])
        for d in enrichment.get("module_descriptions", []):
            if d.get("module_id") and d.get("description"):
                desc_by_id[d["module_id"]] = d["description"]

    def is_vendored(m: dict) -> bool:
        path = m.get("path")
        if path in product_ids:    # enrichment rescue beats the heuristic
            return False
        if path in vendored_ids:   # enrichment catch beats the heuristic
            return True
        return bool(m.get("vendored_guess"))
```

Replace the ordering block (currently lines 2435-2441) — ordering is now unconditional:

```python
    # Products first (original order), vendored last.
    products = [m for m in mods if not is_vendored(m)]
    vendored = [m for m in mods if is_vendored(m)]
    ordered = products + vendored
```

Replace the vendored-note condition (currently line 2457) — drop the `enrichment and` requirement:

```python
    vendored_note = ""
    if any(is_vendored(m) for m in mods):
```

(The note body text stays exactly as it is.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd plugin/skills/map-repo/scripts && python3 -m unittest tests.test_render_enrichment -v`

Expected: ALL pass, including `DegradationTest` (golden) — fittalk's old codemap.json has no `vendored_guess` keys, so `is_vendored` returns False for every module and the output is byte-identical.

- [ ] **Step 5: Run the full suite**

Run: `python3 -m unittest discover -s plugin/skills/map-repo/scripts/tests 2>&1 | tail -5`

Expected: OK.

- [ ] **Step 6: Commit**

```bash
git add plugin/skills/map-repo/scripts/render.py plugin/skills/map-repo/scripts/tests/test_render_enrichment.py
git commit -m "feat: module cards use heuristic vendored flag without enrichment

vendored badging/dimming/sorting now works in --no-llm mode via
vendored_guess; enrichment classification still overrides in both
directions."
```

---

### Task 3: System Map — node selection, band assignment, geometry

Pure computation layer: which modules appear on the map, which band each sits in, and the x/y geometry of every node, cluster, band, and store. No SVG yet.

**Files:**
- Modify: `plugin/skills/map-repo/scripts/render.py` (new functions, add directly after `render_modules` / before `SERVICE_KIND_COLORS` comment block at current line ~2477)
- Create: `plugin/skills/map-repo/scripts/tests/test_render_system_map.py`

- [ ] **Step 1: Write the failing tests**

Create `plugin/skills/map-repo/scripts/tests/test_render_system_map.py`:

```python
"""Tests for the System Map hero section (selection, layout, edges, render)."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import render

FITTALK = Path("/home/mckechniep/projects/fittalk-monorepo/.codemap/codemap.json")


def synthetic_data():
    """Small controlled codemap: 1 frontend svc (2 modules), 1 backend svc
    (3 modules, one vendored), 1 store."""
    return {
        "scan_depth": "medium",
        "project": {"name": "synth"},
        "services": [
            {"id": "web", "name": "web", "kind": "frontend", "loc": 1000,
             "file_count": 10, "color": "#292929", "primary_language": "TypeScript"},
            {"id": "api", "name": "api", "kind": "backend", "loc": 5000,
             "file_count": 50, "color": "#3178c6", "primary_language": "TypeScript"},
        ],
        "modules": [],
        "module_graph": {
            "nodes": [
                {"id": "web/pages", "name": "pages", "service": "web", "loc": 600,
                 "files": 6, "primary_language": "TypeScript", "color": "#3178c6",
                 "vendored_guess": False},
                {"id": "web/api-client", "name": "api-client", "service": "web", "loc": 400,
                 "files": 4, "primary_language": "TypeScript", "color": "#3178c6",
                 "vendored_guess": False},
                {"id": "api/auth", "name": "auth", "service": "api", "loc": 2000,
                 "files": 20, "primary_language": "TypeScript", "color": "#3178c6",
                 "vendored_guess": False},
                {"id": "api/billing", "name": "billing", "service": "api", "loc": 1500,
                 "files": 15, "primary_language": "TypeScript", "color": "#3178c6",
                 "vendored_guess": False},
                {"id": "api/copied-lib-master", "name": "copied-lib-master", "service": "api",
                 "loc": 9000, "files": 90, "primary_language": "JavaScript",
                 "color": "#f1e05a", "vendored_guess": True},
            ],
            "edges": [
                {"source": "web/pages", "target": "web/api-client", "weight": 5},
                {"source": "api/billing", "target": "api/auth", "weight": 3},
                {"source": "api/copied-lib-master", "target": "api/auth", "weight": 1},
            ],
        },
        "http_topology": {
            "entry_modules": [
                {"service": "api", "module": "api/auth", "endpoint_count": 7},
            ],
            "endpoints": [
                {"service": "api", "module": "api/auth", "file": "api/auth/c.ts",
                 "framework": "NestJS", "method": "POST", "path": "/api/login"},
            ],
            "edges": [
                {"source_service": "web", "target_service": "api",
                 "method": "POST", "path": "/api/login", "weight": 4},
            ],
        },
        "data_lineage": {
            "stores": [{"id": "postgres", "kind": "postgres", "name": "PostgreSQL",
                        "evidence": ["api/.env"]}],
            "models": [],
            "edges": [{"source_service": "api", "target_store": "postgres",
                       "models": ["User"], "frameworks": ["Prisma"], "weight": 1}],
        },
    }


class SelectTest(unittest.TestCase):
    def test_vendored_node_excluded(self):
        sel = render._sysmap_select(synthetic_data(), None)
        all_ids = [n["id"] for nodes in sel["bands"].values() for n in nodes]
        self.assertNotIn("api/copied-lib-master", all_ids)
        self.assertEqual(sel["excluded_vendored"], 1)

    def test_band_assignment_by_service_kind(self):
        sel = render._sysmap_select(synthetic_data(), None)
        frontend_ids = {n["id"] for n in sel["bands"]["frontend"]}
        backend_ids = {n["id"] for n in sel["bands"]["backend"]}
        self.assertEqual(frontend_ids, {"web/pages", "web/api-client"})
        self.assertEqual(backend_ids, {"api/auth", "api/billing"})

    def test_enrichment_rescue_overrides_heuristic(self):
        enr = {"classification": {
            "products": [{"module_id": "api/copied-lib-master", "role": "x", "why": "y"}],
            "vendored": []}}
        sel = render._sysmap_select(synthetic_data(), enr)
        all_ids = [n["id"] for nodes in sel["bands"].values() for n in nodes]
        self.assertIn("api/copied-lib-master", all_ids)

    def test_enrichment_vendored_catches_unflagged(self):
        enr = {"classification": {
            "products": [],
            "vendored": [{"module_id": "api/billing", "kind": "vendored-lib",
                          "source": "x", "why": "y"}]}}
        sel = render._sysmap_select(synthetic_data(), enr)
        all_ids = [n["id"] for nodes in sel["bands"].values() for n in nodes]
        self.assertNotIn("api/billing", all_ids)

    def test_entry_modules_survive_truncation(self):
        """Entry-point modules outrank bigger non-entry modules under a tight cap."""
        data = synthetic_data()
        data["scan_depth"] = "shallow"  # cap = 20, no truncation here, but pin rank order
        sel = render._sysmap_select(data, None)
        backend = [n["id"] for n in sel["bands"]["backend"]]
        self.assertEqual(backend[0], "api/auth")  # entry module ranks first

    def test_empty_data_returns_none(self):
        self.assertIsNone(render._sysmap_select({"module_graph": {"nodes": []}}, None))
        self.assertIsNone(render._sysmap_select({}, None))


class LayoutTest(unittest.TestCase):
    def setUp(self):
        self.sel = render._sysmap_select(synthetic_data(), None)
        self.layout = render._sysmap_layout(self.sel)

    def test_every_visible_node_is_placed(self):
        visible_ids = {n["id"] for nodes in self.sel["bands"].values() for n in nodes}
        self.assertEqual(set(self.layout["placed"].keys()), visible_ids)

    def test_frontend_band_above_backend_band(self):
        front_y = self.layout["bands"]["frontend"]["y"]
        back_y = self.layout["bands"]["backend"]["y"]
        self.assertLess(front_y, back_y)

    def test_stores_below_backend(self):
        back = self.layout["bands"]["backend"]
        data_band = self.layout["bands"]["data"]
        self.assertGreater(data_band["y"], back["y"] + back["h"])

    def test_no_nan_or_negative_coordinates(self):
        for nid, p in self.layout["placed"].items():
            for k in ("x", "y", "w", "h"):
                self.assertEqual(p[k], p[k], f"NaN {k} on {nid}")  # NaN != NaN
                self.assertGreaterEqual(p[k], 0, f"negative {k} on {nid}")

    def test_nodes_fit_within_viewbox(self):
        for nid, p in self.layout["placed"].items():
            self.assertLessEqual(p["x"] + p["w"], render.SYSMAP_W, f"{nid} overflows")

    def test_no_node_overlap_within_band(self):
        boxes = list(self.layout["placed"].values())
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                overlap = not (a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"]
                               or a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"])
                self.assertFalse(overlap, f"nodes overlap: {a} vs {b}")

    def test_one_cluster_per_service_per_band(self):
        keys = {(c["band"], c["service_id"]) for c in self.layout["clusters"]}
        self.assertEqual(keys, {("frontend", "web"), ("backend", "api")})

    def test_deterministic(self):
        layout2 = render._sysmap_layout(render._sysmap_select(synthetic_data(), None))
        self.assertEqual(
            sorted(self.layout["placed"].keys()), sorted(layout2["placed"].keys()))
        for nid in self.layout["placed"]:
            self.assertEqual(self.layout["placed"][nid]["x"], layout2["placed"][nid]["x"])
            self.assertEqual(self.layout["placed"][nid]["y"], layout2["placed"][nid]["y"])


class FittalkSmokeTest(unittest.TestCase):
    """Integration smoke test against the real fittalk codemap."""

    @unittest.skipUnless(FITTALK.is_file(), "fittalk test data not present")
    def test_fittalk_selects_and_lays_out(self):
        data = json.loads(FITTALK.read_text())
        sel = render._sysmap_select(data, None)
        self.assertIsNotNone(sel)
        layout = render._sysmap_layout(sel)
        # fittalk: 37 graph nodes, none flagged (old codemap) -> capped at 40
        self.assertGreater(len(layout["placed"]), 10)
        self.assertLessEqual(len(layout["placed"]), 40)
        # 3 services -> at least 3 clusters
        self.assertGreaterEqual(len(layout["clusters"]), 3)
        # 4 stores -> 4 cylinders
        self.assertEqual(len(layout["stores"]), 4)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd plugin/skills/map-repo/scripts && python3 -m unittest tests.test_render_system_map -v 2>&1 | head -15`

Expected: ERROR — `AttributeError: module 'render' has no attribute '_sysmap_select'`

- [ ] **Step 3: Implement selection + geometry**

In `render.py`, add after the end of `render_modules` (after current line 2475, before the `SERVICE_KIND_COLORS` comment). Note: `SERVICE_KIND_COLORS` and `STORE_KIND_COLORS` are defined LATER in the file — Python resolves them at call time, not definition time, so referencing them here is fine (same pattern existing sections use).

```python
# ====================================================================
# System map — layered-bands hero ("how the system fits together")
# ====================================================================
#
# The orienting "big picture": every PRODUCT module drawn as a node in
# its tier band (frontend / backend / data), wired with the cross-tier
# relationships the scanner found. Vendored modules are absent by
# design — this map answers "what did this team build", not "what code
# is in the repo". Fine-grained within-service import detail stays in
# the dependency matrix; this map's job is the system-level wiring.

SYSMAP_FRONTEND_KINDS = frozenset({"frontend", "mobile"})

SYSMAP_W = 1120                 # SVG viewBox width
SYSMAP_MARGIN_X = 20
SYSMAP_NODE_H = 32
SYSMAP_NODE_GAP = 10            # horizontal gap between sibling nodes
SYSMAP_ROW_GAP = 12             # vertical gap between node rows in a cluster
SYSMAP_CLUSTER_PAD = 16         # padding inside a service-cluster outline
SYSMAP_CLUSTER_GAP = 24         # gap between sibling clusters
SYSMAP_CLUSTER_LABEL_H = 24     # space reserved for the cluster's service label
SYSMAP_BAND_LABEL_W = 28        # vertical band-label gutter on the left
SYSMAP_BAND_GAP = 76            # vertical space between bands (edges route here)
SYSMAP_STORE_W = 88
SYSMAP_STORE_H = 60
SYSMAP_STORE_GAP = 40
SYSMAP_MAX_NODES = {"shallow": 20, "medium": 40, "full": 60}
SYSMAP_MAX_IMPORT_EDGES = 40


def _sysmap_node_w(label: str, is_entry: bool, loc: int = 0) -> float:
    """Node width: fits the (truncated) label, with a LOC-bucket minimum
    so bigger modules read as bigger (spec: 3 size buckets)."""
    text = _truncate_label(label)
    w = len(text) * 7.4 + 24
    if is_entry:
        w += 26  # room for the entry badge
    # LOC buckets: <1k small, 1k-10k medium, >10k large.
    loc_min = 80.0 if loc < 1_000 else (110.0 if loc < 10_000 else 140.0)
    return max(loc_min, min(max(72.0, w), 200.0))


def _sysmap_select(
    data: dict[str, Any], enrichment: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Select product modules for the map and assign them to bands.

    Returns None when there is nothing to draw. Otherwise:
      {
        "bands": {"frontend": [node, ...], "backend": [node, ...]},
        "stores": [store, ...],
        "entry_counts": {module_id: endpoint_count},
        "excluded_vendored": int,
        "truncated": int,
        "services": {service_id: service_dict},
      }
    """
    graph = data.get("module_graph") or {}
    nodes = list(graph.get("nodes") or [])
    services = {s["id"]: s for s in (data.get("services") or [])}
    if not nodes or not services:
        return None

    # Vendored filter: heuristic flag on the node, refined by enrichment.
    cls = (enrichment or {}).get("classification") or {}
    enr_products = {p.get("module_id") for p in (cls.get("products") or [])}
    enr_vendored = {v.get("module_id") for v in (cls.get("vendored") or [])}

    def is_vendored(n: dict[str, Any]) -> bool:
        nid = n.get("id")
        if nid in enr_products:
            return False
        if nid in enr_vendored:
            return True
        return bool(n.get("vendored_guess"))

    product = [n for n in nodes if not is_vendored(n)]
    excluded = len(nodes) - len(product)
    if not product:
        return None

    # Connectivity ranking: degree + entry-point boost, then LOC.
    edges = list(graph.get("edges") or [])
    degree: dict[str, int] = {}
    for e in edges:
        degree[e["source"]] = degree.get(e["source"], 0) + 1
        degree[e["target"]] = degree.get(e["target"], 0) + 1

    topo = data.get("http_topology") or {}
    entry_counts: dict[str, int] = {
        em["module"]: em.get("endpoint_count", 0)
        for em in (topo.get("entry_modules") or [])
        if em.get("module")
    }

    def rank(n: dict[str, Any]) -> tuple[int, int]:
        boost = 1000 if n["id"] in entry_counts else 0
        return (degree.get(n["id"], 0) + boost, n.get("loc", 0))

    product.sort(key=rank, reverse=True)
    cap = SYSMAP_MAX_NODES.get(data.get("scan_depth", "medium")) or 40
    truncated = max(0, len(product) - cap)
    visible = product[:cap]

    # Band assignment by the owning service's kind.
    bands: dict[str, list[dict[str, Any]]] = {"frontend": [], "backend": []}
    for n in visible:
        svc = services.get(n.get("service")) or {}
        kind = (svc.get("kind") or "unknown").lower()
        key = "frontend" if kind in SYSMAP_FRONTEND_KINDS else "backend"
        bands[key].append(n)

    stores = list((data.get("data_lineage") or {}).get("stores") or [])

    return {
        "bands": bands,
        "stores": stores,
        "entry_counts": entry_counts,
        "excluded_vendored": excluded,
        "truncated": truncated,
        "services": services,
    }


def _sysmap_layout(sel: dict[str, Any]) -> dict[str, Any]:
    """Compute x/y geometry for every node, cluster, band, and store.

    Deterministic: same selection -> same coordinates. Bands stack
    top-to-bottom (frontend, backend, data); service clusters sit
    side-by-side within a band, each wrapping its nodes into rows.
    """
    services = sel["services"]
    entry_counts = sel["entry_counts"]
    placed: dict[str, dict[str, Any]] = {}
    clusters: list[dict[str, Any]] = []
    band_boxes: dict[str, dict[str, float]] = {}

    y_cursor = 0.0
    content_w = SYSMAP_W - 2 * SYSMAP_MARGIN_X - SYSMAP_BAND_LABEL_W
    x_origin = SYSMAP_MARGIN_X + SYSMAP_BAND_LABEL_W

    for band_key in ("frontend", "backend"):
        band_nodes = sel["bands"].get(band_key) or []
        if not band_nodes:
            continue
        band_top = y_cursor

        # Group nodes by service; biggest cluster first for stable layout.
        by_service: dict[str, list[dict[str, Any]]] = {}
        for n in band_nodes:
            by_service.setdefault(n.get("service") or "?", []).append(n)
        service_ids = sorted(by_service, key=lambda sid: (-len(by_service[sid]), sid))

        k = len(service_ids)
        cluster_w = (content_w - (k - 1) * SYSMAP_CLUSTER_GAP) / k
        band_h = 0.0
        cx = x_origin
        band_clusters: list[dict[str, Any]] = []
        for sid in service_ids:
            cnodes = by_service[sid]
            svc = services.get(sid) or {}
            inner_w = cluster_w - 2 * SYSMAP_CLUSTER_PAD

            # Wrap nodes into rows.
            rows: list[list[dict[str, Any]]] = [[]]
            row_w = 0.0
            for n in cnodes:
                w = _sysmap_node_w(n.get("name") or n["id"],
                                   n["id"] in entry_counts,
                                   n.get("loc", 0))
                n["_w"] = w
                if row_w + w > inner_w and rows[-1]:
                    rows.append([])
                    row_w = 0.0
                rows[-1].append(n)
                row_w += w + SYSMAP_NODE_GAP

            # Place nodes row by row.
            ny = band_top + SYSMAP_CLUSTER_LABEL_H + SYSMAP_CLUSTER_PAD
            for row in rows:
                nx = cx + SYSMAP_CLUSTER_PAD
                for n in row:
                    placed[n["id"]] = {
                        "x": nx, "y": ny, "w": n["_w"], "h": float(SYSMAP_NODE_H),
                        "band": band_key, "node": n,
                    }
                    nx += n["_w"] + SYSMAP_NODE_GAP
                ny += SYSMAP_NODE_H + SYSMAP_ROW_GAP

            cluster_h = (ny - SYSMAP_ROW_GAP + SYSMAP_CLUSTER_PAD) - band_top
            kind = (svc.get("kind") or "unknown").lower()
            band_clusters.append({
                "service_id": sid,
                "band": band_key,
                "x": cx, "y": band_top, "w": cluster_w, "h": cluster_h,
                "color": SERVICE_KIND_COLORS.get(kind, SERVICE_KIND_COLORS["unknown"]),
                "label": svc.get("name") or sid,
                "kind": kind,
            })
            band_h = max(band_h, cluster_h)
            cx += cluster_w + SYSMAP_CLUSTER_GAP

        # Equalize cluster heights within the band.
        for c in band_clusters:
            c["h"] = band_h
        clusters.extend(band_clusters)
        band_boxes[band_key] = {"y": band_top, "h": band_h}
        y_cursor = band_top + band_h + SYSMAP_BAND_GAP

    # Data band: store cylinders, horizontally centered.
    stores = sel["stores"]
    store_pos: dict[str, dict[str, Any]] = {}
    if stores:
        band_top = y_cursor
        total_w = len(stores) * SYSMAP_STORE_W + (len(stores) - 1) * SYSMAP_STORE_GAP
        sx = x_origin + max(0.0, (content_w - total_w) / 2)
        for s in stores:
            store_pos[s["id"]] = {
                "x": sx, "y": band_top + 4, "w": float(SYSMAP_STORE_W),
                "h": float(SYSMAP_STORE_H), "store": s,
            }
            sx += SYSMAP_STORE_W + SYSMAP_STORE_GAP
        band_boxes["data"] = {"y": band_top, "h": SYSMAP_STORE_H + 30.0}
        y_cursor = band_top + SYSMAP_STORE_H + 30.0
    elif band_boxes:
        # No stores: trim the trailing band gap.
        y_cursor -= SYSMAP_BAND_GAP

    return {
        "placed": placed,
        "clusters": clusters,
        "stores": store_pos,
        "bands": band_boxes,
        "height": y_cursor + 10.0,
    }
```

- [ ] **Step 4: Run tests to verify SelectTest, LayoutTest, FittalkSmokeTest pass**

Run: `cd plugin/skills/map-repo/scripts && python3 -m unittest tests.test_render_system_map -v`

Expected: all PASS.

- [ ] **Step 5: Run the full suite (golden must stay green — no document changes yet)**

Run: `python3 -m unittest discover -s plugin/skills/map-repo/scripts/tests 2>&1 | tail -5`

Expected: OK.

- [ ] **Step 6: Commit**

```bash
git add plugin/skills/map-repo/scripts/render.py plugin/skills/map-repo/scripts/tests/test_render_system_map.py
git commit -m "feat: system-map node selection, band assignment, and geometry

Pure computation layer for the layered-bands hero: vendored filtering
(heuristic + enrichment override), connectivity-ranked node selection
with depth caps, per-service cluster layout with row wrapping, store
band placement. No SVG yet."
```

---

### Task 4: System Map — edge computation

Three edge kinds joining data the scanner already has. Pure computation, returns drawable edge dicts with anchor coordinates.

**Files:**
- Modify: `plugin/skills/map-repo/scripts/render.py` (add after `_sysmap_layout`)
- Modify: `plugin/skills/map-repo/scripts/tests/test_render_system_map.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_render_system_map.py`:

```python
class EdgesTest(unittest.TestCase):
    def setUp(self):
        self.data = synthetic_data()
        self.sel = render._sysmap_select(self.data, None)
        self.layout = render._sysmap_layout(self.sel)
        self.edges = render._sysmap_edges(self.data, self.layout)

    def kinds(self):
        return [e["kind"] for e in self.edges]

    def test_import_edge_between_visible_nodes(self):
        imports = [e for e in self.edges if e["kind"] == "import"]
        # web/pages -> web/api-client and api/billing -> api/auth are drawable;
        # the edge from the vendored module is NOT (source not placed).
        self.assertEqual(len(imports), 2)

    def test_no_edge_touches_unplaced_node(self):
        # The vendored module was excluded; no edge may reference it.
        # (All returned edges carry coordinates, so this is implicitly true;
        # pin it by checking edge count above and total here.)
        self.assertEqual(len(self.edges), 4)  # 2 import + 1 http + 1 store

    def test_http_edge_resolves_target_module(self):
        https = [e for e in self.edges if e["kind"] == "http"]
        self.assertEqual(len(https), 1)
        # Target anchor must be the api/auth node's top edge.
        auth = self.layout["placed"]["api/auth"]
        self.assertAlmostEqual(https[0]["x2"], auth["x"] + auth["w"] / 2)
        self.assertAlmostEqual(https[0]["y2"], auth["y"])

    def test_store_edge_anchors_to_cylinder(self):
        stores = [e for e in self.edges if e["kind"] == "store"]
        self.assertEqual(len(stores), 1)
        pg = self.layout["stores"]["postgres"]
        self.assertAlmostEqual(stores[0]["x2"], pg["x"] + pg["w"] / 2)

    def test_import_edge_cap(self):
        """More than SYSMAP_MAX_IMPORT_EDGES drawable edges -> capped, highest weight kept."""
        data = synthetic_data()
        # Generate 50 extra synthetic backend nodes + edges, all drawable.
        for i in range(50):
            data["module_graph"]["nodes"].append(
                {"id": f"api/m{i}", "name": f"m{i}", "service": "api", "loc": 10,
                 "files": 1, "primary_language": "TypeScript", "color": "#3178c6",
                 "vendored_guess": False})
            data["module_graph"]["edges"].append(
                {"source": f"api/m{i}", "target": "api/auth", "weight": i + 10})
        data["scan_depth"] = "full"  # cap 60 nodes so all are placed
        sel = render._sysmap_select(data, None)
        layout = render._sysmap_layout(sel)
        edges = render._sysmap_edges(data, layout)
        imports = [e for e in edges if e["kind"] == "import"]
        self.assertLessEqual(len(imports), render.SYSMAP_MAX_IMPORT_EDGES)
        # Highest-weight edge must survive the cap.
        weights = [e["weight"] for e in imports]
        self.assertIn(59, weights)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd plugin/skills/map-repo/scripts && python3 -m unittest tests.test_render_system_map.EdgesTest -v 2>&1 | head -10`

Expected: ERROR — `AttributeError: module 'render' has no attribute '_sysmap_edges'`

- [ ] **Step 3: Implement**

Add to `render.py` directly after `_sysmap_layout`:

```python
def _sysmap_edges(
    data: dict[str, Any], layout: dict[str, Any]
) -> list[dict[str, Any]]:
    """Compute drawable edges between placed elements.

    Three kinds:
      "import" — module → module (module_graph.edges), both endpoints placed
      "http"   — frontend service cluster → backend entry module
                 (http_topology.edges joined to endpoints by path)
      "store"  — service cluster → store cylinder (data_lineage.edges)

    Every edge: {kind, x1, y1, x2, y2, weight, same_band, [color]}.
    Import edges are capped at SYSMAP_MAX_IMPORT_EDGES by weight.
    """
    placed = layout["placed"]
    cluster_by_service = {c["service_id"]: c for c in layout["clusters"]}
    stores = layout["stores"]
    out: list[dict[str, Any]] = []

    # ---- import edges
    graph_edges = (data.get("module_graph") or {}).get("edges") or []
    drawable = [
        e for e in graph_edges
        if e.get("source") in placed and e.get("target") in placed
        and e["source"] != e["target"]
    ]
    drawable.sort(key=lambda e: -(e.get("weight") or 1))
    for e in drawable[:SYSMAP_MAX_IMPORT_EDGES]:
        s, t = placed[e["source"]], placed[e["target"]]
        same_band = s["band"] == t["band"]
        if same_band:
            # Anchor both ends at node bottoms; drawn as an arc below.
            out.append({
                "kind": "import", "same_band": True,
                "x1": s["x"] + s["w"] / 2, "y1": s["y"] + s["h"],
                "x2": t["x"] + t["w"] / 2, "y2": t["y"] + t["h"],
                "weight": e.get("weight") or 1,
            })
        else:
            src_above = s["y"] < t["y"]
            out.append({
                "kind": "import", "same_band": False,
                "x1": s["x"] + s["w"] / 2,
                "y1": s["y"] + (s["h"] if src_above else 0),
                "x2": t["x"] + t["w"] / 2,
                "y2": t["y"] + (0 if src_above else t["h"]),
                "weight": e.get("weight") or 1,
            })

    # ---- HTTP edges: source service cluster → target entry module
    topo = data.get("http_topology") or {}
    ep_module_by_path: dict[tuple[str, str], str] = {}
    for ep in topo.get("endpoints") or []:
        if ep.get("module") and ep.get("path"):
            ep_module_by_path[(ep.get("service"), ep["path"])] = ep["module"]

    http_weight: dict[tuple[str, str], int] = {}
    for e in topo.get("edges") or []:
        target_module = ep_module_by_path.get(
            (e.get("target_service"), e.get("path")))
        if not target_module or target_module not in placed:
            continue
        if e.get("source_service") not in cluster_by_service:
            continue
        key = (e["source_service"], target_module)
        http_weight[key] = http_weight.get(key, 0) + (e.get("weight") or 1)

    for (src_service, target_module), weight in sorted(http_weight.items()):
        c = cluster_by_service[src_service]
        t = placed[target_module]
        out.append({
            "kind": "http", "same_band": False,
            "x1": c["x"] + c["w"] / 2, "y1": c["y"] + c["h"],
            "x2": t["x"] + t["w"] / 2, "y2": t["y"],
            "weight": weight,
            # Carried so the bento can name this path ("web → auth").
            "source_service": src_service,
            "target_id": target_module,
        })

    # ---- store edges: service cluster → store cylinder
    for e in (data.get("data_lineage") or {}).get("edges") or []:
        c = cluster_by_service.get(e.get("source_service"))
        sp = stores.get(e.get("target_store"))
        if not c or not sp:
            continue
        kind = (sp["store"].get("kind") or "unknown")
        out.append({
            "kind": "store", "same_band": False,
            "x1": c["x"] + c["w"] / 2, "y1": c["y"] + c["h"],
            "x2": sp["x"] + sp["w"] / 2, "y2": sp["y"],
            "weight": e.get("weight") or 1,
            "color": STORE_KIND_COLORS.get(kind, "#888888"),
        })

    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd plugin/skills/map-repo/scripts && python3 -m unittest tests.test_render_system_map -v`

Expected: all PASS (including earlier Select/Layout tests).

- [ ] **Step 5: Commit**

```bash
git add plugin/skills/map-repo/scripts/render.py plugin/skills/map-repo/scripts/tests/test_render_system_map.py
git commit -m "feat: system-map edge computation (import / http / store)

Joins module_graph edges, http_topology edges->endpoints->module, and
data_lineage edges into drawable anchored edges. Import edges capped
at top-40 by weight."
```

---

### Task 5: System Map — SVG render, section assembly, CSS, document integration

The visible part: bands, cluster outlines, nodes with entry badges, store cylinders, edges, legend — assembled into the standard hero section and inserted into `render_document` right after the overview.

**Files:**
- Modify: `plugin/skills/map-repo/scripts/render.py`:
  - new functions after `_sysmap_edges`
  - new `"sysmap"` key in `SECTION_INTROS` (currently line 1830)
  - new CSS block appended near the other hero frame styles (after `.modgraph-frame` rules, currently line ~494)
  - print rules: add `#codemap-sysmap-section` to the hero page lists (currently lines 1527-1532, 1546-1552, 1556-1558) and `.sysmap-frame` to the frame list (currently lines 1563-1567)
  - `render_document`: insert `render_system_map(data, enrichment)` after `render_overview(...)` (currently line 5833)
- Modify: `plugin/skills/map-repo/scripts/tests/test_render_system_map.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_render_system_map.py`:

```python
class RenderSectionTest(unittest.TestCase):
    def test_section_renders_with_synthetic_data(self):
        html = render.render_system_map(synthetic_data(), None)
        self.assertIn("codemap-sysmap-section", html)
        self.assertIn("How the system fits together", html)
        self.assertIn("sysmap-frame", html)
        self.assertIn("<svg", html)
        # Product modules present, vendored module absent.
        self.assertIn("auth", html)
        self.assertNotIn("copied-lib-master", html)
        # Store cylinder present.
        self.assertIn("PostgreSQL", html)

    def test_empty_data_renders_nothing(self):
        self.assertEqual(render.render_system_map({}, None), "")
        self.assertEqual(render.render_system_map({"module_graph": {"nodes": []}}, None), "")

    def test_entry_badge_rendered(self):
        html = render.render_system_map(synthetic_data(), None)
        # api/auth is an entry module with 7 endpoints.
        self.assertIn("7", html)
        self.assertIn("sysmap-entry-badge", html)

    def test_section_in_document_after_overview(self):
        """render_document includes the map; it appears before the languages section."""
        data = synthetic_data()
        data["languages"] = [{"name": "TypeScript", "files": 10, "loc": 1000,
                              "color": "#3178c6"}]
        data["project"] = {"name": "synth", "total_files": 10, "total_loc": 1000,
                           "primary_language": "TypeScript"}
        html = render.render_document(data)
        self.assertIn("codemap-sysmap-section", html)
        self.assertLess(html.index("codemap-sysmap-section"),
                        html.index("<h2>Languages</h2>"))

    def test_enrichment_descriptions_become_tooltips(self):
        enr = {"classification": {"products": [], "vendored": []},
               "module_descriptions": [
                   {"module_id": "api/auth", "description": "Login and tokens.",
                    "is_product": True}]}
        html = render.render_system_map(synthetic_data(), enr)
        self.assertIn("Login and tokens.", html)

    @unittest.skipUnless(FITTALK.is_file(), "fittalk test data not present")
    def test_fittalk_full_section_renders(self):
        data = json.loads(FITTALK.read_text())
        html = render.render_system_map(data, None)
        self.assertIn("codemap-sysmap-section", html)
        self.assertIn("<svg", html)
        # No NaN ever ends up in coordinates.
        self.assertNotIn("nan", html.lower().replace("narration", ""))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd plugin/skills/map-repo/scripts && python3 -m unittest tests.test_render_system_map.RenderSectionTest -v 2>&1 | head -10`

Expected: ERROR — `AttributeError: module 'render' has no attribute 'render_system_map'`

- [ ] **Step 3: Add the SECTION_INTROS entry**

In `SECTION_INTROS` (render.py, currently line 1830), add a `"sysmap"` key after the `"flows"` entry:

```python
    "sysmap":   "One map of the whole system: the product's own modules (vendored "
                "and third-party code is excluded) arranged in tiers — user-facing "
                "code on top, server code in the middle, data stores at the bottom. "
                "<strong>Dashed lines</strong> are HTTP calls from the frontend to a "
                "backend module, <strong>solid lines</strong> are code imports, and "
                "<strong>coloured lines into cylinders</strong> show which service "
                "writes to which store. Modules marked with <strong>▸</strong> are "
                "entry points — the doors through which requests arrive.",
```

- [ ] **Step 4: Implement SVG emission + section assembly**

Add to `render.py` after `_sysmap_edges`:

```python
def _sysmap_emit_svg(
    layout: dict[str, Any],
    edges: list[dict[str, Any]],
    sel: dict[str, Any],
    enrichment: dict[str, Any] | None = None,
) -> str:
    """Emit the system-map SVG. Drawing order: band labels, cluster
    outlines, edges (under nodes), nodes, stores."""
    height = layout["height"]
    parts: list[str] = [
        f'<svg class="sysmap-svg" viewBox="0 0 {SYSMAP_W} {height:.0f}" '
        f'width="100%" role="img" '
        f'aria-label="System map: product modules in tiers with their connections">'
    ]

    band_titles = {"frontend": "FRONTEND", "backend": "BACKEND", "data": "DATA"}
    # Module descriptions from enrichment become <title> tooltips.
    desc_by_id: dict[str, str] = {}
    for d in (enrichment or {}).get("module_descriptions") or []:
        if d.get("module_id") and d.get("description"):
            desc_by_id[d["module_id"]] = d["description"]

    # ---- band gutter labels (rotated, left edge)
    for band_key, box in layout["bands"].items():
        cy = box["y"] + box["h"] / 2
        parts.append(
            f'<text x="{SYSMAP_MARGIN_X + 8}" y="{cy:.1f}" class="sysmap-band-label" '
            f'transform="rotate(-90 {SYSMAP_MARGIN_X + 8} {cy:.1f})" '
            f'text-anchor="middle">{escape(band_titles.get(band_key, band_key.upper()))}</text>'
        )

    # ---- service cluster outlines + labels
    for c in layout["clusters"]:
        parts.append(
            f'<rect x="{c["x"]:.1f}" y="{c["y"]:.1f}" '
            f'width="{c["w"]:.1f}" height="{c["h"]:.1f}" rx="10" '
            f'fill="{escape(c["color"])}" fill-opacity="0.05" '
            f'stroke="{escape(c["color"])}" stroke-opacity="0.45" '
            f'stroke-width="1.25" stroke-dasharray="none" />'
        )
        parts.append(
            f'<text x="{c["x"] + 12:.1f}" y="{c["y"] + 16:.1f}" '
            f'class="sysmap-cluster-label" fill="{escape(c["color"])}">'
            f'{escape(_topov2_truncate(c["label"], 38))}'
            f' <tspan class="sysmap-cluster-kind">· {escape(c["kind"].upper())}</tspan></text>'
        )

    # ---- edges (drawn under nodes)
    for e in edges:
        x1, y1, x2, y2 = e["x1"], e["y1"], e["x2"], e["y2"]
        w = max(1.0, min(4.0, 1.0 + math.log2(max(1, e["weight"]))))
        if e["kind"] == "import" and e["same_band"]:
            # Arc dipping below both nodes.
            dip = 26 + abs(x2 - x1) * 0.04
            my = max(y1, y2) + dip
            parts.append(
                f'<path d="M{x1:.1f},{y1:.1f} Q{(x1 + x2) / 2:.1f},{my:.1f} '
                f'{x2:.1f},{y2:.1f}" class="sysmap-edge-import" '
                f'stroke-width="{w:.1f}" fill="none" />'
            )
        elif e["kind"] == "import":
            parts.append(
                f'<path d="M{x1:.1f},{y1:.1f} C{x1:.1f},{(y1 + y2) / 2:.1f} '
                f'{x2:.1f},{(y1 + y2) / 2:.1f} {x2:.1f},{y2:.1f}" '
                f'class="sysmap-edge-import" stroke-width="{w:.1f}" fill="none" />'
            )
        elif e["kind"] == "http":
            parts.append(
                f'<path d="M{x1:.1f},{y1:.1f} C{x1:.1f},{(y1 + y2) / 2:.1f} '
                f'{x2:.1f},{(y1 + y2) / 2:.1f} {x2:.1f},{y2:.1f}" '
                f'class="sysmap-edge-http" stroke-width="{w:.1f}" fill="none" '
                f'marker-end="url(#sysmap-arrow)" />'
            )
        else:  # store
            color = e.get("color", "#888888")
            parts.append(
                f'<path d="M{x1:.1f},{y1:.1f} C{x1:.1f},{(y1 + y2) / 2:.1f} '
                f'{x2:.1f},{(y1 + y2) / 2:.1f} {x2:.1f},{y2:.1f}" '
                f'stroke="{escape(color)}" stroke-opacity="0.75" '
                f'stroke-width="{w:.1f}" fill="none" '
                f'marker-end="url(#sysmap-arrow)" />'
            )

    # Arrowhead marker definition.
    parts.append(
        '<defs><marker id="sysmap-arrow" viewBox="0 0 8 8" refX="7" refY="4" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M0,0 L8,4 L0,8 z" fill="oklch(50% 0.01 250)" /></marker></defs>'
    )

    # ---- module nodes
    entry_counts = sel["entry_counts"]
    for nid, p in layout["placed"].items():
        n = p["node"]
        label = _truncate_label(n.get("name") or nid)
        is_entry = nid in entry_counts
        title = desc_by_id.get(nid) or nid
        parts.append(f'<g class="sysmap-node{" is-entry" if is_entry else ""}">')
        parts.append(f'<title>{escape(title)}</title>')
        parts.append(
            f'<rect x="{p["x"]:.1f}" y="{p["y"]:.1f}" width="{p["w"]:.1f}" '
            f'height="{p["h"]:.1f}" rx="6" class="sysmap-node-rect" />'
        )
        tx = p["x"] + 10
        if is_entry:
            parts.append(
                f'<text x="{tx:.1f}" y="{p["y"] + p["h"] / 2 + 4:.1f}" '
                f'class="sysmap-entry-badge">▸</text>'
            )
            tx += 12
        parts.append(
            f'<text x="{tx:.1f}" y="{p["y"] + p["h"] / 2 + 4:.1f}" '
            f'class="sysmap-node-label">{escape(label)}</text>'
        )
        if is_entry:
            count = entry_counts[nid]
            parts.append(
                f'<text x="{p["x"] + p["w"] - 8:.1f}" y="{p["y"] + p["h"] / 2 + 4:.1f}" '
                f'text-anchor="end" class="sysmap-endpoint-count">{count}</text>'
            )
        parts.append('</g>')

    # ---- store cylinders + labels
    for sid, sp in layout["stores"].items():
        s = sp["store"]
        kind = (s.get("kind") or "unknown")
        color = STORE_KIND_COLORS.get(kind, "#888888")
        parts.append(_lineage2_emit_cylinder(sp["x"], sp["y"], sp["w"], sp["h"] - 18, color))
        parts.append(
            f'<text x="{sp["x"] + sp["w"] / 2:.1f}" y="{sp["y"] + sp["h"] + 6:.1f}" '
            f'text-anchor="middle" class="sysmap-store-label">'
            f'{escape(s.get("name") or sid)}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


def _sysmap_headline(sel: dict[str, Any], edges: list[dict[str, Any]]) -> str:
    """One-sentence editorial headline above the map."""
    n_front = len(sel["bands"].get("frontend") or [])
    n_back = len(sel["bands"].get("backend") or [])
    n_stores = len(sel["stores"])
    n_http = sum(1 for e in edges if e["kind"] == "http")
    bits: list[str] = []
    if n_front:
        bits.append(f"<strong>{n_front}</strong> frontend module{'s' if n_front != 1 else ''}")
    bits.append(f"<strong>{n_back}</strong> backend module{'s' if n_back != 1 else ''}")
    if n_stores:
        bits.append(f"<strong>{n_stores}</strong> data store{'s' if n_stores != 1 else ''}")
    headline = "The product is " + ", ".join(bits)
    if n_http:
        headline += f", connected by <strong>{n_http}</strong> HTTP call path{'s' if n_http != 1 else ''}"
    headline += "."
    if sel["excluded_vendored"]:
        headline += (f" <span class='sysmap-excluded'>{sel['excluded_vendored']} vendored "
                     f"module{'s' if sel['excluded_vendored'] != 1 else ''} excluded.</span>")
    return headline


def render_system_map(
    data: dict[str, Any], enrichment: dict[str, Any] | None = None
) -> str:
    """The 'How the system fits together' hero — layered-bands map of
    product modules. Renders deterministically; enrichment only refines
    the vendored filter and adds node tooltips."""
    sel = _sysmap_select(data, enrichment)
    if sel is None:
        return ""
    if not sel["bands"].get("frontend") and not sel["bands"].get("backend"):
        return ""
    layout = _sysmap_layout(sel)
    edges = _sysmap_edges(data, layout)
    svg = _sysmap_emit_svg(layout, edges, sel, enrichment)
    headline = _sysmap_headline(sel, edges)

    truncation_note = ""
    if sel["truncated"]:
        truncation_note = (
            f'<p class="sysmap-note">+{sel["truncated"]} smaller modules not shown '
            f'(map shows the most-connected modules; the dependency matrix below '
            f'shows everything).</p>'
        )

    legend = (
        '<div class="sysmap-legend">'
        '<span class="sysmap-leg-item"><span class="sysmap-leg-http"></span> HTTP call</span>'
        '<span class="sysmap-leg-item"><span class="sysmap-leg-import"></span> code import</span>'
        '<span class="sysmap-leg-item"><span class="sysmap-leg-store"></span> reads/writes data</span>'
        '<span class="sysmap-leg-item">▸ entry point (number = endpoints)</span>'
        '</div>'
    )

    observations_html = _render_observations(_observations_for_sysmap(sel, edges, data))
    bento_html = render_sysmap_bento(data, sel, edges)

    return f"""
<section id="codemap-sysmap-section">
  <h2>How the system fits together</h2>
  {section_intro("sysmap")}
  <div class="sysmap-frame">
    <p class="sysmap-headline">{headline}</p>
    <div class="sysmap-wrap">{svg}</div>
    {legend}
    {truncation_note}
  </div>
  {observations_html}
  {bento_html}
</section>
"""
```

**Note:** `_observations_for_sysmap` and `render_sysmap_bento` are implemented in Task 6. For THIS task, add temporary stubs right above `render_system_map` so tests pass, then Task 6 replaces them:

```python
def _observations_for_sysmap(
    sel: dict[str, Any], edges: list[dict[str, Any]], data: dict[str, Any]
) -> list[str]:
    return []  # Replaced with real observations in the next task.


def render_sysmap_bento(
    data: dict[str, Any], sel: dict[str, Any], edges: list[dict[str, Any]]
) -> str:
    return ""  # Replaced with real bento in the next task.
```

- [ ] **Step 5: Add the CSS**

In the `CSS` string (render.py), add after the `.modgraph-matrix-wrap` block (around current line 500), a new block:

```css
/* ---- System map (layered-bands hero) ---- */
.sysmap-frame {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: var(--space-5) var(--space-5) var(--space-4);
  margin-bottom: var(--space-4);
  margin-left: -56px;
  margin-right: -56px;
}
@media (max-width: 880px) {
  .sysmap-frame { margin-left: 0; margin-right: 0; }
}
.sysmap-wrap { overflow-x: auto; }
.sysmap-headline {
  font-size: 1.05rem;
  color: var(--ink-2);
  margin: 0 0 var(--space-4);
}
.sysmap-excluded { color: var(--muted); }
.sysmap-band-label {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.14em;
  fill: var(--muted);
}
.sysmap-cluster-label {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
}
.sysmap-cluster-kind { font-weight: 400; opacity: 0.7; font-size: 10px; }
.sysmap-node-rect {
  fill: var(--surface);
  stroke: oklch(70% 0.01 250);
  stroke-width: 1.25;
}
.sysmap-node.is-entry .sysmap-node-rect {
  stroke: var(--accent);
  stroke-width: 1.5;
}
.sysmap-node-label {
  font-family: var(--font-mono);
  font-size: 12px;
  fill: var(--ink);
}
.sysmap-entry-badge { font-size: 12px; fill: var(--accent); }
.sysmap-endpoint-count {
  font-family: var(--font-mono);
  font-size: 10px;
  fill: var(--muted);
}
.sysmap-store-label {
  font-family: var(--font-mono);
  font-size: 11px;
  fill: var(--ink-2);
}
.sysmap-edge-import { stroke: oklch(60% 0.01 250 / 0.55); }
.sysmap-edge-http { stroke: oklch(58% 0.14 250 / 0.8); stroke-dasharray: 5 4; }
.sysmap-legend {
  display: flex;
  gap: var(--space-4);
  flex-wrap: wrap;
  margin-top: var(--space-3);
  font-size: 0.8rem;
  color: var(--muted);
  font-family: var(--font-mono);
}
.sysmap-leg-item { display: inline-flex; align-items: center; gap: 6px; }
.sysmap-leg-http, .sysmap-leg-import, .sysmap-leg-store {
  display: inline-block; width: 26px; height: 0;
}
.sysmap-leg-http { border-top: 2px dashed oklch(58% 0.14 250 / 0.8); }
.sysmap-leg-import { border-top: 2px solid oklch(60% 0.01 250 / 0.55); }
.sysmap-leg-store { border-top: 2px solid #336791; }
.sysmap-note { font-size: 0.85rem; color: var(--muted); margin-top: var(--space-3); }

/* Bento beneath the map — same grid/tile pattern as .modgraph-bento (render.py:586). */
.sysmap-bento {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-3);
  margin-top: var(--space-3);
}
.sysmap-tile {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--space-4) var(--space-4) var(--space-3);
  display: flex;
  flex-direction: column;
  min-height: 220px;
}
.sysmap-tile .tile-label {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: var(--space-2);
}
.sysmap-tile .tile-headline {
  font-family: var(--font-serif);
  font-size: 1rem;
  color: var(--ink);
  margin: 0 0 var(--space-3);
  line-height: 1.35;
}
.sysmap-tile .tile-body { flex: 1; }
.sysmap-rows { display: flex; flex-direction: column; gap: 6px; font-family: var(--font-mono); font-size: 0.82rem; color: var(--ink-2); }
.sysmap-row { display: flex; justify-content: space-between; gap: 12px; }
.sysmap-row .v { color: var(--ink); font-weight: 600; white-space: nowrap; }
```

(All CSS custom properties above — `--font-mono`, `--font-serif`, `--border`, `--radius`, `--shadow`, `--space-2/3/4/5`, `--accent`, `--ink`, `--ink-2`, `--muted`, `--surface` — already exist in the `:root` block; verified against render.py:23-80 and the `.modgraph-tile` rules at render.py:586-640.)

- [ ] **Step 6: Add print rules**

In the print CSS (render.py, currently lines 1527-1567), add the sysmap section to all four hero lists:

The `page: hero` assignment (currently lines 1527-1532) becomes:

```css
#codemap-sysmap-section,
#codemap-modgraph-section,
#codemap-topov2-section,
#codemap-cpaths-section,
#codemap-lineage2-section {
  page: hero;
}
```

The page-break-before list (currently ~lines 1546-1552) becomes:

```css
  #codemap-sysmap-section,
  #codemap-modgraph-section,
  #codemap-topov2-section,
  #codemap-cpaths-section,
  #codemap-lineage2-section {
    page-break-before: always;
    break-before: page;
  }
```

The h2 page-break-after list (currently ~lines 1556-1558) becomes:

```css
  #codemap-sysmap-section h2,
  #codemap-modgraph-section h2,
  #codemap-topov2-section h2,
  #codemap-cpaths-section h2,
  #codemap-lineage2-section h2 { page-break-after: avoid; break-after: avoid; }
```

The frame list (currently lines 1563-1567) gets `.sysmap-frame` added:

```css
  .sysmap-frame,
  .modgraph-frame,
  .topov2-frame,
  .cpaths-frame,
  .lineage2-frame {
```

- [ ] **Step 7: Insert into render_document**

In `render_document` (currently line 5831-5836), insert the map right after the overview:

```python
    body = (
        render_cover(data)
        + render_overview(data, enrichment)
        # System map: the orienting big-picture hero. Sits first among the
        # diagrams so the reader sees the whole system before drilling in.
        + render_system_map(data, enrichment)
        + render_readme(data, enrichment)
        + render_languages(data)
        + render_modules(data, enrichment)
```

- [ ] **Step 8: Run the new tests**

Run: `cd plugin/skills/map-repo/scripts && python3 -m unittest tests.test_render_system_map -v`

Expected: ALL pass.

- [ ] **Step 9: Run the full suite — golden test now FAILS (expected)**

Run: `python3 -m unittest discover -s plugin/skills/map-repo/scripts/tests 2>&1 | tail -15`

Expected: `DegradationTest.test_no_enrichment_matches_golden` and `test_none_enrichment_matches_golden` FAIL — the deterministic body now contains the new section. This is the **intentional** body change the spec calls for. Everything else passes.

**Do NOT regenerate the golden fixture yet** — that happens in Task 7 after the bento/observations are final (regenerating now would mean regenerating twice).

- [ ] **Step 10: Commit (with the golden failure noted)**

```bash
git add plugin/skills/map-repo/scripts/render.py plugin/skills/map-repo/scripts/tests/test_render_system_map.py
git commit -m "feat: system-map hero section — SVG render, CSS, document integration

Layered-bands map inserted after the overview: band gutter labels,
service cluster outlines, module nodes with entry badges, store
cylinders, three edge kinds, legend, print-hero page rules.

NOTE: golden_fittalk.html intentionally stale until the section is
complete (observations+bento land next, then the fixture is
regenerated once)."
```

---

### Task 6: System Map — observations + bento

Replace the Task-5 stubs with real data-derived observations and small-multiples.

**Files:**
- Modify: `plugin/skills/map-repo/scripts/render.py` (replace `_observations_for_sysmap` and `render_sysmap_bento` stubs)
- Modify: `plugin/skills/map-repo/scripts/tests/test_render_system_map.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_render_system_map.py`:

```python
class ObservationsAndBentoTest(unittest.TestCase):
    def test_observations_present_in_section(self):
        html = render.render_system_map(synthetic_data(), None)
        self.assertIn("Observations", html)
        self.assertIn("observations", html)  # the aside class

    def test_hub_observation_names_the_hub(self):
        obs = render._observations_for_sysmap(
            render._sysmap_select(synthetic_data(), None),
            [], synthetic_data())
        joined = " ".join(obs)
        # api/auth has the highest degree (2 in-edges) -> named as hub.
        self.assertIn("auth", joined)

    def test_tier_imbalance_observation(self):
        sel = render._sysmap_select(synthetic_data(), None)
        obs = render._observations_for_sysmap(sel, [], synthetic_data())
        joined = " ".join(obs)
        self.assertIn("backend", joined.lower())

    def test_vendored_exclusion_observation(self):
        sel = render._sysmap_select(synthetic_data(), None)
        obs = render._observations_for_sysmap(sel, [], synthetic_data())
        joined = " ".join(obs)
        self.assertIn("vendored", joined.lower())

    def test_bento_renders_tiles(self):
        sel = render._sysmap_select(synthetic_data(), None)
        layout = render._sysmap_layout(sel)
        edges = render._sysmap_edges(synthetic_data(), layout)
        html = render.render_sysmap_bento(synthetic_data(), sel, edges)
        self.assertIn("sysmap-bento", html)
        self.assertIn("sysmap-tile", html)
        self.assertIn("tile-label", html)     # same tile anatomy as other bentos
        # Tier composition tile names both tiers.
        self.assertIn("Frontend", html)
        self.assertIn("Backend", html)

    def test_bento_names_real_call_paths(self):
        """The call-paths tile shows 'web → auth', not 'call path 1'."""
        data = synthetic_data()
        sel = render._sysmap_select(data, None)
        layout = render._sysmap_layout(sel)
        edges = render._sysmap_edges(data, layout)
        html = render.render_sysmap_bento(data, sel, edges)
        self.assertIn("auth", html)
        self.assertNotIn("call path 1", html)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd plugin/skills/map-repo/scripts && python3 -m unittest tests.test_render_system_map.ObservationsAndBentoTest -v 2>&1 | head -20`

Expected: FAIL — observations list is empty (stub), bento is empty string (stub).

- [ ] **Step 3: Implement real observations**

Replace the `_observations_for_sysmap` stub:

```python
def _observations_for_sysmap(
    sel: dict[str, Any], edges: list[dict[str, Any]], data: dict[str, Any]
) -> list[str]:
    """Data-derived observations for the system map: hubs, tier imbalance,
    orphans, vendored exclusions."""
    obs: list[str] = []
    all_nodes = [n for nodes in sel["bands"].values() for n in nodes]
    if not all_nodes:
        return obs

    # 1. Biggest hub (highest degree among visible nodes).
    graph_edges = (data.get("module_graph") or {}).get("edges") or []
    visible_ids = {n["id"] for n in all_nodes}
    degree: dict[str, int] = {}
    for e in graph_edges:
        if e.get("source") in visible_ids:
            degree[e["source"]] = degree.get(e["source"], 0) + 1
        if e.get("target") in visible_ids:
            degree[e["target"]] = degree.get(e["target"], 0) + 1
    if degree:
        hub_id, hub_deg = max(degree.items(), key=lambda kv: kv[1])
        hub_name = next((n.get("name") or hub_id for n in all_nodes if n["id"] == hub_id), hub_id)
        if hub_deg >= 2:
            obs.append(
                f"<strong><code>{escape(hub_name)}</code></strong> is the most-connected "
                f"module on the map ({hub_deg} import relationships) — changes there "
                f"ripple furthest."
            )

    # 2. Tier imbalance by LOC.
    front_loc = sum(n.get("loc", 0) for n in sel["bands"].get("frontend") or [])
    back_loc = sum(n.get("loc", 0) for n in sel["bands"].get("backend") or [])
    total = front_loc + back_loc
    if total > 0 and back_loc / total >= 0.7:
        obs.append(
            f"<strong>{pct(back_loc, total):.0f}%</strong> of mapped code lives in the "
            f"backend tier — this is a backend-heavy system; the frontend is comparatively thin."
        )
    elif total > 0 and front_loc / total >= 0.7:
        obs.append(
            f"<strong>{pct(front_loc, total):.0f}%</strong> of mapped code lives in the "
            f"frontend tier — most of the logic runs in the client."
        )

    # 3. Orphan modules (no edges at all).
    orphans = [n for n in all_nodes if degree.get(n["id"], 0) == 0]
    if orphans:
        names = ", ".join(f"<code>{escape(n.get('name') or n['id'])}</code>" for n in orphans[:4])
        more = f" (+{len(orphans) - 4} more)" if len(orphans) > 4 else ""
        obs.append(
            f"{len(orphans)} module{'s' if len(orphans) != 1 else ''} on the map have "
            f"<strong>no detected connections</strong>: {names}{more} — either truly "
            f"standalone or wired together in a way the scanner can't see."
        )

    # 4. Vendored exclusions.
    if sel["excluded_vendored"]:
        obs.append(
            f"<strong>{sel['excluded_vendored']}</strong> vendored module"
            f"{'s were' if sel['excluded_vendored'] != 1 else ' was'} excluded from this "
            f"map — third-party code copied into the repo, not part of the product itself."
        )

    # 5. Unreached entry modules (entry points with no HTTP edge landing on them).
    http_targets = {(e.get("x2"), e.get("y2")) for e in edges if e["kind"] == "http"}
    n_http = sum(1 for e in edges if e["kind"] == "http")
    n_entries = sum(1 for n in all_nodes if n["id"] in sel["entry_counts"])
    if n_entries and n_http == 0:
        obs.append(
            f"The map shows <strong>{n_entries}</strong> entry-point module"
            f"{'s' if n_entries != 1 else ''} but <strong>no resolved HTTP call paths</strong> "
            f"from the frontend — calls may go through a gateway or use URLs the scanner "
            f"couldn't match to routes."
        )
    return obs[:5]
```

- [ ] **Step 4: Implement the bento**

Replace the `render_sysmap_bento` stub. The markup follows the established tile anatomy exactly (`tile-label` / `tile-headline` / `tile-body`, see `render_module_section_bento` at render.py:3504-3526); the wrapper/tile classes are the section-scoped `.sysmap-bento` / `.sysmap-tile` whose CSS was added in Task 5:

```python
def render_sysmap_bento(
    data: dict[str, Any], sel: dict[str, Any], edges: list[dict[str, Any]]
) -> str:
    """2x2 small-multiples beneath the system map.

    The map shows the wiring; the bento adds the magnitudes it
    compresses: tier composition, heaviest call paths, entry-point
    density, and what the map deliberately leaves out.
    """
    front = sel["bands"].get("frontend") or []
    back = sel["bands"].get("backend") or []
    node_name = {n["id"]: (n.get("name") or n["id"])
                 for nodes in sel["bands"].values() for n in nodes}

    def row(label: str, value: str) -> str:
        return (f'<div class="sysmap-row"><span>{label}</span>'
                f'<span class="v">{value}</span></div>')

    # ---------- Tile 1: tier composition ----------
    front_loc = sum(n.get("loc", 0) for n in front)
    back_loc = sum(n.get("loc", 0) for n in back)
    tile1_body = '<div class="sysmap-rows">' + "".join([
        row("Frontend modules", f"{len(front)} · {fmt_num(front_loc)} LOC"),
        row("Backend modules", f"{len(back)} · {fmt_num(back_loc)} LOC"),
        row("Data stores", str(len(sel["stores"]))),
    ]) + '</div>'

    # ---------- Tile 2: heaviest call paths ----------
    https = sorted([e for e in edges if e["kind"] == "http"],
                   key=lambda e: -e["weight"])[:6]
    if https:
        tile2_body = '<div class="sysmap-rows">' + "".join(
            row(f'{escape(_topov2_truncate(e["source_service"], 14))} → '
                f'{escape(_topov2_truncate(node_name.get(e["target_id"], e["target_id"]), 14))}',
                f'{e["weight"]} calls')
            for e in https
        ) + '</div>'
    else:
        tile2_body = ('<p class="sysmap-note">No frontend→backend calls could be '
                      'matched to a route.</p>')

    # ---------- Tile 3: entry points per service ----------
    entries_by_service: dict[str, int] = {}
    for n in front + back:
        if n["id"] in sel["entry_counts"]:
            sid = n.get("service") or "?"
            entries_by_service[sid] = entries_by_service.get(sid, 0) + 1
    if entries_by_service:
        tile3_body = '<div class="sysmap-rows">' + "".join(
            row(escape(_topov2_truncate(sid, 22)),
                f'{cnt} entry module{"s" if cnt != 1 else ""}')
            for sid, cnt in sorted(entries_by_service.items(), key=lambda kv: -kv[1])
        ) + '</div>'
    else:
        tile3_body = '<p class="sysmap-note">No HTTP entry points detected.</p>'

    # ---------- Tile 4: what's not on the map ----------
    tile4_body = '<div class="sysmap-rows">' + "".join([
        row("Vendored modules excluded", str(sel["excluded_vendored"])),
        row("Small modules truncated", str(sel["truncated"])),
    ]) + '</div>'

    return f"""
<div class="sysmap-bento">
  <div class="sysmap-tile">
    <div class="tile-label">Composition</div>
    <div class="tile-headline">Code and stores per tier</div>
    <div class="tile-body">{tile1_body}</div>
  </div>
  <div class="sysmap-tile">
    <div class="tile-label">Call paths</div>
    <div class="tile-headline">Heaviest frontend → backend routes</div>
    <div class="tile-body">{tile2_body}</div>
  </div>
  <div class="sysmap-tile">
    <div class="tile-label">Entry points</div>
    <div class="tile-headline">Where requests arrive, per service</div>
    <div class="tile-body">{tile3_body}</div>
  </div>
  <div class="sysmap-tile">
    <div class="tile-label">Excluded</div>
    <div class="tile-headline">What this map deliberately leaves out</div>
    <div class="tile-body">{tile4_body}</div>
  </div>
</div>
"""
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd plugin/skills/map-repo/scripts && python3 -m unittest tests.test_render_system_map -v`

Expected: ALL pass.

- [ ] **Step 6: Commit**

```bash
git add plugin/skills/map-repo/scripts/render.py plugin/skills/map-repo/scripts/tests/test_render_system_map.py
git commit -m "feat: system-map observations and bento small-multiples

Hub/imbalance/orphan/vendored/unreached-entry observations plus tier
composition, call-path, entry-density, and exclusions tiles."
```

---

### Task 7: Regenerate fixtures, visual verification, full suite

The deterministic body intentionally changed (new section + heuristic vendored support). Regenerate the fittalk test data with the new scanner, regenerate the golden fixture, and do the visual quality gate.

**Files:**
- Modify: `plugin/skills/map-repo/scripts/tests/fixtures/golden_fittalk.html` (regenerated)
- Modify: `/home/mckechniep/projects/fittalk-monorepo/.codemap/codemap.json` (re-scanned — note: this file is OUTSIDE the repo)

- [ ] **Step 1: Re-scan fittalk with the new scanner**

```bash
python3 plugin/skills/map-repo/scripts/scan.py \
  --path /home/mckechniep/projects/fittalk-monorepo \
  --depth medium \
  --out /home/mckechniep/projects/fittalk-monorepo/.codemap/codemap.json
```

Expected output: `scanned 506 files, 147987 LOC -> ...` (numbers may differ slightly — what matters is it completes without error).

Verify the new flag exists: `python3 -c "import json; d=json.load(open('/home/mckechniep/projects/fittalk-monorepo/.codemap/codemap.json')); print(all('vendored_guess' in m for m in d['modules']), all('vendored_guess' in n for n in d['module_graph']['nodes']))"`

Expected: `True True`

- [ ] **Step 2: Render fittalk HTML and inspect the map**

```bash
python3 plugin/skills/map-repo/scripts/render.py \
  --in /home/mckechniep/projects/fittalk-monorepo/.codemap/codemap.json \
  --out /home/mckechniep/projects/fittalk-monorepo/.codemap/codemap.html
```

Then open the HTML and inspect the System Map section. **Visual quality gate** (the project's bar is high — "output quality is the priority"):

- [ ] All three fittalk services appear as clusters; the React Native app is in the FRONTEND band, both backends in the BACKEND band
- [ ] Entry modules show the ▸ badge and endpoint counts
- [ ] Edges don't cross through node rectangles (minor crossing in gaps is OK; through-node is not)
- [ ] No text overflows its node; no NaN anywhere; no overlapping nodes
- [ ] All 4 stores render as cylinders with correct brand colors
- [ ] The map is NOT spaghetti. If same-band import arcs make it unreadable, apply the documented fallback: in `_sysmap_edges`, filter same-band import edges to CROSS-SERVICE only (`placed[e["source"]]["node"].get("service") != placed[e["target"]]["node"].get("service")`) and add a sentence to the `"sysmap"` SECTION_INTROS entry: "Imports between modules of the same service are omitted here — the dependency matrix below shows them."

- [ ] **Step 3: Render the PDF and verify the map prints on a landscape hero page**

```bash
bash plugin/skills/map-repo/scripts/to-pdf.sh \
  /home/mckechniep/projects/fittalk-monorepo/.codemap/codemap.html \
  /home/mckechniep/projects/fittalk-monorepo/.codemap/codemap.pdf
```

Check: the System Map gets its own landscape page (like the matrix/topology/cpaths/lineage do), nothing is clipped.

- [ ] **Step 4: Regenerate the golden fixture**

The golden fixture is the no-enrichment render of the fittalk codemap:

```bash
python3 -c "
import json, sys
sys.path.insert(0, 'plugin/skills/map-repo/scripts')
import render
data = json.loads(open('/home/mckechniep/projects/fittalk-monorepo/.codemap/codemap.json').read())
html = render.render_document(data)
open('plugin/skills/map-repo/scripts/tests/fixtures/golden_fittalk.html', 'w').write(html)
print('golden regenerated:', len(html), 'bytes')
"
```

- [ ] **Step 5: Run the FULL suite — everything must pass now**

Run: `python3 -m unittest discover -s plugin/skills/map-repo/scripts/tests -v 2>&1 | tail -25`

Expected: OK. Every test passes, including `DegradationTest` against the regenerated golden.

- [ ] **Step 6: Verify the enrichment path still degrades correctly**

The load-bearing invariant — render WITH enrichment, strip the enrichment-only sections, confirm the deterministic sections are identical:

Run: `cd plugin/skills/map-repo/scripts && python3 -m unittest tests.test_render_enrichment -v`

Expected: all pass (the body-comparison tests in there cover this).

- [ ] **Step 7: Commit (golden fixture only — codemap.json lives outside the repo)**

```bash
git add plugin/skills/map-repo/scripts/tests/fixtures/golden_fittalk.html
git commit -m "test: regenerate golden fixture with system-map section

The deterministic body intentionally gained the system map and
heuristic vendored support; fittalk test data re-scanned with the
0.8.0 scanner (vendored_guess on modules and graph nodes)."
```

---

## Verification checklist (after all tasks)

- [ ] `python3 -m unittest discover -s plugin/skills/map-repo/scripts/tests` → OK, zero failures
- [ ] Fittalk HTML report has the System Map as the first diagram, right after the overview
- [ ] Fittalk PDF prints the map on its own landscape page
- [ ] `git log --oneline` shows one commit per task, conventional-commit formatted
- [ ] No new external dependencies (`grep -rn "^import \|^from " plugin/skills/map-repo/scripts/render.py | grep -v "^.*: *#"` shows only stdlib)
- [ ] Version bump NOT done here — it happens at the end of Plan 2 (flows), per the spec

## Out of scope for this plan

- Flow skeletons, SKILL.md changes, Key Flows rendering at scale → Plan 2 (`2026-06-03-full-coverage-flows.md`, written after this plan executes)
- plugin.json version bump to 0.8.0 → end of Plan 2
- Updating SKILL.md's vendored prose to mention the heuristic flag → Plan 2 (it touches Step 1.5 anyway)
- Propagating `vendored_guess` into the evidence pack (`evidence.py`) so Step 1.5 starts from the heuristic instead of re-deriving it → Plan 2 (the evidence pack is reworked there for flow skeletons anyway)
