# smokeyp-codebase-mapper

> A Claude Code plugin that scans any repository and produces a polished HTML or PDF architecture report — studio-grade, self-contained, printable (light or dark), and beginner-friendly.

<p align="center">
  <img src="assets/gpt-smokeyp-mapper-v1.webp" alt="smokeyp-codebase-mapper — architecture report with a System Map hero and four detail diagrams" width="900">
</p>

`/smokeyp-codebase-mapper:map-repo` walks a codebase, detects services and modules (monorepo-aware), parses imports across multiple languages, extracts HTTP endpoint declarations and outbound client calls, infers ORM/data-store usage, and renders everything as a single self-contained HTML file with **five architecture diagrams** — a *System Map* hero plus four detail figures. Every diagram is deterministic SVG with inlined fonts and styles and **no network dependency**, so it renders identically offline and in print. The System Map and Service Topology layer on optional, dependency-free *focus* interactions — click a service to trace just its connections — that **degrade to the complete static figure** when JavaScript is off or on paper, so nothing is lost in the PDF or behind an airgap. With Chrome installed, it also prints to PDF. Built for client deliverables, onboarding docs, and architectural audits — explanatory throughout, no jargon left unexplained.

## What's in a report

- **Masthead** — SmokeyP Labs masthead image, project name, and a metadata readout strip (scan date, primary language, file count, LOC, language count, module count)
- **Overview & Key flows** *(LLM evaluation, on by default)* — an accurate, code-derived summary of what the project actually is and does, vendored/reference code flagged and de-emphasised (so it stops dominating the module list), per-module descriptions for product code, and several end-to-end execution flows where every step cites a real `file:symbol`. Derived by reading the source, not the README. Pass `--no-llm` for a fast deterministic-only report.
- **README extract** — a clean first-paragraph blockquote (demoted to a small secondary aside when the LLM overview is present, since a README is often a roadmap rather than a description)
- **Languages** — stacked share bar + sortable table with file counts and lines
- **Top-level modules** — each detected module (recursive for monorepos) as a card with description (auto-detected from README, `package.json`, or `__init__.py` docstring)
- **System Map** *(hero — "How the system fits together")* — the opening picture of the whole system: every product service and its modules laid out in tiers (frontend / backend / data), with code imports, HTTP calls, and data-store writes drawn between them. HTTP routes bundle into a per-target-service lane (and cap, overflow pointing to the topology) so a busy system stays legible; the map renders at native size rather than ballooning. Hover or click a module to trace its imports, or click a service box to isolate just its HTTP flow — and **per-service facet small-multiples** below show each service in isolation. Degrades to a full static figure in print.
- **Module dependency matrix** *(diagram 1 — "How the modules connect")* — a Bertin-style matrix: rows are importing modules, columns are imported modules, cell shading shows import weight. Modules are ordered by service so clean architectures show a block-diagonal pattern at a glance.
- **Service topology** *(diagram 2 — "How the services talk to each other")* — a C4-style layered diagram of service cards (kind-coloured, kind-chipped) with weighted HTTP call edges between them. Built from `@Controller` / `@router.get` / `app.METHOD` declarations matched against `axios.get` / `fetch` / `httpx.post` / custom client calls.
- **Critical paths** *(diagram 3 — "What happens when a request flows through")* — a four-column swimlane tracing every entry-point module from its callers → entry module → key dependencies → data store, so you can read each request's path end to end.
- **Data lineage** *(diagram 4 — "Where each service stores its data")* — a Sankey with cylinder store glyphs: services on the left, data stores on the right (Postgres, Redis, Mongo, S3, Supabase, Firebase, etc.), ribbon thickness scaled by model count. Detected from ORM declarations (Prisma, SQLAlchemy, Mongoose, Django ORM, ActiveRecord, JPA) plus `docker-compose.yml` / `.env` evidence.
- **Architect observations + small-multiples** — under each diagram, a short list of data-derived observations (highest fan-out module, network hub, unmodeled store, etc.) and a *bento* of supporting small-multiples (composition donut, hottest edges, framework breakdown, hot models) that carry the long-tail detail the hero compresses.
- **Entry points** — `main.*`, `index.*`, `cmd/*/main.go`, `bin/*` and friends
- **External dependencies** — pulled from `package.json`, `requirements.txt`, `pyproject.toml`, `go.mod`, `Cargo.toml`, `Gemfile`, `composer.json`, `pom.xml`, `build.gradle`
- **Directory tree** — collapsible on screen, fully expanded in print
- **Glossary** — plain-English definitions of every term used in the report, filtered to what's actually present in the scan

