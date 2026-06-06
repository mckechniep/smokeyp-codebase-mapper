# Ecto Data-Lineage (Slice C of v0.10.0) — Design

**Date:** 2026-06-06
**Status:** Approved (design) — pending spec review → plan
**Target:** 0.10.0 (Slice C of three: flow-edge validation [done] + product-scoping [done] + this)

---

## 1. Problem

The report's **data-lineage** section detects data stores and the models/entities (DB tables) that live in them, and which services write to them. It recognizes Prisma, and usage-site ORMs for TS/JS/Python/Ruby/Java/Kotlin — but **not Elixir's Ecto**. On brevity (Elixir/Phoenix), the real domain model (~30 Ecto schemas in `lib/brevity_schemas/`) is invisible; the section instead shows only the **3 Prisma models from a vendored Remix tutorial** (`blues-stack-main/`), because:

1. `build_data_lineage` never scans Elixir files for models (`"Elixir"` is absent from its language allowlist), and
2. it applies **no `_vendored_path` filtering**, so vendored clones' schemas leak in.

The net effect: the lineage is both *missing the product* and *showing vendored noise* — the inverse of what it should show.

## 2. Architecture

Mirror the existing **Prisma schema-file pass** for Ecto: a regex over Elixir source emitting the same `{service, framework, model, store}` model shape the lineage already produces. The render layer is **framework-agnostic** and needs **zero changes** — "Ecto" appears as a framework pill and `postgres` already has a store color.

Detection signal: `schema "table_name" do` (the Ecto `schema` macro with a quoted table). This is Ecto-specific syntax and is present in all ~30 brevity product schemas. It is the **only** reliable signal because brevity's schemas use `use BrevitySchemas.Base` (a macro wrapper around `use Ecto.Schema`), so grepping `use Ecto.Schema` finds only the base module — we do NOT key off `use Ecto.Schema`.

**Structure:** inline Elixir branch in `_scan_data_models_file` (consistent with how the existing ORMs are handled inline). No new module — the detection is a single regex, unlike the `phoenix_router` parser which earned its own module by complexity.

### 2a. Scope (decided)

- **Enumerate schemas** → one model per `schema "..." do`, attributed to its owning service + a `postgres` store. Produces `backend → postgres` edges with ~30 models. This matches the Prisma pattern and what render draws.
- **Out of scope** (deferred; render doesn't consume them today): per-module read/write attribution (Repo.* call analysis) and `belongs_to`/`has_many` association graphs.

### 2b. Scanner changes (`scan.py`)

- New constant near the other lineage regexes: `ECTO_SCHEMA_RE = re.compile(r'^\s*schema\s+"([^"]+)"\s+do', re.MULTILINE)`.
- `ORM_DEFAULT_STORE` gains `"Ecto": "postgres"`.
- `_scan_data_models_file` gains an `elif language == "Elixir":` branch: for each `ECTO_SCHEMA_RE` match, emit a model via the existing `emit("Ecto", <model_name>)` mechanism.
  - **Model name** = the enclosing module's last segment (e.g. `BrevitySchemas.Recommendation` → `Recommendation`), via the existing `ELIXIR_DEFMODULE_RE` / `_elixir_defmodules` helper; **fall back to the table name** (`recommendations`) if no `defmodule` is found in the file. (One `defmodule` + one `schema` per file is the norm; if a file has multiple schemas, attribute each to the nearest preceding `defmodule`, else the table name.)
- `build_data_lineage`: add `"Elixir"` to the language allowlist (currently `TS/JS/Python/Ruby/Java/Kotlin`) so Elixir files reach `_scan_data_models_file`.

### 2c. Store detection (`scan.py` `_detect_stores`)

- Extend the per-source file list to also read `config/config.exs`, `config/dev.exs`, `config/runtime.exs` (at root and each immediate service subdir, same pattern as the existing `.env`/`database.yml` handling).
- Match `Ecto.Adapters.Postgres` or `postgrex` (and the existing `postgres` pattern) → a `postgres` store. brevity's `backend/docker-compose.yml` already yields postgres; this makes config-only Phoenix apps robust and satisfies the handoff's "detect Postgrex/Postgres store."

### 2d. Product-scoping fix (the core correctness fix)

`build_data_lineage` must respect the same product/vendored boundary as the rest of the report (Slice B). Add a `_vendored_path(str(f.relative_to(root)))` guard to:
1. the per-file model loop (before `_scan_data_models_file`), and
2. the `root.rglob("schema.prisma")` pass (alongside its existing `SKIP_DIRS` check).

Net effect on brevity: the 3 vendored Prisma models (under `blues-stack-main/`) are **dropped**; the ~30 product Ecto schemas **appear**. `_vendored_path` already exists (Slice B) and is used by `aggregate_languages_split`, `find_dependencies`, `walk_tree`.

### 2e. Render

No changes. `render_data_lineage_v2` / `render_lineage_v2_bento` consume `stores`/`models`/`edges` framework-agnostically; "Ecto" shows as a framework pill; the hot-models tile lists the schemas; `STORE_KIND_COLORS["postgres"]` exists.

## 3. Testing

New `tests/test_data_lineage.py` (no lineage test file exists today):

- `_scan_data_models_file` on an Elixir fixture containing `defmodule X.Recommendation do … schema "recommendations" do … end` → emits a model named `Recommendation`, framework `Ecto`, store `postgres`.
- Model-name fallback: a `schema "widgets" do` with no `defmodule` → model name `widgets`.
- `build_data_lineage` end-to-end on a temp tree with a `backend/lib/*.ex` schema → `models` includes it, `stores` includes postgres, `edges` has `backend → postgres` with the model.
- **Vendored exclusion:** a schema under `something-master/` (or `vendor/`) is absent from `models`.
- **Prisma-leak regression:** a `schema.prisma` under a vendored path is excluded (the bug being fixed).
- **Store from config:** a `config/config.exs` containing `adapter: Ecto.Adapters.Postgres` → postgres store detected even with no docker-compose.

No golden change expected (fittalk is not Elixir and has no Ecto schemas; its lineage is unaffected). Acceptance is verified by a brevity re-scan: lineage shows postgres + ~30 Ecto models and **zero** vendored Prisma models.

## 4. Acceptance (brevity)

After implementation, re-scan brevity (`--depth full`, output to /tmp) and confirm:
- `data_lineage.stores` includes a `postgres` store.
- `data_lineage.models` contains ~30 `Ecto` models (the `brevity_schemas`) and **no** Prisma models from `blues-stack-main`.
- `data_lineage.edges` has a `backend → postgres` edge with weight ≈ 30.

## 5. Out of scope / known limitations

- Read/write lineage (which contexts read vs write each schema) and association graphs (`belongs_to`/`has_many`) are deferred — render has no view for them today.
- `embedded_schema` (no table) is intentionally NOT matched — only DB-backed `schema "table" do`.
- Detection is per-file regex, not a full Elixir parser; a schema whose table name is built dynamically (not a string literal) won't match (not observed in brevity).
- Version bump to 0.10.0 happens once, after this slice (a dedicated release commit), then finish the branch.
