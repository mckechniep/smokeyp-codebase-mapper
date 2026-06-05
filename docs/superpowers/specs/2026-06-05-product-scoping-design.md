# Product-Scoping (Slice B of v0.10.0) — Design

**Date:** 2026-06-05
**Status:** Approved (design); pending spec review → plan
**Target:** 0.10.0 (Slice B of three: flow-edge validation [done] + this + Ecto lineage)

---

## 1. Problem

The report's quantitative sections measure **vendored code and dependencies**, not the product. On brevity (Elixir/Phoenix + React Native):

- **Cover headline:** "Primary language HTML · 1,341,493 lines." ~98% noise — HTML 53% is `g.frame-develop/` (WebGL framework) + `google_ads-master/`; Elixir 37% is dominated by `backend/deps/` (517k LOC of hex packages). Actual product is ~tens of thousands of LOC.
- **External dependencies:** "Hex (119) — mix.exs ×84" unions 84 `mix.exs` files (backend + grpc + google_ads + tutorials), showing `phoenix ~> 1.4` etc. that contradict the backend's real `mix.exs` (`phoenix ~> 1.6`).
- **Directory tree** (`--depth full`) dumps the entire `backend/deps/` hex cache, burying the ~121 product files.
- **Tiers:** docs, infra, and language stubs are all counted as "backend modules (14)."
- **Two headline counts disagree:** cover says 7,182 files / 1.34M LOC; tree root says 8,773 / 1.63M — a 22% gap, unexplained.

Root cause: `_vendored_guess` already flags vendored *modules* (used to dim cards + exclude them from the System Map), but that classification is **never applied to the aggregates** — languages, LOC, deps, tree, tiers. `SKIP_DIRS` (scan.py:87) excludes `node_modules`/`vendor`/`.venv`/`dist`/`target` but **not** Elixir's `deps/`/`_build/`.

## 2. Architecture

Two kinds of "not product", two mechanisms:

1. **Dependency caches → `SKIP_DIRS`** (excluded from *everything*, like `node_modules`): add `deps`, `_build`, `.elixir_ls`, `_checkouts`. They are not the repo's code in any sense.
2. **Committed-but-vendored clones → product/repo-wide split**: `g.frame-develop`, `google_ads-master`, `blues-stack-main` are committed to the repo (so repo-wide counts them) but are not the product. The split keys off the existing per-module `vendored_guess`.