## Install

### Manually (current method)

```bash
git clone https://github.com/SmokeyPete/smokeyp-codebase-mapper.git ~/.claude/plugins/smokeyp-codebase-mapper
```

Then enable the plugin in Claude Code settings.

### Via marketplace (once published)

```
/plugin install smokeyp-codebase-mapper
```

> **Note:** Marketplace listing is pending. Use the manual install above for now.

## Usage

**Invocation is explicit-only.** The plugin activates only when you type the slash command — natural-language phrases like "map this repo" will *not* trigger it. This is intentional: nothing happens to your codebase until you ask for it directly.

```
/smokeyp-codebase-mapper:map-repo
```

### Arguments

```
/smokeyp-codebase-mapper:map-repo [path?] [--format html|pdf|both] [--depth shallow|medium|full] [--out PATH]
```

| Flag | Default | Description |
|---|---|---|
| `path` | current directory | Path to scan |
| `--format` | `both` | Output format: `html`, `pdf`, or `both` |
| `--depth` | `medium` | `shallow` = 2-level tree, 10 module cards, 30 graph nodes (single-glance summary). `medium` *(default)* = 4-level tree, 25 cards, 80 graph nodes (right for most monorepos). `full` = everything, no truncation. |
| `--theme` | `light` | `light` *(default)* = warm-cream "Workshop Light", print/PDF-safe. `dark` = near-black on-screen variant (ink-heavy in PDF; prefer with `--format html`). Same design, swapped palette. |
| `--out` | `<path>/.codemap/` | Output directory |
| `--no-llm` | off (evaluation on) | Skip the LLM evaluation step (overview, classification, flows); produce the deterministic-only report. Alias: `--fast` |

### Examples

```text
# Map the current directory; produce both HTML and PDF in ./.codemap/
/smokeyp-codebase-mapper:map-repo

# Map a specific project, full depth, HTML only
/smokeyp-codebase-mapper:map-repo ~/code/my-app --format html --depth full

# Custom output path
/smokeyp-codebase-mapper:map-repo . --out ./docs/architecture
```

## Requirements

- **Python 3.10+** — scanner and renderer are stdlib-only
- **Chrome, Chromium, Edge, or Brave** — required *only* for PDF output. Skip if you only need HTML.

Tested on macOS, Linux, and Windows/WSL2.

## Output

Two files (or one, with `--format html|pdf`):

```
<out>/codemap.json    # raw data model — also useful as input to other tools
<out>/codemap.html    # self-contained HTML report
<out>/codemap.pdf     # printable PDF
```

The HTML has no external dependencies — fonts, styles, and SVG icons are inlined. You can email it, attach it, host it anywhere, or open it offline.

## The diagrams

The diagrams are the marquee feature. Each answers a different question, and together they tell the full story of a codebase: *how it fits together, what's wired to what, what happens at runtime, and where the data lives.* All are deterministic SVG with the layout computed at render time and baked into the file — nothing loads from the network. The four detail figures are pure static SVG; the **System Map** and **Service Topology** add an optional layer of dependency-free *focus* interactivity (hover or click to isolate a service or flow) that falls back to the complete static figure when JavaScript is off or in print. That's the deliberate trade: a report you can email, print, or open behind an airgap and trust to look identical everywhere — interactive where it helps on screen, complete and static on paper.

### System Map — the hero ("How the system fits together")

