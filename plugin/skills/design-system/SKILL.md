---
name: design-system
description: Documents the SmokeyP Labs "Workshop" visual standard used by the codebase-mapper report. Load when the user asks to change the report's palette, typography, layout, or theme; when the user wants to add a new visual section to the HTML; or when reviewing the rendered output for design-quality regressions. Provides the Workshop palette (light + dark), the inlined font stack, the spacing/geometry scale, component patterns, and the principles that hold them together.
allowed-tools: Read
version: 0.2.0
---

# SmokeyP Codebase Map — Visual Standard ("Workshop")

This is the reference for the visual language used by `skills/map-repo/scripts/render.py`. When the user asks for design changes, edit the CSS in `render.py` while preserving the principles below.

The skin is a port of the **SmokeyP Labs field-report template** (`assets/smokeyp-labs-template-{light,dark}-v1.html`). Same machined "workshop" identity: a crest masthead, a metadata readout strip, numbered section blocks, corner-bracket detailing, and a faint circuit-grid + grain atmosphere.

## Two themes, one design

The report ships **Workshop Light** by default and **Workshop Dark** behind `--theme dark` (renderer flag) which emits `<html data-theme="dark">`. They are the *same design* — only the `:root` palette differs. Light is the print/PDF-safe default and the right choice for client deliverables; dark is a striking on-screen variant that is ink-heavy if printed.

To add a new theme, add a `:root[data-theme="<name>"]{…}` override block (see the "parked presets" — Terminal, Blueprint — in the template head for ready-made palettes) and thread the choice through `render.py`'s `--theme` argument.

## Design intent (the why)

The report is a **client-deliverable architecture audit** with a workshop/field-report personality. Operating principles:

1. **Machined, not corporate.** Uppercase condensed display type, mono labels, two-digit section indices, hairline rules, corner brackets. It should read like an instrument readout, not a SaaS dashboard.
2. **Print is a first-class output.** Every decision must survive headless-Chrome PDF rendering. No web-only effects beyond the dependency-free focus interactions (which degrade to the full static figure in print). The atmosphere layers (`body::before`/`::after`) are stripped in `@media print`; `print-color-adjust: exact` paints the chosen paper + panel backgrounds into the PDF.
3. **Self-contained file.** All CSS, **fonts** (base64 woff2 in `theme_assets.py`), and the **crest** (base64 webp data URI) are inlined; no external resources. Anyone receiving the HTML can open it offline, print it, email it, attach it.

## Palette

Colors are plain hex, declared once in `:root`. **Change only the variable definitions** — never search-and-replace through the CSS.

### Workshop Light (default)

| Token | Value | Role |
|---|---|---|
| `--bg` | `#f1ebdf` | Page base — warm cream paper |
| `--bg-elev` | `#faf6ec` | Raised panels / cards |
| `--bg-sink` | `#e6dccb` | Inset wells / code blocks |
| `--ink` | `#211a10` | Primary text — warm espresso |
| `--ink-dim` | `#6b6150` | Muted / labels |
| `--ink-faint` | `#a89d86` | Hairline annotations / diagram strokes |
| `--gold` | `#9c6a15` | Primary accent — deep amber |
| `--gold-deep` | `#6f4a0e` | Borders, section indices, links |
| `--rust` | `#a8421d` | Secondary accent — the ember |
| `--line` | `#dcd3bf` | Hairlines / borders |
| `--ok` / `--warn` / `--stop` | `#5e7a30` / `#a9741a` / `#b0411f` | Status colors |

Workshop Dark swaps the same tokens (near-black `#0c0b0a` base, cream `#e9e2d2` ink, gold `#d9a441`, rust `#c05a2b`) in the `:root[data-theme="dark"]` block.

### Compatibility aliases (important)

The report's component + diagram CSS predates this skin and references an older token vocabulary. Those names are kept as **aliases pointing at the Workshop tokens**, so re-skinning is a single edit point:

```
--surface → --bg-elev    --accent      → --gold       --code-bg → --bg-sink
--ink-2   → --ink-dim     --accent-deep → --gold-deep  --border  → --line
--muted   → --ink-faint   --accent-soft → soft gold wash
--font-serif/sans → --f-body   --font-mono → --f-mono
```

When you change the palette, edit the **Workshop tokens** at the top of `:root`; the aliases (and therefore every card, table, tree, dep row, and diagram SVG fill) follow automatically. Do not "fix" a component by editing its rule — fix the token.

