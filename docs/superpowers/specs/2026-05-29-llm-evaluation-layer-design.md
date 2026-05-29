# LLM Evaluation Layer — Design

**Date:** 2026-05-29
**Status:** Approved design, pending implementation plan
**Component:** `smokeyp-codebase-mapper` plugin (`plugin/skills/map-repo`)

## Problem

The report's "what this codebase is" understanding is derived from the
project README's first paragraph, and per-module descriptions from each
module's README/`package.json`. This fails badly on real codebases:

- **READMEs lie or mislead.** The motivating case, `brevity`, has a root
  README that is a *Gantt chart and KPI plan for an unbuilt generation
  pipeline* — it describes a system that does not exist yet and says
  nothing about the Elixir/Phoenix backend + React Native app that
  actually run. Giving it prominence actively misinforms the reader.
- **The deterministic scanner is language- and structure-blind.** Import
  parsing supports only Python/JS/TS/Go, so `brevity`'s Elixir product
  yields a near-empty module-dependency matrix ("2 import relationships"
  for an 800k-LOC repo). Workspace packages that import each other by
  package name (`@scope/pkg`) are treated as external and dropped.
- **Vendored/reference code is indistinguishable from product code.** The
  top "module" in the `brevity` report is `google_ads-master/lib/google`
  at 151k LOC — vendored Google Ads code, not the product. Third-party
  framework clones (g.frame) fill the module list and bury the real app.
- **No notion of user/execution flows.** The report shows structure
  (matrix), services (topology), request anatomy (critical paths), and
  storage (lineage), but never the end-to-end *stories* the code tells
  (signup, a domain state machine, a scheduled job, a data pipeline).

These are the deterministic scanner hitting its ceiling. The fix is a
semantic layer that reads the actual code.

## Key insight

The plugin runs **inside Claude Code** — the LLM is already in the loop.
"Have the LLM evaluate the codebase" does not mean adding an API key to
`scan.py`. It means the `map-repo` *skill* performs a semantic pass
(Claude reading real code) that writes structured fields consumed by the
renderer. The deterministic scripts stay offline-capable; `render.py`
stays a pure function of its inputs; the enrichment is additive.

## Decisions (locked)

| Decision | Choice |
|---|---|
| How Claude evaluates a repo it can't fully read | **Bounded evidence pack + on-demand reads** — `scan.py` pre-selects a budget-capped slice; Claude may pull a few more files within a read budget |
| Summary scope | **LLM authors the prominent Overview *and* per-product-module descriptions**; README demoted to a small aside |
| Flows | **New "Key flows" section, complementary** to the deterministic critical-paths hero (which stays as-is) |
| Gating | **On by default; `--no-llm` / `--fast` to skip**; `render.py` degrades gracefully when enrichment is absent |
| Data flow | **Sidecar enrichment file** — deterministic `codemap.json` untouched; Claude writes a separate `codemap.enrichment.json`; `render.py` merges via optional `--enrichment` |
| Flow rendering | **Hybrid: SVG spine (numbered nodes + connectors) with HTML step text** positioned alongside |

## Architecture & data flow

One new step is added to the skill's pipeline, between scan and render.
The deterministic scripts and the deterministic `codemap.json` are
unchanged.

```
scan.py ──► codemap.json            (deterministic, unchanged, reproducible)
        └─► codemap.evidence.json   (NEW: bounded high-signal slice for Claude)
                    │
            [Claude, in SKILL Step 1.5]
            reads evidence pack (+ ≤ read-budget on-demand files)
                    │
                    ▼
        codemap.enrichment.json     (NEW: schema'd overview + classification + flows)
                    │
render.py --in codemap.json [--enrichment codemap.enrichment.json]
        ──► codemap.html ──► codemap.pdf
```

**Invariants preserved:**
- `codemap.json` remains byte-reproducible for a given repo + depth.
- `render.py` remains a pure function of its inputs; no network, no JS
  runtime in output; works with or without `--enrichment`.
