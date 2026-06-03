# Full-Coverage Key Flows + System Map — Design

**Date:** 2026-06-03
**Status:** Approved design, pending implementation plan
**Component:** `smokeyp-codebase-mapper` plugin (`plugin/skills/map-repo`)
**Target version:** 0.8.0

## Problem

Two gaps, both identified by the user as the highest-leverage improvements:

1. **Key Flows are the report's biggest value but its scarcest content.**
   Flows are authored by Claude during Step 1.5 and capped at 3 flows at
   `--depth medium` / 6 at `--depth full`. The cap exists because every
   flow step must cite a real `file:symbol` that Claude actually read,
   and reading is bounded (evidence pack + ~20 files). On fittalk that
   means 3 stories for a codebase with 139 endpoints across 16
   controllers — coverage of roughly one fifth of what the app does.

2. **The report has no single orienting "big picture" diagram.** The four
   hero sections each answer a narrow question (module coupling, service
   topology, request anatomy, storage). Nothing shows the whole system —
   actual product components in their tiers (frontend / backend / data),
   wired together — on one canvas. The closest section (C4 topology)
   draws whole services as single boxes, which is too coarse: fittalk's
   topology is 3 boxes.

Both gaps share a blocker: **vendored code is only identified by the LLM.**
Without enrichment there is no way to keep `google_ads-master`-style
vendored trees out of any "product components" view.

## Key insight

The scanner already computes everything a flow skeleton needs — endpoints
(trigger), module-graph edges (key dependencies), data-lineage edges
(terminus). The LLM's expensive job (discovering flows by reading code)
can be eliminated; its irreplaceable job (narrating the story, naming the
flow, catching non-HTTP flows) stays. ast-grep integration (v0.7.0) means
handler symbol names can also be extracted deterministically, so skeletons
arrive with real `file:symbol` citations pre-attached.

Same pattern as the LLM evaluation layer itself: deterministic core does
the heavy lifting, the LLM adds judgment on top.

## Decisions made during brainstorming

| Decision | Choice |
|---|---|
| Flow coverage target | Full coverage — every route group + every non-HTTP flow the LLM finds |
| Flow granularity | Per route-group (≈ per entry module), not per endpoint, not per domain |
| Flow generation approach | Scanner pre-computes skeletons; LLM narrates (approach 1A) |
| Map layout | Layered bands: frontend → backend → data tiers, modules as nodes (option A) |
| Map data approach | Deterministic hero + heuristic vendored filter; enrichment refines (approach 2A) |
| Map placement | Immediately after "What this codebase is" (new section 3) |
| Flows without enrichment | Stay enrichment-gated — un-narrated skeletons are redundant with Critical Paths |
| Version | 0.8.0 (pre-1.0 MINOR bump, two features) |

## Part 1 — Deterministic vendored detection (shared foundation)

`scan.py` gains a per-module boolean `vendored_guess`, computed from the
heuristics that currently live only as Step 1.5 prose in SKILL.md:

- Module path contains a `vendor/` or `node_modules/` segment, or is under
  a top-level `vendor/` directory.