A layered-bands overview that opens the architecture section: product services and their modules stacked in tiers (frontend → backend → data), with three kinds of edge drawn between them — code imports, HTTP calls, and data-store writes. HTTP routes funnel through a **per-target-service gateway lane** (and a cap, with overflow pointing to the topology) so the cross-tier traffic reads as a few bundles instead of a hairball, and the map renders at its native size rather than scaling up to fill the page. On screen it's interactive: hover or click a module to trace its imports, click a service box to isolate just that service's HTTP flow (callers and callees light up, the rest fades), and toggle layers (imports / HTTP / stores / orphans). Below it, **per-service facet small-multiples** show each service on its own — same trace-on-click behaviour, one card per service. With JavaScript off or in print it degrades to the full static map. Vendored / reference code is detected and excluded so the map shows what the team actually built.

### Diagram 1 — Module dependency matrix ("How the modules connect")

A Bertin-style dependency matrix. Rows are importing modules, columns are imported modules; each filled cell is an `imports from` relationship, shaded by the number of underlying file-level imports. Modules are ordered by service, so a cleanly-separated architecture shows a **block-diagonal pattern** — dense blocks on the diagonal (intra-service coupling), sparse off-diagonal cells (cross-service coupling). Within a service block, faint dashed dividers separate sub-domains. The matrix scales to ~60 modules without the hairball problem a node-link graph hits at that size.

### Diagram 2 — Service topology ("How the services talk to each other")