**Rules:**
- Gold and rust are the only chromatic accents. Keep neutrals neutral. Gold = primary/structure, rust = "pay attention" (field notes, the footer tick). Status uses `--ok/--warn/--stop`.
- Diagram edge *types* stay distinguishable by their own treatment (import = faint `--ink-faint`, HTTP = dashed blue, store = brand color) — that distinction is semantic, not decorative; preserve it.

## Typography

Three faces, **inlined** as base64 woff2 in `theme_assets.FONTS_CSS` (no network dependency):

| Variable | Face | Use |
|---|---|---|
| `--f-display` | **Saira Condensed** (700/800) | `h1`/`h2`, the masthead title, section indices, footer slogan — uppercase, machined |
| `--f-body` | **Saira** (400/500) | Body, captions, table cells, the README quote (kept legible, *not* condensed) |
| `--f-mono` | **JetBrains Mono** (400/700) | Code, file paths, version strings, kicker/eyebrow/label chrome, the meta-strip |

`--font-serif` is aliased to `--f-body` (Saira) so prose/quote rules stay readable; real headings are promoted to `--f-display` explicitly. To change fonts, regenerate `theme_assets.py` and update the `--f-*` stacks together.

**Scale:** headings use `clamp()` for fluid sizing; body is fixed at 16px. The masthead title runs up to 60px; section `h2`s are uppercase 20–26px with the numeric index in front.

## Spacing & geometry

- Eight-step spacing scale `--space-1`…`--space-8` (4 → 64 px). Always reference variables.
- `--radius: 3px` — sharp, machined (not rounded). `--tick: 9px` — corner-bracket arm length. `--maxw: 980px` — reading column.
- Section rhythm: `--space-8` before each `<h2>`; the eyebrow (`.section-eyebrow`) absorbs that gap when present so it hugs its heading.

## Component patterns

### Masthead (`render_cover`)

`<header class="masthead">` — the cover. A framed **masthead image** (the `.crest` slot, corner-bracketed) beside `.head-text`: a mono `.kicker` ("SmokeyP Labs // Codebase Map"), the uppercase condensed `.title`, a `.subtitle`, and a `.status` pill with a pulsing LED. Followed by a `.meta-strip` readout (Scanned / Primary / Files / Lines / Languages / Modules) and the `.report-explainer` aside. It is a `<header>`, not a `<section>`, so it is not numbered.

The masthead image is inlined from `theme_assets.py`, which carries two: `MAPPER_URI` (the GPT_SmokeyP "cartographer" scene — **current**, framed as a 5:4 photo) and `CREST_URI` (the round emblem — kept for an instant revert). To switch, change the one constant `render_cover` references and re-render; the round emblem wants `object-fit: contain` + `border-radius: 50%` back on `.crest img`.

### Numbered section heads (CSS counters)

Every `<main > section>` increments a CSS `counter(section)`; each `h2` renders `01`, `02`, … via `::before`, with a gradient rule via `::after`. **No per-section markup** — keep section headings as a single direct-child `<h2>` so numbering stays correct (one index per section, no dupes).

### Corner brackets (`.bracket`)

Opt-in machined detail: two L-shaped gold ticks on opposing corners, via `::before`/`::after`. Applied to the crest and any panel that should read as an instrument readout.

### Atmosphere

`body::before` (vignette + circuit grid) and `body::after` (SVG grain), fixed and behind `main` (z-index 2). Both are disabled in `@media print`.

### Card / Language bar / Tree / Pills / Field note

- **Card** — `--bg-elev` surface, 1px `--line`, 3px radius; mono name + meta head, body `.desc`, optional `.langs` pills.
- **Language bar** — stacked LOC bar in linguist colors, always paired with the sortable table below.
- **Tree** — nested `<details>`; `@media print` forces all open and swaps the triangle for a bullet.
- **Pills (`.tag`)** — small mono labels on a soft-gold wash; metadata only, never action chips.
- **Field note** — left-rust-bordered callout for gotchas/assumptions.

### Footer (`.foot`)

Two-part machined strip: a condensed uppercase `.slogan` (rust tick) on the left, a mono `.est` block (tool version + "SmokeyP Labs · Est. 2024") on the right.

## When to break the rules

- **Massive repos (>1000 files in one directory):** roll up "top N languages, then other" *in the data*, not the CSS.
- **Truly long reports (>50 modules):** widen the page (`--maxw`) before shrinking cards.
- **Client PDFs:** keep `--theme light`. Dark prints heavy and reads amateur on paper; reserve it for on-screen `--format html`.

## What this skill does NOT do

- It does **not** describe the SmokeyP brand at large (that's a separate marketing skill). It scopes only to the codebase-mapper report's visual language.
- It does **not** prescribe content. Section ordering and copy belong in `map-repo`'s SKILL.md and `render.py`.
