---
name: map-repo
description: Slash command. Use this skill ONLY when the user explicitly invokes the /smokeyp-codebase-mapper:map-repo slash command. Do NOT trigger on conversational requests, natural-language phrases, or implicit intent — even if the user says "map this repo", "generate an architecture report", "document the codebase", "audit my project", or any other paraphrase. Activation is by slash command only. When invoked, scans a codebase and produces a polished, beginner-friendly HTML/PDF architecture report with directory tree, language breakdown, module summaries, dependency listing, entry-point detection, and a glossary of technical terms.
argument-hint: "[path?] [--format html|pdf|both] [--depth shallow|medium|full] [--out PATH] [--no-semantic]"
allowed-tools: Read, Glob, Grep, Bash, Write
version: 0.1.0
---

# Map Repo

When invoked, scan a target repository and produce a styled architecture report at `<target>/.codemap/`.

## Argument parsing

Parse arguments in this order:

1. **`path`** (optional, positional) — directory to scan. Defaults to the current working directory.
2. **`--format`** — one of `html`, `pdf`, `both`. Defaults to `both`.
3. **`--depth`** — one of `shallow`, `medium`, `full`. Defaults to `medium`.
   - `shallow`: 2-level tree, top 10 module cards, 30 graph nodes, 20 deps per ecosystem. Use for very large repos when you want a single-glance summary.
   - `medium` *(default)*: 4-level tree, top 25 module cards, 80 graph nodes, 40 deps per ecosystem. The right setting for most monorepos and mid-size projects.
   - `full`: complete tree, every module, every dependency. Use for archival or when investigating a specific corner that medium truncated.
4. **`--out`** — output directory. Defaults to `<path>/.codemap/`.
5. **`--no-llm`** (alias `--fast`) — skip the LLM evaluation step (Step 1.5) and produce the deterministic-only report. Defaults to running the evaluation.
6. **`--semantic`** / **`--no-semantic`** — turn semantic code retrieval in Step 1.5 on or off. Default: **auto** — on when `grepai` and a local Ollama embedding model are available, off otherwise. `--semantic` forces it on (warn if unavailable, then continue without it); `--no-semantic` forces it off. Ignored when `--no-llm` is set.

Resolve the target path to an absolute path. If it does not exist or is not a directory, stop and report the error to the user.

## Execution pipeline

The pipeline is three subprocess calls. Do not re-implement scanning or rendering in Claude — the scripts are deterministic and faster.

### Step 1 — Scan

Run the scanner to produce a JSON data model:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/map-repo/scripts/scan.py" \
  --path "<resolved-path>" \
  --depth "<shallow|medium|full>" \
  --out "<out-dir>/codemap.json" \
  --evidence-out "<out-dir>/codemap.evidence.json"
```

Omit `--evidence-out` when `--no-llm` is set (the evidence pack is only consumed by Step 1.5).

If `python3` is not available, fall back to `python`. If neither is available, stop and tell the user Python 3.10+ is required.

### Step 1.5 — LLM evaluation (skip if `--no-llm`)

Read `<out-dir>/codemap.evidence.json`. It contains the module list and truncated contents of high-signal files (entry points, manifests, READMEs, route/schema files). You may additionally `Read`/`Grep` up to ~20 more files in the target repo to confirm flows and citations — **do not read the whole repo**.

#### Semantic retrieval (optional, recommended)

When semantic mode is enabled (the default when available — see argument parsing), use **vector code search** to find the *right* code to ground each claim instead of guessing from the bounded evidence pack. This matters most for flow citations and for large repos the evidence pack only samples.

First check availability and build the index (one-shot; uses `grepai` + a local Ollama embedding model). Skip this whole subsection if `--no-semantic` was passed:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/map-repo/scripts/semantic_index.sh" available \
  && bash "${CLAUDE_PLUGIN_ROOT}/skills/map-repo/scripts/semantic_index.sh" build "<resolved-path>" 300
```

If `available` fails (grepai / Ollama / the embedding model is missing), fall back to the evidence pack plus targeted `Read`/`Grep` — semantic mode is purely additive. If the user explicitly passed `--semantic` and it is unavailable, warn them and continue without it.

Once the index is built, retrieve grounding code with targeted natural-language queries. The JSON output is `{file_path, start_line, end_line, content, score}` — there is **no** `symbol` field, so read the returned `content` to name the symbol for a citation:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/map-repo/scripts/semantic_index.sh" search "<resolved-path>" "<query>" 5
```

Run one query per question you need to answer, for example:
- **Flows**: `"application bootstrap / entrypoint"`, `"HTTP route handlers"`, `"scheduled / cron job"`, `"background worker or job queue"`, `"payment or billing webhook"`, `"user authentication / login"`.
- **Overview**: `"core domain / business logic"`, `"primary data models"`.
- **Data stores**: `"database queries or ORM model definitions"`.
- **Classification**: a query naming a suspected vendored library, to confirm it is third-party.

Cite the `file_path` + `start_line` each hit returns. Prefer grepai hits over guesses — they land flow citations on real code (and pass `validate_enrichment.py`).

When enrichment is finished, free the index:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/map-repo/scripts/semantic_index.sh" cleanup "<resolved-path>"
```