- Directory name ends `-master`, `-develop`, or `-main` (git-archive clones).
- The module's `package.json` declares a `repository` URL pointing at a
  third-party project (not matching the repo's own name/org), or carries a
  third-party `LICENSE` file alongside a publishable package name.

Rules:

- `vendored_guess` is advisory and **deterministic** — same scan, same flag.
- Enrichment classification **overrides in both directions**: a module the
  heuristic flags can be rescued by `classification.products`; a module the
  heuristic misses can be caught by `classification.vendored`.
- Consumers: the modules section (badging/dimming/sorting now works in
  `--no-llm` mode), the System Map (vendored modules excluded entirely),
  and Step 1.5 (the evidence pack carries the guess so Claude starts from
  it instead of re-deriving it).

## Part 2 — Flow skeletons in the scanner

New top-level `flow_skeletons` array in `codemap.json`. One skeleton per
entry module (route group), built by joining data the scanner already has:

```json
{
  "id": "Back-End-FitTalk/src/modules/workouts",
  "service": "Back-End-FitTalk",
  "kind_hint": "request",
  "trigger": "HTTP /api/v1/workouts/* — 19 endpoints (GET×8, POST×5, PATCH×3, DELETE×3)",
  "entry": {
    "module": "Back-End-FitTalk/src/modules/workouts",
    "file": "Back-End-FitTalk/src/modules/workouts/workouts.controller.ts",
    "symbols": ["createWorkout", "getWorkouts", "logSession"]
  },
  "key_deps": [
    {"module": "Back-End-FitTalk/src/common", "weight": 19},
    {"module": "Back-End-FitTalk/src/modules/notifications", "weight": 4}
  ],
  "stores": ["postgres"],
  "endpoint_count": 19
}
```

Construction:

- **One skeleton per `http_topology.entry_modules` entry.** Route prefix
  derived from the longest common path prefix of that module's endpoints;
  method counts aggregated.
- **`entry.file`** = the file contributing the most endpoints for that
  module. **`entry.symbols`** = handler names extracted by ast-grep
  (decorated methods for NestJS, route-handler functions for Express/
  FastAPI/Flask, etc.), using the existing `astgrep_imports.py` bridge
  pattern: never raise, regex fallback, empty list when neither works.
- **`key_deps`** = outgoing `module_graph.edges` from the entry module,
  sorted by weight, capped at 5.
- **`stores`** = stores reachable via `data_lineage.edges` for the
  skeleton's service.
- Skeletons are built for **product modules only** (`vendored_guess` /
  enrichment-classified vendored modules never get skeletons).
- Depth scaling: `shallow` caps skeletons at 10, `medium` at 30, `full`
  unlimited. Ordered by endpoint count descending so truncation keeps the
  most important route groups.

`evidence.py` includes the skeletons in `codemap.evidence.json` so Step 1.5
receives them without re-reading `codemap.json`.

## Part 3 — Step 1.5: narrate, don't discover

SKILL.md's flow instructions change from "write 3–6 flows you discovered"
to a two-part contract:

1. **Narrate every skeleton.** For each skeleton in the evidence pack:
   give it a human name ("Workout tracking", not "workouts module"), write
   the `narration` (what actually happens end-to-end), set `trigger` and
   `terminates` in plain English, and produce `steps` citing the
   skeleton's entry file/symbols, key deps, and store. Claude may read the
   entry file to sharpen symbols/notes but does not need to hunt for the
   flow — the skeleton already locates it. Each narrated flow carries
   `skeleton_id` so coverage is measurable.
2. **Add what only the LLM can see.** Bootstrap, background workers,
   scheduled jobs, webhook consumers, state machines, data pipelines —
   anything without an HTTP entry point. Same citation rules as today.
   No numeric cap; quality-gated by the citation requirement.

Schema changes (`validate_enrichment.py`):

- `flows[].skeleton_id` — optional string. When present, must match a
  skeleton id from `codemap.json` (validator warns, does not fail, on
  unknown ids).
- `schema_version` stays `1`; all additions are optional and backward
  compatible. Existing enrichment files still validate.
- Citation validation unchanged: every step needs `file` + `symbol`, file
  must exist, broken flows dropped at render time.

Reading budget guidance in SKILL.md changes from "~20 extra files" to
"~1 file per skeleton plus ~10 for discovered flows" — bounded and
proportional, not fixed.

## Part 4 — Key Flows section at scale

The existing atlas design (kind-coded lanes, collapsible cards,
expand-all) survives. Changes for 20+ flows:

- Within the **request** lane, flows group by service with a small service
  header (16 request flows can't be one flat pile). Other lanes stay flat.
- Each lane header shows a flow count; lanes gain per-lane expand-all.
- Card summaries gain the endpoint count when the flow has a
  `skeleton_id` ("Workout tracking · 19 endpoints · 5 steps").
- A coverage stat joins the section intro: "Flows cover 16 of 16 route
  groups + 4 non-HTTP flows."
- Print stylesheet behavior unchanged (force-open everything, single
  column).

## Part 5 — The System Map hero

New `render_system_map(data, enrichment)` in `render.py`, rendered as
**section 3**, immediately after "What this codebase is" and before
the Languages section. Follows the established hero pattern:
`h2 → section_intro → hero frame → observations → bento`.

### Layout (deterministic, no force simulation)

- **Three horizontal bands** stacked top to bottom:
  - *Frontend band*: modules of services with kind `frontend` / `mobile`.
  - *Backend band*: modules of services with kind `backend` / `worker` /
    `api` / anything else that isn't a store.
  - *Data band*: stores from `data_lineage.stores` drawn with the existing
    cylinder glyphs and brand colors.
  - A band renders only if it has content (a backend-only repo gets two
    bands; missing bands produce no empty placeholder).
- **Within a band**, modules cluster by service. Each service cluster gets
  a faint outline + service name label (reusing `SERVICE_KIND_COLORS`).
  Modules sort by connectivity (degree in `module_graph.edges`) descending,
  most-connected nearest the band's horizontal center.
- **Nodes** are rounded rects sized by LOC bucket (3 sizes). Entry-point
  modules get the ▸ badge + endpoint count. Node label = module `name`;
  service prefix omitted (the cluster label carries it).
- **Vendored modules are absent** — not dimmed, not ghosted; absent.
  Filter = `vendored_guess` OR enrichment `classification.vendored`,
  minus enrichment `classification.products` rescues.

### Edges

| Edge type | Source → target | Style | Data source |
|---|---|---|---|
| Import | module → module | solid, neutral, width by weight | `module_graph.edges` |
| HTTP call | frontend service cluster → backend entry module | dashed, accent | `http_topology.edges` joined to `endpoints` by path to resolve target module |
| Store access | backend service cluster → store | solid, store-green | `data_lineage.edges` |

- Cross-band edges route vertically with slight horizontal curvature
  (quadratic Bézier); same-band import edges arc below the band.
- **Edge cap**: top 40 import edges by weight; aggregate the remainder
  into a per-service-pair "+N more" note in the section intro. HTTP and
  store edges are aggregated at service level already and render fully.

### Truncation

- Max ~40 module nodes (consistent with `--depth medium`'s 80-node graph
  cap halved for readability), selected by connectivity + LOC. Each band
  shows "+N more modules" when truncated.
- `--depth shallow`: 20 nodes. `--depth full`: 60 nodes (beyond that the
  map stops being a map).

### Observations + bento

- Observations (reuse `_render_observations`): biggest hub module, tier
  imbalance ("87% of code lives in the backend tier"), orphan modules
  (no edges), cross-tier coupling count, vendored modules excluded count.
- Bento small multiples: tier composition donut, top cross-tier edges,
  entry-point density per service, excluded-vendored summary.

### Enrichment refinement

With enrichment present: vendored filter sharpens (LLM classification),
and product module descriptions appear as `<title>` tooltips on nodes.
Without enrichment: heuristic filter only, no tooltips. Both render the
full map — the section is **not** enrichment-gated.

## Part 6 — Degradation invariant + testing

- `render.py` remains a pure function of `(codemap.json, enrichment?)`.
- The System Map and the modules-section vendored badging are deterministic
  features → the no-enrichment body changes → **`golden_fittalk.html` is
  regenerated once** as part of this work. The body-comparison test in
  `test_render_enrichment.py` continues to guard the invariant afterward.
- Flow skeletons change `codemap.json` and `codemap.evidence.json` but not
  the deterministic HTML body (Key Flows stays enrichment-gated).

New tests (stdlib `unittest`, under `plugin/skills/map-repo/scripts/tests/`):

| Test | What it pins |
|---|---|
| `test_vendored.py` | Heuristic rules: vendor paths, `-master` suffixes, third-party package.json; product code never flagged |
| `test_flow_skeletons.py` | Skeleton construction against `graph_repo` fixture: one per entry module, correct trigger/deps/stores, depth caps, vendored exclusion |
| `test_astgrep_handlers.py` | Handler symbol extraction per framework; regex fallback; never-raise contract |
| `test_render_system_map.py` | Band count, node count, vendored exclusion, edge cap, no-NaN coordinates, renders with and without enrichment |
| `test_render_flows_scale.py` | 20-flow enrichment renders grouped lanes, coverage stat, valid HTML |
| Golden fixture | Regenerated `golden_fittalk.html`; body-comparison test green |

Existing tests must stay green, including the two-mode (forced-regex vs
ast-grep) graph tests from v0.7.0.

## Out of scope

- Domain-block clustering (option C) — revisit if layered bands prove
  insufficient on monorepos with many services.
- Rendering un-narrated skeletons in `--no-llm` mode.
- Client-side module attribution for HTTP edges (frontend edges originate
  from service clusters, not individual frontend modules — the `clients`
  data is file-level and noisy; deferred).
- Enrichment caching keyed by repo content hash (pre-existing follow-up,
  unchanged).

## Risks

- **Map readability on extreme repos** (1-2 modules, or 60+ after
  truncation): band layout degrades gracefully — few nodes means a small
  map, truncation caps the top end. The fittalk fixture (37 modules,
  3 services) and brevity (vendored-heavy) are the validation targets.
- **ast-grep handler extraction variance across frameworks**: mitigated by
  the same never-raise + fallback contract as import extraction; a
  skeleton with `symbols: []` is still valid (LLM fills the symbol).
- **Step 1.5 token cost grows with skeleton count**: bounded by depth caps
  (30 skeletons at medium) and the 1-file-per-skeleton reading guidance.
  Worst case the LLM narrates more shallowly; citations stay enforced.