- Claude only ever *writes a new small file*; it never edits the large
  `codemap.json`.

## Component: Evidence pack (`scan.py` addition)

`scan.py` emits a second artifact, `codemap.evidence.json`, alongside
`codemap.json`. It is a deterministic, budget-capped slice that lets
Claude evaluate without reading the whole repo.

**Contents:**
- The module list: paths, LOC, languages, file counts, and the current
  deterministic description guess (so Claude can improve/replace it).
- **Curated file contents**, each truncated (target ~6 KB / ~200 lines),
  selected by deterministic heuristics:
  - All detected entry points.
  - Manifests/configs: `package.json` (root + per service), `mix.exs`,
    `go.mod`, `pyproject.toml`, `requirements.txt`, `docker-compose.yml`
    / `compose.yml`, `.env.example`, `Gemfile`, `pom.xml`,
    `build.gradle`, `Cargo.toml`.
  - Root README + per-module READMEs.
  - Router / schema / route files, found via `http_topology` and by
    filename patterns (`router.ex`, `urls.py`, `routes.rb`, `schema.*`,
    `*.graphql`, `app/api/**/route.ts`).
  - A representative file (entry/index/largest) from each top-N module by
    LOC and by module-graph centrality.
  - Architecture docs if present (`docs/ARCHITECTURE*`, `CODEBASE_MAP*`).
- A pointer to the deterministic signals already in `codemap.json`
  (module graph, http topology, data lineage, deps) — Claude references
  these rather than re-deriving them.
- A **budget** (target ~200 KB of file content; exact cap a constant)
  with an explicit "omitted / truncated" manifest so Claude knows the
  coverage limits of what it was handed.

Selection is deterministic so the evidence pack is reproducible.

## Component: Enrichment schema (`codemap.enrichment.json`)

Versioned data contract. Shape:

```jsonc
{
  "schema_version": 1,
  "generated_by": "claude (map-repo LLM evaluation)",
  "target": "<resolved repo path>",
  "overview": {
    "what_it_is": "1–2 sentences",
    "what_it_does": "short paragraph",
    "how_it_works": "short paragraph, architecture in plain English",
    "primary_stack": ["Elixir/Phoenix", "React Native"],
    "confidence": "high | medium | low",
    "caveats": ["root README is a roadmap, not a description", "..."]
  },
  "classification": {
    "products": [
      { "module_id": "...", "role": "backend|frontend|worker|lib|...", "why": "..." }
    ],
    "vendored": [
      { "module_id": "...", "kind": "dependency|reference|vendored-framework",
        "source": "github.com/...", "why": "..." }
    ]
  },
  "module_descriptions": [
    { "module_id": "...", "description": "...", "is_product": true }
  ],
  "flows": [
    {
      "name": "User signup",
      "kind": "request|background|scheduled|state-machine|pipeline|bootstrap",
      "trigger": "GraphQL mutation signUp",
      "narration": "one line",
      "steps": [
        { "label": "resolver.sign_up/2",
          "file": "backend/lib/brevity_web/graphql/resolver.ex",
          "symbol": "sign_up/2", "line": 28, "note": "validates + delegates" }
      ],
      "terminates": "auth token returned to client"
    }
  ]
}
```

`line` is optional; `file` and `symbol` are required on every step. Flow
count target: ~3 at `--depth medium`, ~6 at `--depth full`.

## Component: Skill orchestration (`SKILL.md` new Step 1.5)

After scan, before render, unless `--no-llm` is set and only when running
inside Claude Code:

1. Read `codemap.evidence.json`.
2. Optionally `Read`/`Grep` up to a **read budget** (~15–25 additional
   files) to confirm flows and citations.
3. **Classify product vs vendored.** Vendored signals: path under
   `vendor/` or `node_modules/`; directory names like `*-master` /
   `*-develop` / `*-main` (git-archive clones); a third-party
   `LICENSE` or repo URL in `package.json`; declared as a path
   dependency in a manifest; package name scoped to a third party.
   Product signals: referenced by the app's own manifests/imports; under
   a workspace root (`apps/*`, `packages/*`); contains the app's domain
   code. Combine signals with judgment.