Write a `codemap.enrichment.json` to `<out-dir>/` with this shape (the authoritative schema is enforced by `validate_enrichment.py`):

- **`schema_version`**: `1`.
- **`overview`**: `what_it_is` / `what_it_does` / `how_it_works` (plain English, grounded in the code you actually read — **NOT** the README), `primary_stack` (array), `confidence` (`high`|`medium`|`low`), `caveats` (array — call out a misleading or roadmap-style README here).
- **`classification`**: `products` and `vendored` arrays. Treat as **vendored** any module that is a dependency or reference clone: paths under `vendor/` or `node_modules/`, directory names ending `-master`/`-develop`/`-main` (git-archive clones), a third-party `LICENSE` or repo URL in its `package.json`, or a path-dependency. Everything that is the actual product is a **product** (each with a `role` and a one-line `why`). Use the module `path` as `module_id`.
- **`module_descriptions`**: for each PRODUCT module, an accurate one-line `description` (fill gaps the scanner left empty — e.g. Elixir modules with no `package.json`). Include `is_product: true`.
- **`flows`**: 3 flows at `--depth medium`, up to 6 at `--depth full`. Each is an end-to-end story (signup, a domain state machine, a scheduled job, a data pipeline, app bootstrap) with `name`, `kind` (`request`|`background`|`scheduled`|`state-machine`|`pipeline`|`bootstrap`), `trigger`, `narration`, `terminates`, and `steps`. **Every step must cite a real `file` + `symbol` you actually saw** (optional `line`, `note`). No uncited steps.

Then validate before rendering:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/map-repo/scripts/validate_enrichment.py" \
  --enrichment "<out-dir>/codemap.enrichment.json" \
  --repo "<resolved-path>"
```

If it reports structural errors, fix the JSON and re-validate. (Flows with broken citations are dropped automatically at render time, but fix them if you can.) If you cannot produce valid enrichment, skip it and render the deterministic-only report.

### Step 2 — Render HTML

Run the renderer (pass `--enrichment` unless `--no-llm` was set or no valid enrichment was produced):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/map-repo/scripts/render.py" \
  --in "<out-dir>/codemap.json" \
  --out "<out-dir>/codemap.html" \
  --enrichment "<out-dir>/codemap.enrichment.json"
```

The renderer follows the SmokeyP visual standard documented in the `design-system` skill. If the user has asked for design adjustments (alternate palette, theme, etc.), load that skill before re-rendering with overrides.

### Step 3 — Render PDF (only if `--format` is `pdf` or `both`)

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/map-repo/scripts/to-pdf.sh" \
  "<out-dir>/codemap.html" \
  "<out-dir>/codemap.pdf"
```

The shell script detects an installed Chrome/Chromium/Edge/Brave binary and prints to PDF. If none is found, report that PDF rendering requires a Chromium-family browser; the HTML output is still valid and usable.

## Reporting back to the user

After the pipeline succeeds, report:

- The absolute path(s) to the generated file(s)
- A one-sentence summary of what was scanned (e.g. "Scanned 234 files across 8 languages; primary language TypeScript")
- A suggestion: open the HTML in a browser or print the PDF

Pull the summary numbers from the `project` object in `codemap.json` — do not invent them.

## Edge cases

- **Empty repository** — if `total_files` is 0, still produce a report (it will just be a near-empty cover card). Mention this in the summary.
- **Very large repos** (>50k files) — prefer `--depth shallow`. If the user passed `full` on a large repo, complete the scan but warn that the HTML may be large.
- **Permission errors during scan** — `scan.py` skips unreadable files silently. If the JSON output is empty due to no readable files, report that to the user.
- **Re-running** — overwrites the previous `codemap.json`, `codemap.html`, and `codemap.pdf` in `<out-dir>` without prompting. This is intentional; the user invoked the command, they want fresh output.
- **Semantic mode** — needs `grepai` plus a local Ollama embedding model (`nomic-embed-text`); it is auto-skipped when absent, with no failure. Indexing a large repo takes a minute or more and writes a transient `.grepai/` index under the scanned repo (removed by `semantic_index.sh cleanup`); `grepai init` may also append `.grepai/` to the repo's `.gitignore`. The embeddings run locally, so no network is used. Force it off with `--no-semantic`.

## What this skill does NOT do

- It does **not** push anything to GitHub or external services.
- It does **not** modify source files in the target repo. The only writes happen inside `<out-dir>` — except optional semantic mode, which writes a transient `.grepai/` index (removed on cleanup) and may add a `.grepai/` line to the repo's `.gitignore`.
- It does **not** require network access. The HTML is self-contained (inline CSS, no CDN fonts).
