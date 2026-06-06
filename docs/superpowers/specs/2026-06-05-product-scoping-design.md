# Product-Scoping (Slice B of v0.10.0) — Design

**Date:** 2026-06-05
**Status:** Implemented (as-built is **path-based** — see §2 note; the original approved design used module-subtraction)
**Target:** 0.10.0 (Slice B of three: flow-edge validation [done] + this + Ecto lineage)

---

## 1. Problem

The report's quantitative sections measure **vendored code and dependencies**, not the product. On brevity (Elixir/Phoenix + React Native):

- **Cover headline:** "Primary language HTML · 1,341,493 lines." ~98% noise — HTML dominated by `g.frame-develop/` (a WebGL framework clone, incl. 705k LOC of generated `docs/`) + `google_ads-master/`; Elixir dominated by `backend/deps/` (517k LOC of hex packages). Actual product is ~tens of thousands of LOC.
- **External dependencies:** "Hex (119) — mix.exs ×84" unions 84 `mix.exs` files (backend + grpc + google_ads + tutorials), showing `phoenix ~> 1.4` etc. that contradict the backend's real `mix.exs` (`phoenix ~> 1.6`).
- **Directory tree** (`--depth full`) dumps the entire `backend/deps/` hex cache, burying the product files.
- **Tiers:** docs, infra, and language stubs are all counted as "backend modules."
- **Two headline counts disagree:** cover vs tree root — an unexplained gap.

Root cause: `_vendored_guess` already flags vendored *modules* (used to dim cards + exclude them from the System Map), but that classification is **never applied to the aggregates** — languages, LOC, deps, tree, tiers. `SKIP_DIRS` (scan.py) excludes `node_modules`/`vendor`/`.venv`/`dist`/`target` but **not** Elixir's `deps/`/`_build/`.

## 2. Architecture

Two kinds of "not product", two mechanisms:

1. **Dependency caches → `SKIP_DIRS`** (excluded from *everything*, like `node_modules`): add `deps`, `_build`, `_checkouts`. They are not the repo's code in any sense.
2. **Committed-but-vendored code → product/repo-wide split**: `g.frame-develop`, `google_ads-master`, `blues-stack-main` are committed to the repo (so repo-wide counts them) but are not the product.

