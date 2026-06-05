# Elixir/Phoenix Support + Enrichment Overrides — Design

**Date:** 2026-06-05
**Status:** Approved (brainstorm complete; pending spec review → implementation plan)
**Target version:** 0.9.0 (pre-1.0 MINOR — new language support + enrichment override surface)

---

## 1. Problem statement

Running the mapper on `~/projects/brevity` (a real Elixir/Phoenix + React-Native monorepo) produced a **wrong System Architecture diagram**. Two symptoms, both traced to one root cause: the first diagram is built deterministically by `scan.py`, a static heuristic tuned for JS/TS/Python and effectively blind to Elixir/Phoenix.

**Symptom 1 — the Elixir backend was tagged `frontend` and placed in the frontend band.**
`_classify_service` (`scan.py:374-407`) reads the first manifest and does a raw substring test (`hint.lower() in lower`, lines 387-392) against the whole manifest text. For `backend/mix.exs`:
- No backend hints matched — Phoenix/Elixir frameworks are absent from `BACKEND_FRAMEWORK_HINTS` (`scan.py:347-362`).
- Exactly one frontend hint matched: `"expo"`, as a **substring of `:export_gql_schema`** in `compilers: [...] ++ [:export_gql_schema]`.
- Result: `stack: ["expo"]`, `kind: "frontend"` — the strongest backend signal in the file (the GraphQL schema compiler) produced a phantom frontend classification.

