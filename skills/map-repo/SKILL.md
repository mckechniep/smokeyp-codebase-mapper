---
name: map-repo
description: Slash command. Use this skill ONLY when the user explicitly invokes the /smokeyp-codebase-mapper:map-repo slash command. Do NOT trigger on conversational requests, natural-language phrases, or implicit intent — even if the user says "map this repo", "generate an architecture report", "document the codebase", "audit my project", or any other paraphrase. Activation is by slash command only. When invoked, scans a codebase and produces a polished, beginner-friendly HTML/PDF architecture report with directory tree, language breakdown, module summaries, dependency listing, entry-point detection, and a glossary of technical terms.
argument-hint: "[path?] [--format html|pdf|both] [--depth shallow|full] [--out PATH]"
allowed-tools: Read, Glob, Grep, Bash, Write
version: 0.1.0
---

# Map Repo

When invoked, scan a target repository and produce a styled architecture report at `<target>/.codemap/`.

## Argument parsing

Parse arguments in this order:

1. **`path`** (optional, positional) — directory to scan. Defaults to the current working directory.
2. **`--format`** — one of `html`, `pdf`, `both`. Defaults to `both`.
3. **`--depth`** — one of `shallow`, `full`. Defaults to `shallow`.
   - `shallow`: 2 levels of directory tree, top 10 modules, top 20 dependencies per ecosystem.
   - `full`: complete tree, all modules, all dependencies.
4. **`--out`** — output directory. Defaults to `<path>/.codemap/`.

Resolve the target path to an absolute path. If it does not exist or is not a directory, stop and report the error to the user.

## Execution pipeline

The pipeline is three subprocess calls. Do not re-implement scanning or rendering in Claude — the scripts are deterministic and faster.

### Step 1 — Scan

Run the scanner to produce a JSON data model:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/map-repo/scripts/scan.py" \
  --path "<resolved-path>" \
  --depth "<shallow|full>" \
  --out "<out-dir>/codemap.json"
```

If `python3` is not available, fall back to `python`. If neither is available, stop and tell the user Python 3.10+ is required.

### Step 2 — Render HTML

Run the renderer:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/map-repo/scripts/render.py" \
  --in "<out-dir>/codemap.json" \
  --out "<out-dir>/codemap.html"
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

## What this skill does NOT do

- It does **not** push anything to GitHub or external services.
- It does **not** modify source files in the target repo. The only writes happen inside `<out-dir>`.
- It does **not** require network access. The HTML is self-contained (inline CSS, no CDN fonts).