4. **Author** the overview, per-product-module descriptions, and flows.
   **Every flow step must cite a real `file:symbol` that Claude actually
   read** — no uncited steps. This is the anti-hallucination rule.
5. **Write** `codemap.enrichment.json` and validate it (schema + cited
   files exist) before rendering.

The existing guidance ("do not re-implement scanning in Claude — the
scripts are deterministic and faster") is preserved; the LLM step is the
explicit exception that does the semantic work the scripts cannot.

## Component: Render changes (`render.py`)

- New optional `--enrichment PATH` argument. Load if present and valid;
  otherwise render exactly today's deterministic-only report.
- **Overview section**, placed immediately after the cover (before
  Languages): the prominent "what this is" narrative — `what_it_is`
  headline, `what_it_does` / `how_it_works` prose, a compact
  product-vs-vendored chip map, and confidence/caveats. This becomes the
  document's narrative opener.
- **README demotion**: the existing README extract becomes a small "What
  the README says" aside, carrying the LLM's caveat when the README is
  misleading.
- **Module cards**: when enrichment is present, product modules use the
  LLM descriptions and sort first; vendored modules get a "vendored"
  badge, dimmed treatment, and group at the bottom (optionally
  collapsed) so they stop dominating the list.
- **Key flows section** (placed after critical-paths): one card per flow,
  rendered as a **hybrid** — an SVG spine (numbered nodes + connecting
  line) with HTML step text (`label`, `file:symbol` in mono, `note`)
  positioned alongside, plus the `kind` chip, `trigger`, `narration`, and
  `terminates`. Print-tested so flow cards paginate at step boundaries.

## Gating & degradation

- On by default; `--no-llm` (alias `--fast`) skips the LLM step and the
  evidence-pack consumption.
- `render.py` always produces a valid report without `--enrichment`, so
  the three scripts remain standalone and offline outside Claude Code.

## Validation & failure modes

- A small `validate_enrichment.py` (with unit tests) checks the JSON
  against the schema and verifies that every cited `file` path exists in
  the target repo. Flows with broken citations are dropped (or flagged).
- Invalid or missing enrichment ⇒ graceful deterministic-only render.
- LLM unavailable (scripts run outside Claude Code) ⇒ no enrichment file
  ⇒ deterministic-only.
- Cost/time on huge repos is bounded by the evidence-pack budget and the
  read budget, plus the `--no-llm` escape hatch.

## Testing

- **`brevity` (acceptance / stress test):** overview correctly
  identifies the Elixir/Phoenix backend + React Native app; g.frame and
  `google_ads-master` flagged as vendored and demoted; ≥3 flows emitted,
  every step citing a file that exists.
- **`fittalk` (regression):** clean monorepo still renders well; product
  classification doesn't mis-flag real modules.
- **Degradation test:** rendering without `--enrichment` produces output
  byte-identical to today.
- **Citation test:** every flow step's `file` exists in the repo.
- **Schema validator unit tests:** accepts valid, rejects malformed.

## Non-goals (YAGNI)

- No generic AST-based flow extractor.
- No network access added to any script.
- `render.py` never calls an LLM.
- No auto-merge of enrichment back into `codemap.json` (sidecar only).
- No support for the LLM step outside Claude Code — it simply degrades to
  the deterministic report.
- Not fixing Elixir / workspace-package *import parsing* here (a separate
  deterministic-scanner enhancement); the LLM layer mitigates the
  symptom by describing what the matrix cannot show.

## Open follow-ups (out of scope, noted)

- Deterministic Elixir import parsing and `@scope/pkg` workspace-import
  resolution, to make the dependency matrix non-empty for those stacks.
- Optional caching of enrichment keyed by repo content hash, to avoid
  re-running the LLM pass on an unchanged repo.
