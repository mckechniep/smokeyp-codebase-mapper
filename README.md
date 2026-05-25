# smokeyp-codebase-mapper

> A Claude Code plugin that scans any repository and produces a polished HTML or PDF architecture report — editorial-quality, self-contained, printable.

`/smokeyp-codebase-mapper:map-repo` walks a codebase, parses the dependency manifests, detects modules and entry points, extracts the README intent, and renders everything as a single self-contained HTML file. With Chrome installed, it also prints to PDF. Built for client deliverables, onboarding docs, and architectural audits.

## What's in a report

- **Cover** — project name, primary language, file count, LOC, language count
- **README extract** — first paragraph and headings, so the document opens with context
- **Languages** — stacked share bar + sortable table with file counts and lines
- **Top-level modules** — each `src/`, `lib/`, `cmd/`, `apps/`, `packages/` child as a card with description (auto-detected from README, `package.json`, or `__init__.py` docstring)
- **Entry points** — `main.*`, `index.*`, `cmd/*/main.go`, `bin/*` and friends
- **External dependencies** — pulled from `package.json`, `requirements.txt`, `pyproject.toml`, `go.mod`, `Cargo.toml`, `Gemfile`, `composer.json`, `pom.xml`, `build.gradle`
- **Directory tree** — collapsible on screen, fully expanded in print

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
/smokeyp-codebase-mapper:map-repo [path?] [--format html|pdf|both] [--depth shallow|full] [--out PATH]
```

| Flag | Default | Description |
|---|---|---|
| `path` | current directory | Path to scan |
| `--format` | `both` | Output format: `html`, `pdf`, or `both` |
| `--depth` | `shallow` | `shallow` truncates tree to 2 levels and limits lists; `full` includes everything |
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

## How it works

The plugin is two skills:

1. **`map-repo`** — the slash command. Orchestrates a three-step pipeline: `scan.py` → `render.py` → `to-pdf.sh`. The skill itself doesn't do parsing; it shells out to the scripts.
2. **`design-system`** — a knowledge-only skill that documents the visual standard (palette, typography, spacing, component patterns). Loaded when the user wants to customize the report's look.

The scanner is intentionally simple. Language detection is by file extension; dependency parsing is light regex. This keeps the plugin Python-stdlib-only and means it just works without `pip install`.

## Customizing the report

Ask Claude. For example:

> "Make the cover use a deep blue accent instead of ember."

Claude will load the `design-system` skill, edit `:root` in `render.py`, and re-render. The skill documents which variables to touch and which principles to preserve.

## Roadmap

- **v0.2.0** — module-to-module dependency graph (mermaid)
- **v0.3.0** — multi-language AST parsing via tree-sitter (better import accuracy)
- **v0.4.0** — diff mode (`map-repo --vs main`) to highlight architectural drift between branches

## Contributing

Issues and PRs welcome. See `LICENSE` (MIT).

## License

MIT. See [LICENSE](LICENSE).