**Product = repo-wide − vendored (by subtraction).** The scanner keeps its complete, file-based repo-wide totals (now also minus the new `SKIP_DIRS` entries) as the authoritative numbers, and derives product-scoped numbers by subtracting the vendored modules' contribution. This can't lose loose files (a root `config.js` in no module stays in the total and isn't vendored → stays in product). New per-module data makes the subtraction per-language.

**Render-time enrichment refinement.** Because the LLM's `classification.products`/`vendored` overrides which modules are vendored, render recomputes the *vendored set* from enrichment and subtracts *that* set's `loc_by_language` from the repo-wide totals — yielding an LLM-refined product headline. With no enrichment (`--no-llm`), the deterministic `vendored_guess`-based product numbers are used. Either way the cover **leads with product-scoped**, repo-wide as a secondary "incl. dependencies" line.

### 2a. Data model additions (`codemap.json`)

- Each **module** gains `loc_by_language: dict[str, int]` (e.g. `{"Elixir": 12043, "HTML": 50}`). Modules already carry `loc`, `file_count`, `languages`, `vendored_guess`, `path`.
- **Project / top level** gains the repo-wide *and* product aggregates:
  - `total_files`, `total_loc`, `languages` → **product-scoped** (the lead; product = repo-wide − vendored).
  - `total_files_all`, `total_loc_all`, `languages_all` → **repo-wide** (complete, file-based, authoritative).
  - `languages` / `languages_all` keep the existing per-language list shape (`[{name, files, loc, color}]`).

### 2b. Scanner changes

- `_measure_dir` (scan.py:474) returns a 4th value `loc_by_language: dict[str, int]`, accumulating `count_lines(f)` per `detect_language(f)`. All callers updated to receive + store it on the module.
- `SKIP_DIRS` += `deps`, `_build`, `.elixir_ls`, `_checkouts`.
- New `build_language_breakdown(languages_all, modules)`: given the complete repo-wide per-language totals and the modules, subtract every `vendored_guess` module's `loc_by_language` → the product per-language list. Pure; reused by render with a refined vendored set.
- `total_files`/`total_loc` (product) = `total_*_all` − Σ(vendored module `file_count`/`loc`).
- `build_data_model` emits both `_all` and product aggregates.

### 2c. Deps scoping

- A dependency manifest is **product** iff its owning module is not vendored. Build a product deps view (exclude manifests under vendored modules / `SKIP_DIRS`) alongside the repo-wide view: `deps` (product) + `deps_all` (repo-wide). Never union vendored manifests into the product list. Render leads with `deps`, repo-wide secondary; render refines the product set with enrichment classification.

### 2d. Tree

- `deps/`/`_build/` auto-excluded once in `SKIP_DIRS`.
- Vendored top-level dirs (`vendored_guess` modules) **collapse to a one-line summary** in the rendered tree: `▸ google_ads-master/ — 151k LOC · vendored (hidden)`, instead of expanding their file lists. The collapse is render-side (the tree data still carries the nodes; render folds vendored subtrees into a summary node).

### 2e. Tiers

- The "backend/frontend modules" tier counts (System Map caption + tier buckets) exclude **non-code** modules: a module whose role/path is `docs`/`infra`/`config` (top-level `docs/`, `infra/`, `.github/`, `ops/`, `deploy/`, doc-only dirs) is not a service tier. Add a `_is_infra_or_docs(path)` predicate; such modules are dropped from tier counts (still listed elsewhere if relevant).

### 2f. Count reconciliation

- The cover total and the directory-tree root total must measure the **same** product-scoped set. Investigate the current divergence (the tree counter vs `sum(languages)`); make both derive from the product aggregate (or, if a repo-wide tree is wanted, label each explicitly: "product" vs "incl. dependencies"). No unexplained gap may remain on the page.

## 3. Render

- `_apply_enrichment_overrides` (or a sibling) recomputes the vendored module set from `enrichment.classification` (products rescue, vendored catches) and re-derives the product `languages`/`total_*`/`deps` via the same `build_language_breakdown` subtraction — so System Map, cover, languages, and deps all see the refined product numbers from one place. Falls back to the deterministic product aggregate when no enrichment.
- Cover + languages + deps sections **lead with product**, repo-wide as a muted secondary line ("incl. dependencies: …").
- Tree collapses vendored subtrees (2d). Tier captions use product, infra/docs-excluded counts (2e).

## 4. Testing

- `_measure_dir` returns `loc_by_language` summing to `loc`; per-language correct on a mixed-language temp dir.
- `build_language_breakdown`: product = repo-wide − vendored; a vendored module's languages are fully removed; a non-vendored module's are kept; loose-file LOC (in `_all`, in no vendored module) survives into product.
- `SKIP_DIRS` includes `deps`/`_build`; a temp repo with a `deps/` dir excludes it from totals and tree.
- Deps scoping: a vendored module's manifest deps are absent from the product `deps`, present in `deps_all`.
- Tier predicate: `docs/`/`infra/` modules excluded from backend/frontend counts.
- Render: cover leads with product number + shows a repo-wide secondary; enrichment that reclassifies a module shifts the product headline (the subtraction uses the refined vendored set); `--no-llm` uses the deterministic product aggregate.
- Count reconciliation: cover total == tree root total for the same scope (test on a synthetic repo with a vendored dir).
- **Golden:** the deterministic fittalk body **will change** (product-scoped numbers + new secondary lines). Regenerate the golden deliberately and verify the body diff is exactly the product-scoping change (numbers + "incl. dependencies" lines + tree collapse), nothing unintended — same discipline used in Slice A's predecessor work.

## 5. Out of scope / known limitations

- The product/vendored unit is the **module**; a single module that mixes product + vendored code is classified as a whole (the existing `vendored_guess` granularity). Not split per-file beyond `SKIP_DIRS`.
- `_is_product_path` semantics live in `vendored_guess` (path suffix + `third_party`/`extern` + package.json URL); Slice B reuses that flag rather than re-deriving file-level vendoredness.
- Ecto data-lineage (the empty data-store problem) is **Slice C**, not here.
- Version bump to 0.10.0 happens once, after Slice C.
