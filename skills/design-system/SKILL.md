---
name: design-system
description: Documents the SmokeyP editorial visual standard used by the codebase-mapper report. Load when the user asks to change the report's palette, typography, layout, or theme; when the user wants to add a new visual section to the HTML; or when reviewing the rendered output for design-quality regressions. Provides the OKLCH palette, font pairing, spacing scale, component patterns, and the principles that hold them together.
allowed-tools: Read
version: 0.1.0
---

# SmokeyP Codebase Map — Visual Standard

This is the reference for the visual language used by `skills/map-repo/scripts/render.py`. When the user asks for design changes, edit the CSS in `render.py` while preserving the principles below.

## Design intent (the why)

The report is a **client-deliverable architecture audit**, not a developer dashboard. Three operating principles:

1. **Editorial feel over dashboard feel.** Serifs for headings, generous vertical rhythm, restrained accent color, sentences over labels. The reader is a stakeholder skimming the document, not a developer hunting for a value.
2. **Print is a first-class output.** Every styling decision must survive headless-Chrome PDF rendering. No web-only effects (no `position: sticky`, no JS animations, no CDN-loaded fonts). Page breaks are explicit at `<h2>` boundaries.
3. **Self-contained file.** All CSS is inlined; no external resources. Anyone receiving the HTML can open it offline, print it, email it, attach it.

## Palette (OKLCH)

All colors are declared in OKLCH so lightness adjustments preserve hue. When asked to change the palette, change *only the variable definitions* in `:root` — never search-and-replace through the CSS.

| Token | Value | Role |
|---|---|---|
| `--bg` | `oklch(99% 0.006 60)` | Page background — warm off-white |
| `--surface` | `oklch(100% 0 0)` | Card / panel background — pure white |
| `--ink` | `oklch(20% 0.012 250)` | Primary text — near-black cool slate |
| `--ink-2` | `oklch(38% 0.012 250)` | Secondary text — body copy in cards |
| `--muted` | `oklch(60% 0.008 250)` | Tertiary text — meta, captions, labels |
| `--accent` | `oklch(58% 0.20 30)` | Brand accent — ember/coral (warm) |
| `--accent-deep` | `oklch(45% 0.20 30)` | Accent for links and buttons (more legible) |
| `--accent-soft` | `oklch(96% 0.04 30)` | Accent background tint |
| `--border` | `oklch(93% 0.006 60)` | Card / section divider |
| `--border-soft` | `oklch(96% 0.004 60)` | Row dividers in tables |
| `--code-bg` | `oklch(96% 0.005 60)` | Inline code, monospace blocks |

**Rules:**
- Only `--accent` and `--accent-deep` ever carry chroma > 0.05. Everything else is near-neutral. This is what keeps the report from feeling "designed by a developer."
- Never introduce a second accent color in v0.1.0. If a stakeholder asks for a second accent, push back — semantic categories should be encoded by *position and weight*, not color.
- For dark mode (future), invert lightness values but keep the same hue + chroma. The OKLCH structure makes this safe.

## Typography

Three stacks, all system fonts (no network dependency):

| Variable | Stack | Use |
|---|---|---|
| `--font-serif` | Iowan Old Style → Apple Garamond → Baskerville → Times New Roman | All headings, the README quote block |
| `--font-sans` | ui-sans-serif → system-ui → Segoe UI → Roboto → Helvetica Neue | Body, captions, table cells |
| `--font-mono` | ui-monospace → SF Mono → Cascadia Code → JetBrains Mono | Code, file paths, version strings, eyebrow labels |

**Pairing rationale:** the serif/sans contrast is the only "decorative" move in the system. Headings carry weight through *type contrast*, not size alone. Body sans-serif gives modern legibility at smaller sizes; monospace creates a clear visual separator for code-like content (file paths, versions, package names).

**Scale:** headings use `clamp()` for fluid sizing; body is fixed at 15.5px to balance density and print readability.

## Spacing

Eight-step scale on `--space-1` through `--space-8` (4 → 64 px, roughly geometric). Always reference variables; never hard-code px values in new sections.

Vertical rhythm pattern:
- Inside a card: `--space-3` between elements
- Between cards: `--space-3`
- Between sections: `--space-8` before each `<h2>`
- Page-level margins: `--space-7` (top), `--space-8` (bottom)

## Component patterns

### Cover

Single hero panel at the top with a faint accent gradient. Contains:
- Mono eyebrow ("Codebase Architecture Report")
- Serif H1 with the project name
- Lede sentence with inline `<strong>` highlights
- Stat grid (4 cells: Files, LOC, Languages, Modules)
- Footer eyebrow with scan timestamp and depth

### Card

Default container for any list of repeating entities (modules, future sections):
- White surface, 1px border, 10px radius
- `.head` row with mono name (left) and meta (right)
- `.desc` paragraph if present (description, summary, etc.)
- Optional `.langs` row of pill tags

### Language bar

Horizontal stacked bar where each segment is sized by LOC percentage and colored with the language's linguist color. Always paired with a sortable table directly below — the bar is decoration, the table is the data.

### Tree

Nested `<details>` elements. Each directory shows file count + LOC on the right. Files show language + LOC. The root `<details>` opens by default; descendants are collapsed.

In **print**, `@media print` forces all `<details>` open and replaces the disclosure triangle with a bullet — full content, no interactivity.

### Pills (tags)

`.tag` class — small mono labels with accent-soft background. Used for language tags on modules. Never use pills for action chips (no clicks here) — pills are pure metadata.

## When to break the rules

- **Massive repos (>1000 files in a single directory)**: the language bar starts to look like a single solid color. Add a "top N languages, then 'other'" rollup *in the data*, not in the CSS.
- **Truly long reports (>50 modules)**: switch the card grid from one column to two columns at the page level. Don't make the cards smaller — make the page wider (max-width adjustment).
- **Internal-only reports**: dark mode is OK. Public/client reports stay light because PDFs of dark UI waste ink and look amateur when printed.

## What this skill does NOT do

- It does **not** describe the SmokeyP brand at large (that's a separate marketing skill). It scopes only to the codebase-mapper report's visual language.
- It does **not** prescribe content. Section ordering and copy belong in `map-repo`'s SKILL.md and `render.py`.