> **AS-BUILT NOTE — path-based, not module-subtraction.** The originally approved design computed product as *repo-wide − vendored **modules*** (`build_language_breakdown` subtracting each `vendored_guess` module's per-language stats). During execution (Task 9 acceptance on brevity) this proved **insufficient**: vendored code frequently lives **outside any detected module** — e.g. brevity's `g.frame-develop/docs/` holds 705k LOC of generated HTML that is counted repo-wide but belongs to no module, so module-subtraction left the product headline at HTML. The shipped design is therefore **path-based**: a file is *product* iff its path does **not** match `_vendored_path` (the cheap path-only vendored signal: a `-master`/`-develop`/`-main` clone suffix on any segment, or a conventional vendor segment like `vendor`/`third_party`). This also unifies the slice — deps scoping (§2c), tree collapse (§2d), and `SKIP_DIRS` (§2) were already path-based; only language aggregation was not. `build_language_breakdown`/`_is_under` were removed as dead.

**Product = files whose path is not vendored.** The scanner keeps complete, file-based repo-wide totals (`*_all`, now also minus the new `SKIP_DIRS` entries) as the authoritative numbers, and computes product in the **same single walk** by excluding `_vendored_path` files. Per-file path classification can't lose loose files and reaches vendored code anywhere in the tree, inside a module or not.

**Render-time enrichment refinement.** The LLM's `classification.products`/`vendored` reclassify individual **modules**. Render adjusts the scan's path-based product by a per-module **delta** (§3): re-include a path-vendored module the LLM rescued; subtract a non-path-vendored module the LLM caught. With no enrichment (`--no-llm`), the deterministic path-based product stands. Either way the cover **leads with product-scoped**, repo-wide as a secondary "incl. dependencies" line.

### 2a. Data model additions (`codemap.json`)

- Each **module** gains `lang_stats: dict[str, dict[str, int]]` (e.g. `{"Elixir": {"files": 12, "loc": 12043}, "HTML": {"files": 1, "loc": 50}}`). Used by the render-time enrichment delta (§3). Modules already carry `loc`, `file_count`, `languages`, `vendored_guess`, `path`.
- Each **directory tree node** gains `vendored: bool` (from `_vendored_path` of its rel path) so render can collapse vendored subtrees (§2d).
- **Project / top level** gains repo-wide *and* product aggregates:
  - `total_files`, `total_loc`, `languages` → **product-scoped** (the lead; product = non-vendored-path files).
  - `total_files_all`, `total_loc_all`, `languages_all` → **repo-wide** (complete, file-based, authoritative).
  - `deps` (product) + `deps_all` (repo-wide).
  - `languages` / `languages_all` keep the existing per-language list shape (`[{name, files, loc, color}]`).

### 2b. Scanner changes

- `_measure_dir` returns a 4th value `lang_stats: dict[str, dict[str,int]]` (per-language `{files, loc}`), accumulated in its existing walk. Module-record call sites store it (including the flat service-container fallback).
- `SKIP_DIRS` += `deps`, `_build`, `_checkouts`.
- New `_vendored_path(rel_path) -> bool`: the cheap path-only half of `_vendored_guess` (segment in `VENDORED_PATH_SEGMENTS`, or any segment ending in `VENDORED_DIR_SUFFIXES`), reused by language aggregation, deps scoping, and tree tagging. `_vendored_guess` delegates its path checks to it and keeps the `package.json` repository-URL check.
- New `aggregate_languages_split(root) -> (product, repo_wide)`: one walk; `repo_wide` counts every file (== the historical `aggregate_languages`, which now delegates to `split(root)[1]`); `product` excludes files where `_vendored_path(rel)` is True. Both sorted by LOC desc.
- `build_data_model` emits `languages, languages_all = aggregate_languages_split(root)` plus `total_*`/`total_*_all` and `deps`/`deps_all`.

### 2c. Deps scoping

- `find_dependencies(root, max, product_only=False)`: when `product_only`, skip manifests whose path matches `_vendored_path`. `SKIP_DIRS` already hides `deps/` manifests; this drops the committed vendored-clone manifests (`google_ads-master/mix.exs`, …). `build_data_model` emits `deps` (product) + `deps_all` (repo-wide). Render leads with `deps`, repo-wide secondary.

### 2d. Tree

- `deps/`/`_build/` auto-excluded once in `SKIP_DIRS`.
- `walk_tree` tags every dir node `vendored` via `_vendored_path`. `_tree_node` **collapses** a vendored dir to a one-line summary — `▸ google_ads-master/ — N files · M LOC · vendored (hidden)` — instead of expanding its children. Preserves the "exists in your repo" signal without the file dump.

### 2e. Tiers

- The System Map "backend/frontend modules" tier counts exclude **non-code** modules: `_is_infra_or_docs(path)` returns True when the **first path segment** is one of `docs/doc/documentation/infra/infrastructure/ops/deploy/deployment/ci/.github`. First-segment-only (not any-segment) so a real product module like `services/ci` is never mis-excluded. Such nodes are skipped in `_sysmap_select`'s band assignment.

### 2f. Count reconciliation

- The cover counts **code files** (recognized source languages) and is labeled "Code files"; the directory tree counts all files. The gap is real-by-design and resolved by **labeling + product-scoping both**, not by forcing equality.

## 3. Render

- Cover + languages + deps sections **lead with product**; repo-wide appears as a muted secondary line **only when it differs** from product (so simple repos show no redundant line). Cover: "incl. dependencies: {total_loc_all} lines across {total_files_all} files". Languages: a parallel aside. Deps: "Showing {N} product dependencies · {M} incl. vendored clones".
- `_apply_enrichment_overrides` re-derives the product as a **path-aware delta** on `data["languages"]` (the scan path-based product): for each module, if it is `_vendored_path` AND the LLM rescued it (`module_id` in `classification.products`) → **add** its `lang_stats` back; if it is NOT `_vendored_path` AND the LLM caught it (in `classification.vendored`) → **subtract** its `lang_stats`. `product_ids` is checked first (product wins on self-contradiction — never undercount product). Updates `languages` + `project.total_files`/`total_loc`; `*_all` stay at scan values. No-enrichment / http-edges-only paths leave the product untouched.
- Tree collapses vendored subtrees (2d). Tier captions use product, infra/docs-excluded counts (2e).

## 4. Testing

- `_measure_dir` returns `lang_stats` summing to `loc`; per-language correct on a mixed temp dir; flat service-container fallback carries `lang_stats`.
- `aggregate_languages_split`: product excludes a vendored-path dir's files (e.g. `g.frame-develop/docs/*.html`) while repo-wide includes them; `aggregate_languages == split()[1]`.
- `SKIP_DIRS` includes `deps`/`_build`/`_checkouts`; a temp repo with a `deps/` dir excludes it from totals.
- Deps scoping: a vendored-clone manifest's deps are absent from product `deps`, present in `deps_all`.
- Tier predicate: first-segment `docs/`/`infra/` excluded; `services/ci` etc. NOT excluded.
- Tree: `walk_tree` tags vendored dirs; `_tree_node` collapses a vendored subtree (counts rendered, children hidden).
- Render: cover/languages lead product + show a repo-wide secondary only when differing; "Code files" label.
- Enrichment delta: catch shrinks product, rescue grows it, no-enrichment + http-edges-only leave it untouched, self-contradiction → product wins.
- **Golden:** the deterministic fittalk body changes (product-scoped numbers, "Code files" label, tier count). Regenerated deliberately with a verified diff. (fittalk has no vendored dirs, so its product == repo-wide and the secondary "incl. dependencies" lines do not appear; the product display is proven end-to-end on **brevity**, not the golden.)
- **Acceptance (brevity, validated):** product 98,905 LOC (9.6% of repo-wide 1,028,260), primary language flips HTML→Elixir, product hex deps 50 vs repo-wide 66, tree collapses 16 vendored subtrees.

## 5. Out of scope / known limitations

- The product unit is the **file path** (path-based via `_vendored_path`), which reaches vendored code wherever it sits — improving on the original module-granularity design. A path-vendored directory that genuinely mixes product + vendored code is classified whole by path; the LLM enrichment delta (§3) is the per-module escape hatch (rescue/catch).
- Enrichment reclassification is keyed on **modules** (`module_id`), applied as a delta on the path-based product; a rescued/caught unit smaller than a module is not expressible.
- Ecto data-lineage (the empty data-store problem) is **Slice C**, not here.
- Version bump to 0.10.0 happens once, after Slice C.
