# System Map — Focus & Facet Views Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make the System Map explorable — add interactive focus (hover/click to trace a node's connections or isolate a service, plus edge-layer toggles) and a static per-service facet strip that decomposes the overview into clean small-multiples.

**Architecture:** All additive, inside the existing `#codemap-sysmap-section`. (1) Emit identity hooks (`data-*`) on nodes/edges. (2) Inline vanilla JS (zero deps) reads those hooks to drive focus + layer toggles. (3) `@media print` restores the full static map. (4) A new `render_sysmap_facets` reuses the existing select/layout/edge/emit machinery on per-service data slices. Default (unfocused) state is the full bright map exactly as today. Facets in a responsive small-multiples grid.

**Tech Stack:** Python 3.10+ stdlib only (render); inline vanilla JS (no framework/CDN); stdlib `unittest`.

**Design decisions (from brainstorming):** interactive + facets both; small inline JS acceptable (precedent: matrix tooltips, flows expand/collapse) provided it degrades to the full static map in print; default state = full bright map; facets = responsive small-multiples grid.

**Working branch:** `feat/0.8.0-flows-and-system-map` (continues Plan 1's System Map work).

**Focus model (precise):**
- **Node focus** (hover/click a module node) = highlight that node + its IMPORT-edge neighbors + the import edges between them; fade the rest. (Import edges are node↔node — the clean, well-defined "trace code dependencies" neighborhood.)
- **Cluster focus** (click a service cluster label/box) = highlight the whole service: all its nodes + every edge touching it (internal imports, HTTP to/from it, store edges from it).
- **Layer toggles** (chips) = independently show/hide `import` / `http` / `store` edges and `orphan` nodes. Independent of focus; state persists.
- Click background or press `Esc` = clear focus.

**Current code facts (verified at plan time):**

| Fact | Location |
|---|---|
| `SYSMAP_*` constants | `render.py:2627-2649` |
| `_sysmap_select` | `render.py:2664` |
| `_sysmap_layout` (returns placed/clusters/stores/bands/height) | `render.py:2746` |
| `_sysmap_edges` (import edges carry NO src/tgt ids; http carry `source_service`+`target_id`; store carry only coords+color) | `render.py:2899` |
| `_sysmap_emit_svg` (nodes `<g class="sysmap-node">`, edges `<path class="sysmap-edge-*">`) | `render.py:3072` |
| node `<g>` emission | `render.py:3168-3196` |
| edge emission | `render.py:3119-3157` |
| cluster outline+label emission | `render.py:3103-3117` |
| `render_system_map` (assembles section) | `render.py:3404-3453` |
| `render_sysmap_bento` | `render.py` (ends ~3401) |
| CSS string `.sysmap-*` block | added in Plan 1 Task 5, after `.modgraph-matrix-wrap` |
| `@media print` sysmap rules (`.sysmap-svg` height cap, page:hero) | in the print block (Plan 1 Task 5 fix) |
| Existing inline-JS precedent | matrix tooltip `<script>` + `FLOWS_JS` |

**Run tests (from scripts dir):** `cd plugin/skills/map-repo/scripts && python3 -m unittest discover -s tests 2>&1 | tail -8`

**IMPORTANT — golden test during this plan:** Task 1 modifies `_sysmap_emit_svg` (in the document body), so the `DegradationTest` golden tests go red and STAY red through Task 5. That is expected — golden is regenerated once in Task 6. Throughout Tasks 1-5, the "tests pass" bar is: new tests pass; the ONLY failures are the 2 `DegradationTest` golden tests; they fail by content-diff (not a crash). If anything else fails, fix it. Do NOT regenerate the golden before Task 6.

**Browser caveat:** headless Chrome can't run in this environment, so interactive behavior is verified by EMITTED-HOOK tests (attributes/JS/CSS present and well-formed) + user eyeball, not automated click simulation. Facet SVGs are verified by the same geometry checks as the overview (no overflow/NaN, deterministic).

**Line-number note:** numbers above are plan-time; locate code by quoted snippets, not line numbers.

---

### Task 1: Identity hooks on nodes and edges

Focus JS needs to know which edges touch which node. Add stable ids to edge dicts and `data-*` attributes to emitted nodes/edges.

**Files:**
- Modify: `plugin/skills/map-repo/scripts/render.py` (`_sysmap_edges`, `_sysmap_emit_svg`)
- Modify: `plugin/skills/map-repo/scripts/tests/test_render_system_map.py`

- [ ] **Step 1: Write failing tests**

Add to `test_render_system_map.py` (a new `IdentityHooksTest` class):

```python
class IdentityHooksTest(unittest.TestCase):
    def setUp(self):
        self.data = synthetic_data()
        self.sel = render._sysmap_select(self.data, None)
        self.layout = render._sysmap_layout(self.sel)
        self.edges = render._sysmap_edges(self.data, self.layout)

    def test_import_edges_carry_src_tgt_ids(self):
        imp = [e for e in self.edges if e["kind"] == "import"]
        self.assertTrue(imp)
        for e in imp:
            self.assertIn("src", e)
            self.assertIn("tgt", e)
            self.assertIn(e["src"], self.layout["placed"])
            self.assertIn(e["tgt"], self.layout["placed"])

    def test_http_edges_carry_src_service_and_tgt(self):
        for e in [e for e in self.edges if e["kind"] == "http"]:
            self.assertIn("source_service", e)
            self.assertIn("target_id", e)

    def test_store_edges_carry_src_service_and_store(self):
        for e in [e for e in self.edges if e["kind"] == "store"]:
            self.assertIn("source_service", e)
            self.assertIn("target_store", e)

    def test_svg_nodes_have_data_attrs(self):
        svg = render._sysmap_emit_svg(self.layout, self.edges, self.sel, None)
        # every node group exposes its id + service + is focusable
        self.assertIn('data-nid="api/auth"', svg)
        self.assertIn('data-svc="api"', svg)
        self.assertIn('tabindex="0"', svg)
        self.assertIn('role="button"', svg)

    def test_svg_edges_have_data_attrs(self):
        svg = render._sysmap_emit_svg(self.layout, self.edges, self.sel, None)
        self.assertIn('data-kind="import"', svg)
        self.assertIn('data-kind="http"', svg)
        self.assertIn('data-kind="store"', svg)
        # an import edge exposes its endpoints
        self.assertRegex(svg, r'data-src="[^"]+" data-tgt="[^"]+"')
```

- [ ] **Step 2: Run — verify they fail**

Run: `cd plugin/skills/map-repo/scripts && python3 -m unittest tests.test_render_system_map.IdentityHooksTest -v`
Expected: FAIL (no `src`/`tgt` on import edges; no `data-nid` in svg).

- [ ] **Step 3: Add ids to edge dicts in `_sysmap_edges`**

In `_sysmap_edges`, every emitted edge dict must carry identity:
- **import** edges (both the dip and bracket branches, and the cross-band branch): add `"src": e["source"], "tgt": e["target"]` (the module-graph edge's endpoints — they're in scope as `e["source"]`/`e["target"]` from the drawable loop).
- **http** edges: already carry `source_service` and `target_id` — leave as is.
- **store** edges: add `"source_service": e.get("source_service")` and `"target_store": e.get("target_store")` (the `data_lineage` edge's fields, in scope in the store loop).

Make sure NO other behavior changes (coords, ctrl, weight, color unchanged).

- [ ] **Step 4: Emit `data-*` in `_sysmap_emit_svg`**

Node group (currently `<g class="sysmap-node{...}">`): change to include identity + focusability:
```python
        parts.append(
            f'<g class="sysmap-node{" is-entry" if is_entry else ""}" '
            f'data-nid="{escape(nid)}" data-svc="{escape(n.get("service") or "")}" '
            f'tabindex="0" role="button" '
            f'aria-label="{escape((n.get("name") or nid))}">'
        )
```

Each edge `<path>` gets `data-kind` plus endpoint hooks. For imports add `data-src`/`data-tgt`; for http add `data-src-svc`/`data-tgt`; for store add `data-src-svc`/`data-tgt-store`. Example for the import branch:
```python
            parts.append(
                f'<path d="{dpath}" class="sysmap-edge-import" '
                f'data-kind="import" data-src="{escape(e["src"])}" data-tgt="{escape(e["tgt"])}" '
                f'stroke-width="{sw:.1f}" fill="none" />'
            )
```
http branch: add `data-kind="http" data-src-svc="{escape(e["source_service"])}" data-tgt="{escape(e["target_id"])}"`.
store branch: add `data-kind="store" data-src-svc="{escape(e.get("source_service") or "")}" data-tgt-store="{escape(e.get("target_store") or "")}"`.

Also add `data-svc` to each cluster outline rect and label so cluster-focus JS can find them — give the cluster `<rect>` (or wrap cluster rect+label in a `<g class="sysmap-cluster" data-svc="...">`). Simplest: wrap the cluster rect+label emission in `<g class="sysmap-cluster" data-svc="{escape(c["service_id"])}" tabindex="0" role="button">...</g>`.

And give each store `<g class="sysmap-store">` a `data-store="{escape(sid)}"` so store-layer toggle / cluster-focus can target it.

- [ ] **Step 5: Run new tests — pass**

Run: `cd plugin/skills/map-repo/scripts && python3 -m unittest tests.test_render_system_map.IdentityHooksTest -v` → PASS.

- [ ] **Step 6: Full suite — only golden red**

Run: `cd plugin/skills/map-repo/scripts && python3 -m unittest discover -s tests 2>&1 | tail -8`
Expected: only the 2 `DegradationTest` golden tests fail (content-diff: new data-attrs). Everything else green.

- [ ] **Step 7: Commit**

```bash
git add plugin/skills/map-repo/scripts/render.py plugin/skills/map-repo/scripts/tests/test_render_system_map.py
git commit -m "feat: identity hooks (data-*) on system-map nodes and edges

Edge dicts now carry src/tgt ids; SVG nodes/edges/clusters/stores emit
data attributes + focusability so the upcoming inline focus JS can build
an adjacency map. Golden intentionally stale until the focus feature is
complete (regenerated at the end)."
```

---

### Task 2: Focus CSS (states only, no behavior)

Define the visual states focus/toggles will switch between. No JS yet.

**Files:**
- Modify: `plugin/skills/map-repo/scripts/render.py` (CSS string)
- Modify: `plugin/skills/map-repo/scripts/tests/test_render_system_map.py`

- [ ] **Step 1: Write failing test**

```python
class FocusCssTest(unittest.TestCase):
    def test_focus_and_toggle_css_present(self):
        css = render.CSS
        # dimming when a focus is active
        self.assertIn(".sysmap-svg.has-focus", css)
        self.assertIn(".is-active", css)
        # layer-hide classes
        for cls in ("hide-import", "hide-http", "hide-store", "hide-orphan"):
            self.assertIn(cls, css)
        # print restores everything
        # (assert the print block neutralizes focus dimming)
        self.assertIn("sysmap-controls", css)
```

- [ ] **Step 2: Run — fail.** `...FocusCssTest -v` → FAIL.

- [ ] **Step 3: Add CSS** (append to the existing `.sysmap-*` CSS block):

```css
/* ---- System map: focus + layer toggles ---- */
.sysmap-controls { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 var(--space-3); align-items: center; }
.sysmap-chip {
  font-family: var(--font-mono); font-size: 0.78rem; cursor: pointer;
  border: 1px solid var(--border); border-radius: 999px; padding: 3px 12px;
  background: var(--surface); color: var(--ink-2); user-select: none;
  transition: background var(--duration-fast, 150ms), color var(--duration-fast, 150ms), opacity var(--duration-fast, 150ms);
}
.sysmap-chip[aria-pressed="false"] { opacity: 0.45; text-decoration: line-through; }
.sysmap-chip:hover { border-color: var(--accent); }
.sysmap-hint { font-size: 0.78rem; color: var(--muted); margin-left: auto; }

/* default: nothing dimmed. when a node/cluster is focused, fade the rest. */
.sysmap-svg .sysmap-node, .sysmap-svg [class^="sysmap-edge"], .sysmap-svg .sysmap-store {
  transition: opacity 140ms ease;
}
.sysmap-svg.has-focus .sysmap-node:not(.is-active),
.sysmap-svg.has-focus [class^="sysmap-edge"]:not(.is-active),
.sysmap-svg.has-focus .sysmap-store:not(.is-active) { opacity: 0.10; }
.sysmap-svg .sysmap-node.is-active .sysmap-node-rect { stroke-width: 2; }

/* node hover affordance */
.sysmap-svg .sysmap-node { cursor: pointer; }
.sysmap-svg .sysmap-node:focus { outline: none; }
.sysmap-svg .sysmap-node:focus .sysmap-node-rect { stroke: var(--accent); stroke-width: 2; }

/* layer toggles hide edge kinds / orphans */
.sysmap-svg.hide-import [data-kind="import"],
.sysmap-svg.hide-http [data-kind="http"],
.sysmap-svg.hide-store [data-kind="store"] { display: none; }
.sysmap-svg.hide-orphan .sysmap-node[data-orphan="1"] { display: none; }
```

Add to the `@media print` block so the PDF is the full static map:
```css
  .sysmap-controls { display: none; }
  .sysmap-svg.has-focus .sysmap-node,
  .sysmap-svg.has-focus [class^="sysmap-edge"],
  .sysmap-svg.has-focus .sysmap-store { opacity: 1 !important; }
  .sysmap-svg.hide-import [data-kind="import"],
  .sysmap-svg.hide-http [data-kind="http"],
  .sysmap-svg.hide-store [data-kind="store"],
  .sysmap-svg.hide-orphan .sysmap-node[data-orphan="1"] { display: initial !important; }
```

**CSS var check:** confirm `--duration-fast` exists; if not, inline `150ms`.

- [ ] **Step 4: Mark orphan nodes.** In `_sysmap_emit_svg`, when emitting a node, add `data-orphan="1"` when the node has no drawn edges (compute the set of node ids that appear as `src`/`tgt` of any import edge OR `target_id` of http OR participate via cluster — simplest: a node is "orphan" if it is not an endpoint of any edge in `edges`). Build `connected_ids` from `edges` once before the node loop; emit `data-orphan="1"` for nodes not in it. Add a test in `IdentityHooksTest` or `FocusCssTest`:
```python
    def test_orphan_nodes_marked(self):
        svg = render._sysmap_emit_svg(self.layout, self.edges, self.sel, None) \
            if hasattr(self, "layout") else None
        # build fresh if needed
        import json
        d = synthetic_data()
        sel = render._sysmap_select(d, None); L = render._sysmap_layout(sel); E = render._sysmap_edges(d, L)
        svg = render._sysmap_emit_svg(L, E, sel, None)
        self.assertIn('data-orphan="1"', svg)  # synthetic has the vendored-excluded? ensure an orphan exists
```
(If synthetic_data has no orphan, add one isolated node to the fixture-local data in this test so the assertion is meaningful.)

- [ ] **Step 5: Run FocusCssTest + full suite.** New tests pass; only the 2 golden fail.

- [ ] **Step 6: Commit**

```bash
git add plugin/skills/map-repo/scripts/render.py plugin/skills/map-repo/scripts/tests/test_render_system_map.py
git commit -m "feat: focus + layer-toggle CSS states for the system map

Adds dimming on .has-focus, .is-active highlight, hide-import/http/store/
orphan layer classes, control-chip styles, and print rules that restore
the full static map. Behavior wired in the next task. Orphan nodes now
marked with data-orphan."
```

---

### Task 3: Focus JS (node + cluster focus)

Inline vanilla JS: hover/click a node → import-neighborhood focus; click a cluster → service-subgraph focus; Esc/background → clear.

**Files:**
- Modify: `plugin/skills/map-repo/scripts/render.py` (`render_system_map` — add a `SYSMAP_JS` string + `<script>` in the section)
- Modify: `plugin/skills/map-repo/scripts/tests/test_render_system_map.py`

- [ ] **Step 1: Write failing test**

```python
class FocusJsTest(unittest.TestCase):
    def test_section_includes_focus_script(self):
        html = render.render_system_map(synthetic_data(), None)
        self.assertIn("<script>", html)
        # references the section/svg and key behaviors by hook
        self.assertIn("has-focus", html)
        self.assertIn("is-active", html)
        self.assertIn("data-nid", html)        # JS reads node ids
        self.assertIn("addEventListener", html)
        self.assertIn("Escape", html)          # esc clears focus

    def test_script_is_dependency_free(self):
        html = render.render_system_map(synthetic_data(), None)
        # no external/script srcs, no framework globals
        self.assertNotIn("src=", html[html.index("<script>"):])
        for banned in ("require(", "import ", "d3.", "React", "cdn"):
            self.assertNotIn(banned, html[html.index("<script>"):])
```

- [ ] **Step 2: Run — fail.**

- [ ] **Step 3: Implement `SYSMAP_JS`**

Add a module-level `SYSMAP_JS` string in `render.py` (near `render_system_map`). It must be a self-contained IIFE scoped to the sysmap section, dependency-free. Behavior:
- On load, find the sysmap `<svg class="sysmap-svg">`.
- Build adjacency: for each `[data-kind="import"]` path, read `data-src`/`data-tgt`; map each node id → set of incident import paths + neighbor node ids. For http/store, map service id → incident paths, and target node/store → incident paths.
- **Node interactions:** `mouseenter`/`focus` on a `.sysmap-node` (when nothing is pinned) → call `applyNodeFocus(nid)`: add `has-focus` to svg; add `is-active` to the node, its import-neighbor nodes, and the import paths between them. `mouseleave`/`blur` → if not pinned, `clearFocus()`.
- **Click a node** → toggle a pinned focus on that node (pin = stays after mouse leaves; clicking the same pinned node, or background, or Esc, clears).
- **Click a `.sysmap-cluster`** → pinned cluster focus: `is-active` on all nodes with that `data-svc`, all import paths whose src AND/OR tgt is in the service, all http/store paths with `data-src-svc == svc` (or `data-tgt` in service), and the service's stores.
- **Background click** (on the svg but not a node/cluster/store) and **Escape** → `clearFocus()` + unpin.
- Keyboard: nodes are `tabindex=0`; `Enter`/`Space` on a focused node = same as click (pin).

Keep it small (~60-90 lines). Escape all is class-toggling; no innerHTML injection.

In `render_system_map`, append `<script>{SYSMAP_JS}</script>` at the END of the returned section (after the bento). Since multiple sysmap svgs may exist later (facets), scope the JS to the MAIN overview svg only — select `#codemap-sysmap-section .sysmap-frame .sysmap-svg` (facets live outside `.sysmap-frame`). Document that scoping in a comment.

- [ ] **Step 4: Run FocusJsTest + full suite.** New tests pass; only 2 golden fail.

- [ ] **Step 5: Commit**

```bash
git add plugin/skills/map-repo/scripts/render.py plugin/skills/map-repo/scripts/tests/test_render_system_map.py
git commit -m "feat: inline focus JS for the system map (node + service tracing)

Dependency-free IIFE: hover/click a module to trace its import
neighborhood, click a service to isolate its subgraph, Esc/background to
clear. Scoped to the overview SVG; print shows the full static map."
```

---

### Task 4: Layer-toggle chips

Controls above the map to show/hide edge kinds and orphans.

**Files:**
- Modify: `plugin/skills/map-repo/scripts/render.py` (`render_system_map` controls markup; extend `SYSMAP_JS`)
- Modify: `plugin/skills/map-repo/scripts/tests/test_render_system_map.py`

- [ ] **Step 1: Write failing test**

```python
class LayerChipsTest(unittest.TestCase):
    def test_controls_present_with_chips(self):
        html = render.render_system_map(synthetic_data(), None)
        self.assertIn("sysmap-controls", html)
        for label in ("Imports", "HTTP", "Stores", "Orphans"):
            self.assertIn(label, html)
        self.assertIn('aria-pressed="true"', html)   # chips start enabled
        self.assertIn("sysmap-chip", html)

    def test_chip_toggle_wired_in_js(self):
        html = render.render_system_map(synthetic_data(), None)
        js = html[html.index("<script>"):]
        for cls in ("hide-import", "hide-http", "hide-store", "hide-orphan"):
            self.assertIn(cls, js)
```

- [ ] **Step 2: Run — fail.**

- [ ] **Step 3: Implement**

In `render_system_map`, build a controls bar placed ABOVE the svg inside `.sysmap-frame`:
```python
    controls = (
        '<div class="sysmap-controls" role="group" aria-label="Map filters">'
        '<button type="button" class="sysmap-chip" data-layer="import" aria-pressed="true">Imports</button>'
        '<button type="button" class="sysmap-chip" data-layer="http" aria-pressed="true">HTTP</button>'
        '<button type="button" class="sysmap-chip" data-layer="store" aria-pressed="true">Stores</button>'
        '<button type="button" class="sysmap-chip" data-layer="orphan" aria-pressed="true">Orphans</button>'
        '<span class="sysmap-hint">hover a module to trace · click to pin · click a service to isolate</span>'
        '</div>'
    )
```
Insert `{controls}` before `<div class="sysmap-wrap">{svg}</div>`.

Extend `SYSMAP_JS`: for each `.sysmap-chip`, on click toggle `aria-pressed` and toggle the matching `hide-<layer>` class on the svg (`import`→`hide-import`, `orphan`→`hide-orphan`, etc.).

- [ ] **Step 4: Run LayerChipsTest + full suite.** New tests pass; only 2 golden fail.

- [ ] **Step 5: Commit**

```bash
git add plugin/skills/map-repo/scripts/render.py plugin/skills/map-repo/scripts/tests/test_render_system_map.py
git commit -m "feat: layer-toggle chips (imports/http/stores/orphans) for system map

Per-kind show/hide on demand; chips reflect state via aria-pressed and
toggle hide-* classes. Hidden in print."
```

---

### Task 5: Per-service facet maps

Static small-multiples: one mini-map per service showing only its internal wiring + stores.

**Files:**
- Modify: `plugin/skills/map-repo/scripts/render.py` (new `_sysmap_service_slice`, `render_sysmap_facets`, viewBox-crop support in emit, CSS; wire into `render_system_map`)
- Modify: `plugin/skills/map-repo/scripts/tests/test_render_system_map.py`

- [ ] **Step 1: Write failing tests**

```python
class FacetsTest(unittest.TestCase):
    def test_one_facet_per_product_service(self):
        html = render.render_sysmap_facets(synthetic_data(), None)
        self.assertIn("sysmap-facets", html)
        # synthetic has 2 services (web, api) -> 2 facet cards
        self.assertEqual(html.count("sysmap-facet-card"), 2)

    def test_facet_titles_name_services(self):
        html = render.render_sysmap_facets(synthetic_data(), None)
        self.assertIn("web", html)
        self.assertIn("api", html)

    def test_facet_svg_no_overflow_or_nan(self):
        # build one facet slice and check geometry like the overview
        d = synthetic_data()
        slc = render._sysmap_service_slice(d, "api")
        sel = render._sysmap_select(slc, None)
        layout = render._sysmap_layout(sel)
        for p in layout["placed"].values():
            self.assertGreaterEqual(p["x"], 0)
            self.assertEqual(p["x"], p["x"])  # NaN guard
        html = render.render_sysmap_facets(d, None)
        self.assertNotIn("nan", html.lower())

    def test_facets_in_document(self):
        html = render.render_system_map(synthetic_data(), None)
        self.assertIn("sysmap-facets", html)
        # facets come after the bento
        self.assertGreater(html.index("sysmap-facets"), html.index("sysmap-bento"))

    def test_facet_excludes_other_services_nodes(self):
        slc = render._sysmap_service_slice(synthetic_data(), "api")
        node_ids = {n["id"] for n in slc["module_graph"]["nodes"]}
        self.assertTrue(all(nid.startswith("api/") for nid in node_ids))
```

- [ ] **Step 2: Run — fail.**

- [ ] **Step 3: Implement the slice + facets**

`_sysmap_service_slice(data, service_id)` → a new data-shaped dict scoped to one service:
- `services`: just the service dict for `service_id`.
- `module_graph.nodes`: only nodes whose `service == service_id` (drop vendored via the same flag logic? — keep it simple: include the service's nodes; vendored filtering happens in `_sysmap_select`).
- `module_graph.edges`: only edges where BOTH endpoints are in the service's node set (internal imports).
- `data_lineage`: stores + edges for that service only (`edges` where `source_service == service_id`; `stores` limited to those targeted, preserving full store dicts).
- `http_topology`: keep `entry_modules`/`endpoints` for the service (so entry badges show) but `edges: []` (cross-service HTTP is summarized as text, not drawn, in the facet).
- `scan_depth`: carry over (caps a giant service's facet too).

`render_sysmap_facets(data, enrichment)`:
- For each product service (services with ≥1 non-vendored node), build the slice, run `_sysmap_select`/`_sysmap_layout`/`_sysmap_edges`, emit a COMPACT svg (see Step 4), and wrap in a `<figure class="sysmap-facet-card">` with a `<figcaption>` = service name + a one-line stat ("N modules · M imports · K stores") and, if known, a small "called by / calls" text line derived from the FULL `data`'s `http_topology.edges` (services that call this one / that this one calls) — text only, no lines.
- Wrap all cards in `<div class="sysmap-facets">` with a small `<h3>Per-service views</h3>` + one-line intro.
- Return "" if there are fewer than 2 product services (a single-service repo's facet would duplicate the overview).

- [ ] **Step 4: Compact viewBox for facets**

`_sysmap_emit_svg` currently hard-codes the viewBox width to `SYSMAP_W`. Add an optional `view_w: float | None = None` parameter; when provided, use it as the viewBox width (and for the right-edge clamp of band labels). In `render_sysmap_facets`, compute `view_w = max(node.x+node.w, store.x+store.w, cluster.x+cluster.w) + SYSMAP_MARGIN_X` from the facet layout and pass it, so each facet crops to its actual content instead of 1120px of mostly-empty canvas. The overview call passes nothing (keeps 1120). Confirm no other caller breaks.

- [ ] **Step 5: CSS for the facet grid** (append to `.sysmap-*` CSS):

```css
.sysmap-facets { margin-top: var(--space-5); }
.sysmap-facets > h3 { font-family: var(--font-serif); margin: 0 0 var(--space-2); }
.sysmap-facet-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--space-3); }
@media (max-width: 760px) { .sysmap-facet-grid { grid-template-columns: 1fr; } }
.sysmap-facet-card {
  margin: 0; background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: var(--space-3);
}
.sysmap-facet-card figcaption {
  font-family: var(--font-mono); font-size: 0.82rem; color: var(--ink-2);
  margin-bottom: var(--space-2);
}
.sysmap-facet-card .sysmap-facet-stat { color: var(--muted); }
@media print { .sysmap-facet-grid { grid-template-columns: 1fr 1fr; } }
```
Wrap the facet cards in `<div class="sysmap-facet-grid">` inside `.sysmap-facets`.

- [ ] **Step 6: Wire into `render_system_map`** — append `render_sysmap_facets(data, enrichment)` after the bento, before the `</section>` and the `<script>`. (Facets are static; they sit outside `.sysmap-frame` so the focus JS — scoped to `.sysmap-frame .sysmap-svg` — leaves them alone.)

- [ ] **Step 7: Run FacetsTest + full suite.** New tests pass; only 2 golden fail.

- [ ] **Step 8: Commit**

```bash
git add plugin/skills/map-repo/scripts/render.py plugin/skills/map-repo/scripts/tests/test_render_system_map.py
git commit -m "feat: per-service facet maps (static small-multiples)

Each product service gets a compact mini-map of its internal imports +
stores, viewBox-cropped to content, in a responsive grid below the
overview. Cross-service calls summarized as text. No JS; print-friendly."
```

---

### Task 6: Golden regen + full programmatic gate + visual handoff

**Files:**
- Modify: `plugin/skills/map-repo/scripts/tests/fixtures/golden_fittalk.html`

- [ ] **Step 1: Regenerate the golden** from the canonical codemap the test loads:
```bash
cd plugin/skills/map-repo/scripts && python3 -c "
import json, render
d=json.loads(open('/home/mckechniep/projects/fittalk-monorepo/.codemap/codemap.json').read())
open('tests/fixtures/golden_fittalk.html','w').write(render.render_document(d))
print('regenerated')
"
```

- [ ] **Step 2: Full suite — ALL green now.**
Run: `cd plugin/skills/map-repo/scripts && python3 -m unittest discover -s tests 2>&1 | tail -6` → OK, zero failures.

- [ ] **Step 3: Render fittalk + programmatic gate.** Render the full report to a temp HTML and verify: focus JS block present once; controls present; every node has `data-nid`; facet count == product-service count; no NaN; no node overflow in overview or any facet; the focus CSS + print-restore rules present. Report the numbers.

- [ ] **Step 4: Hand the HTML to the user** for eyeball (browser): confirm hover-trace, click-pin, cluster isolate, layer chips, and the facet grid all read well, and the PDF still shows the full static map. Wait for approval.

- [ ] **Step 5: Commit the golden**
```bash
git add plugin/skills/map-repo/scripts/tests/fixtures/golden_fittalk.html
git commit -m "test: regenerate golden with system-map focus + facets

Deterministic body now includes data hooks, controls, focus JS, and the
per-service facet grid. Full suite green."
```

---

## Verification checklist (after all tasks)
- [ ] Full suite green (0 failures)
- [ ] Overview map unchanged at rest (default = full bright map); focus/toggles are additive
- [ ] Inline JS is dependency-free and scoped to the overview svg; facets untouched by it
- [ ] PDF/print shows the full static map (controls hidden, opacity restored)
- [ ] Each product service has one facet; facets crop to content; no overflow/NaN
- [ ] User eyeball sign-off on interactions + facets

## Out of scope
- Full-coverage Key Flows (Plan 2 — separate) — note "trace a path" as a narrative lives there; this plan is structural focus on the map.
- plugin.json version bump (end of Plan 2).
- Cross-service edges drawn inside facets (summarized as text instead).
- Animating focus transitions beyond a simple opacity fade.
