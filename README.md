# smokeyp-codebase-mapper

> A Claude Code plugin that scans any repository and produces a polished HTML or PDF architecture report — editorial-quality, self-contained, printable, and beginner-friendly.

`/smokeyp-codebase-mapper:map-repo` walks a codebase, detects services and modules (monorepo-aware), parses imports across multiple languages, extracts HTTP endpoint declarations and outbound client calls, infers ORM/data-store usage, and renders everything as a single self-contained HTML file with **four print-first architecture diagrams**. Every diagram is deterministic static SVG — no JavaScript, no force simulation, no network dependency — so the same layout you see on screen is what lands on the page. With Chrome installed, it also prints to PDF. Built for client deliverables, onboarding docs, and architectural audits — explanatory throughout, no jargon left unexplained.

## What's in a report

- **Cover** — project name, primary language, file count, LOC, language count, monorepo flag
- **README extract** — a clean first-paragraph blockquote so the document opens with context
- **Languages** — stacked share bar + sortable table with file counts and lines
- **Top-level modules** — each detected module (recursive for monorepos) as a card with description (auto-detected from README, `package.json`, or `__init__.py` docstring)
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
| `--out` | `<path>/.codemap/` | Output directory |

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

## The four diagrams

The diagrams are the marquee feature. Each answers a different question, and together they tell the full story of a codebase: *what's in it, what's wired to what, what happens at runtime, and where the data lives.* All four are deterministic static SVG — the layout is computed at render time and baked into the file, so there's nothing to interact with and nothing to load. That's the deliberate trade: a report you can email, print, or open behind an airgap and trust to look identical everywhere.

### Diagram 1 — Module dependency matrix ("How the modules connect")

A Bertin-style dependency matrix. Rows are importing modules, columns are imported modules; each filled cell is an `imports from` relationship, shaded by the number of underlying file-level imports. Modules are ordered by service, so a cleanly-separated architecture shows a **block-diagonal pattern** — dense blocks on the diagonal (intra-service coupling), sparse off-diagonal cells (cross-service coupling). Within a service block, faint dashed dividers separate sub-domains. The matrix scales to ~60 modules without the hairball problem a node-link graph hits at that size.

### Diagram 2 — Service topology ("How the services talk to each other")

A C4-style layered diagram. Each card is an independently-deployable service (coloured and chipped by kind — frontend, backend, worker); each edge is the count of distinct HTTP routes one service calls on another, drawn with an orthogonal connector and a weight pill. Tiers run left-to-right in call direction (roots like frontends on the left, leaf workers on the right). This is the relationship that wouldn't show up at all in an import scan — `mobile → backend → AI worker` over HTTP, not via shared code. Renders only when more than one service is detected.

### Diagram 3 — Critical paths ("What happens when a request flows through")

A four-column swimlane with one row per entry-point module. Each row traces a request left to right: **callers → entry module → key dependencies → data store**, joining five sources (entry modules, endpoints, HTTP edges, import edges, and data-lineage edges) into a single readable path. Where the matrix shows *structure* and the topology shows *services*, this shows *execution* — what a request actually touches on its way through.

### Diagram 4 — Data lineage ("Where each service stores its data")

A Sankey with cylinder store glyphs: services on the left, data stores on the right (Postgres, Redis, Mongo, S3, Supabase, Firebase, Elasticsearch, Kafka, etc.), with each store drawn in its brand colour. Ribbon thickness scales (log) with the count of distinct data models each service touches in a store. Stores detected from config but not referenced by any ORM model still render, at reduced opacity, so nothing in the infrastructure goes silently unrepresented. Detected from ORM declarations plus `docker-compose.yml` / `.env*` evidence.

### Reading them in print

There's no on-screen interaction to learn — every diagram is a finished static figure. The four diagram sections print on **Letter landscape** pages (the reading sections stay portrait), each diagram centred and height-capped so its heading and figure share one page. Because the figures are SVG, text stays crisp at any scale — it's vector all the way to paper.

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

Every diagram is rendered to static SVG by `render.py` at report time — there is no client-side runtime, no vendored JavaScript library, and no `<script>` in the output. Layouts are computed in Python (matrix ordering, topology tiers, swimlane columns, Sankey ribbons) and emitted as plain SVG with inlined fonts and styles. The rendered file pulls nothing from the network — open it on a plane, on a kiosk, or behind an airgap and all four diagrams look identical to the PDF.

## Customizing the report

Ask Claude. For example:

> "Make the cover use a deep blue accent instead of ember."

Claude will load the `design-system` skill, edit `:root` in `render.py`, and re-render. The skill documents which variables to touch and which principles to preserve.

## Roadmap

- **v0.2.0** *(shipped)* — first module diagram with per-language import parsing (Python, JS/TS, Go)
- **v0.3.0** *(shipped)* — monorepo-aware recursive module detection, service-topology HTTP graph (10 framework families), data-lineage diagram (6 ORM families), entry-point detection, `--depth medium` default
- **v0.3.x** *(shipped)* — editorial redesign: all diagrams rebuilt as deterministic static SVG (Bertin dependency matrix, C4 service topology, critical-paths swimlane, Sankey data lineage), per-diagram architect observations + small-multiples, D3/force-simulation runtime removed. Print-first throughout.
- **v0.4.0** — TypeScript path-alias support, Express `app.use('/api', router)` mount following, third-party service detection (external API calls grouped as "outbound services" node)
- **v0.5.0** — optional per-service file-level matrix appendix (a static drill-down figure for a chosen module, keeping the print-first, no-JS constraint)
- **v0.6.0** — diff mode (`map-repo --vs main`) to highlight architectural drift between branches
- **v1.0.0** — optional tree-sitter AST backend for sharper edge accuracy on languages where it matters

## Contributing

Issues and PRs welcome. See `LICENSE` (MIT).

## License

MIT. See [LICENSE](LICENSE).
