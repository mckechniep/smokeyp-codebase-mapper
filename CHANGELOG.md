# Changelog

All notable changes to **smokeyp-codebase-mapper** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — 2026-06-07

First stable release. The 0.x series built the scanner, the five-diagram report,
the LLM evaluation layer, and broad language/framework coverage; 1.0.0 wraps all
of it in a studio-grade visual identity and commits to the public API.

### Added
- **SmokeyP Labs "Workshop" design system** — a field-report skin: framed photo
  masthead (the GPT_SmokeyP "cartographer"), numbered section heads, a
  circuit-grid + grain atmosphere, machined corner brackets, a status pill, a
  scan-time badge, and a metadata readout strip.
- **Light and dark themes** from a single design. Light (warm cream) is the
  default and print-safe; `--theme dark` emits the near-black variant via
  `:root[data-theme="dark"]`.
- **Inlined typography and imagery** — Saira Condensed / Saira / JetBrains Mono
  (base64 woff2) and the masthead artwork are embedded, so the report stays
  fully self-contained and renders identically offline and in print.
- `--theme {light|dark}` CLI flag, exposed as a `map-repo` slash-command argument.

### Changed
- The report's existing component and diagram CSS tokens are aliased to the
  Workshop palette, so the entire report re-skins from a single `:root` edit point.
- The print path now paints the chosen paper and panel colours into the PDF via
  `print-color-adjust: exact`.
- README gains a hero image; the `design-system` skill is rewritten to document
  the Workshop standard.

### Fixed
- Dark-theme legibility pass (verified with composited WCAG contrast): scoped a
  leaked global `.meta` selector that was boxing every tree/card/lineage label,
  lifted `--ink-faint`, and made the service-topology and system-map connector
  lines and arrowheads theme-adaptive — previously ~1.5–2.5:1 and effectively
  invisible on the near-black canvas.

## [0.10.0] — 2026-06-06

- Flow-edge validation drops fabricated flow couplings before they render.
- Product-scoping: headline metrics and diagrams exclude vendored / dependency
  code, shown separately as an "incl. dependencies" total.
- Ecto data-lineage: Elixir schemas map to Postgres, detected from `config/*.exs`
  and `postgrex`.

## [0.9.0] — 2026-06-05

- Elixir / Phoenix support: `.ex`/`.exs` import parsing and Phoenix-router
  endpoint detection feed the dependency matrix and service topology.
- Enrichment-override path so the LLM evaluation can correct misclassifications
  it spots while reading the source.

## [0.8.0] — 2026-06-04

- **System Map** hero: a layered-bands overview of services and modules with
  import / HTTP / data-store edges, per-service facet small-multiples, and
  vendored-code exclusion.
- Full-coverage **Key Flows** — one cited execution flow per HTTP route group.
- Dependency-free focus interactions on the System Map and Service Topology that
  degrade to the complete static figure in print.

## [0.7.0] — 2026-06-02

- AST-accurate import extraction via tree-sitter when the `ast-grep` binary is
  present (one batched scan, ~0.1s on large monorepos; full regex fallback).
- Semantic (grepai) indexing no longer builds by default — opt in with
  `--semantic`; otherwise an already-warm index is used if present.

## [0.6.1] — 2026-06-01

- Reliable semantic indexing on large repos: waits for grepai's own completion
  signal, scales the timeout with repo size, fails honestly (and removes the
  partial index) instead of reporting a corrupted one as built, and never
  deletes a user-managed `.grepai/` index.

## [0.6.0] — 2026-05-31

- Optional semantic code retrieval for the LLM evaluation pass (`grepai` + a
  local Ollama embedding model), auto-detected; `--no-semantic` to skip. The
  deterministic scan and renderer are untouched, so reports stay reproducible.

## [0.5.2] — 2026-05-31

- Dependency rows whose "version" is a long non-semver value (a local tarball
  path or git URL) wrap that value onto its own line instead of collapsing the
  package name into vertical one-character-per-line text.

## [0.5.1] — 2026-05-31

- External-dependency entries no longer overlap (name/version columns, with
  long/scoped names wrapping) plus a `*`-version legend; Key-flows step numbers
  align with their text at any step height.

## [0.5.0] — 2026-05-31

- Interactive, beginner-friendly report: click-to-expand language profiles, a
  Key-flows board of collapsible lanes grouped by trigger kind, an auto-populated
  glossary of the tools/libraries named in the report, and an explanation of
  faded "vendored" modules. Plus monorepo-wide and Elixir (`mix.exs`) dependency
  detection.

## [0.4.0] — 2026-05-30

- LLM evaluation layer (on by default; `--no-llm` to skip): a code-derived
  overview, product-vs-vendored classification, per-product-module descriptions,
  and a cited "Key flows" section. Plus Elixir import parsing and JS/TS
  workspace-package (`@scope/pkg`) resolution.

## [0.3.x] and earlier — 2026-05-25 → 2026-05-29

- Foundational work: monorepo-aware recursive module detection; the five
  deterministic static-SVG diagrams (Bertin dependency matrix, C4 service
  topology, critical-paths swimlane, Sankey data lineage) with per-diagram
  architect observations and supporting small-multiples; HTTP framework and ORM
  coverage; entry-point and dependency detection; the `--depth` tiers. The
  D3/force-simulation runtime was removed in favour of print-first static SVG,
  and the project was restructured into a Claude Code plugin.