**Symptom 2 — no HTTP arrows anywhere.**
`http_topology.edges == []`. The endpoint extractor `_scan_endpoints_file` (`scan.py:1519-1578`) only branches on `TypeScript`/`JavaScript` (NestJS/Express/Next) and `Python` (FastAPI). It never opens `.ex` files — `"Elixir"` is not even in the `SCANNABLE` set (`scan.py:1935`). The real HTTP surface (the Phoenix router's `/api/graphql`, webhooks, LiveView) is invisible. Because `endpoints`/`entry_modules` are also the upstream source for v0.8.0 flow skeletons, the full-coverage Key Flows feature silently degrades to "whatever the LLM finds by hand" on any Elixir backend.

The enrichment (LLM) layer corrected the prose, product/vendored classification, and flows — but it has **no lever** to override a service's `kind` or to add an HTTP edge it can see, so the top diagram stayed wrong even though the LLM clearly knew the truth (it correctly traced "Apollo → /api/graphql → Absinthe → resolver" in the Key Flows section).

---

## 2. Architecture principle

Every fix slots into the existing **deterministic-core + LLM-overlay** seam — no new architecture:

- **Deterministic where we can be exact** — make the scanner understand Elixir manifests and Phoenix routers (Slices 1 & 2). This fixes *all* Elixir/Phoenix repos with zero LLM cost.
- **LLM where exactness is structurally impossible** — give enrichment a correction lever for a service's true tier and for edges whose target is an env-injected base URL static analysis can't resolve (Slice 3). This generalizes to the long tail of languages the scanner will never hardcode (Rust/Actix, Crystal, Haskell, Phoenix-before-Slice-2).

Key leverage: the scanner's `endpoints` + `entry_modules` are the single upstream source for the System Map HTTP layer, the Critical Paths diagram, **and** the flow skeletons. The Phoenix router parser is therefore a data-source fix that lights up everything downstream at once.

**Degradation invariant (unchanged):** the deterministic no-enrichment golden body must stay byte-identical. Every Slice-3 change is enrichment-gated; every Slice-1/2 change alters deterministic *data*, which the golden fixture is regenerated against deliberately.

---

## 3. Slice 1 — Classification correctness + diagram width *(deterministic, low effort)*

### A. Token matching (kills the substring false-positive class)

Replace the raw substring loop in `_classify_service` (`scan.py:387-392`) with structured matching.

- For `package.json` / `deno.json` / `composer.json`: parse JSON, collect dependency **keys** from `dependencies`, `devDependencies`, `peerDependencies`, `optionalDependencies`, `require`, `require-dev`. Exact name match.
- For everything else (`mix.exs`, `go.mod`, `Cargo.toml`, `pyproject.toml`, `Gemfile`, `pom.xml`, gradle, …): tokenize the text on `[A-Za-z0-9_.@/-]+` and match hints as **exact tokens**. `:phoenix` → token `phoenix`; `export_gql_schema` → a single token that never matches `expo`.

Matcher helper `_hit(hint, tokens)`:
- hint ending `/` (scope prefix, e.g. `@nestjs/`, `@vue/`) → any token `startswith(hint)`.
- hint containing `/` (full module id, e.g. `github.com/gin-gonic/gin`) → exact token membership (the tokenizer keeps `/` and `.`, so the id stays one token).
- otherwise → exact token membership.

Then `found_frontend = [h for h in FRONTEND_FRAMEWORK_HINTS if _hit(h, tokens)]` (same for backend). The classify decision tree (lines 395-407) is unchanged.

**Known limitation (acceptable):** the non-JSON path tokenizes the whole file, not just the deps list, so a hint appearing in a module name or comment could still match. In practice these tokens rarely appear outside deps, and a stray `phoenix` hit still yields the correct "backend". True deps-list parsing is reserved for the JSON manifests where it is cheap.

### B. Elixir/BEAM backend hints

Add to `BACKEND_FRAMEWORK_HINTS`: `phoenix`, `plug`, `plug_cowboy`, `bandit`, `absinthe`, `ecto`, `ecto_sql`, `oban`, `broadway`. With token matching (A), a Phoenix `mix.exs` now yields `found_backend = [phoenix, absinthe, ecto_sql, oban, plug_cowboy, …]`, `found_frontend = []` → `kind: "backend"`. A pure Elixir library (no web/data hits) falls through to the existing "manifest but no hits → library" default — which is the correct classification for shared `elixir_common`-style packages. No special-case mix.exs fallback is added (the hints subsume it — KISS).

### C. Dependency-graph width

`.modgraph-frame` (`render.py:494-505`) breaks out of the 780px text column with a fixed `margin-left/right: -56px` → ~892px. The System Map's `.sysmap-frame` (`render.py:532-534`) uses a viewport-relative full-bleed (`width: min(94vw, 1200px)` + `margin-{left,right}: calc(50% - min(47vw, 600px))`) → ~1200px / 94vw. Port the sysmap formula onto `.modgraph-frame`, keeping the existing `@media (max-width: 880px)` collapse. Reclaims ~300px; intrinsically huge N×N matrices still scroll (accepted — "some scroll is fine").

---

## 4. Slice 2 — Phoenix router parser *(deterministic, medium-plus effort)*

### Wiring

- Add `"Elixir"` to `SCANNABLE` (`scan.py:1935`) so `.ex` files are opened by the topology loop. (Pre-req: confirm `detect_language` maps `.ex`/`.exs` → `"Elixir"`; add to `LANGUAGES` if absent.)
- Add an `elif language == "Elixir":` branch in `_scan_endpoints_file` that runs the router parser only on files whose path ends `router.ex` (or matches `*_web/router.ex`). Non-router `.ex` files emit nothing.

### Constructs parsed (from `router.ex`)

| Construct | Emitted | Framework label |
|---|---|---|
| `get/post/put/patch/delete/head/options "/path", Ctrl, :action` | one endpoint | `Phoenix` |
| `forward "/path", SomePlug` | one endpoint | `Absinthe` if plug name contains `Absinthe`, else `Phoenix` |
| `live "/path", Module[, :action]` | one endpoint | `Phoenix LiveView` |
| `scope "/prefix"[, Module] do … end` | path-prefix composition onto contained routes; **nesting-aware** (a stack of active prefixes) | — |
| `resources "/path", Ctrl [, opts] [do … end]` | **full RESTful expansion** (see below) | `Phoenix` |

### `resources` expansion (no deferral)

Base expansion of `resources "/users", UserController`:

| Method | Path | Action |
|---|---|---|
| GET | `/users` | index |
| GET | `/users/new` | new |
| POST | `/users` | create |
| GET | `/users/:id` | show |
| GET | `/users/:id/edit` | edit |
| PATCH | `/users/:id` | update |
| PUT | `/users/:id` | update |
| DELETE | `/users/:id` | delete |

Options handled:
- `only: [:index, :show]` → keep only those actions.
- `except: [:delete]` → drop those actions.
- `param: "slug"` → `:id` segment becomes `:slug`.
- `singleton: true` → drop `index`; drop the `:id` segment (paths become `/account`, `/account/edit`, etc.).
- **Nested** `resources "/users", … do resources "/posts", … end` → child paths prefixed `/users/:user_id/posts/…` (parent path + `:<singular>_id`, naive singularization = strip a trailing `s`). One level of nesting supported.

**Log-don't-drop (no silent caps):** anything the parser cannot cleanly expand — 2+ levels of nesting, exotic options (`as:`, `name:`, custom controllers per action) — emits the **base route(s)** it can and logs to stderr:
`[phoenix_router] partial expansion of resources "/x" (<reason>)`. Mirrors the never-raise + report-what-was-dropped contract of the `astgrep_*` bridges. The parser is pure line/regex parsing; it returns `[]` on any internal failure and never raises.

---

## 5. Slice 3 — Enrichment overrides *(validator + render + SKILL.md; replaces proposed Bug D)*

Rejected the originally-proposed render-side language→tier heuristic ("Bug D"): a language backstop can override a *correct* classification (a Python build tool that is genuinely frontend; an Elixir LiveView app that is arguably frontend-ish). Language ≠ tier. The enrichment override is strictly more general and matches the existing product/vendored reclassification pattern.

### Schema additions (both optional — absence renders identically; golden body safe)

Inside the existing `classification` block (array form, consistent with `products`/`vendored`):

```jsonc
"services": [
  { "service_id": "backend", "kind": "backend",
    "why": "Phoenix/Absinthe API; mix.exs heuristic mislabeled it frontend via :export_gql_schema" }
]
```

New top-level array (parallel to `flows`):

```jsonc
"http_edges": [
  { "source_service": "brevity-mobile-app-dev", "target_service": "backend",
    "method": "POST", "path": "/api/graphql",
    "why": "Apollo httpLink targets the Absinthe endpoint; traced in flows" }
]
```

- `kind` ∈ `{frontend, backend, library, service}` (the scanner's kind vocabulary).
- `service_id` references a `services[].id` from the codemap. `source_service`/`target_service` likewise.

### Validator (`validate_enrichment.py`)

- Accept `classification.services` and top-level `http_edges` as optional. Absence is valid.
- `classification.services[].kind` must be in the kind set, else **error**. Missing `service_id`/`kind` → **error**.
- `http_edges[]` require `source_service`, `target_service` (and a `path`); missing → **error**.
- Unknown `service_id` / unknown edge endpoint (not in the codemap's service id set) → **warning, not error**, reusing the warn-don't-fail channel built for `skeleton_id` (the CLI already loads the codemap via `--codemap`; extend it to pass the service-id set). This keeps the LLM's good-faith corrections non-fatal while surfacing typos.

### Render (`render.py`)

A pure `_apply_enrichment_overrides(data, enrichment) -> data` at the **top of `render_document`** (pure data transform, no filesystem — unlike the citation-drop safety net, which stays in `main()`):

1. **Kind override:** build `{service_id: kind}` from `classification.services`; return a new `data` whose `services[]` carry the corrected `kind`. Applied once, so *every* consumer (System Map bands, Topology v2 chips/colors) sees the corrected tier automatically. Immutable: new list, no mutation of the input.
2. **Edge injection:** append each `http_edges` entry to `data["http_topology"]["edges"]` with `"inferred": True` and `"weight": 1`. Deterministic edges keep their existing shape (no `inferred` key → treated as solid).

**Visual treatment (honesty about provenance):** inferred edges render **dashed + reduced opacity** in the System Map HTTP layer, plus a one-line legend note ("dashed = inferred by AI"). Solid = the scanner proved it; dashed = the LLM asserts it. This preserves the deterministic/LLM line the tool's credibility rests on. The existing `data-kind="http"` layer-toggle still applies (inferred edges are HTTP edges, toggled with the rest).

### SKILL.md

Step 1.5 instructions teach the LLM:
- It may override a service's band with `classification.services[]` (`service_id`, `kind`, `why`) when the deterministic classification is wrong — typically a backend in a language the scanner doesn't parse (Elixir, Rust, etc.).
- It may assert a cross-service HTTP edge with `http_edges[]` when it has *read* the call (e.g. an Apollo `httpLink` whose target is an env var) — these render dashed/low-confidence; only assert what was actually traced.

---

## 6. Data shapes (reference)

Deterministic HTTP edge (existing, `scan.py:2010-2019`):
```python
{"source_service": str, "target_service": str, "method": str, "path": str, "weight": int}
```
Inferred HTTP edge (added at render time from enrichment):
```python
{"source_service": str, "target_service": str, "method": str, "path": str, "weight": 1, "inferred": True}
```
Endpoint (existing, emitted by `_scan_endpoints_file`):
```python
{"service": str|None, "module": str|None, "file": str, "framework": str, "method": str, "path": str}
```
Service (existing) carries a stable `id` used as the override key.

---

## 7. Testing strategy (TDD per slice)

- **Slice 1A:** `_classify_service` / token matcher — the `expo`-inside-`:export_gql_schema` case as an explicit regression test; `package.json` key parsing; `@scope/` and `github.com/...` hint forms; build-tool-only frontend.
- **Slice 1B:** a Phoenix-shaped `mix.exs` string → `backend`; a pure Elixir lib → `library`.
- **Slice 1C:** render assertion that `.modgraph-frame` CSS carries the viewport-relative breakout (or a snapshot of the rule).
- **Slice 2:** Phoenix router parser — verb macros, `forward` (GraphQL), `live`, `scope` prefix composition + nesting, full `resources` expansion incl. `only`/`except`/`param`/`singleton`/one-level nesting, and the log-don't-drop path for deep nesting. Pure-Python parser → string fixtures, no binary dependency, no skip guard.
- **Slice 3 validator:** optional `classification.services` + `http_edges` accepted; bad kind → error; unknown service_id → warning.
- **Slice 3 render:** kind override flips a service's System Map band; injected edge appears dashed/inferred; no-enrichment body unchanged.
- Every slice ends green on the full suite (`python3 -m unittest discover -s tests -t . -q`). Golden no-enrichment body stays byte-identical; the deterministic golden fixture is regenerated where Slice 1/2 changes its data.

---

## 8. Sequencing & versioning

1. **Slice 1** (token matching + Elixir hints + width) — fixes the visible brevity mislabel and reclaims diagram width. Smallest, highest immediate payoff.
2. **Slice 2** (Phoenix router parser) — lights up the HTTP layer **and** flow-skeleton coverage for all Elixir/Phoenix backends.
3. **Slice 3** (enrichment overrides) — the general long-tail lever + the dashed cross-service arrow that subsumes the unsolvable deterministic client-edge problem (C.2).

Each slice is independently shippable and independently green. Version bumps to **0.9.0** in a dedicated final commit (pre-1.0 MINOR; mechanical, no phase transition).

---

## 9. Out of scope / known limitations

- Deterministic Apollo/GraphQL **client** edge resolution (env-var base URLs) — intentionally *not* attempted; the LLM `http_edges` lever is the answer instead.
- `resources` nesting beyond one level and exotic options — base routes emitted + logged, not fully expanded.
- Non-JSON manifest deps parsed by whole-file tokenization, not true deps-list parsing (acceptable; see §3A).
- Other BEAM/long-tail backend frameworks not in the hint list — covered by the Slice-3 enrichment `kind` override rather than by expanding the hardcoded list indefinitely.