A C4-style layered diagram. Each card is an independently-deployable service (coloured and chipped by kind — frontend, backend, worker); each edge is the count of distinct HTTP routes one service calls on another, drawn with an orthogonal connector and a weight pill (lifted *above* its connector so pills don't pile up on the lines at junctions). Tiers run left-to-right in call direction (roots like frontends on the left, leaf workers on the right). This is the relationship that wouldn't show up at all in an import scan — `mobile → backend → AI worker` over HTTP, not via shared code. On screen, click a service card to isolate every flow touching it (or click a single flow) and the rest fades; in print it falls back to the full static figure. Renders only when more than one service is detected.

### Diagram 3 — Critical paths ("What happens when a request flows through")

A four-column swimlane with one row per entry-point module. Each row traces a request left to right: **callers → entry module → key dependencies → data store**, joining five sources (entry modules, endpoints, HTTP edges, import edges, and data-lineage edges) into a single readable path. Where the matrix shows *structure* and the topology shows *services*, this shows *execution* — what a request actually touches on its way through.

### Diagram 4 — Data lineage ("Where each service stores its data")

A Sankey with cylinder store glyphs: services on the left, data stores on the right (Postgres, Redis, Mongo, S3, Supabase, Firebase, Elasticsearch, Kafka, etc.), with each store drawn in its brand colour. Ribbon thickness scales (log) with the count of distinct data models each service touches in a store. Stores detected from config but not referenced by any ORM model still render, at reduced opacity, so nothing in the infrastructure goes silently unrepresented. Detected from ORM declarations plus `docker-compose.yml` / `.env*` evidence.

### Reading them in print

On paper there's nothing to learn — the System Map's and Topology's focus interactions simply don't apply, and every diagram falls back to its complete static figure. The diagram sections print on **Letter landscape** pages (the reading sections stay portrait), each diagram centred and height-capped so its heading and figure share one page. Because the figures are SVG, text stays crisp at any scale — it's vector all the way to paper.

### Framework coverage

#### HTTP endpoint detection (Diagram 2 — server side)

| Stack | Patterns detected |
|---|---|
| **NestJS** | `@Controller('prefix')` + `@Get/@Post/@Put/@Patch/@Delete/@All/@Head/@Options(...)`. Honors `setGlobalPrefix('api/v1')` from `main.ts`. |
| **Express / Koa / Fastify / Hono** | `app.METHOD('/path', ...)`, `router.METHOD('/path', ...)`. Detects single-prefix `app.use('/api', ...)` mounts. |
| **FastAPI** | `@app.METHOD('/path')`, `@router.METHOD('/path')`, `APIRouter(prefix=...)`, `include_router(..., prefix=...)`. |
| **Flask** | `@app.route('/path', methods=['GET','POST'])`, blueprint `.route(...)`. |
| **Django** | `urlpatterns = [path('foo/', ...), re_path(r'^...$', ...), url(...)]` in `urls.py`. |
| **Rails** | `routes.rb` — `get '/path'`, `post`, `resources :users`, `resource :session`, etc. |
| **Spring Boot** | `@RestController` + `@RequestMapping('/prefix')` + `@GetMapping/@PostMapping/@PutMapping/@PatchMapping/@DeleteMapping`. |
| **Laravel** | `Route::get('/path', ...)`, `Route::post`, `Route::resource`, `Route::apiResource`. |
| **Go** | `http.HandleFunc(...)` (stdlib), `r.GET/POST/...` (gin / echo / chi / gorilla/mux). |
| **Next.js** | File-based routing for both Pages Router (`pages/api/*.ts`) and App Router (`app/api/.../route.ts` with `export GET/POST/...`). |

#### HTTP client detection (Diagram 2 — caller side)

| Stack | Patterns detected |
|---|---|
| **JS/TS** | `axios.METHOD('/path')` and `axios({url, method})`; `fetch('/path', {method})`; `ky/got.METHOD('/path')`; `$.get/$.post/$.ajax(...)`; `this.<x>Client/Service/Api/Http.METHOD(...)`; bare-function `post('/path')` when imported from a local client module. |
| **Python** | `requests.METHOD('/path')`, `httpx.METHOD('/path')`, `urllib.request.urlopen('/path')`, `aiohttp` session.METHOD. |
| **Go** | `http.Get/Post/Head/Delete/Put/Patch/NewRequest('/path')`, custom-client `.Get/.Post/...` variants. |
| **Ruby** | `Net::HTTP.METHOD(URI('/path'))`, `HTTParty.METHOD('/path')`, `Faraday.METHOD('/path')`. |
| **Java/Kotlin** | `restTemplate.METHOD('/path')`, `webClient.METHOD('/path')`, `httpClient.METHOD('/path')`. |

Client URLs are matched against endpoints by longest-prefix, with each service's detected global prefix (e.g. `/api/v1`) also tried as a candidate — bridges the common pattern of `axios.create({ baseURL: '/api/v1' })` plus relative-path calls.

#### Import edge detection (Diagram 1)

| Language | How edges are inferred |
|---|---|
| Python | `import X` / `from X import …` — first segment matched against detected module names (scoped to the importing file's service). |
| JavaScript / TypeScript | `import … from "./path"`, `require("./path")`, dynamic `import("./path")` — relative paths resolved against module roots. Bare specifiers (npm packages) are treated as external. |
| Go | `import "<module-path>/internal/..."` — internal paths derived from the `module` directive in `go.mod`. |

Languages outside that set still appear as nodes (sized + colored correctly) but no import arrows are drawn for them. The diagram annotates which detected languages were skipped so you know what's missing rather than guessing.

#### Data lineage (Diagram 4)

| ORM | Patterns detected | Default store guess |
|---|---|---|
| **Prisma** | `this.prisma.<model>.X` calls + `model Foo {}` declarations in `schema.prisma` | Postgres |
| **SQLAlchemy** | `class Foo(Base)` declarations + `session.query(Foo)` / `select(Foo)` | Postgres |
| **Mongoose** | `mongoose.model('Foo', ...)` | MongoDB |
| **Django ORM** | `class Foo(models.Model)` + `Foo.objects.X` | Postgres |
| **ActiveRecord** | `class Foo < ApplicationRecord` | Postgres |
| **Spring Data JPA** | `@Entity class Foo` | Postgres |

Stores are detected separately from `docker-compose.yml`, `compose.yml`, `.env` / `.env.example` files (project root + per-service). When an ORM model references a store kind that wasn't found in any config file, the diagram synthesizes a placeholder store entry (labeled "inferred from ORM usage") so the relationship still shows up.

### Module aggregation

File-level imports are rolled up to module-level edges. Internal imports within the same module become self-loops and are dropped. The reason: a 1,000-file repo would be unreadable spaghetti at file granularity, while ~10–80 module nodes is the architecture diagram you actually want. Monorepos recursively descend through nested source roots (`apps/<app>/src/<module>`, `services/<svc>/src/<feature>`) so the visible modules match what contributors actually work on, not just the outermost container directories.

### Display caps

- **`--depth shallow`** — 10 module cards, 30 modules in the diagrams. Best for very large repos when you want a single-glance summary.
- **`--depth medium`** *(default)* — 25 module cards, 80 modules in the diagrams. Right for most monorepos and mid-size projects.
- **`--depth full`** — every detected module, every dependency, full tree.

In all tiers, the diagram cap is intentionally larger than the cards cap; readers benefit from seeing more modules in a figure than they'd want to read as text cards.

### What the diagrams don't do

- They don't trace runtime call graphs (no dynamic analysis — only static scanning).
- They don't follow TypeScript path aliases (`@/foo` from `tsconfig.paths`) or webpack/Vite resolve overrides — only literal relative paths.
- They don't follow Express `app.use('/prefix', router)` mounts across files — only single-file dominant-prefix detection.
- They infer layout from static structure only — service tiers in the topology come from call direction, not from any declared architecture; a misleading call pattern can produce a misleading tier.
- They use pragmatic regex, not full AST parsing, so unusual routing setups or import statements inside comments/strings can produce false positives or misses in rare cases.
- They don't resolve external-API client calls into a "third-party services" view (yet — see roadmap).

## How it works

The plugin is two skills:

1. **`map-repo`** — the slash command. Orchestrates a three-step pipeline: `scan.py` → `render.py` → `to-pdf.sh`. The skill itself doesn't do parsing; it shells out to the scripts.
2. **`design-system`** — a knowledge-only skill that documents the visual standard (palette, typography, spacing, component patterns). Loaded when the user wants to customize the report's look.

The scanner is intentionally simple. Language detection is by file extension; dependency, import, HTTP endpoint/client, and ORM model parsing are all light regex. This keeps the plugin Python-stdlib-only and means it just works without `pip install`. The trade-off is accepted explicitly: pragmatic patterns over heavy AST infrastructure. Anything the scanner misses gets surfaced in the report as a "could not detect" note rather than silently dropped.

Monorepo detection runs as a discovery pass: any top-level directory that has its own dependency manifest (or its own conventional source root) becomes a *service*. Modules are then detected recursively *inside* each service, so `Back-End-FitTalk/src/modules/auth/` is its own module rather than being collapsed into a single bubble for the whole backend app.

Every diagram is rendered to SVG by `render.py` at report time — no client-side runtime, no vendored JavaScript library, no framework. The System Map and Service Topology include a small **inline, dependency-free** `<script>` for the focus interactions; it only toggles CSS classes (it never rewrites the DOM or fetches anything), so with JavaScript off — or in print — every diagram is the complete static figure. Layouts are computed in Python (system-map bands, matrix ordering, topology tiers, swimlane columns, Sankey ribbons) and emitted as plain SVG with inlined fonts and styles. The rendered file pulls nothing from the network — open it on a plane, on a kiosk, or behind an airgap and it looks identical to the PDF.

## Customizing the report

Ask Claude. For example:

> "Make the cover use a deep blue accent instead of ember."

Claude will load the `design-system` skill, edit `:root` in `render.py`, and re-render. The skill documents which variables to touch and which principles to preserve.

## Roadmap

- **v0.2.0** *(shipped)* — first module diagram with per-language import parsing (Python, JS/TS, Go)
- **v0.3.0** *(shipped)* — monorepo-aware recursive module detection, service-topology HTTP graph (10 framework families), data-lineage diagram (6 ORM families), entry-point detection, `--depth medium` default
- **v0.3.x** *(shipped)* — editorial redesign: all diagrams rebuilt as deterministic static SVG (Bertin dependency matrix, C4 service topology, critical-paths swimlane, Sankey data lineage), per-diagram architect observations + small-multiples, D3/force-simulation runtime removed. Print-first throughout.
- **v0.4.0** *(shipped)* — LLM evaluation layer (on by default, `--no-llm` to skip): a code-derived overview that replaces README prominence, product-vs-vendored classification (vendored code demoted), per-product-module descriptions, and a "Key flows" section of cited execution flows. Plus Elixir (`.ex`/`.exs`) import parsing and JS/TS workspace-package (`@scope/pkg`) resolution, so the dependency matrix populates for those stacks.
- **v0.5.0** *(shipped)* — interactive, beginner-friendly report: click-to-expand language profiles (what each language is, where it runs, its typical role), a Key-flows board of collapsible lanes grouped by trigger kind, an auto-populated glossary of the tools/libraries/services named in the report (Sentry, Apollo, GraphQL, OTP, …), an explanation of faded "vendored" modules, and a dependency-matrix axis-label fix. Plus monorepo-wide and Elixir (`mix.exs`) dependency detection, so the dependency list populates across subdirectories and Elixir stacks.
- **v0.5.1** *(shipped)* — legibility fixes: External-dependencies entries no longer overlap (name/version columns, with long/scoped names wrapping) and a `*`-version legend; Key-flows step numbers now align with their text at any step height.
- **v0.5.2** *(shipped)* — dependency rows whose "version" is a long non-semver value (a local tarball path or git URL) now wrap that value onto its own line, instead of collapsing the package name into vertical one-character-per-line text.
- **v0.6.0** *(shipped)* — optional semantic code retrieval for the LLM evaluation pass: when `grepai` + a local Ollama embedding model are present, the evaluator indexes the repo and uses vector search to ground flows/overview/classification in the most relevant code (auto-detected; `--no-semantic` to skip). The deterministic scan and renderer are untouched, so reports stay reproducible.
- **v0.6.1** *(shipped)* — reliable semantic indexing on large repos: the index build now waits for grepai's own completion signal instead of inferring from chunk counts, the timeout scales with the repo's file count, a build that can't finish fails honestly (and removes its partial index) instead of reporting a corrupted one as built, and a `.grepai/` index the user created themselves is never deleted.
- **v0.7.0** *(shipped)* — AST-accurate import extraction + semantic indexing rethink. When the `ast-grep` binary is present, the module dependency graph is built from tree-sitter parses (one batched scan, ~0.1s even on large monorepos) instead of regexes — catching `import type`, re-exports, dynamic imports, and multi-line forms the regexes miss; auto-detected with full regex fallback. Semantic (grepai) indexing no longer builds by default — it only uses an index that already exists (e.g. your own `grepai watch` daemon); building is opt-in via `--semantic`.
- **v0.8.0** *(in progress)* — a **System Map** hero ("How the system fits together"): a layered-bands overview of services and modules with import, HTTP, and data-store edges; HTTP routes bundled into per-target-service lanes and capped (overflow points to the topology); per-service facet small-multiples; vendored/reference-code exclusion. Plus optional dependency-free **focus interactions** on the System Map and Service Topology (hover/click to isolate a service or flow, layer toggles) that degrade to the full static figure in print, and technical eyebrow labels on the plain-speak section headings. *(Still planned, deferred to a later release: TypeScript path-alias support, Express `app.use('/api', router)` mount following, third-party "outbound services" detection.)*
- **v0.9.0** — optional per-service file-level matrix appendix (a static drill-down figure for a chosen module, keeping the print-first, no-JS constraint)
- **v0.10.0** — diff mode (`map-repo --vs main`) to highlight architectural drift between branches
- **v1.0.0** — call-graph extraction on the tree-sitter backend: function-level caller→callee edges feeding Key Flows and critical paths with real data instead of heuristics

## Contributing

Issues and PRs welcome. See `LICENSE` (MIT).

## License

MIT. See [LICENSE](LICENSE).
