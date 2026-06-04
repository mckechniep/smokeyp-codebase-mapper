#!/usr/bin/env python3
"""HTML renderer for smokeyp-codebase-mapper.

Reads the JSON data model produced by scan.py and emits a single
self-contained HTML file. No external dependencies, no CDNs.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from html import escape
from pathlib import Path
from typing import Any


# -------- CSS -----------------------------------------------------------

CSS = r"""
:root {
  --bg:           oklch(99% 0.006 60);
  --surface:      oklch(100% 0 0);
  --ink:          oklch(20% 0.012 250);
  --ink-2:        oklch(38% 0.012 250);
  --muted:        oklch(60% 0.008 250);
  --accent:       oklch(58% 0.20 30);
  --accent-deep:  oklch(45% 0.20 30);
  --accent-soft:  oklch(96% 0.04 30);
  --border:       oklch(93% 0.006 60);
  --border-soft:  oklch(96% 0.004 60);
  --code-bg:      oklch(96% 0.005 60);
  --shadow:       0 1px 2px oklch(20% 0.01 250 / 0.04), 0 8px 32px oklch(20% 0.01 250 / 0.04);

  --font-serif: "Iowan Old Style", "Apple Garamond", Baskerville, "Times New Roman", "Droid Serif", Times, "Source Serif Pro", serif;
  --font-sans:  ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --font-mono:  ui-monospace, "SF Mono", "Cascadia Code", "JetBrains Mono", "Roboto Mono", Consolas, "Liberation Mono", monospace;

  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;
  --space-7: 48px;
  --space-8: 64px;

  --radius: 10px;
}

* { box-sizing: border-box; }

html, body {
  margin: 0;
  padding: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: var(--font-sans);
  font-size: 15.5px;
  line-height: 1.55;
  -webkit-font-smoothing: antialiased;
}

main {
  max-width: 780px;
  margin: 0 auto;
  padding: var(--space-7) var(--space-5) var(--space-8);
}

h1, h2, h3, h4 {
  font-family: var(--font-serif);
  font-weight: 600;
  letter-spacing: -0.012em;
  color: var(--ink);
}

h1 {
  font-size: clamp(2.4rem, 1.8rem + 2.2vw, 3.2rem);
  margin: 0 0 var(--space-3);
  line-height: 1.05;
}

h2 {
  font-size: 1.55rem;
  margin: var(--space-8) 0 var(--space-4);
  padding-bottom: var(--space-3);
  border-bottom: 1px solid var(--border);
}

h3 {
  font-size: 1.1rem;
  margin: var(--space-5) 0 var(--space-2);
}

p, ul, ol { margin: 0 0 var(--space-4); }
ul, ol { padding-left: 1.4em; }

a { color: var(--accent-deep); text-decoration: underline; text-decoration-thickness: 1px; text-underline-offset: 2px; }
a:hover { color: var(--accent); }

code, pre, .mono { font-family: var(--font-mono); font-size: 0.92em; }
code { background: var(--code-bg); padding: 0.15em 0.4em; border-radius: 4px; }
pre { background: var(--code-bg); padding: var(--space-3) var(--space-4); border-radius: var(--radius); overflow-x: auto; }
pre code { background: transparent; padding: 0; }

/* ---- Cover ---- */
.cover {
  background: linear-gradient(180deg, var(--surface) 0%, var(--accent-soft) 100%);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--space-7) var(--space-6);
  box-shadow: var(--shadow);
  margin-bottom: var(--space-6);
}
.cover .eyebrow {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--accent-deep);
  margin-bottom: var(--space-3);
}
.cover h1 { margin-bottom: var(--space-4); }
.cover .lede {
  color: var(--ink-2);
  font-size: 1.05rem;
  margin: 0 0 var(--space-5);
  max-width: 56ch;
}

/* ---- Stats row ---- */
.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--space-4);
  margin-top: var(--space-5);
}
.stat {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--space-4);
}
.stat .label {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: var(--space-2);
}
.stat .value {
  font-family: var(--font-serif);
  font-size: 1.8rem;
  font-weight: 600;
  line-height: 1.1;
  color: var(--ink);
}
.stat .unit {
  font-family: var(--font-sans);
  font-size: 0.85rem;
  color: var(--muted);
  margin-left: 4px;
}

/* ---- Language bar ---- */
.lang-bar {
  display: flex;
  height: 14px;
  border-radius: 999px;
  overflow: hidden;
  margin: var(--space-4) 0 var(--space-5);
  box-shadow: inset 0 0 0 1px var(--border);
}
.lang-bar > span {
  display: block;
  height: 100%;
}
.lang-table {
  width: 100%;
  border-collapse: collapse;
}
.lang-table th, .lang-table td {
  text-align: left;
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--border-soft);
  font-size: 0.92rem;
}
.lang-table th {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--muted);
  font-weight: 500;
}
.lang-swatch {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 3px;
  margin-right: var(--space-2);
  vertical-align: middle;
}

/* ---- Languages: click-to-expand per-language profiles ---- */
.lang-row[data-target] { cursor: pointer; }
.lang-row[data-target] td:first-child { user-select: none; }
.lang-caret {
  display: inline-block;
  width: 0.9em;
  margin-right: 4px;
  color: var(--muted);
  transition: transform 150ms ease;
}
.lang-row.is-open .lang-caret { transform: rotate(90deg); color: var(--accent-deep); }
.lang-caret-spacer { display: inline-block; width: 0.9em; margin-right: 4px; }
.lang-row[data-target]:hover td { background: var(--surface); }
.lang-row[data-target]:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.lang-detail-row { display: none; }
.lang-detail-row.is-open { display: table-row; }
.lang-detail {
  padding: var(--space-3) var(--space-4) var(--space-4) !important;
  background: var(--surface);
  border-bottom: 1px solid var(--border-soft);
}
.lang-where {
  display: inline-block;
  font-family: var(--font-mono);
  font-size: 0.68rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--accent-deep);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 2px 10px;
  margin-bottom: var(--space-2);
}
.lang-detail p {
  margin: 0;
  color: var(--ink-2);
  font-size: 0.94rem;
  line-height: 1.6;
  max-width: 72ch;
}
@media print {
  /* PDF export has no JS — show every profile so nothing is lost on paper. */
  .lang-detail-row { display: table-row !important; }
  .lang-caret { transform: rotate(90deg); }
}

/* ---- Cards ---- */
.card-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-3);
}
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--space-4) var(--space-5);
}
.card .head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-4);
  margin-bottom: var(--space-2);
}
.card .name { font-family: var(--font-mono); font-weight: 600; color: var(--ink); }
.card .meta { font-family: var(--font-mono); font-size: 0.78rem; color: var(--muted); }
.card .desc { color: var(--ink-2); font-size: 0.95rem; margin: var(--space-2) 0 0; }
.card .langs {
  margin-top: var(--space-3);
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
.tag {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  letter-spacing: 0.04em;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent-deep);
}

/* ---- Tree ---- */
.tree { font-family: var(--font-mono); font-size: 0.88rem; line-height: 1.6; }
.tree details { padding-left: 14px; }
.tree summary {
  cursor: pointer;
  list-style: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--ink);
  user-select: none;
}
.tree summary::-webkit-details-marker { display: none; }
.tree summary::before {
  content: "▸";
  display: inline-block;
  width: 1em;
  color: var(--muted);
  transition: transform 0.15s ease;
}
.tree details[open] > summary::before { transform: rotate(90deg); }
.tree .file { display: block; padding-left: 22px; color: var(--ink-2); }
.tree .file .meta { float: right; color: var(--muted); font-size: 0.8em; }
.tree .empty { color: var(--muted); padding-left: 22px; font-style: italic; }
.tree .truncated { color: var(--muted); padding-left: 22px; font-style: italic; }

/* ---- Deps table ---- */
.deps-eco { margin: var(--space-4) 0 var(--space-5); }
.deps-eco .title {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: var(--space-2);
}
.deps-eco .title .file { font-family: var(--font-mono); font-size: 0.85rem; color: var(--muted); }
.deps-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: var(--space-2) var(--space-4);
  font-family: var(--font-mono);
  font-size: 0.83rem;
}
/* Name takes the line; a long "version" (e.g. a tarball path or git URL, not a
   real semver) wraps to its OWN line via flex-wrap instead of crushing the name
   down to one-character-per-line. Both sides set min-width:0 + overflow-wrap so
   neither can overrun the column. */
.deps-list .dep {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0 10px;
  min-width: 0;
  border-bottom: 1px solid var(--border-soft);
  padding-bottom: 3px;
}
.deps-list .dep .dep-name { flex: 1 1 auto; min-width: 0; overflow-wrap: anywhere; color: var(--ink); }
.deps-list .dep .ver { flex: 0 1 auto; min-width: 0; overflow-wrap: anywhere; color: var(--muted); }

/* ---- Entry points ---- */
.entries {
  list-style: none;
  padding: 0;
}
.entries li {
  display: flex;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--border-soft);
  font-family: var(--font-mono);
  font-size: 0.9rem;
}
.entries li:last-child { border-bottom: 0; }
.entries .kind { color: var(--muted); }

/* ---- README extract ---- */
.readme-quote {
  margin: var(--space-3) 0 var(--space-4);
  padding: var(--space-4) var(--space-5);
  border-left: 3px solid var(--accent);
  background: var(--surface);
  color: var(--ink-2);
  font-family: var(--font-serif);
  font-style: italic;
  font-size: 1.05rem;
  line-height: 1.55;
  border-radius: 0 var(--radius) var(--radius) 0;
}
.readme-headings {
  list-style: none;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--space-2);
  font-family: var(--font-mono);
  font-size: 0.85rem;
}
.readme-headings li {
  background: var(--code-bg);
  padding: 6px 10px;
  border-radius: 6px;
  color: var(--ink-2);
}

/* ---- Section intros (beginner explanations) ---- */
.section-intro {
  color: var(--ink-2);
  font-family: var(--font-serif);
  font-style: italic;
  font-size: 1.02rem;
  line-height: 1.6;
  margin: 0 0 var(--space-5);
}

/* Plain explanatory paragraphs under a section intro (e.g. modules). Kept
   sans/non-italic so they read as "notes" against the editorial intro. */
.module-note {
  color: var(--ink-2);
  font-size: 0.95rem;
  line-height: 1.6;
  margin: 0 0 var(--space-3);
  max-width: 72ch;
}
.module-note .vendored-badge { margin-left: 0; }

.report-explainer {
  margin: var(--space-5) 0 var(--space-3);
  padding: var(--space-4) var(--space-5);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--ink-2);
  font-size: 0.96rem;
  line-height: 1.6;
}
.report-explainer strong { color: var(--ink); }

/* ---- Glossary ---- */
.glossary-group { margin-bottom: var(--space-5); }
.glossary-group .group-label {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: var(--space-3);
}
.glossary dl { margin: 0; }
.glossary dt {
  font-family: var(--font-mono);
  font-weight: 600;
  color: var(--ink);
  margin-top: var(--space-3);
  font-size: 0.92rem;
}
.glossary dd {
  margin: 4px 0 0 0;
  color: var(--ink-2);
  font-size: 0.94rem;
  line-height: 1.55;
}

/* ---- Footer ---- */
footer {
  margin-top: var(--space-8);
  padding-top: var(--space-5);
  border-top: 1px solid var(--border);
  font-family: var(--font-mono);
  font-size: 0.78rem;
  color: var(--muted);
  text-align: center;
}
footer .brand { color: var(--accent-deep); font-weight: 600; }

/* ---- Diagram ---- */
.diagram-note {
  font-family: var(--font-serif);
  font-style: italic;
  color: var(--muted);
  font-size: 0.94rem;
  margin: var(--space-2) 0;
}

/* ---- Module dependency matrix (replaces force module graph) ---- */
.modgraph-frame {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: var(--space-5) var(--space-5) var(--space-4);
  margin-bottom: var(--space-4);
  /* Escape past main's 780px text column on wider viewports so the
     matrix can breathe. Collapses back to 0 on narrow screens. */
  margin-left: -56px;
  margin-right: -56px;
}
@media (max-width: 880px) {
  .modgraph-frame {
    margin-left: 0;
    margin-right: 0;
  }
}
.modgraph-matrix-wrap {
  overflow-x: auto;
  margin: 0 calc(var(--space-5) * -1);
  padding: 0 var(--space-5);
}

/* ---- System map (layered-bands hero) ---- */
.sysmap-frame {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: var(--space-5) var(--space-5) var(--space-4);
  margin-bottom: var(--space-4);
  margin-left: -56px;
  margin-right: -56px;
}
@media (max-width: 880px) {
  .sysmap-frame { margin-left: 0; margin-right: 0; }
}
.sysmap-wrap { overflow-x: auto; }
.sysmap-headline {
  font-size: 1.05rem;
  color: var(--ink-2);
  margin: 0 0 var(--space-4);
}
.sysmap-excluded { color: var(--muted); }
.sysmap-band-label {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.14em;
  fill: var(--muted);
}
.sysmap-cluster-label {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
}
.sysmap-cluster-kind { font-weight: 400; opacity: 0.7; font-size: 10px; }
.sysmap-node-rect {
  fill: var(--surface);
  stroke: oklch(70% 0.01 250);
  stroke-width: 1.25;
}
.sysmap-node.is-entry .sysmap-node-rect {
  stroke: var(--accent);
  stroke-width: 1.5;
}
.sysmap-node-label {
  font-family: var(--font-mono);
  font-size: 12px;
  fill: var(--ink);
}
.sysmap-entry-badge { font-size: 12px; fill: var(--accent); }
.sysmap-endpoint-count {
  font-family: var(--font-mono);
  font-size: 10px;
  fill: var(--muted);
}
.sysmap-store-label {
  font-family: var(--font-mono);
  font-size: 11px;
  fill: var(--ink-2);
}
.sysmap-edge-import { stroke: oklch(60% 0.01 250 / 0.55); }
.sysmap-edge-http { stroke: oklch(58% 0.14 250 / 0.8); stroke-dasharray: 5 4; }
.sysmap-legend {
  display: flex;
  gap: var(--space-4);
  flex-wrap: wrap;
  margin-top: var(--space-3);
  font-size: 0.8rem;
  color: var(--muted);
  font-family: var(--font-mono);
}
.sysmap-leg-item { display: inline-flex; align-items: center; gap: 6px; }
.sysmap-leg-http, .sysmap-leg-import, .sysmap-leg-store {
  display: inline-block; width: 26px; height: 0;
}
.sysmap-leg-http { border-top: 2px dashed oklch(58% 0.14 250 / 0.8); }
.sysmap-leg-import { border-top: 2px solid oklch(60% 0.01 250 / 0.55); }
.sysmap-leg-store { border-top: 2px solid #336791; }
.sysmap-note { font-size: 0.85rem; color: var(--muted); margin-top: var(--space-3); }

/* ---- System map: focus + layer toggles ---- */
.sysmap-controls { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 var(--space-3); align-items: center; }
.sysmap-chip {
  font-family: var(--font-mono); font-size: 0.78rem; cursor: pointer;
  border: 1px solid var(--border); border-radius: 999px; padding: 3px 12px;
  background: var(--surface); color: var(--ink-2); user-select: none;
  transition: background var(--duration-fast, 150ms), color var(--duration-fast, 150ms), opacity var(--duration-fast, 150ms);
}
.sysmap-chip[aria-pressed="false"] { opacity: 0.45; text-decoration: line-through; }
.sysmap-chip:hover { border-color: var(--accent); }
.sysmap-hint { font-size: 0.78rem; color: var(--muted); margin-left: auto; }

/* default: nothing dimmed. when a node/cluster is focused, fade the rest. */
.sysmap-svg .sysmap-node, .sysmap-svg [class^="sysmap-edge"], .sysmap-svg .sysmap-store {
  transition: opacity 140ms ease;
}
.sysmap-svg.has-focus .sysmap-node:not(.is-active),
.sysmap-svg.has-focus [class^="sysmap-edge"]:not(.is-active),
.sysmap-svg.has-focus .sysmap-store:not(.is-active) { opacity: 0.10; }
.sysmap-svg .sysmap-node.is-active .sysmap-node-rect { stroke-width: 2; }

/* node hover affordance */
.sysmap-svg .sysmap-node { cursor: pointer; }
.sysmap-svg .sysmap-node:focus { outline: none; }
.sysmap-svg .sysmap-node:focus .sysmap-node-rect { stroke: var(--accent); stroke-width: 2; }

/* layer toggles hide edge kinds / orphans */
.sysmap-svg.hide-import [data-kind="import"],
.sysmap-svg.hide-http [data-kind="http"],
.sysmap-svg.hide-store [data-kind="store"] { display: none; }
.sysmap-svg.hide-orphan .sysmap-node[data-orphan="1"] { display: none; }

/* Bento beneath the map — same grid/tile pattern as .modgraph-bento. */
.sysmap-bento {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-3);
  margin-top: var(--space-3);
}
.sysmap-tile {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--space-4) var(--space-4) var(--space-3);
  display: flex;
  flex-direction: column;
  min-height: 220px;
}
.sysmap-tile .tile-label {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: var(--space-2);
}
.sysmap-tile .tile-headline {
  font-family: var(--font-serif);
  font-size: 1rem;
  color: var(--ink);
  margin: 0 0 var(--space-3);
  line-height: 1.35;
}
.sysmap-tile .tile-body { flex: 1; }
.sysmap-rows { display: flex; flex-direction: column; gap: 6px; font-family: var(--font-mono); font-size: 0.82rem; color: var(--ink-2); }
.sysmap-row { display: flex; justify-content: space-between; gap: 12px; }
.sysmap-row .v { color: var(--ink); font-weight: 600; white-space: nowrap; }

/* Per-service facet maps (static small-multiples below the overview). */
.sysmap-facets { margin-top: var(--space-5); }
.sysmap-facets > h3 { font-family: var(--font-serif); margin: 0 0 var(--space-2); }
.sysmap-facet-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--space-3); }
@media (max-width: 760px) { .sysmap-facet-grid { grid-template-columns: 1fr; } }
.sysmap-facet-card {
  margin: 0; background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: var(--space-3);
}
.sysmap-facet-card figcaption {
  font-family: var(--font-mono); font-size: 0.82rem; color: var(--ink-2);
  margin-bottom: var(--space-2);
}
.sysmap-facet-card .sysmap-facet-stat { color: var(--muted); }
.sysmap-facet-card .sysmap-facet-rel { display: block; color: var(--muted); font-size: 0.76rem; margin-top: 2px; }
@media print { .sysmap-facet-grid { grid-template-columns: 1fr 1fr; } }
.modgraph-matrix {
  display: block;
  margin: 0 auto;
  overflow: visible;
}
.modgraph-cell { transition: fill-opacity 0.12s ease; }
.modgraph-cell:hover { fill-opacity: 1 !important; }
.modgraph-row-band, .modgraph-col-band {
  pointer-events: none;
  fill: var(--accent);
  fill-opacity: 0;
  transition: fill-opacity 0.12s ease;
}
.modgraph-hovered .modgraph-row-band[data-active="1"],
.modgraph-hovered .modgraph-col-band[data-active="1"] {
  fill-opacity: 0.05;
}
.modgraph-label {
  font-family: var(--font-mono);
  fill: var(--ink-2);
  pointer-events: none;
}
.modgraph-label.is-active { fill: var(--ink); font-weight: 600; }
.modgraph-svc-bar {
  /* Service-color stripe in the outer margin */
}
.modgraph-svc-line {
  stroke: var(--ink);
  stroke-opacity: 0.18;
  stroke-width: 1.25;
  shape-rendering: crispEdges;
}
.modgraph-domain-line {
  stroke: var(--ink);
  stroke-opacity: 0.08;
  stroke-width: 1;
  stroke-dasharray: 3 4;
  shape-rendering: crispEdges;
}
.modgraph-diag {
  fill: var(--border);
  fill-opacity: 0.55;
}
.modgraph-axis-title {
  font-family: var(--font-mono);
  /* font-size is set inline (SVG user units) so it scales with the diagram
     and stays larger than the module labels — see render_module_graph_section. */
  letter-spacing: 0.06em;
  text-transform: uppercase;
  fill: var(--ink-2);
}
.modgraph-headline {
  font-family: var(--font-serif);
  font-size: 1.05rem;
  line-height: 1.5;
  color: var(--ink-2);
  margin: 0 0 var(--space-4);
  max-width: 64ch;
}
.modgraph-headline strong { color: var(--ink); font-weight: 600; }
.modgraph-headline em {
  font-style: normal;
  font-family: var(--font-mono);
  font-size: 0.92em;
  color: var(--accent-deep);
}
.modgraph-tip {
  position: absolute;
  pointer-events: none;
  background: var(--ink);
  color: var(--surface);
  padding: 6px 10px;
  border-radius: 6px;
  font-family: var(--font-mono);
  font-size: 0.78rem;
  line-height: 1.4;
  opacity: 0;
  transition: opacity 0.1s ease;
  z-index: 10;
  white-space: nowrap;
  box-shadow: 0 4px 12px oklch(20% 0.012 250 / 0.18);
}
.modgraph-tip .t-meta { color: oklch(85% 0.01 60); }
.modgraph-tip .t-arrow { color: var(--accent-soft); }

/* ---- Bento small-multiples (module section) ---- */
.modgraph-bento {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-3);
  margin-top: var(--space-3);
}
.modgraph-tile {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--space-4) var(--space-4) var(--space-3);
  display: flex;
  flex-direction: column;
  min-height: 220px;
}
.modgraph-tile .tile-label {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: var(--space-2);
}
.modgraph-tile .tile-headline {
  font-family: var(--font-serif);
  font-size: 1rem;
  color: var(--ink);
  margin: 0 0 var(--space-3);
  line-height: 1.35;
}
.modgraph-tile .tile-body { flex: 1; }
.modgraph-tile.is-donut {
  align-items: center;
  text-align: center;
}
.modgraph-tile.is-donut .donut-legend {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: flex-start;
  margin-top: var(--space-3);
  font-family: var(--font-mono);
  font-size: 0.78rem;
  color: var(--ink-2);
  width: 100%;
}
.modgraph-tile.is-donut .donut-legend-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}
.modgraph-tile.is-donut .donut-legend-row .swatch {
  width: 9px; height: 9px; border-radius: 2px; flex: 0 0 auto;
}
.modgraph-tile.is-donut .donut-legend-row .name { flex: 1; }
.modgraph-tile.is-donut .donut-legend-row .pct { color: var(--muted); }
.modgraph-edge-list, .modgraph-entry-list {
  list-style: none;
  padding: 0;
  margin: 0;
  font-family: var(--font-mono);
  font-size: 0.82rem;
}
.modgraph-edge-list li, .modgraph-entry-list li {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-3);
  padding: 6px 0;
  border-bottom: 1px solid var(--border-soft);
}
.modgraph-edge-list li:last-child, .modgraph-entry-list li:last-child {
  border-bottom: none;
}
.modgraph-edge-list .arc {
  color: var(--ink-2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}
.modgraph-edge-list .arc .arrow { color: var(--muted); margin: 0 6px; }
.modgraph-edge-list .arc .svc {
  color: var(--muted);
  font-size: 0.85em;
}
.modgraph-edge-list .weight, .modgraph-entry-list .count {
  font-family: var(--font-sans);
  font-size: 0.78rem;
  color: var(--accent-deep);
  background: var(--accent-soft);
  padding: 1px 8px;
  border-radius: 999px;
  flex: 0 0 auto;
}
.modgraph-entry-list .mod-name {
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}
.modgraph-entry-list .mod-svc { color: var(--muted); font-size: 0.85em; margin-left: 4px; }
.modgraph-langs-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-content: flex-start;
}
.modgraph-langs-cloud .lang-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 9px;
  border-radius: 999px;
  background: var(--code-bg);
  border: 1px solid var(--border);
  font-family: var(--font-mono);
  font-size: 0.78rem;
  color: var(--ink-2);
}
.modgraph-langs-cloud .lang-pill .swatch {
  width: 8px; height: 8px; border-radius: 50%;
}
.modgraph-langs-cloud .lang-pill .share {
  color: var(--muted);
  font-size: 0.9em;
}
.modgraph-empty {
  color: var(--muted);
  font-style: italic;
  font-size: 0.9rem;
}

/* ---- Service topology v2 (C4-style) ---- */
.topov2-frame {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: var(--space-5) var(--space-5) var(--space-4);
  margin-bottom: var(--space-4);
  /* Slightly wider escape than the matrix so a 3-service horizontal
     C4 layout (220×3 + 70×2 + 40 ≈ 840px) fits without scrolling. */
  margin-left: -72px;
  margin-right: -72px;
  position: relative;
}
@media (max-width: 920px) {
  .topov2-frame { margin-left: 0; margin-right: 0; }
}
.topov2-headline {
  font-family: var(--font-serif);
  font-size: 1.05rem;
  line-height: 1.5;
  color: var(--ink-2);
  margin: 0 0 var(--space-4);
}
.topov2-headline strong { color: var(--ink); font-weight: 600; }
.topov2-headline em {
  font-style: normal;
  font-family: var(--font-mono);
  font-size: 0.92em;
  color: var(--accent-deep);
}
.topov2-wrap {
  overflow-x: auto;
  margin: 0 calc(var(--space-5) * -1);
  padding: 0 var(--space-5);
}
.topov2-svg { display: block; margin: 0 auto; overflow: visible; }
.topov2-node-bg {
  fill: var(--surface);
  stroke: var(--border);
  stroke-width: 1;
}
.topov2-node-stripe {
  /* The colored top stripe by service kind. fill set per-node. */
}
.topov2-node-title {
  font-family: var(--font-serif);
  font-weight: 600;
  fill: var(--ink);
}
.topov2-node-stack {
  font-family: var(--font-mono);
  fill: var(--ink-2);
}
.topov2-node-stat {
  font-family: var(--font-mono);
  fill: var(--muted);
}
.topov2-kind-chip {
  /* Pill in the top-right of each card. Filled by kind color. */
}
.topov2-kind-chip-text {
  font-family: var(--font-mono);
  font-size: 8.5px;
  letter-spacing: 0.1em;
  fill: white;
  font-weight: 600;
}
.topov2-edge {
  fill: none;
  stroke: var(--ink-2);
  stroke-opacity: 0.55;
  stroke-linejoin: round;
  stroke-linecap: round;
  transition: stroke-opacity 0.15s ease;
}
.topov2-edge:hover { stroke-opacity: 0.95; }
.topov2-edge-label-bg {
  fill: var(--surface);
  stroke: var(--border);
  stroke-width: 1;
}
.topov2-edge-label {
  font-family: var(--font-mono);
  font-size: 10px;
  fill: var(--ink-2);
}

/* ---- Topology v2 bento ---- */
.topov2-bento {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-3);
  margin-top: var(--space-3);
}
.topov2-tile {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--space-4) var(--space-4) var(--space-3);
  display: flex;
  flex-direction: column;
  min-height: 200px;
}
.topov2-tile .tile-label {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: var(--space-2);
}
.topov2-tile .tile-headline {
  font-family: var(--font-serif);
  font-size: 1rem;
  color: var(--ink);
  margin: 0 0 var(--space-3);
  line-height: 1.35;
}
.topov2-tile .tile-body { flex: 1; }
.topov2-call-list { list-style: none; padding: 0; margin: 0; }
.topov2-call-list > li {
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--border-soft);
}
.topov2-call-list > li:last-child { border-bottom: none; }
.topov2-call-list .svc-name {
  font-family: var(--font-mono);
  font-size: 0.86rem;
  color: var(--ink);
  font-weight: 600;
}
.topov2-call-list .neighbours {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 4px 0 0 var(--space-3);
  padding-left: var(--space-3);
  border-left: 2px solid var(--border);
  font-family: var(--font-mono);
  font-size: 0.78rem;
  color: var(--ink-2);
}
.topov2-call-list .neighbours .row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.topov2-call-list .neighbours .count {
  color: var(--accent-deep);
  background: var(--accent-soft);
  padding: 0 7px;
  border-radius: 999px;
  font-size: 0.72rem;
}
.topov2-fw-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-content: flex-start;
}
.topov2-fw-cloud .fw-pill {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--code-bg);
  border: 1px solid var(--border);
  font-family: var(--font-mono);
  font-size: 0.78rem;
  color: var(--ink-2);
}
.topov2-fw-cloud .fw-group {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
  width: 100%;
  margin-top: var(--space-3);
}
.topov2-fw-cloud .fw-group:first-child { margin-top: 0; }
.topov2-stat-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--border-soft);
  font-family: var(--font-mono);
  font-size: 0.82rem;
}
.topov2-stat-row:last-child { border-bottom: none; }
.topov2-stat-row .k { color: var(--ink-2); }
.topov2-stat-row .v { color: var(--ink); font-weight: 600; }
.topov2-stat-row .v.muted { color: var(--muted); font-weight: 400; }
.topov2-tile-foot {
  font-family: var(--font-serif);
  font-style: italic;
  font-size: 0.85rem;
  line-height: 1.55;
  color: var(--muted);
  margin: var(--space-3) 0 0;
  padding-top: var(--space-3);
  border-top: 1px dashed var(--border);
}
.topov2-empty {
  color: var(--muted);
  font-style: italic;
  font-size: 0.9rem;
}

/* ---- Data lineage v2 (Sankey + cylinders) ---- */
.lineage2-frame {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: var(--space-5) var(--space-5) var(--space-4);
  margin-bottom: var(--space-4);
  margin-left: -56px;
  margin-right: -56px;
  position: relative;
}
@media (max-width: 880px) {
  .lineage2-frame { margin-left: 0; margin-right: 0; }
}
.lineage2-headline {
  font-family: var(--font-serif);
  font-size: 1.05rem;
  line-height: 1.5;
  color: var(--ink-2);
  margin: 0 0 var(--space-4);
}
.lineage2-headline strong { color: var(--ink); font-weight: 600; }
.lineage2-headline em {
  font-style: normal;
  font-family: var(--font-mono);
  font-size: 0.92em;
  color: var(--accent-deep);
}
.lineage2-wrap {
  overflow-x: auto;
  margin: 0 calc(var(--space-5) * -1);
  padding: 0 var(--space-5);
}
.lineage2-svg { display: block; margin: 0 auto; overflow: visible; }
.lineage2-svc-bg {
  fill: var(--surface);
  stroke: var(--border);
  stroke-width: 1;
}
.lineage2-svc-title {
  font-family: var(--font-serif);
  font-weight: 600;
  fill: var(--ink);
}
.lineage2-svc-meta {
  font-family: var(--font-mono);
  fill: var(--ink-2);
}
.lineage2-band {
  fill: none;
  stroke-linecap: round;
  transition: stroke-opacity 0.15s ease;
}
.lineage2-band:hover { stroke-opacity: 0.95 !important; }
.lineage2-band-label-bg {
  fill: var(--surface);
  stroke: var(--border);
  stroke-width: 1;
}
.lineage2-band-label {
  font-family: var(--font-mono);
  font-size: 10px;
  fill: var(--ink-2);
}
.lineage2-cyl-body, .lineage2-cyl-top {
  /* fill set per-store */
}
.lineage2-cyl-stroke {
  fill: none;
  stroke-width: 1.25;
}
.lineage2-cyl-name {
  font-family: var(--font-serif);
  font-weight: 600;
  fill: var(--ink);
  font-size: 13.5px;
}
.lineage2-cyl-kind {
  font-family: var(--font-mono);
  font-size: 8.5px;
  letter-spacing: 0.1em;
  fill: var(--muted);
  text-transform: uppercase;
}
.lineage2-cyl-models {
  font-family: var(--font-mono);
  font-size: 10px;
  fill: var(--ink-2);
}
.lineage2-cyl.is-unlinked { opacity: 0.45; }
.lineage2-cyl.is-unlinked .lineage2-cyl-models {
  fill: var(--muted);
  font-style: italic;
}
.lineage2-axis-title {
  font-family: var(--font-mono);
  font-size: 0.62rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  fill: var(--muted);
}

/* ---- Lineage v2 bento ---- */
.lineage2-bento {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-3);
  margin-top: var(--space-3);
}
.lineage2-tile {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--space-4) var(--space-4) var(--space-3);
  display: flex;
  flex-direction: column;
  min-height: 200px;
}
.lineage2-tile .tile-label {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: var(--space-2);
}
.lineage2-tile .tile-headline {
  font-family: var(--font-serif);
  font-size: 1rem;
  color: var(--ink);
  margin: 0 0 var(--space-3);
  line-height: 1.35;
}
.lineage2-tile .tile-body { flex: 1; }
.lineage2-store-list { list-style: none; padding: 0; margin: 0; }
.lineage2-store-list > li {
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--border-soft);
}
.lineage2-store-list > li:last-child { border-bottom: none; }
.lineage2-store-list .store-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-mono);
  font-size: 0.86rem;
  color: var(--ink);
  font-weight: 600;
}
.lineage2-store-list .store-head .swatch {
  width: 10px; height: 10px; border-radius: 2px;
}
.lineage2-store-list .store-head .kind {
  color: var(--muted);
  font-weight: 400;
  font-size: 0.85em;
}
.lineage2-store-list .sources {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 4px 0 0 var(--space-4);
  padding-left: var(--space-3);
  border-left: 2px solid var(--border);
  font-family: var(--font-mono);
  font-size: 0.78rem;
  color: var(--ink-2);
}
.lineage2-store-list .sources .row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.lineage2-store-list .sources .row .count {
  color: var(--accent-deep);
  background: var(--accent-soft);
  padding: 0 7px;
  border-radius: 999px;
  font-size: 0.72rem;
}
.lineage2-store-list .sources .row.is-unlinked .count {
  color: var(--muted);
  background: var(--code-bg);
}
.lineage2-store-list .sources .row .reason {
  font-style: italic;
  font-family: var(--font-serif);
  color: var(--muted);
  font-size: 0.85em;
}
.lineage2-orm-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.lineage2-orm-cloud .orm-pill {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--code-bg);
  border: 1px solid var(--border);
  font-family: var(--font-mono);
  font-size: 0.78rem;
  color: var(--ink-2);
}
.lineage2-hot-list { list-style: none; padding: 0; margin: 0; }
.lineage2-hot-list li {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-3);
  padding: 6px 0;
  border-bottom: 1px solid var(--border-soft);
  font-family: var(--font-mono);
  font-size: 0.82rem;
}
.lineage2-hot-list li:last-child { border-bottom: none; }
.lineage2-hot-list .model-name { color: var(--ink); flex: 1; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lineage2-hot-list .meta {
  color: var(--muted); font-size: 0.85em;
}
.lineage2-empty {
  color: var(--muted);
  font-style: italic;
  font-size: 0.9rem;
}
.lineage2-tile-foot {
  font-family: var(--font-serif);
  font-style: italic;
  font-size: 0.85rem;
  line-height: 1.55;
  color: var(--muted);
  margin: var(--space-3) 0 0;
  padding-top: var(--space-3);
  border-top: 1px dashed var(--border);
}

/* ---- Architect-observation bullets (shared across sections) ---- */
.observations {
  background: var(--accent-soft);
  border-left: 3px solid var(--accent-deep);
  border-radius: 0 var(--radius) var(--radius) 0;
  padding: var(--space-3) var(--space-5);
  margin: var(--space-3) 0 var(--space-4);
}
.observations-label {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--accent-deep);
  margin-bottom: var(--space-2);
}
.observations ul {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.observations li {
  font-family: var(--font-serif);
  font-size: 0.96rem;
  line-height: 1.55;
  color: var(--ink);
  padding-left: 1.1em;
  position: relative;
}
.observations li::before {
  content: '◆';
  position: absolute;
  left: 0;
  top: 0.05em;
  color: var(--accent-deep);
  font-size: 0.78em;
}
.observations li strong { color: var(--ink); font-weight: 700; }
.observations li code {
  background: var(--surface);
  border: 1px solid var(--border);
  padding: 0.05em 0.4em;
  border-radius: 4px;
  font-size: 0.92em;
}

/* ---- Critical paths (swimlane behaviour view) ---- */
.cpaths-frame {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: var(--space-5) var(--space-5) var(--space-4);
  margin-bottom: var(--space-4);
  margin-left: -72px;
  margin-right: -72px;
  position: relative;
}
@media (max-width: 920px) {
  .cpaths-frame { margin-left: 0; margin-right: 0; }
}
.cpaths-headline {
  font-family: var(--font-serif);
  font-size: 1.05rem;
  line-height: 1.5;
  color: var(--ink-2);
  margin: 0 0 var(--space-4);
}
.cpaths-headline strong { color: var(--ink); font-weight: 600; }
.cpaths-headline em {
  font-style: normal;
  font-family: var(--font-mono);
  font-size: 0.92em;
  color: var(--accent-deep);
}
.cpaths-wrap {
  overflow-x: auto;
  margin: 0 calc(var(--space-5) * -1);
  padding: 0 var(--space-5);
}
.cpaths-svg { display: block; margin: 0 auto; overflow: visible; }
.cpaths-header-text {
  font-family: var(--font-mono);
  font-size: 0.62rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  fill: var(--muted);
}
.cpaths-row-stripe {
  /* Alternating row backgrounds for legibility on long lists. */
}
.cpaths-row-stripe.is-even { fill: var(--bg); }
.cpaths-row-stripe.is-odd { fill: var(--surface); }
.cpaths-caller-pill, .cpaths-store-pill {
  /* fill set per item from kind/store color. */
}
.cpaths-caller-text, .cpaths-store-text {
  font-family: var(--font-mono);
  font-size: 10.5px;
  fill: white;
  font-weight: 500;
  paint-order: stroke;
  stroke: oklch(20% 0.012 250 / 0.25);
  stroke-width: 2px;
  stroke-linejoin: round;
}
.cpaths-entry-bg {
  fill: var(--surface);
  stroke: var(--border);
  stroke-width: 1;
}
.cpaths-entry-name {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
  fill: var(--ink);
}
.cpaths-entry-sample {
  font-family: var(--font-mono);
  font-size: 9.5px;
  fill: var(--muted);
}
.cpaths-ep-badge {
  fill: var(--accent-soft);
  stroke: var(--accent-deep);
  stroke-width: 0.75;
}
.cpaths-ep-badge-text {
  font-family: var(--font-mono);
  font-size: 9.5px;
  font-weight: 600;
  fill: var(--accent-deep);
}
.cpaths-dep-pill {
  fill: var(--code-bg);
  stroke: var(--border);
  stroke-width: 0.75;
}
.cpaths-dep-pill-text {
  font-family: var(--font-mono);
  font-size: 10px;
  fill: var(--ink-2);
}
.cpaths-dep-pill.is-shared {
  fill: var(--code-bg);
  stroke: var(--border);
  stroke-dasharray: 2 2;
}
.cpaths-dep-overflow {
  font-family: var(--font-mono);
  font-size: 9.5px;
  fill: var(--muted);
  font-style: italic;
}
.cpaths-arrow {
  stroke: var(--ink-2);
  stroke-opacity: 0.4;
  stroke-width: 1.25;
  fill: none;
}
.cpaths-empty-cell {
  font-family: var(--font-mono);
  font-size: 10px;
  fill: var(--muted);
  font-style: italic;
}
.cpaths-overflow-note {
  font-family: var(--font-serif);
  font-style: italic;
  font-size: 0.92rem;
  color: var(--muted);
  margin-top: var(--space-3);
  text-align: center;
}

/* ---- Cpaths bento ---- */
.cpaths-bento {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-3);
  margin-top: var(--space-3);
}
.cpaths-tile {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--space-4) var(--space-4) var(--space-3);
  display: flex;
  flex-direction: column;
  min-height: 200px;
}
.cpaths-tile .tile-label {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: var(--space-2);
}
.cpaths-tile .tile-headline {
  font-family: var(--font-serif);
  font-size: 1rem;
  color: var(--ink);
  margin: 0 0 var(--space-3);
  line-height: 1.35;
}
.cpaths-tile .tile-body { flex: 1; }
.cpaths-method-bars {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.cpaths-method-bars .row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-mono);
  font-size: 0.78rem;
}
.cpaths-method-bars .row .method {
  width: 56px;
  color: white;
  text-align: center;
  padding: 1px 0;
  border-radius: 4px;
  font-weight: 600;
  font-size: 0.72rem;
  letter-spacing: 0.04em;
}
.cpaths-method-bars .row .bar {
  flex: 1;
  height: 8px;
  background: var(--code-bg);
  border-radius: 999px;
  overflow: hidden;
  position: relative;
}
.cpaths-method-bars .row .bar > span {
  position: absolute;
  left: 0; top: 0; bottom: 0;
  background: var(--accent);
  border-radius: 999px;
}
.cpaths-method-bars .row .num {
  width: 36px;
  text-align: right;
  color: var(--ink-2);
}
.cpaths-prefix-list, .cpaths-svc-list {
  list-style: none;
  padding: 0;
  margin: 0;
}
.cpaths-prefix-list li, .cpaths-svc-list li {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-3);
  padding: 6px 0;
  border-bottom: 1px solid var(--border-soft);
  font-family: var(--font-mono);
  font-size: 0.82rem;
}
.cpaths-prefix-list li:last-child,
.cpaths-svc-list li:last-child { border-bottom: none; }
.cpaths-prefix-list .prefix { color: var(--ink); }
.cpaths-prefix-list .count {
  color: var(--accent-deep);
  background: var(--accent-soft);
  padding: 0 7px;
  border-radius: 999px;
  font-size: 0.78rem;
}
.cpaths-svc-list .svc {
  color: var(--ink);
  display: flex;
  align-items: center;
  gap: 8px;
}
.cpaths-svc-list .swatch {
  width: 9px; height: 9px; border-radius: 2px;
}
.cpaths-coverage-stat {
  font-family: var(--font-serif);
  font-size: 1.6rem;
  font-weight: 600;
  color: var(--ink);
  text-align: center;
  margin: var(--space-3) 0;
}
.cpaths-coverage-stat .denom {
  font-size: 0.7em;
  color: var(--muted);
  font-weight: 400;
}
.cpaths-coverage-label {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
  text-align: center;
}
.cpaths-empty {
  color: var(--muted);
  font-style: italic;
  font-size: 0.9rem;
}
.modgraph-tile-foot {
  font-family: var(--font-serif);
  font-style: italic;
  font-size: 0.85rem;
  line-height: 1.55;
  color: var(--muted);
  margin: var(--space-3) 0 0;
  padding-top: var(--space-3);
  border-top: 1px dashed var(--border);
}
.modgraph-tile-foot code {
  background: transparent;
  padding: 0;
  font-size: 0.95em;
  color: var(--ink-2);
}
.modgraph-edge-list .arc .svc {
  color: var(--muted);
  font-size: 0.82em;
  font-family: var(--font-mono);
  margin-left: 4px;
}
.modgraph-edge-list .arc .svc::before { content: '· '; }
.modgraph-edge-list .arc .svc.is-cross::before { content: ''; }

/* ---- Print ---- */
/*
   Two page geometries.
     - Default `@page`: Letter portrait, 0.6in margins. Used for the
       reading sections (cover, README, languages, modules, tree, deps,
       glossary, footer).
     - Named `@page hero`: Letter landscape, 0.4in margins. Used for
       the four hero diagram sections via the `page: hero` property.
       Landscape gives ~980px of usable content width at 96 DPI, which
       fits the matrix (790px), topology (840px), critical-paths (864px)
       and Sankey (670px) without any horizontal scrolling or scaling.
*/
@page { size: Letter portrait; margin: 0.6in; }
@page hero { size: Letter landscape; margin: 0.4in; }

#codemap-sysmap-section,
#codemap-modgraph-section,
#codemap-topov2-section,
#codemap-cpaths-section,
#codemap-lineage2-section {
  page: hero;
}

@media print {
  html, body { background: white; }
  main { padding: 0; max-width: none; }
  .cover, .card, .stat { box-shadow: none; }
  details { padding-left: 14px; }
  details > summary::before { content: "•"; transform: none !important; }
  details > * { display: block !important; }
  details:not([open]) > *:not(summary) { display: block !important; }
  h2 { page-break-before: auto; break-before: auto; }
  .cover { page-break-after: avoid; }
  .card, .deps-eco, .entries li { page-break-inside: avoid; break-inside: avoid; }

  /* Each hero section starts a fresh landscape page. */
  #codemap-sysmap-section,
  #codemap-modgraph-section,
  #codemap-topov2-section,
  #codemap-cpaths-section,
  #codemap-lineage2-section {
    page-break-before: always;
    break-before: page;
  }

  /* Avoid awkward splits between heading and body */
  #codemap-sysmap-section h2,
  #codemap-modgraph-section h2,
  #codemap-topov2-section h2,
  #codemap-cpaths-section h2,
  #codemap-lineage2-section h2 { page-break-after: avoid; break-after: avoid; }

  /* On landscape hero pages the page itself is wide enough — we don't
     need the negative-margin "escape" used on screen. */
  .sysmap-frame,
  .modgraph-frame,
  .topov2-frame,
  .cpaths-frame,
  .lineage2-frame {
    box-shadow: none;
    margin-left: 0;
    margin-right: 0;
    page-break-inside: avoid;
    break-inside: avoid;
  }

  /* Don't clip the SVG by the wrapper's overflow:auto on screen. */
  .modgraph-matrix-wrap,
  .topov2-wrap,
  .cpaths-wrap,
  .lineage2-wrap {
    overflow: visible;
  }

  /* In print, the section-intro paragraph ("how to read this diagram")
     is redundant — a recipient printing an architecture audit knows
     what they're looking at. Hiding it lets the h2 + frame share a
     single landscape page instead of stranding the heading on a
     near-empty intro-only page above the SVG. */
  #codemap-sysmap-section > .section-intro,
  #codemap-modgraph-section > .section-intro,
  #codemap-topov2-section > .section-intro,
  #codemap-cpaths-section > .section-intro,
  #codemap-lineage2-section > .section-intro {
    display: none;
  }

  /* Tighten the print h2 so it doesn't claim a 3rd of the page above
     the diagram. The serif still reads as a section heading. */
  #codemap-sysmap-section > h2,
  #codemap-modgraph-section > h2,
  #codemap-topov2-section > h2,
  #codemap-cpaths-section > h2,
  #codemap-lineage2-section > h2 {
    font-size: 1.25rem;
    margin: 0 0 var(--space-3);
    padding-bottom: var(--space-2);
  }

  /* Centre the SVGs and cap their height so the h2 + frame
     fit together on one landscape page. Landscape Letter usable
     height ≈ 740px at 96 DPI; we leave ~140px for h2 + frame
     padding + headline, so the SVG itself caps at 6.0in (~576px).
     viewBox preserves aspect ratio while scaling — text stays
     crisp because PDF is vector. */
  .sysmap-svg,
  .topov2-svg,
  .lineage2-svg {
    display: block;
    margin: 0 auto;
    width: auto !important;
    height: auto !important;
    max-width: 100%;
    max-height: 6.0in;
  }

  /* The PDF is the full static map: hide interactive controls, undo any
     focus dimming, and restore every layer the on-screen toggles can hide. */
  .sysmap-controls { display: none; }
  .sysmap-svg.has-focus .sysmap-node,
  .sysmap-svg.has-focus [class^="sysmap-edge"],
  .sysmap-svg.has-focus .sysmap-store { opacity: 1 !important; }
  .sysmap-svg.hide-import [data-kind="import"],
  .sysmap-svg.hide-http [data-kind="http"],
  .sysmap-svg.hide-store [data-kind="store"],
  .sysmap-svg.hide-orphan .sysmap-node[data-orphan="1"] { display: initial !important; }

  /* The matrix is square (n x n), so on a wide landscape page it is
     height-bound. The cap must leave room for the h2 + headline so the
     whole frame stays on one page (a taller cap splits the grid from its
     heading). 6.4in fits alongside the heading while still rendering the
     matrix larger than the other heroes — the new geometry (16px cells,
     gutter-sized labels) is already intrinsically wider than before. For
     a dramatically larger matrix the section would need its own portrait
     page; that is deferred because it also reshapes the section bento. */
  .modgraph-matrix {
    display: block;
    margin: 0 auto;
    width: auto !important;
    height: auto !important;
    max-width: 100%;
    max-height: 6.4in;
  }

  /* Critical-paths has 16 rows of structured content (each row is
     a self-contained trace). Letting it run slightly taller and
     splitting at row boundaries reads cleaner than crushing 16
     rows into 6 inches of paper. The frame removes break-inside:
     avoid only for this section so rows can split across pages. */
  .cpaths-svg {
    display: block;
    margin: 0 auto;
    width: auto !important;
    height: auto !important;
    max-width: 100%;
    max-height: 6.6in;
  }

  /* Use the extra horizontal room for a 4-up bento layout. */
  .modgraph-bento,
  .topov2-bento,
  .cpaths-bento,
  .lineage2-bento {
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
  }
  .modgraph-tile,
  .topov2-tile,
  .cpaths-tile,
  .lineage2-tile {
    box-shadow: none;
    page-break-inside: avoid;
    break-inside: avoid;
    min-height: 0;
  }

  /* Hide on-screen affordances that don't belong on paper. */
  .modgraph-tip { display: none !important; }

  /* Tone down the accent-soft observations block so it doesn't read
     as a coloured box on monochrome printouts. */
  .observations {
    background: transparent;
    border-left-color: var(--ink);
  }

  /* Keep each flow card intact across page breaks; don't strand the heading. */
  .flow-card { break-inside: avoid; page-break-inside: avoid; }
  .key-flows h2 { break-after: avoid; page-break-after: avoid; }
  /* PDF has no JS: stack the lanes full-width and expand every flow trace.
     !important is required — the base .flow-board rule appears later in the
     stylesheet and would otherwise win the cascade in print. */
  .flow-board { grid-template-columns: 1fr !important; }
  .flow-detail { display: block !important; }
  .flow-caret { transform: rotate(90deg); }
  .flows-toolbar { display: none; }
}

/* ---- LLM evaluation: Overview ---- */
.overview { margin: var(--space-5) 0; }
.overview-lede { font-size: 1.4rem; font-weight: 600; line-height: 1.3; color: var(--ink); margin: 0 0 var(--space-3); font-family: var(--font-serif); }
.overview-body p { margin: 0 0 var(--space-2); color: var(--ink-2); }
.overview-stack { margin: var(--space-3) 0; display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.overview-caveats { margin: var(--space-3) 0; padding: var(--space-2) var(--space-3); border-left: 3px solid var(--accent); background: var(--accent-soft); border-radius: 0 var(--radius) var(--radius) 0; }
.overview-caveats ul { margin: 4px 0 0; padding-left: 18px; }
.overview-conf { font-size: 0.82rem; color: var(--muted); font-family: var(--font-mono); margin-top: var(--space-2); }

/* ---- LLM evaluation: vendored modules + README demotion ---- */
.vendored-badge { font-size: 0.7rem; font-family: var(--font-mono); color: var(--muted); border: 1px solid var(--border); border-radius: 4px; padding: 1px 6px; margin-left: 8px; vertical-align: middle; }
.card.is-vendored { opacity: 0.6; }
.card.is-vendored .name { color: var(--muted); }
.readme-demoted { opacity: 0.85; }
.readme-demoted .readme-quote { font-size: 0.92rem; }

/* ---- LLM evaluation: Key flows (interactive atlas) ---- */
.key-flows { margin: var(--space-6) 0; }
.flows-toolbar { display: flex; justify-content: flex-end; gap: var(--space-2); margin: 0 0 var(--space-4); }
.flows-btn {
  font-family: var(--font-mono); font-size: 0.7rem; letter-spacing: 0.05em;
  text-transform: uppercase; color: var(--ink-2); background: var(--surface);
  border: 1px solid var(--border); border-radius: 999px; padding: 4px 12px; cursor: pointer;
}
.flows-btn:hover { border-color: var(--accent); color: var(--ink); }
.flows-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

/* The board: one lane per flow "kind" (the ways the system gets kicked off). */
.flow-board {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
  gap: var(--space-4);
  align-items: start;
}
.flow-lane {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  overflow: hidden;
}
.flow-lane-head {
  padding: var(--space-3) var(--space-4);
  border-top: 3px solid var(--lane-color, var(--accent));
  border-bottom: 1px solid var(--border-soft);
}
.flow-lane-kind {
  font-family: var(--font-mono); font-size: 0.72rem; letter-spacing: 0.08em;
  text-transform: uppercase; font-weight: 600; color: var(--lane-color, var(--accent-deep));
}
.flow-lane-count { color: var(--muted); font-weight: 400; }
.flow-lane-meaning { color: var(--ink-2); font-size: 0.86rem; margin-top: 2px; line-height: 1.45; }

.flow-card { border-top: 1px solid var(--border-soft); }
.flow-card:first-of-type { border-top: none; }
.flow-summary {
  width: 100%; text-align: left; background: none; border: none; cursor: pointer;
  font: inherit; color: inherit;
  display: flex; gap: 10px; align-items: flex-start;
  padding: var(--space-3) var(--space-4);
}
.flow-summary:hover { background: var(--bg); }
.flow-summary:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.flow-caret { color: var(--muted); flex: 0 0 auto; margin-top: 3px; transition: transform 150ms ease; }
.flow-card.is-open .flow-caret { transform: rotate(90deg); color: var(--lane-color, var(--accent-deep)); }
.flow-summary-main { flex: 1 1 auto; min-width: 0; }
.flow-name { font-size: 1rem; font-weight: 600; font-family: var(--font-serif); color: var(--ink); }
.flow-oneline { color: var(--muted); font-size: 0.83rem; margin-top: 3px; line-height: 1.4; overflow-wrap: anywhere; }
.flow-oneline .flow-arrow { color: var(--lane-color, var(--accent)); padding: 0 5px; font-weight: 600; }
.flow-stepn { flex: 0 0 auto; font-family: var(--font-mono); font-size: 0.7rem; color: var(--muted); margin-top: 4px; white-space: nowrap; }

.flow-detail { display: none; padding: 0 var(--space-4) var(--space-4); }
.flow-card.is-open .flow-detail { display: block; }
.flow-narration { color: var(--ink-2); font-size: 0.9rem; line-height: 1.55; margin: 0 0 var(--space-3); overflow-wrap: anywhere; }
.flow-ends { font-size: 0.86rem; color: var(--ink); margin-top: var(--space-2); overflow-wrap: anywhere; }

/* Each step owns its number badge inside its own grid row, so numbers stay
   aligned with their text however tall a step grows. A pseudo-element draws
   the connector between consecutive badges (pure CSS, print-safe).
   minmax(0,1fr) + overflow-wrap keep long monospace citations from
   overflowing a narrow lane. */
.flow-steps { list-style: none; margin: 0; padding: 0; }
.flow-step {
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr);
  gap: 14px;
  position: relative;
  padding-bottom: var(--space-3);
  min-width: 0;
}
.flow-step:last-child { padding-bottom: 0; }
.flow-step:not(:last-child)::after {
  content: "";
  position: absolute;
  left: 11px;
  top: 22px;
  bottom: 0;
  width: 2px;
  background: var(--border);
  transform: translateX(-50%);
}
.flow-step-num {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 2px solid var(--lane-color, var(--accent));
  background: var(--bg);
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--ink);
  position: relative;
  z-index: 1;
}
.flow-step-main { min-width: 0; }
.flow-step-label { font-weight: 600; font-size: 0.95rem; color: var(--ink); overflow-wrap: anywhere; }
.flow-step-cite { font-size: 0.8rem; color: var(--muted); overflow-wrap: anywhere; }
.flow-step-cite code { font-family: var(--font-mono); overflow-wrap: anywhere; }
.flow-step-note { font-size: 0.85rem; color: var(--ink-2); overflow-wrap: anywhere; }
"""


# -------- beginner-friendly section intros -----------------------------
#
# Each report section opens with a one-sentence plain-English explainer
# aimed at a non-developer reader. The voice is editorial and warm —
# "this is what you're looking at and why it matters" — never jargon-first.

REPORT_EXPLAINER = (
    "This report is a structural snapshot of a software codebase. It shows "
    "<strong>what languages</strong> are used, <strong>what the main building blocks</strong> "
    "are, <strong>what outside packages</strong> the project relies on, and <strong>where the "
    "program starts running</strong>. Use it to onboard a new contributor, share a high-level "
    "overview with stakeholders, or audit how a project is organized. A glossary at the end "
    "explains any technical terms."
)

SECTION_INTROS: dict[str, str] = {
    "readme":   "The author's own words from the project README — the closest thing to an "
                "official summary of what this codebase is and what it does.",
    "flows":    "These are the main paths a request or job takes through the code, traced "
                "from a real trigger to where it ends. Each step cites the actual file and "
                "function it runs, so you can follow the path in the source yourself.",
    "sysmap":   "One map of the whole system: the product's own modules (vendored "
                "and third-party code is excluded) arranged in tiers — user-facing "
                "code on top, server code in the middle, data stores at the bottom. "
                "<strong>Dashed lines</strong> are HTTP calls from the frontend to a "
                "backend module, <strong>solid lines</strong> are code imports, and "
                "<strong>coloured lines into cylinders</strong> show which service "
                "writes to which store. Modules marked with <strong>▸</strong> are "
                "entry points — the doors through which requests arrive. Solid lines "
                "are code imports; the dependency matrix further down shows the full "
                "import detail.",
    "languages": "Programming languages are the rules and vocabulary used to write code. "
                 "A codebase usually has one primary language plus several supporting ones "
                 "(configuration files, documentation, build scripts).",
    "modules":  "A module is a self-contained folder of related code that handles one job. "
                "Modules relate to one another by <em>importing</em> each other — one module "
                "calls into another to reuse what it already does, and that wiring is exactly "
                "what the dependency matrix further down maps out.",
    "entries":  "An entry point is the file the program starts running from. Different "
                "languages have different conventions — “main.py” for Python, "
                "“index.js” for JavaScript, “main.go” for Go.",
    "deps":     "Software packages are pre-written, reusable chunks of code published by "
                "other developers. Listing a package as a dependency means this codebase "
                "uses it instead of writing the same functionality from scratch.",
    "tree":     "The directory tree is the physical layout of folders and files on disk. "
                "Folder names usually hint at what lives inside; file names usually hint "
                "at purpose.",
    "modgraph": "Each row and column is a module. A coloured cell at row <em>A</em>, "
                "column <em>B</em> means <em>A imports from B</em> — darker cells "
                "mean more imports flow that way. Modules are grouped by service "
                "(the coloured bands on the edges), with each service's modules "
                "sorted from largest to smallest. A clean codebase shows tight "
                "<strong>blocks along the diagonal</strong> (each service mostly "
                "depends on itself); off-diagonal blocks indicate cross-service "
                "coupling. The pale grey diagonal just marks where each module "
                "sits — modules don't import themselves.",
    "topology": "Each card is a separately-deployable service — its own app or process, "
                "with its own deployment lifecycle. The coloured strip across the top "
                "and the badge in the corner tell you what kind of service it is "
                "(<em>frontend</em>, <em>backend</em>, <em>worker</em>, …). The arrows "
                "between cards are <strong>HTTP calls</strong> aggregated across every "
                "route the source service makes to the target — the number on each arrow "
                "is the total call count, so thicker arrows mean heavier traffic. "
                "Where the matrix above showed file-level imports inside services, this "
                "view shows the conversation between services across the network.",
    "lineage":  "Where does each service store its data? Cards on the left are services; "
                "the <strong>cylinders on the right are data stores</strong> — the universal "
                "database glyph. The <strong>weighted ribbon</strong> between a service and "
                "a store is sized by the number of distinct data models (database tables, "
                "document types, etc.) declared via that service's ORM. Stores drawn at "
                "<em>reduced opacity</em> were detected in environment config but have no "
                "ORM model declarations — they're typically accessed via raw client "
                "libraries (Redis SDK, Firebase Admin, etc.) rather than through an ORM.",
    "cpaths":   "Where the diagrams above show <em>structure</em>, this one shows "
                "<em>behaviour</em> — what happens when a request flows through the "
                "system. Each row is one <strong>entry-point module</strong>: the "
                "caller(s) on the left, the module receiving the request in the "
                "middle, that module's key code dependencies, and the data store the "
                "flow ultimately writes to on the right. Reading top-to-bottom gives "
                "you a near-complete map of which HTTP surfaces exist in this "
                "codebase and how each one connects all the way down to persistence.",
}


# -------- glossary -----------------------------------------------------
#
# Per-term plain-English definitions. The glossary only includes entries
# whose subject actually appears in the scanned report — no point
# explaining "Rust" if no Rust files were found.

GLOSSARY_LANGUAGES: dict[str, str] = {
    "TypeScript": "A programming language that adds type checking on top of JavaScript. Popular for web frontends, Node.js servers, and large applications where catching bugs before running the code matters.",
    "JavaScript": "The programming language of the web — runs in every browser. Also runs servers (via Node.js). The most widely used language on the planet.",
    "Python": "A general-purpose programming language known for readable syntax. Popular for scripting, data analysis, AI/ML, web backends, and automation.",
    "Go": "A language made by Google, designed for backend services. Known for fast compilation, simple syntax, and built-in concurrency.",
    "Elixir": "A functional language that runs on the Erlang/BEAM virtual machine, built for highly concurrent, fault-tolerant backends. Most often paired with the Phoenix web framework. Powers systems that need to stay up and handle many connections at once.",
    "Rust": "A systems programming language focused on safety and performance. Used for performance-critical infrastructure, browsers, and low-level tools.",
    "Java": "A general-purpose language widely used in enterprise software, Android apps, and big-data systems. Runs on the Java Virtual Machine (JVM).",
    "Kotlin": "A modern JVM language used heavily for Android development and increasingly for backend services. More concise than Java.",
    "Swift": "Apple's language for iOS, macOS, watchOS, and other Apple platforms.",
    "C": "The original systems language. Used in operating systems, embedded devices, and low-level libraries. Everything else is built on top of C.",
    "C++": "A low-level systems language used for game engines, browsers, and performance-critical software.",
    "C#": "Microsoft's language for the .NET platform. Used for Windows apps, game development (Unity), and web servers (ASP.NET).",
    "Ruby": "A scripting language emphasizing simplicity and developer happiness. Best known via the Ruby on Rails web framework.",
    "PHP": "A scripting language for web backends. Powers WordPress and a large portion of the older web.",
    "Scala": "A functional/object-oriented hybrid language on the JVM. Popular in data engineering and academic research.",
    "Shell": "Scripting language for the command line (Bash, Zsh, etc.). Used for automation, build steps, and glue code between programs.",
    "Markdown": "A lightweight format for writing formatted text. Used for READMEs, documentation, and notes. Compiles to HTML.",
    "MDX": "Markdown extended with embedded React components. Used by modern documentation sites that need interactive examples.",
    "HTML": "The markup language of web pages — defines the structure of a page (headings, paragraphs, links, images).",
    "CSS": "The styling language of web pages — controls colors, layout, fonts, and animations.",
    "SCSS": "An extension of CSS that adds variables, nesting, and helper functions. Compiles to plain CSS at build time.",
    "Less": "Another CSS preprocessor with variables and nesting. Similar idea to SCSS, slightly different syntax.",
    "Vue": "A JavaScript framework for building user interfaces. A lighter, more approachable alternative to React.",
    "Svelte": "A JavaScript framework that compiles components down to vanilla JS at build time — no runtime framework code shipped to users.",
    "SQL": "The language used to query and manipulate databases. Stands for Structured Query Language.",
    "YAML": "A human-readable data format. Used heavily for configuration files in CI/CD, Kubernetes, and modern dev tooling.",
    "JSON": "A data format used to send structured data between systems. Most web APIs speak JSON.",
    "TOML": "A configuration format chosen for readability. Used by Rust's Cargo, Python's pyproject.toml, and others.",
    "Dockerfile": "A set of instructions for building a container image. A container packages an app with its OS and dependencies so it runs identically anywhere.",
    "Makefile": "A build script format. Defines named tasks (build, test, clean) that you run with `make <task>`. Old but still widely used.",
}

# -------- per-language profiles (Languages section drop-downs) ----------
#
# Each entry is (where_it_runs_chip, body_html). The body is author-controlled
# copy (safe to inline un-escaped) and answers the three questions a
# non-developer asks of a language: what is it, where does it run (backend /
# frontend / config / …), and what role does it usually play in a codebase.
# Languages without a profile simply render as a non-expandable row.

LANG_PROFILES: dict[str, tuple[str, str]] = {
    "Python": ("Backend · data · scripting",
        "A general-purpose language known for clean, readable syntax. In most codebases it "
        "lives on the <strong>backend</strong> — powering web APIs and services — or off to the "
        "side running data analysis, AI/ML, automation, and build scripts. It almost never runs "
        "in the browser."),
    "JavaScript": ("Frontend · backend",
        "The native language of the web browser, and — through Node.js — a popular backend "
        "language too. In a typical codebase it drives <strong>interactive frontend behaviour</strong> "
        "and/or <strong>server-side APIs</strong>. The most widely deployed language in the world."),
    "TypeScript": ("Frontend · backend",
        "JavaScript plus a type system that catches mistakes before the code runs. Used wherever "
        "JavaScript is, but favoured for larger apps and teams because the types document intent "
        "and prevent whole classes of bugs. Compiles down to plain JavaScript."),
    "Elixir": ("Backend · concurrency",
        "A functional language running on the battle-tested Erlang/BEAM virtual machine, built for "
        "highly concurrent, fault-tolerant <strong>backends</strong>. Usually paired with the Phoenix "
        "web framework for APIs and real-time features. Excels where a system must stay up and handle "
        "many simultaneous connections."),
    "Go": ("Backend · systems",
        "A language from Google designed for backend services and infrastructure tools. Known for "
        "fast compilation, simple syntax, and first-class concurrency. Compiles to a single "
        "self-contained binary, which makes it easy to deploy."),
    "Rust": ("Systems · backend",
        "A systems language focused on performance and memory safety without a garbage collector. "
        "Used for performance-critical infrastructure, developer tooling, and increasingly backends "
        "where reliability is paramount."),
    "Java": ("Backend · mobile",
        "A general-purpose language running on the Java Virtual Machine. Dominant in large enterprise "
        "<strong>backends</strong>, Android apps, and big-data systems. Verbose but stable and "
        "universally supported."),
    "Kotlin": ("Mobile · backend",
        "A modern, more concise language on the Java Virtual Machine. The preferred language for "
        "<strong>Android</strong> development and increasingly used for backend services."),
    "Swift": ("Mobile · Apple",
        "Apple's language for building iOS, macOS, watchOS, and other Apple-platform apps. Its "
        "presence almost always means the project ships a native Apple app."),
    "C": ("Systems",
        "The original systems language — operating systems, embedded devices, and the low-level "
        "libraries nearly everything else is built on. Fast and close to the hardware."),
    "C++": ("Systems · performance",
        "A lower-level language for performance-critical software: game engines, browsers, trading "
        "systems, and high-performance tooling. Powerful and fast, with a steep learning curve."),
    "C#": ("Backend · apps · games",
        "Microsoft's language for the .NET platform — web servers (ASP.NET), desktop applications, "
        "and game development (Unity)."),
    "Ruby": ("Backend",
        "A scripting language built around developer happiness, best known through the Ruby on Rails "
        "web framework. Common in <strong>backends</strong> and developer tooling."),
    "PHP": ("Backend · web",
        "A long-standing web backend language that powers WordPress and a large share of the existing "
        "web. Almost always runs server-side."),
    "Scala": ("Backend · data",
        "A language blending functional and object-oriented styles on the JVM. Popular in data "
        "engineering (Spark) and systems that value strong typing."),
    "HTML": ("Markup · frontend",
        "The markup language that defines the <strong>structure</strong> of a web page — headings, "
        "paragraphs, links, forms, images. It describes <em>what</em> is on the page; CSS controls "
        "how it looks and JavaScript makes it interactive. Not a programming language in the usual "
        "sense, so it carries no logic to trace."),
    "CSS": ("Styling · frontend",
        "The styling language of the web — colours, layout, spacing, fonts, animation. It decides "
        "how the HTML structure actually looks and adapts across screen sizes. Pure presentation; "
        "it contains no program logic."),
    "SCSS": ("Styling · frontend",
        "A superset of CSS that adds variables, nesting, and reusable mixins, then compiles to plain "
        "CSS at build time. Teams use it to keep large stylesheets organised and consistent."),
    "Less": ("Styling · frontend",
        "A CSS preprocessor with variables and nesting, similar in spirit to SCSS. Compiles to plain "
        "CSS."),
    "Vue": ("Frontend",
        "A JavaScript framework for building user interfaces — a lighter, approachable alternative to "
        "React. Its files describe <strong>frontend</strong> components."),
    "Svelte": ("Frontend",
        "A JavaScript UI framework that compiles components to lean vanilla JavaScript at build time, "
        "shipping very little framework code to the browser."),
    "Markdown": ("Docs",
        "A lightweight plain-text format for writing formatted documents — READMEs, docs, notes — "
        "that converts cleanly to HTML. Its presence usually signals <strong>documentation</strong> "
        "rather than application code."),
    "MDX": ("Docs · frontend",
        "Markdown with embedded interactive components. Used by documentation sites that need live, "
        "interactive examples alongside the prose."),
    "JSON": ("Data · config",
        "A simple, language-neutral format for structured data. In a codebase it shows up as "
        "<strong>configuration</strong> files, package manifests, fixtures, and the payloads most "
        "web APIs send and receive. Data, not code."),
    "YAML": ("Config",
        "A human-friendly configuration format. Heavily used for CI/CD pipelines, container "
        "orchestration (Kubernetes), and tool settings. Lots of YAML usually means substantial "
        "automation or deployment config."),
    "TOML": ("Config",
        "A configuration format chosen for being easy to read and unambiguous. Common in Rust "
        "(`Cargo.toml`) and Python (`pyproject.toml`) projects to declare settings and dependencies."),
    "SQL": ("Data · database",
        "The language for querying and manipulating relational databases. Not general-purpose — it "
        "expresses <em>what</em> data to read or change, which the database engine then carries out."),
    "Dockerfile": ("Build · ops",
        "A recipe for building a <strong>container image</strong> — a self-contained package of an "
        "app plus the operating system and dependencies it needs to run identically anywhere. Its "
        "presence means the project is meant to be containerised and deployed."),
    "Makefile": ("Build",
        "A build-automation format that defines named tasks (build, test, clean) you run with "
        "`make`. Old but durable; often the front door to a project's common commands."),
    "Shell": ("Scripting · ops",
        "Command-line scripts (Bash, Zsh, etc.) used for automation, setup steps, and glue between "
        "programs. Usually part of build pipelines and developer tooling rather than the product "
        "itself."),
}

# Toggle behaviour for the language rows. Kept as a plain (non-f) string so its
# braces survive; referenced as {LANG_TABLE_JS} from the render f-string. The
# section degrades gracefully without JS (rows just don't expand on screen; the
# print stylesheet shows every profile regardless).
LANG_TABLE_JS = """
<script>
(function () {
  var rows = document.querySelectorAll('#codemap-languages .lang-row[data-target]');
  rows.forEach(function (row) {
    function toggle() {
      var detail = document.getElementById(row.getAttribute('data-target'));
      if (!detail) return;
      var open = detail.classList.toggle('is-open');
      row.classList.toggle('is-open', open);
      row.setAttribute('aria-expanded', open ? 'true' : 'false');
    }
    row.addEventListener('click', toggle);
    row.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
    });
  });
})();
</script>
"""

GLOSSARY_ECOSYSTEMS: dict[str, str] = {
    "npm":     "Node Package Manager — the standard registry of JavaScript and TypeScript packages. Dependencies are listed in `package.json`.",
    "pip":     "Python's standard package installer. Reads dependencies from `requirements.txt` or `pyproject.toml`.",
    "pipenv":  "A higher-level Python dependency tool that combines pip and virtualenv into one workflow. Uses a `Pipfile`.",
    "python":  "Generic Python packaging via `pyproject.toml` (PEP 621) — the modern standard for declaring a Python project's dependencies and metadata.",
    "go":      "Go modules — the language's built-in dependency system. Dependencies are declared in `go.mod`.",
    "cargo":   "Rust's package manager and build tool. Reads dependencies from `Cargo.toml` and builds everything in one step.",
    "bundler": "Ruby's dependency manager. Reads `Gemfile` and locks versions in `Gemfile.lock`.",
    "composer": "PHP's dependency manager. Reads `composer.json`.",
    "maven":   "Java's traditional build and dependency tool. Reads `pom.xml` (an XML file).",
    "gradle":  "A modern build tool for Java, Kotlin, and Android. Reads `build.gradle` or `build.gradle.kts`.",
    "hex":     "Elixir's package manager and registry. Dependencies are declared in the `deps` function of `mix.exs` and locked in `mix.lock`.",
}

GLOSSARY_TERMS: dict[str, str] = {
    "Module": "A self-contained folder of related code that handles one responsibility — for example an 'auth' module handles login, a 'billing' module handles payments. Most codebases split work into modules so contributors can focus on one area at a time.",
    "Package": "A piece of reusable code published by someone else that this codebase depends on. Adding a package is faster and safer than re-writing the same code from scratch.",
    "Dependency": "An external package this project needs to run. The dependency listing is essentially the project's shopping list of outside code.",
    "Entry point": "The specific file the program starts running from when launched. Languages have different conventions: Python uses `main.py`, JavaScript uses `index.js`, Go uses `main.go`, Rust uses `main.rs`.",
    "Manifest": "A small file at the project's root that declares its dependencies and metadata. Examples: `package.json`, `requirements.txt`, `Cargo.toml`, `go.mod`.",
    "LOC (Lines of code)": "A rough size indicator — *not* a quality measure. A 100-LOC module isn't necessarily worse than a 1,000-LOC one. Use LOC for orientation, not judgement.",
    "Source root": "A directory holding the main program code, kept separate from configuration, tests, and build artifacts. Common names: `src`, `lib`, `app`, `cmd`, `pkg`.",
    "Service": "An independently deployable unit of code — its own app, its own process, its own deploy. A monorepo can hold many services (e.g. one for the mobile app, one for the backend API, one for the AI worker). Services talk to each other over the network, not by importing each other's code.",
    "Endpoint": "A specific URL a service responds to, paired with an HTTP method. `GET /api/v1/users/:id` is an endpoint. Services advertise endpoints; other services call them.",
    "ORM (Object-Relational Mapper)": "A library that lets you read and write database rows using normal code objects instead of writing SQL by hand. Popular ORMs: Prisma (TS), SQLAlchemy (Python), Mongoose (Mongo), ActiveRecord (Ruby).",
    "Data store": "A place where data persists between requests. Databases (Postgres, MySQL, Mongo), caches (Redis), and object storage (S3, MinIO) are all data stores.",
    "Topology": "The shape of a system — which pieces exist and how they connect. A topology diagram answers \"what's deployed and what talks to what.\"",
    "Vendored": "Third-party code copied directly into this repository instead of installed from a package registry. Vendored folders ship with the project but aren't part of its own product code, so the report shows them faded. Teams vendor a library to pin an exact version, patch it locally, or keep building when the upstream package isn't available — but it becomes code you now carry and maintain.",
}


# -------- auto-detected tools / libraries / services --------------------
#
# Beginner readers hit a wall of brand names and acronyms (Sentry, Apollo,
# GraphQL, OTP, BullMQ, …) that the language/ecosystem glossaries don't cover.
# This curated dictionary defines them, and `glossary_tech_hits` includes an
# entry ONLY when its term actually appears in the report's text — the AI
# overview/flow prose AND structural data (dependency names, module paths,
# README). Each value is (definition, alias_tuple, case_sensitive).
#
# case_sensitive=True is for short all-caps acronyms (OTP, BEAM, JWT, S3, REST)
# that would otherwise match common lowercase words. Aliases are matched on
# word/identifier boundaries, so "@sentry/node" and "Apollo Client" both hit.

GLOSSARY_TECH: dict[str, tuple[str, tuple[str, ...], bool]] = {
    "GraphQL": ("A query language for APIs: instead of many fixed endpoints, the client asks for exactly the data it wants in one request. Often contrasted with REST.", ("GraphQL",), False),
    "REST": ("An architectural style for web APIs built around resources and standard HTTP verbs (GET, POST, …). The traditional alternative to GraphQL.", ("REST",), True),
    "Apollo Client": ("A widely used client library for talking to a GraphQL API from a frontend (commonly React or React Native). Handles fetching, caching, and updating GraphQL data.", ("Apollo Client", "Apollo"), False),
    "Sentry": ("An error-monitoring and crash-reporting service. Apps send their exceptions and performance data to Sentry so developers get alerted and can debug production issues.", ("Sentry",), False),
    "Stripe": ("A payments platform that handles card processing, subscriptions, and billing so the app never stores card data itself. Events (like a successful payment) are delivered back via webhooks.", ("Stripe", "stripity_stripe"), False),
    "BullMQ": ("A Node.js library for background job queues backed by Redis. Lets an app hand slow work (emails, media processing) to worker processes instead of blocking a web request.", ("BullMQ",), False),
    "WebGL": ("A browser API for rendering hardware-accelerated 2D/3D graphics directly in a web page using the GPU. Underlies in-browser games, 3D scenes, and heavy data visualisation.", ("WebGL",), False),
    "OTP (Open Telecom Platform)": ("The framework at the heart of Erlang and Elixir for building concurrent, fault-tolerant systems. An 'OTP application' is a supervised tree of lightweight processes that restart themselves on failure.", ("OTP",), True),
    "BEAM": ("The virtual machine that runs Erlang and Elixir, designed for massive concurrency and 'let it crash' fault tolerance. Elixir code is compiled to run on the BEAM.", ("BEAM",), True),
    "Phoenix": ("The standard web framework for Elixir — routing, controllers, real-time channels, and the LiveView UI layer. Roughly Elixir's equivalent of Rails or Django.", ("Phoenix",), False),
    "Absinthe": ("The GraphQL toolkit for Elixir. Defines a GraphQL schema and resolvers on a Phoenix backend.", ("Absinthe",), False),
    "Ecto": ("Elixir's database library — maps code to database tables, builds queries, and runs migrations (an ORM-style toolkit for Elixir).", ("Ecto",), False),
    "Oban": ("A background-job framework for Elixir that stores its job queue in PostgreSQL, used to run scheduled and asynchronous work reliably.", ("Oban",), False),
    "LiveView": ("A Phoenix feature for building interactive, real-time web UIs in Elixir with little or no custom JavaScript — the server pushes UI updates over a websocket.", ("LiveView",), False),
    "Supervisor": ("In Erlang/Elixir, a process whose only job is to start, watch, and restart other processes when they crash — the backbone of OTP fault tolerance.", ("supervisor", "supervision tree"), False),
    "React": ("A JavaScript library for building user interfaces out of reusable components. The most widely used frontend library.", ("React",), False),
    "React Native": ("A framework for building native iOS and Android apps with React and JavaScript/TypeScript, sharing most code across both platforms.", ("React Native",), False),
    "Expo": ("A toolchain and platform on top of React Native that simplifies building, running, and shipping mobile apps.", ("Expo",), False),
    "NestJS": ("A structured, opinionated framework for building Node.js backend applications in TypeScript.", ("NestJS", "Nest.js"), False),
    "FastAPI": ("A modern Python framework for building web APIs quickly, with automatic validation and interactive documentation.", ("FastAPI",), False),
    "Django": ("A batteries-included Python web framework covering routing, templates, ORM, and admin out of the box.", ("Django",), False),
    "Flask": ("A lightweight Python web microframework — minimal core, add what you need.", ("Flask",), False),
    "Next.js": ("A popular React framework for server-rendered and statically-generated web apps.", ("Next.js",), False),
    "Airtable": ("A cloud service that is part spreadsheet, part database, with an API. Apps often use it as an easy content or back-office store.", ("Airtable",), False),
    "PostgreSQL": ("A powerful open-source relational (SQL) database — a very common primary data store for web backends.", ("PostgreSQL", "Postgres", "postgrex"), False),
    "Redis": ("An in-memory data store used as a cache, message broker, and job-queue backend. Fast because it keeps data in RAM.", ("Redis",), False),
    "MongoDB": ("A document database that stores flexible JSON-like records instead of fixed tables.", ("MongoDB", "Mongo"), False),
    "Prisma": ("A TypeScript ORM that maps database tables to type-safe code objects; its schema lives in `schema.prisma`.", ("Prisma",), False),
    "Webhook": ("A way for one service to notify another in real time: when an event happens (e.g. a payment), the source service makes an HTTP request to a URL your app exposes.", ("webhook", "webhooks"), False),
    "gRPC": ("A high-performance framework for service-to-service calls using Protocol Buffers over HTTP/2 — an alternative to REST/JSON for internal APIs.", ("gRPC",), False),
    "Docker": ("A tool that packages an application and its dependencies into a portable container that runs the same everywhere.", ("Docker",), False),
    "Kubernetes": ("An orchestration system that runs and scales containerised apps across many machines. Often abbreviated K8s.", ("Kubernetes", "K8s"), False),
    "Terraform": ("An infrastructure-as-code tool for provisioning cloud resources from declarative configuration files.", ("Terraform",), False),
    "OAuth": ("An open standard for delegated authorization — letting an app act on your behalf (e.g. 'Sign in with Google') without sharing your password.", ("OAuth",), False),
    "JWT (JSON Web Token)": ("A compact, signed token used to prove who a user is between requests — common in API authentication.", ("JWT",), True),
    "Kafka": ("A distributed event-streaming platform for high-throughput message pipelines between services.", ("Kafka",), False),
    "RabbitMQ": ("A message broker that routes messages between services, decoupling producers from consumers.", ("RabbitMQ",), False),
    "S3": ("Amazon's object-storage service for files and blobs (images, uploads, backups). 'S3-compatible' stores like MinIO speak the same API.", ("S3",), True),
    "Tailwind CSS": ("A utility-first CSS framework: you style elements with small predefined classes instead of writing custom CSS.", ("Tailwind",), False),
    "esbuild": ("An extremely fast JavaScript/TypeScript bundler, often used inside build pipelines.", ("esbuild",), False),
    "Webpack": ("A bundler that packages frontend JavaScript, CSS, and assets for delivery to the browser.", ("webpack",), False),
    "Vite": ("A fast frontend build tool and dev server, common in modern JavaScript/TypeScript projects.", ("Vite",), False),
}


def _glossary_corpus(data: dict[str, Any], enrichment: dict[str, Any] | None) -> str:
    """Concatenate the report's searchable text. Data-level sources are always
    present; enrichment-level (AI prose) is added only when enrichment exists —
    which keeps prose-only terms out of the degraded, no-enrichment render."""
    parts: list[str] = []

    rd = data.get("readme") or {}
    parts.append(rd.get("first_paragraph", "") or "")
    parts.extend(rd.get("headings", []) or [])
    for eco in data.get("deps", []) or []:
        for pkg in eco.get("packages", []) or []:
            parts.append(pkg.get("name", "") or "")
    for m in data.get("modules", []) or []:
        parts.append(m.get("path", "") or "")
        parts.append(m.get("description", "") or "")

    if enrichment:
        ov = enrichment.get("overview") or {}
        for k in ("what_it_is", "what_it_does", "how_it_works"):
            parts.append(ov.get(k, "") or "")
        parts.extend(ov.get("primary_stack", []) or [])
        parts.extend(ov.get("caveats", []) or [])
        for f in enrichment.get("flows", []) or []:
            for k in ("name", "trigger", "narration", "terminates"):
                parts.append(f.get(k, "") or "")
            for s in f.get("steps", []) or []:
                for k in ("label", "symbol", "note", "file"):
                    parts.append(s.get(k, "") or "")
        for d in enrichment.get("module_descriptions", []) or []:
            parts.append(d.get("description", "") or "")
        cls = enrichment.get("classification") or {}
        for v in cls.get("vendored", []) or []:
            for k in ("kind", "source", "why"):
                parts.append(v.get(k, "") or "")
        for p in cls.get("products", []) or []:
            parts.append(p.get("why", "") or "")

    return "\n".join(str(x) for x in parts if x)


def glossary_tech_hits(data: dict[str, Any], enrichment: dict[str, Any] | None) -> list[tuple[str, str]]:
    """Return (name, definition) for every GLOSSARY_TECH term whose alias is
    actually mentioned in the report, sorted alphabetically. Matching is on
    identifier boundaries (so `@sentry/node` and `Apollo Client` both hit)."""
    corpus = _glossary_corpus(data, enrichment)
    if not corpus:
        return []
    corpus_lower = corpus.lower()
    hits: list[tuple[str, str]] = []
    for name, (definition, aliases, case_sensitive) in GLOSSARY_TECH.items():
        for alias in aliases:
            if case_sensitive:
                pattern = rf'(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])'
                matched = re.search(pattern, corpus) is not None
            else:
                pattern = rf'(?<![A-Za-z0-9]){re.escape(alias.lower())}(?![A-Za-z0-9])'
                matched = re.search(pattern, corpus_lower) is not None
            if matched:
                hits.append((name, definition))
                break
    return sorted(hits)


# -------- helpers -------------------------------------------------------

def fmt_num(n: int) -> str:
    """Comma-separate integers."""
    return f"{n:,}"


def pct(part: int, whole: int) -> float:
    return 0.0 if whole == 0 else (100.0 * part / whole)


def section_intro(key: str) -> str:
    """Return the beginner-friendly section intro paragraph (already
    safe — copy is author-controlled, not user-controlled)."""
    text = SECTION_INTROS.get(key, "")
    return f'<p class="section-intro">{text}</p>' if text else ""


# -------- section renderers --------------------------------------------

def render_cover(data: dict[str, Any]) -> str:
    p = data["project"]
    lede_parts = []
    if p.get("primary_language"):
        lede_parts.append(f"Primary language <strong>{escape(p['primary_language'])}</strong>")
    if data.get("languages"):
        lede_parts.append(f"<strong>{len(data['languages'])}</strong> languages detected")
    lede_parts.append(f"<strong>{fmt_num(p['total_files'])}</strong> source files")
    lede_parts.append(f"<strong>{fmt_num(p['total_loc'])}</strong> lines of code")
    lede = " · ".join(lede_parts)

    scanned_at = data.get("scanned_at", "")
    depth = data.get("scan_depth", "shallow")

    return f"""
<section class="cover">
  <div class="eyebrow">Codebase Architecture Report</div>
  <h1>{escape(p['name'])}</h1>
  <p class="lede">{lede}.</p>
  <div class="stats">
    <div class="stat">
      <div class="label">Files</div>
      <div class="value">{fmt_num(p['total_files'])}</div>
    </div>
    <div class="stat">
      <div class="label">Lines of code</div>
      <div class="value">{fmt_num(p['total_loc'])}</div>
    </div>
    <div class="stat">
      <div class="label">Languages</div>
      <div class="value">{len(data.get('languages', []))}</div>
    </div>
    <div class="stat">
      <div class="label">Modules</div>
      <div class="value">{len(data.get('modules', []))}</div>
    </div>
  </div>
  <div class="eyebrow" style="margin-top: var(--space-5); color: var(--muted);">
    Scanned {escape(scanned_at)} · depth: {escape(depth)}
  </div>
</section>
<aside class="report-explainer">
  {REPORT_EXPLAINER}
</aside>
"""


def render_languages(data: dict[str, Any]) -> str:
    langs = data.get("languages", [])
    if not langs:
        return ""
    total_loc = sum(l["loc"] for l in langs) or 1
    bar = "".join(
        f'<span style="width: {pct(l["loc"], total_loc):.2f}%; background: {escape(l["color"])};" '
        f'title="{escape(l["name"])} {pct(l["loc"], total_loc):.1f}%"></span>'
        for l in langs
    )
    row_parts: list[str] = []
    any_expandable = False
    for i, l in enumerate(langs):
        name = l["name"]
        swatch = f'<span class="lang-swatch" style="background: {escape(l["color"])};"></span>'
        stats = (
            f'<td class="mono">{fmt_num(l["files"])}</td>'
            f'<td class="mono">{fmt_num(l["loc"])}</td>'
            f'<td class="mono">{pct(l["loc"], total_loc):.1f}%</td>'
        )
        profile = LANG_PROFILES.get(name)
        if profile:
            any_expandable = True
            where, body = profile
            rid = f"lang-detail-{i}"
            row_parts.append(
                f'<tr class="lang-row" data-target="{rid}" tabindex="0" role="button" '
                f'aria-expanded="false" aria-controls="{rid}">'
                f'<td><span class="lang-caret" aria-hidden="true">▸</span>{swatch}{escape(name)}</td>'
                f'{stats}</tr>'
            )
            row_parts.append(
                f'<tr class="lang-detail-row" id="{rid}">'
                f'<td colspan="4" class="lang-detail">'
                f'<span class="lang-where">{escape(where)}</span><p>{body}</p>'
                f'</td></tr>'
            )
        else:
            row_parts.append(
                f'<tr class="lang-row is-static">'
                f'<td><span class="lang-caret-spacer" aria-hidden="true"></span>{swatch}{escape(name)}</td>'
                f'{stats}</tr>'
            )
    rows = "".join(row_parts)
    hint = (
        '<p class="module-note">Click any language marked with a ▸ to see what it is, '
        'where it usually runs, and the role it tends to play in a codebase.</p>'
        if any_expandable else ""
    )
    return f"""
<section id="codemap-languages">
  <h2>Languages</h2>
  {section_intro("languages")}
  {hint}
  <div class="lang-bar">{bar}</div>
  <table class="lang-table">
    <thead><tr><th>Language</th><th>Files</th><th>Lines</th><th>Share</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  {LANG_TABLE_JS}
</section>
"""


def render_tree(data: dict[str, Any]) -> str:
    root = data.get("tree")
    if not root:
        return ""
    html = _tree_node(root, is_root=True)
    return f"""
<section>
  <h2>Directory tree</h2>
  {section_intro("tree")}
  <div class="tree">{html}</div>
</section>
"""


def _tree_node(node: dict[str, Any], is_root: bool = False) -> str:
    if node.get("type") == "file":
        loc = node.get("loc") or 0
        lang = node.get("language") or ""
        meta = f"{lang} · {fmt_num(loc)}" if lang else f"{fmt_num(loc)}"
        return f'<span class="file">{escape(node["name"])}<span class="meta">{escape(meta)}</span></span>'

    name = escape(node["name"])
    fcount = node.get("file_count", 0)
    summary = f'<summary><strong>{name}</strong> <span class="meta">{fmt_num(fcount)} files · {fmt_num(node.get("loc", 0))} LOC</span></summary>'

    if node.get("truncated"):
        body = '<span class="truncated">… truncated (depth limit reached)</span>'
    else:
        children = node.get("children", [])
        if not children:
            body = '<span class="empty">(empty)</span>'
        else:
            body = "\n".join(_tree_node(c) for c in children)

    open_attr = " open" if is_root else ""
    return f"<details{open_attr}>{summary}{body}</details>"


def render_modules(data: dict[str, Any], enrichment: dict[str, Any] | None = None) -> str:
    mods = data.get("modules", [])
    if not mods:
        return ""

    # Build classification + description lookups from enrichment (keyed by path).
    vendored_ids: dict[str, dict] = {}
    product_ids: set[str] = set()
    desc_by_id: dict[str, str] = {}
    if enrichment:
        cls = enrichment.get("classification") or {}
        for v in cls.get("vendored", []) or []:
            if v.get("module_id"):
                vendored_ids[v["module_id"]] = v
        for p in cls.get("products", []) or []:
            if p.get("module_id"):
                product_ids.add(p["module_id"])
        for d in enrichment.get("module_descriptions", []) or []:
            if d.get("module_id") and d.get("description"):
                desc_by_id[d["module_id"]] = d["description"]

    def is_vendored(m: dict) -> bool:
        path = m.get("path")
        if path in product_ids:    # enrichment rescue beats the heuristic
            return False
        if path in vendored_ids:   # enrichment catch beats the heuristic
            return True
        return bool(m.get("vendored_guess"))

    def card(m: dict) -> str:
        path = m.get("path", "")
        vend = is_vendored(m)
        desc = desc_by_id.get(path) or (m.get("description") if not vend else "")
        kind = vendored_ids.get(path, {}).get("kind", "")
        badge = (
            f'<span class="vendored-badge">vendored{(" · " + escape(kind)) if kind else ""}</span>'
            if vend else ""
        )
        desc_html = ('<p class="desc">' + escape(desc) + '</p>') if desc else ""
        return f"""
        <div class="card{' is-vendored' if vend else ''}">
          <div class="head">
            <div class="name">{escape(path)}{badge}</div>
            <div class="meta">{fmt_num(m['file_count'])} files · {fmt_num(m['loc'])} LOC</div>
          </div>
          {desc_html}
          <div class="langs">
            {''.join(f'<span class="tag">{escape(l)}</span>' for l in m.get('languages', []))}
          </div>
        </div>
        """

    # Products first (original order), vendored last.
    products = [m for m in mods if not is_vendored(m)]
    vendored = [m for m in mods if is_vendored(m)]
    ordered = products + vendored

    cards = "".join(card(m) for m in ordered)

    # Plain-English explanation of what "top-level" means here. Always shown.
    toplevel_note = (
        '<p class="module-note">The folders below are this codebase’s '
        '<strong>top-level modules</strong> — the primary areas that do the heavy '
        'lifting, sitting near the top of the directory tree rather than buried as '
        'small helpers deep inside it. They’re the right altitude for a first read: '
        'enough to see the system’s shape without getting lost in every nested file.</p>'
    )

    # Why some cards are faded — shown whenever any module is classified
    # vendored, either by the heuristic flag (vendored_guess) or by enrichment.
    vendored_note = ""
    if vendored:
        vendored_note = (
            '<p class="module-note">Some cards are <strong>faded and tagged '
            '<em>vendored</em></strong>: that code lives in this repository but '
            'wasn’t written by this project — it’s a third-party library or framework '
            'copied in (“vendored”) rather than installed from a package registry. '
            'They’re dimmed because they’re context to be aware of, not part of the '
            'product’s own code. See <em>Vendored</em> in the glossary.</p>'
        )

    return f"""
<section>
  <h2>Top-level modules</h2>
  {section_intro("modules")}
  {toplevel_note}
  {vendored_note}
  <div class="card-grid">{cards}</div>
</section>
"""


# ====================================================================
# System map — layered-bands hero ("how the system fits together")
# ====================================================================
#
# The orienting "big picture": every PRODUCT module drawn as a node in
# its tier band (frontend / backend / data), wired with the cross-tier
# relationships the scanner found. Vendored modules are absent by
# design — this map answers "what did this team build", not "what code
# is in the repo". Fine-grained within-service import detail stays in
# the dependency matrix; this map's job is the system-level wiring.

SYSMAP_FRONTEND_KINDS = frozenset({"frontend", "mobile"})

SYSMAP_W = 1120                 # SVG viewBox width
SYSMAP_MARGIN_X = 20
SYSMAP_NODE_H = 32
SYSMAP_NODE_GAP = 10            # horizontal gap between sibling nodes
SYSMAP_ROW_GAP = 12             # vertical gap between node rows in a cluster
SYSMAP_CLUSTER_PAD = 16         # padding inside a service-cluster outline
SYSMAP_CLUSTER_GAP = 24         # gap between sibling clusters
SYSMAP_CLUSTER_LABEL_H = 24     # space reserved for the cluster's service label
SYSMAP_MIN_CLUSTER_W = 150      # below this a cluster can't hold a node readably
SYSMAP_CLUSTER_ROW_GAP = 20     # vertical gap between wrapped rows of clusters
SYSMAP_BAND_LABEL_W = 28        # vertical band-label gutter on the left
SYSMAP_BAND_GAP = 76            # vertical space between bands (edges route here)
SYSMAP_STORE_W = 88
SYSMAP_STORE_H = 60
SYSMAP_STORE_GAP = 40
SYSMAP_STORE_INSET = 4          # store cylinder vertical inset within data band
SYSMAP_DATA_BAND_PAD = 30       # label + padding below store cylinders
SYSMAP_BOTTOM_PAD = 10          # padding below the last band
SYSMAP_MAX_NODES = {"shallow": 20, "medium": 40, "full": 60}
SYSMAP_MAX_IMPORT_EDGES = 40
SYSMAP_FACET_MAX_W = 520        # compact-width cap for per-service facet clusters
SYSMAP_GUTTER_LANE_STEP = 14    # px between per-target gutter spines (stacked brackets)


def _sysmap_node_w(label: str, is_entry: bool, loc: int = 0) -> float:
    """Node width: fits the (truncated) label, with a LOC-bucket minimum
    so bigger modules read as bigger (spec: 3 size buckets)."""
    text = _truncate_label(label)
    w = len(text) * 7.4 + 24
    if is_entry:
        w += 26  # room for the entry badge
    # LOC buckets: <1k small, 1k-10k medium, >10k large.
    loc_min = 80.0 if loc < 1_000 else (110.0 if loc < 10_000 else 140.0)
    return max(loc_min, min(max(72.0, w), 200.0))


def _sysmap_select(
    data: dict[str, Any], enrichment: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Select product modules for the map and assign them to bands.

    Returns None when there is nothing to draw. Otherwise:
      {
        "bands": {"frontend": [node, ...], "backend": [node, ...]},
        "stores": [store, ...],
        "entry_counts": {module_id: endpoint_count},
        "excluded_vendored": int,
        "truncated": int,
        "services": {service_id: service_dict},
      }
    """
    graph = data.get("module_graph") or {}
    nodes = list(graph.get("nodes") or [])
    services = {s["id"]: s for s in (data.get("services") or [])}
    if not nodes or not services:
        return None

    # Vendored filter: heuristic flag on the node, refined by enrichment.
    cls = (enrichment or {}).get("classification") or {}
    enr_products = {p.get("module_id") for p in (cls.get("products") or [])}
    enr_vendored = {v.get("module_id") for v in (cls.get("vendored") or [])}

    def is_vendored(n: dict[str, Any]) -> bool:
        nid = n.get("id")
        if nid in enr_products:
            return False
        if nid in enr_vendored:
            return True
        return bool(n.get("vendored_guess"))

    product = [n for n in nodes if not is_vendored(n)]
    excluded = len(nodes) - len(product)
    if not product:
        return None

    # Connectivity ranking: degree + entry-point boost, then LOC.
    edges = list(graph.get("edges") or [])
    degree: dict[str, int] = {}
    for e in edges:
        degree[e["source"]] = degree.get(e["source"], 0) + 1
        degree[e["target"]] = degree.get(e["target"], 0) + 1

    topo = data.get("http_topology") or {}
    entry_counts: dict[str, int] = {
        em["module"]: em.get("endpoint_count", 0)
        for em in (topo.get("entry_modules") or [])
        if em.get("module")
    }

    def rank(n: dict[str, Any]) -> tuple[int, int]:
        boost = 1000 if n["id"] in entry_counts else 0
        return (degree.get(n["id"], 0) + boost, n.get("loc", 0))

    product.sort(key=rank, reverse=True)
    cap = SYSMAP_MAX_NODES.get(data.get("scan_depth", "medium")) or SYSMAP_MAX_NODES["medium"]
    truncated = max(0, len(product) - cap)
    visible = product[:cap]

    # Band assignment by the owning service's kind.
    bands: dict[str, list[dict[str, Any]]] = {"frontend": [], "backend": []}
    for n in visible:
        svc = services.get(n.get("service")) or {}
        kind = (svc.get("kind") or "unknown").lower()
        key = "frontend" if kind in SYSMAP_FRONTEND_KINDS else "backend"
        bands[key].append(n)

    stores = list((data.get("data_lineage") or {}).get("stores") or [])

    return {
        "bands": bands,
        "stores": stores,
        "entry_counts": entry_counts,
        "excluded_vendored": excluded,
        "truncated": truncated,
        "services": services,
    }


def _sysmap_layout(
    sel: dict[str, Any], compact_max_w: float | None = None
) -> dict[str, Any]:
    """Compute x/y geometry for every node, cluster, band, and store.

    Deterministic: same selection -> same coordinates. Bands stack
    top-to-bottom (frontend, backend, data); service clusters sit
    side-by-side within a band, each wrapping its nodes into rows.

    ``compact_max_w`` caps each cluster's width so a small service lays
    out as a tidy box (nodes wrap into more rows) instead of stretching
    across the full canvas. The store/data band is centered within the
    same effective width so it aligns under the clusters. When None (the
    overview), layout is byte-identical to the uncapped behavior.
    """
    services = sel["services"]
    entry_counts = sel["entry_counts"]
    placed: dict[str, dict[str, Any]] = {}
    clusters: list[dict[str, Any]] = []
    band_boxes: dict[str, dict[str, float]] = {}

    y_cursor = 0.0
    content_w = SYSMAP_W - 2 * SYSMAP_MARGIN_X - SYSMAP_BAND_LABEL_W
    x_origin = SYSMAP_MARGIN_X + SYSMAP_BAND_LABEL_W

    for band_key in ("frontend", "backend"):
        band_nodes = sel["bands"].get(band_key) or []
        if not band_nodes:
            continue
        band_top = y_cursor

        # Group nodes by service; biggest cluster first for stable layout.
        by_service: dict[str, list[dict[str, Any]]] = {}
        for n in band_nodes:
            by_service.setdefault(n.get("service") or "?", []).append(n)
        service_ids = sorted(by_service, key=lambda sid: (-len(by_service[sid]), sid))

        k = len(service_ids)
        # Clusters arrange in a GRID, not one row: many-service tiers would
        # otherwise shrink each cluster below node width and overflow the
        # viewBox. Wrap onto multiple rows at a minimum cluster width so the
        # band grows vertically and the PDF stays clean (no horizontal scroll).
        cols = int((content_w + SYSMAP_CLUSTER_GAP)
                   // (SYSMAP_MIN_CLUSTER_W + SYSMAP_CLUSTER_GAP))
        cols = max(1, min(cols, k))
        cluster_w = (content_w - (cols - 1) * SYSMAP_CLUSTER_GAP) / cols
        if compact_max_w is not None:
            cluster_w = min(cluster_w, compact_max_w)
        inner_w = cluster_w - 2 * SYSMAP_CLUSTER_PAD

        # Pass 1: lay out each cluster's nodes relative to a (0, 0) origin and
        # record its natural height. Node widths are kept locally (never
        # mutated onto the shared node dict).
        cluster_layouts: list[dict[str, Any]] = []
        for sid in service_ids:
            cnodes = by_service[sid]
            svc = services.get(sid) or {}

            # Wrap nodes into rows; carry each node's width alongside it.
            rows: list[list[tuple[dict[str, Any], float]]] = [[]]
            row_w = 0.0
            for n in cnodes:
                w = _sysmap_node_w(n.get("name") or n["id"],
                                   n["id"] in entry_counts,
                                   n.get("loc", 0))
                if row_w + w > inner_w and rows[-1]:
                    rows.append([])
                    row_w = 0.0
                rows[-1].append((n, w))
                row_w += w + SYSMAP_NODE_GAP

            # Relative node placement: x/y measured from the cluster's own
            # top-left corner. Absolute offsets are applied in pass 2.
            rel: list[dict[str, Any]] = []
            ny = SYSMAP_CLUSTER_LABEL_H + SYSMAP_CLUSTER_PAD
            for row in rows:
                nx = SYSMAP_CLUSTER_PAD
                for n, w in row:
                    rel.append({
                        "id": n["id"], "dx": nx, "dy": ny, "w": w,
                        "node": n,
                    })
                    nx += w + SYSMAP_NODE_GAP
                ny += SYSMAP_NODE_H + SYSMAP_ROW_GAP

            cluster_h = ny - SYSMAP_ROW_GAP + SYSMAP_CLUSTER_PAD
            kind = (svc.get("kind") or "unknown").lower()
            cluster_layouts.append({
                "service_id": sid, "kind": kind,
                "label": svc.get("name") or sid,
                "color": SERVICE_KIND_COLORS.get(kind, SERVICE_KIND_COLORS["unknown"]),
                "h": cluster_h, "rel": rel,
            })

        # Per-grid-row heights: each grid-row is as tall as its tallest cluster.
        num_grid_rows = (k + cols - 1) // cols
        grid_row_h = [0.0] * num_grid_rows
        for i, cl in enumerate(cluster_layouts):
            grid_row_h[i // cols] = max(grid_row_h[i // cols], cl["h"])
        # Cumulative vertical offset of each grid-row (incl. inter-row gaps).
        grid_row_top = [0.0] * num_grid_rows
        for r in range(1, num_grid_rows):
            grid_row_top[r] = (grid_row_top[r - 1] + grid_row_h[r - 1]
                               + SYSMAP_CLUSTER_ROW_GAP)

        # Pass 2: assign grid cells, apply absolute offsets, equalize each
        # cluster's height to ITS grid-row's max, and place nodes.
        band_clusters: list[dict[str, Any]] = []
        for i, cl in enumerate(cluster_layouts):
            row, col = i // cols, i % cols
            cluster_x = x_origin + col * (cluster_w + SYSMAP_CLUSTER_GAP)
            cluster_y = band_top + grid_row_top[row]
            row_h = grid_row_h[row]
            for rn in cl["rel"]:
                placed[rn["id"]] = {
                    "x": cluster_x + rn["dx"], "y": cluster_y + rn["dy"],
                    "w": rn["w"], "h": float(SYSMAP_NODE_H),
                    "band": band_key, "node": rn["node"],
                }
            band_clusters.append({
                "service_id": cl["service_id"],
                "band": band_key,
                "x": cluster_x, "y": cluster_y, "w": cluster_w, "h": row_h,
                "color": cl["color"],
                "label": cl["label"],
                "kind": cl["kind"],
            })

        band_h = (sum(grid_row_h)
                  + (num_grid_rows - 1) * SYSMAP_CLUSTER_ROW_GAP)
        clusters.extend(band_clusters)
        band_boxes[band_key] = {"y": band_top, "h": band_h}
        y_cursor = band_top + band_h + SYSMAP_BAND_GAP

    # Data band: store cylinders, horizontally centered.
    stores = sel["stores"]
    store_pos: dict[str, dict[str, Any]] = {}
    if stores:
        band_top = y_cursor
        total_w = len(stores) * SYSMAP_STORE_W + (len(stores) - 1) * SYSMAP_STORE_GAP
        # Center stores within the SAME effective width as the (possibly
        # capped) clusters so the data band aligns under them. With no cap
        # this equals content_w (overview behavior unchanged).
        effective_w = content_w if compact_max_w is None else min(content_w, compact_max_w)
        sx = x_origin + max(0.0, (effective_w - total_w) / 2)
        for s in stores:
            store_pos[s["id"]] = {
                "x": sx, "y": band_top + SYSMAP_STORE_INSET, "w": float(SYSMAP_STORE_W),
                "h": float(SYSMAP_STORE_H), "store": s,
            }
            sx += SYSMAP_STORE_W + SYSMAP_STORE_GAP
        data_band_h = SYSMAP_STORE_H + SYSMAP_DATA_BAND_PAD
        band_boxes["data"] = {"y": band_top, "h": float(data_band_h)}
        y_cursor = band_top + data_band_h
    elif band_boxes:
        # No stores: trim the trailing band gap.
        y_cursor -= SYSMAP_BAND_GAP

    return {
        "placed": placed,
        "clusters": clusters,
        "stores": store_pos,
        "bands": band_boxes,
        "height": y_cursor + SYSMAP_BOTTOM_PAD,
    }


def _sysmap_edges(
    data: dict[str, Any], layout: dict[str, Any]
) -> list[dict[str, Any]]:
    """Compute drawable edges between placed elements.

    Three kinds:
      "import" — module → module (module_graph.edges), both endpoints placed
      "http"   — frontend service cluster → backend entry module
                 (http_topology.edges joined to endpoints by path); the
                 source is always a frontend cluster. Backend→backend HTTP
                 is shown in the topology section, not here.
      "store"  — service cluster → store cylinder (data_lineage.edges)

    Every edge: {kind, x1, y1, x2, y2, weight, same_band, [color]}.
    Import edges are capped at SYSMAP_MAX_IMPORT_EDGES by weight.
    """
    placed = layout["placed"]
    cluster_by_service = {c["service_id"]: c for c in layout["clusters"]}
    stores = layout["stores"]
    out: list[dict[str, Any]] = []

    # ---- import edges
    # Within-service imports ARE drawn. The spike problem (a vertically-stacked
    # same-cluster pair whose "arc below" collapses into a near-vertical line
    # spearing through the nodes between them) is solved by routing, not by
    # dropping the edge: stacked same-band imports bow out to the cluster's
    # right gutter as a bracket "]" that travels in empty margin space, while
    # near-same-row pairs keep the clean dip-below arc. The dependency matrix
    # further down still carries the full import detail.
    graph_edges = (data.get("module_graph") or {}).get("edges") or []
    drawable = [
        e for e in graph_edges
        if e.get("source") in placed and e.get("target") in placed
        and e["source"] != e["target"]
    ]
    drawable.sort(key=lambda e: -(e.get("weight") or 1))
    capped = drawable[:SYSMAP_MAX_IMPORT_EDGES]

    def _is_stacked_bracket(e: dict[str, Any]) -> bool:
        s = placed[e["source"]]
        t = placed[e["target"]]
        return s["band"] == t["band"] and abs(s["y"] - t["y"]) > 1.2 * s["h"]

    # Pre-pass: every target that will receive a stacked same-band bracket gets
    # its own gutter lane, so edges converging on one hub share a single spine
    # while edges into different hubs sit on separate spines (no merging). The
    # busiest hub takes lane 0 (nearest the cluster); ties break on target id
    # for determinism — no sets influence ordering.
    bracket_count_by_target: dict[str, int] = {}
    for e in capped:
        if _is_stacked_bracket(e):
            tid = e["target"]
            bracket_count_by_target[tid] = bracket_count_by_target.get(tid, 0) + 1
    ranked_targets = sorted(
        bracket_count_by_target,
        key=lambda tid: (-bracket_count_by_target[tid], tid),
    )
    lane_index = {tid: rank for rank, tid in enumerate(ranked_targets)}

    for e in capped:
        s = placed[e["source"]]
        t = placed[e["target"]]
        same_band = s["band"] == t["band"]
        weight = e.get("weight") or 1
        if same_band:
            node_h = s["h"]
            dy = abs(s["y"] - t["y"])
            if dy <= 1.2 * node_h:
                # near same row: gentle dip-below arc between bottom centers
                x1 = s["x"] + s["w"] / 2; y1 = s["y"] + s["h"]
                x2 = t["x"] + t["w"] / 2; y2 = t["y"] + t["h"]
                dip = 22 + abs(x2 - x1) * 0.04
                out.append({
                    "kind": "import", "same_band": True,
                    "src": e["source"], "tgt": e["target"],
                    "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                    "ctrl": [((x1 + x2) / 2, max(y1, y2) + dip)],
                    "weight": weight,
                })
            else:
                # stacked across rows: bracket out to the cluster's right
                # gutter so the curve clears the node column instead of
                # spearing through it.
                s_service = s["node"].get("service")
                t_service = t["node"].get("service")
                clusters = [cluster_by_service.get(s_service),
                            cluster_by_service.get(t_service)]
                rights = [c["x"] + c["w"] for c in clusters if c]
                right = max(rights) if rights else max(s["x"] + s["w"],
                                                       t["x"] + t["w"])
                # Fan the gutter into per-target lanes: edges into the same hub
                # share one spine; different hubs step out by lane.
                base = right + 24
                gx = min(SYSMAP_W - 8,
                         base + lane_index.get(e["target"], 0)
                         * SYSMAP_GUTTER_LANE_STEP)
                x1 = s["x"] + s["w"]; y1 = s["y"] + s["h"] / 2  # source right-mid
                x2 = t["x"] + t["w"]; y2 = t["y"] + t["h"] / 2  # target right-mid
                out.append({
                    "kind": "import", "same_band": True,
                    "src": e["source"], "tgt": e["target"],
                    "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                    "ctrl": [(gx, y1), (gx, y2)],
                    "weight": weight,
                })
        else:
            src_above = s["y"] < t["y"]
            out.append({
                "kind": "import", "same_band": False,
                "src": e["source"], "tgt": e["target"],
                "x1": s["x"] + s["w"] / 2,
                "y1": s["y"] + (s["h"] if src_above else 0),
                "x2": t["x"] + t["w"] / 2,
                "y2": t["y"] + (0 if src_above else t["h"]),
                "weight": weight,
            })

    # ---- HTTP edges: source service cluster → target entry module
    topo = data.get("http_topology") or {}
    ep_module_by_path: dict[tuple[str, str], str] = {}
    for ep in topo.get("endpoints") or []:
        if ep.get("module") and ep.get("path"):
            ep_module_by_path[(ep.get("service"), ep["path"])] = ep["module"]

    http_weight: dict[tuple[str, str], int] = {}
    http_cluster: dict[str, dict[str, Any]] = {}
    for e in topo.get("edges") or []:
        # Keying by (service, path) deliberately collapses methods: GET/POST
        # on the same path map to the same entry module. The diagram only
        # needs the entry module, not the HTTP method.
        target_module = ep_module_by_path.get(
            (e.get("target_service"), e.get("path")))
        if not target_module or target_module not in placed:
            continue
        # HTTP edges originate from frontend clusters only (frontend→backend
        # entry module). Backend→backend service calls are shown in the C4
        # topology section, so they are out of scope here — and anchoring a
        # backend source's bottom to a target's top would render backward.
        src_cluster = cluster_by_service.get(e.get("source_service"))
        if src_cluster is None or src_cluster["band"] != "frontend":
            continue
        key = (e["source_service"], target_module)
        http_weight[key] = http_weight.get(key, 0) + (e.get("weight") or 1)
        http_cluster[e["source_service"]] = src_cluster

    for (src_service, target_module), weight in sorted(http_weight.items()):
        c = http_cluster[src_service]
        t = placed[target_module]
        out.append({
            "kind": "http", "same_band": False,
            "x1": c["x"] + c["w"] / 2, "y1": c["y"] + c["h"],
            "x2": t["x"] + t["w"] / 2, "y2": t["y"],
            "weight": weight,
            # Carried so the bento can name this path ("web → auth").
            "source_service": src_service,
            "target_id": target_module,
        })

    # ---- store edges: service cluster → store cylinder
    for e in (data.get("data_lineage") or {}).get("edges") or []:
        c = cluster_by_service.get(e.get("source_service"))
        sp = stores.get(e.get("target_store"))
        if not c or not sp:
            continue
        kind = (sp["store"].get("kind") or "unknown")
        out.append({
            "kind": "store", "same_band": False,
            "source_service": e.get("source_service"),
            "target_store": e.get("target_store"),
            "x1": c["x"] + c["w"] / 2, "y1": c["y"] + c["h"],
            "x2": sp["x"] + sp["w"] / 2, "y2": sp["y"],
            "weight": e.get("weight") or 1,
            "color": STORE_KIND_COLORS.get(kind, "#888888"),
        })

    return out


def _sysmap_emit_svg(
    layout: dict[str, Any],
    edges: list[dict[str, Any]],
    sel: dict[str, Any],
    enrichment: dict[str, Any] | None = None,
    view_w: float | None = None,
) -> str:
    """Emit the system-map SVG. Drawing order: band labels, cluster
    outlines, edges (under nodes), nodes, stores.

    ``view_w`` overrides the viewBox width so a facet can crop to its actual
    content instead of the full ``SYSMAP_W`` canvas. The overview passes
    nothing (keeps 1120)."""
    height = layout["height"]
    vw = SYSMAP_W if view_w is None else view_w
    parts: list[str] = [
        f'<svg class="sysmap-svg" viewBox="0 0 {vw:.0f} {height:.0f}" '
        f'width="100%" role="img" '
        f'aria-label="System map: product modules in tiers with their connections">'
    ]

    band_titles = {"frontend": "FRONTEND", "backend": "BACKEND", "data": "DATA"}
    # Module descriptions from enrichment become <title> tooltips.
    desc_by_id: dict[str, str] = {}
    for d in (enrichment or {}).get("module_descriptions") or []:
        if d.get("module_id") and d.get("description"):
            desc_by_id[d["module_id"]] = d["description"]

    # ---- band gutter labels (rotated, left edge)
    for band_key, box in layout["bands"].items():
        cy = box["y"] + box["h"] / 2
        parts.append(
            f'<text x="{SYSMAP_MARGIN_X + 8}" y="{cy:.1f}" class="sysmap-band-label" '
            f'transform="rotate(-90 {SYSMAP_MARGIN_X + 8} {cy:.1f})" '
            f'text-anchor="middle">{escape(band_titles.get(band_key, band_key.upper()))}</text>'
        )

    # ---- service cluster outlines + labels
    for c in layout["clusters"]:
        parts.append(
            f'<g class="sysmap-cluster" data-svc="{escape(c["service_id"])}" '
            f'tabindex="0" role="button">'
        )
        parts.append(
            f'<rect x="{c["x"]:.1f}" y="{c["y"]:.1f}" '
            f'width="{c["w"]:.1f}" height="{c["h"]:.1f}" rx="10" '
            f'fill="{escape(c["color"])}" fill-opacity="0.05" '
            f'stroke="{escape(c["color"])}" stroke-opacity="0.45" '
            f'stroke-width="1.25" stroke-dasharray="none" />'
        )
        parts.append(
            f'<text x="{c["x"] + 12:.1f}" y="{c["y"] + 16:.1f}" '
            f'class="sysmap-cluster-label" fill="{escape(c["color"])}">'
            f'{escape(_topov2_truncate(c["label"], 38))}'
            f' <tspan class="sysmap-cluster-kind">· {escape(c["kind"].upper())}</tspan></text>'
        )
        parts.append('</g>')

    # ---- edges (drawn under nodes)
    # data-tgt is the target MODULE id on import and http edges; store edges
    # use data-tgt-store (a store id) instead — the focus JS branches on
    # data-kind to read the right hook.
    for e in edges:
        x1, y1, x2, y2 = e["x1"], e["y1"], e["x2"], e["y2"]
        w = max(1.0, min(4.0, 1.0 + math.log2(max(1, e["weight"]))))
        if e["kind"] == "import":
            sw = max(1.0, min(4.0, 1.0 + math.log2(max(1, e["weight"]))))
            ctrl = e.get("ctrl") or []
            if len(ctrl) == 2:                      # stacked bracket (cubic)
                (c1x, c1y), (c2x, c2y) = ctrl
                dpath = (f'M{e["x1"]:.1f},{e["y1"]:.1f} '
                         f'C{c1x:.1f},{c1y:.1f} {c2x:.1f},{c2y:.1f} '
                         f'{e["x2"]:.1f},{e["y2"]:.1f}')
            elif len(ctrl) == 1:                    # same-row dip (quadratic)
                (cx, cy) = ctrl[0]
                dpath = (f'M{e["x1"]:.1f},{e["y1"]:.1f} '
                         f'Q{cx:.1f},{cy:.1f} {e["x2"]:.1f},{e["y2"]:.1f}')
            else:                                   # cross-band S-curve (existing)
                midy = (e["y1"] + e["y2"]) / 2
                dpath = (f'M{e["x1"]:.1f},{e["y1"]:.1f} '
                         f'C{e["x1"]:.1f},{midy:.1f} {e["x2"]:.1f},{midy:.1f} '
                         f'{e["x2"]:.1f},{e["y2"]:.1f}')
            parts.append(
                f'<path d="{dpath}" class="sysmap-edge-import" '
                f'data-kind="import" data-src="{escape(e["src"])}" '
                f'data-tgt="{escape(e["tgt"])}" '
                f'stroke-width="{sw:.1f}" fill="none" />'
            )
        elif e["kind"] == "http":
            parts.append(
                f'<path d="M{x1:.1f},{y1:.1f} C{x1:.1f},{(y1 + y2) / 2:.1f} '
                f'{x2:.1f},{(y1 + y2) / 2:.1f} {x2:.1f},{y2:.1f}" '
                f'class="sysmap-edge-http" data-kind="http" '
                f'data-src-svc="{escape(e.get("source_service") or "")}" '
                f'data-tgt="{escape(e.get("target_id") or "")}" '
                f'stroke-width="{w:.1f}" fill="none" '
                f'marker-end="url(#sysmap-arrow)" />'
            )
        else:  # store
            color = e.get("color", "#888888")
            parts.append(
                f'<path d="M{x1:.1f},{y1:.1f} C{x1:.1f},{(y1 + y2) / 2:.1f} '
                f'{x2:.1f},{(y1 + y2) / 2:.1f} {x2:.1f},{y2:.1f}" '
                f'class="sysmap-edge-store" data-kind="store" '
                f'data-src-svc="{escape(e.get("source_service") or "")}" '
                f'data-tgt-store="{escape(e.get("target_store") or "")}" '
                f'stroke="{escape(color)}" stroke-opacity="0.75" '
                f'stroke-width="{w:.1f}" fill="none" '
                f'marker-end="url(#sysmap-arrow)" />'
            )

    # Arrowhead marker definition.
    parts.append(
        '<defs><marker id="sysmap-arrow" viewBox="0 0 8 8" refX="7" refY="4" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M0,0 L8,4 L0,8 z" fill="oklch(50% 0.01 250)" /></marker></defs>'
    )

    # ---- module nodes
    entry_counts = sel["entry_counts"]
    # A node is an "orphan" when it is not an endpoint of any drawn edge.
    # Import edges connect two modules (src/tgt); http edges resolve to a
    # target module (target_id). Store edges have no module endpoint (they
    # run service -> store), so they never rescue a node from orphan status.
    connected_ids: set[str] = set()
    for e in edges:
        if e["kind"] == "import":
            if e.get("src"):
                connected_ids.add(e["src"])
            if e.get("tgt"):
                connected_ids.add(e["tgt"])
        elif e["kind"] == "http":
            if e.get("target_id"):
                connected_ids.add(e["target_id"])
    for nid, p in layout["placed"].items():
        n = p["node"]
        label = _truncate_label(n.get("name") or nid)
        is_entry = nid in entry_counts
        title = desc_by_id.get(nid) or nid
        orphan_attr = "" if nid in connected_ids else ' data-orphan="1"'
        parts.append(
            f'<g class="sysmap-node{" is-entry" if is_entry else ""}" '
            f'data-nid="{escape(nid)}" data-svc="{escape(n.get("service") or "")}"'
            f'{orphan_attr} '
            f'tabindex="0" role="button" '
            f'aria-label="{escape((n.get("name") or nid))}">'
        )
        parts.append(f'<title>{escape(title)}</title>')
        parts.append(
            f'<rect x="{p["x"]:.1f}" y="{p["y"]:.1f}" width="{p["w"]:.1f}" '
            f'height="{p["h"]:.1f}" rx="6" class="sysmap-node-rect" />'
        )
        tx = p["x"] + 10
        if is_entry:
            parts.append(
                f'<text x="{tx:.1f}" y="{p["y"] + p["h"] / 2 + 4:.1f}" '
                f'class="sysmap-entry-badge">▸</text>'
            )
            tx += 12
        parts.append(
            f'<text x="{tx:.1f}" y="{p["y"] + p["h"] / 2 + 4:.1f}" '
            f'class="sysmap-node-label">{escape(label)}</text>'
        )
        if is_entry:
            count = entry_counts[nid]
            parts.append(
                f'<text x="{p["x"] + p["w"] - 8:.1f}" y="{p["y"] + p["h"] / 2 + 4:.1f}" '
                f'text-anchor="end" class="sysmap-endpoint-count">{count}</text>'
            )
        parts.append('</g>')

    # ---- store cylinders + labels
    for sid, sp in layout["stores"].items():
        s = sp["store"]
        kind = (s.get("kind") or "unknown")
        color = STORE_KIND_COLORS.get(kind, "#888888")
        full_name = s.get("name") or sid
        parts.append(f'<g class="sysmap-store" data-store="{escape(sid)}">')
        parts.append(f'<title>{escape(full_name)}</title>')
        parts.append(_lineage2_emit_cylinder(sp["x"], sp["y"], sp["w"], sp["h"] - 18, color))
        parts.append(
            f'<text x="{sp["x"] + sp["w"] / 2:.1f}" y="{sp["y"] + sp["h"] + 6:.1f}" '
            f'text-anchor="middle" class="sysmap-store-label">'
            f'{escape(_topov2_truncate(full_name, 14))}</text>'
        )
        parts.append('</g>')

    parts.append("</svg>")
    return "".join(parts)


def _sysmap_headline(sel: dict[str, Any], edges: list[dict[str, Any]]) -> str:
    """One-sentence editorial headline above the map."""
    n_front = len(sel["bands"].get("frontend") or [])
    n_back = len(sel["bands"].get("backend") or [])
    n_stores = len(sel["stores"])
    n_http = sum(1 for e in edges if e["kind"] == "http")
    bits: list[str] = []
    if n_front:
        bits.append(f"<strong>{n_front}</strong> frontend module{'s' if n_front != 1 else ''}")
    bits.append(f"<strong>{n_back}</strong> backend module{'s' if n_back != 1 else ''}")
    if n_stores:
        bits.append(f"<strong>{n_stores}</strong> data store{'s' if n_stores != 1 else ''}")
    headline = "The product is " + ", ".join(bits)
    if n_http:
        headline += f", connected by <strong>{n_http}</strong> HTTP call path{'s' if n_http != 1 else ''}"
    headline += "."
    if sel["excluded_vendored"]:
        headline += (f" <span class='sysmap-excluded'>{sel['excluded_vendored']} vendored "
                     f"module{'s' if sel['excluded_vendored'] != 1 else ''} excluded.</span>")
    return headline


def _observations_for_sysmap(
    sel: dict[str, Any], edges: list[dict[str, Any]], data: dict[str, Any]
) -> list[str]:
    """Data-derived observations for the system map: hubs, tier imbalance,
    orphans, vendored exclusions."""
    obs: list[str] = []
    all_nodes = [n for nodes in sel["bands"].values() for n in nodes]
    if not all_nodes:
        return obs

    # 1. Biggest hub (highest degree among visible nodes).
    graph_edges = (data.get("module_graph") or {}).get("edges") or []
    visible_ids = {n["id"] for n in all_nodes}
    degree: dict[str, int] = {}
    for e in graph_edges:
        if e.get("source") in visible_ids:
            degree[e["source"]] = degree.get(e["source"], 0) + 1
        if e.get("target") in visible_ids:
            degree[e["target"]] = degree.get(e["target"], 0) + 1
    if degree:
        hub_id, hub_deg = max(degree.items(), key=lambda kv: kv[1])
        hub_name = next((n.get("name") or hub_id for n in all_nodes if n["id"] == hub_id), hub_id)
        if hub_deg >= 2:
            obs.append(
                f"<strong><code>{escape(hub_name)}</code></strong> is the most-connected "
                f"module on the map ({hub_deg} import relationships) — changes there "
                f"ripple furthest."
            )

    # 2. Tier imbalance by LOC.
    front_loc = sum(n.get("loc", 0) for n in sel["bands"].get("frontend") or [])
    back_loc = sum(n.get("loc", 0) for n in sel["bands"].get("backend") or [])
    total = front_loc + back_loc
    if total > 0 and back_loc / total >= 0.7:
        obs.append(
            f"<strong>{pct(back_loc, total):.0f}%</strong> of mapped code lives in the "
            f"backend tier — this is a backend-heavy system; the frontend is comparatively thin."
        )
    elif total > 0 and front_loc / total >= 0.7:
        obs.append(
            f"<strong>{pct(front_loc, total):.0f}%</strong> of mapped code lives in the "
            f"frontend tier — most of the logic runs in the client."
        )

    # 3. Orphan modules (no edges at all).
    orphans = [n for n in all_nodes if degree.get(n["id"], 0) == 0]
    if orphans:
        names = ", ".join(f"<code>{escape(n.get('name') or n['id'])}</code>" for n in orphans[:4])
        more = f" (+{len(orphans) - 4} more)" if len(orphans) > 4 else ""
        obs.append(
            f"{len(orphans)} module{'s' if len(orphans) != 1 else ''} on the map have "
            f"<strong>no detected connections</strong>: {names}{more} — either truly "
            f"standalone or wired together in a way the scanner can't see."
        )

    # 4. Vendored exclusions.
    if sel["excluded_vendored"]:
        obs.append(
            f"<strong>{sel['excluded_vendored']}</strong> vendored module"
            f"{'s were' if sel['excluded_vendored'] != 1 else ' was'} excluded from this "
            f"map — third-party code copied into the repo, not part of the product itself."
        )

    # 5. Unreached entry modules (entry points with no HTTP edge landing on them).
    n_http = sum(1 for e in edges if e["kind"] == "http")
    n_entries = sum(1 for n in all_nodes if n["id"] in sel["entry_counts"])
    if n_entries and n_http == 0:
        obs.append(
            f"The map shows <strong>{n_entries}</strong> entry-point module"
            f"{'s' if n_entries != 1 else ''} but <strong>no resolved HTTP call paths</strong> "
            f"from the frontend — calls may go through a gateway or use URLs the scanner "
            f"couldn't match to routes."
        )
    return obs[:5]


def render_sysmap_bento(
    data: dict[str, Any], sel: dict[str, Any], edges: list[dict[str, Any]]
) -> str:
    """2x2 small-multiples beneath the system map.

    The map shows the wiring; the bento adds the magnitudes it
    compresses: tier composition, heaviest call paths, entry-point
    density, and what the map deliberately leaves out.
    """
    front = sel["bands"].get("frontend") or []
    back = sel["bands"].get("backend") or []
    node_name = {n["id"]: (n.get("name") or n["id"])
                 for nodes in sel["bands"].values() for n in nodes}

    def row(label: str, value: str) -> str:
        return (f'<div class="sysmap-row"><span>{label}</span>'
                f'<span class="v">{value}</span></div>')

    # ---------- Tile 1: tier composition ----------
    front_loc = sum(n.get("loc", 0) for n in front)
    back_loc = sum(n.get("loc", 0) for n in back)
    tile1_body = '<div class="sysmap-rows">' + "".join([
        row("Frontend modules", f"{len(front)} · {fmt_num(front_loc)} LOC"),
        row("Backend modules", f"{len(back)} · {fmt_num(back_loc)} LOC"),
        row("Data stores", str(len(sel["stores"]))),
    ]) + '</div>'

    # ---------- Tile 2: heaviest call paths ----------
    https = sorted([e for e in edges if e["kind"] == "http"],
                   key=lambda e: -e["weight"])[:6]
    if https:
        tile2_body = '<div class="sysmap-rows">' + "".join(
            row(f'{escape(_topov2_truncate(e["source_service"], 14))} → '
                f'{escape(_topov2_truncate(node_name.get(e["target_id"], e["target_id"]), 14))}',
                f'{e["weight"]} calls')
            for e in https
        ) + '</div>'
    else:
        tile2_body = ('<p class="sysmap-note">No frontend→backend calls could be '
                      'matched to a route.</p>')

    # ---------- Tile 3: entry points per service ----------
    entries_by_service: dict[str, int] = {}
    for n in front + back:
        if n["id"] in sel["entry_counts"]:
            sid = n.get("service") or "?"
            entries_by_service[sid] = entries_by_service.get(sid, 0) + 1
    if entries_by_service:
        tile3_body = '<div class="sysmap-rows">' + "".join(
            row(escape(_topov2_truncate(sid, 22)),
                f'{cnt} entry module{"s" if cnt != 1 else ""}')
            for sid, cnt in sorted(entries_by_service.items(), key=lambda kv: -kv[1])
        ) + '</div>'
    else:
        tile3_body = '<p class="sysmap-note">No HTTP entry points detected.</p>'

    # ---------- Tile 4: what's not on the map ----------
    tile4_body = '<div class="sysmap-rows">' + "".join([
        row("Vendored modules excluded", str(sel["excluded_vendored"])),
        row("Small modules truncated", str(sel["truncated"])),
    ]) + '</div>'

    return f"""
<div class="sysmap-bento">
  <div class="sysmap-tile">
    <div class="tile-label">Composition</div>
    <div class="tile-headline">Code and stores per tier</div>
    <div class="tile-body">{tile1_body}</div>
  </div>
  <div class="sysmap-tile">
    <div class="tile-label">Call paths</div>
    <div class="tile-headline">Heaviest frontend → backend routes</div>
    <div class="tile-body">{tile2_body}</div>
  </div>
  <div class="sysmap-tile">
    <div class="tile-label">Entry points</div>
    <div class="tile-headline">Where requests arrive, per service</div>
    <div class="tile-body">{tile3_body}</div>
  </div>
  <div class="sysmap-tile">
    <div class="tile-label">Excluded</div>
    <div class="tile-headline">What this map deliberately leaves out</div>
    <div class="tile-body">{tile4_body}</div>
  </div>
</div>
"""


def _sysmap_service_slice(
    data: dict[str, Any], service_id: str
) -> dict[str, Any]:
    """A data-shaped dict scoped to a single service, for a facet mini-map.

    Reuses the overview pipeline (`_sysmap_select`/`_sysmap_layout`/
    `_sysmap_edges`) on a slice that contains ONLY this service's wiring:
      - services: just the one service dict (or a stub if absent).
      - module_graph.nodes: only nodes owned by ``service_id``.
      - module_graph.edges: only INTERNAL imports (both endpoints in the
        service's node set).
      - data_lineage: stores + edges for this service only.
      - http_topology: keep entry_modules/endpoints for the service so entry
        badges still render, but `edges: []` — cross-service HTTP is summarized
        as text in the facet caption, never drawn.
      - scan_depth: carried over so a giant service's facet is capped too.
    """
    svc = next(
        (s for s in (data.get("services") or []) if s.get("id") == service_id),
        {"id": service_id, "name": service_id, "kind": "unknown"},
    )

    graph = data.get("module_graph") or {}
    nodes = [n for n in (graph.get("nodes") or [])
             if n.get("service") == service_id]
    node_ids = {n["id"] for n in nodes}
    edges = [e for e in (graph.get("edges") or [])
             if e.get("source") in node_ids and e.get("target") in node_ids]

    lineage = data.get("data_lineage") or {}
    lin_edges = [e for e in (lineage.get("edges") or [])
                 if e.get("source_service") == service_id]
    targeted = {e.get("target_store") for e in lin_edges if e.get("target_store")}
    lin_stores = [s for s in (lineage.get("stores") or [])
                  if s.get("id") in targeted]

    topo = data.get("http_topology") or {}
    entry_modules = [em for em in (topo.get("entry_modules") or [])
                     if em.get("service") == service_id]
    endpoints = [ep for ep in (topo.get("endpoints") or [])
                 if ep.get("service") == service_id]

    return {
        "scan_depth": data.get("scan_depth", "medium"),
        "services": [svc],
        "module_graph": {"nodes": nodes, "edges": edges},
        "data_lineage": {"stores": lin_stores, "models": [], "edges": lin_edges},
        "http_topology": {
            "entry_modules": entry_modules,
            "endpoints": endpoints,
            "edges": [],
        },
    }


def render_sysmap_facets(
    data: dict[str, Any], enrichment: dict[str, Any] | None = None
) -> str:
    """Static small-multiples: one compact mini-map per product service.

    Each facet shows only that service's internal imports + its stores,
    viewBox-cropped to its own content. Cross-service HTTP is summarized as
    a text "called by / calls" line, never drawn. No JS — the facets sit
    OUTSIDE `.sysmap-frame`, so the overview's focus JS never touches them.

    Returns "" when there are fewer than 2 product services (a single-service
    repo's facet would just duplicate the overview)."""
    services = data.get("services") or []

    # Cross-service HTTP relationships (TEXT only, from the FULL data).
    callers: dict[str, set[str]] = {}   # svc -> services that call it
    callees: dict[str, set[str]] = {}   # svc -> services it calls
    for e in (data.get("http_topology") or {}).get("edges") or []:
        src = e.get("source_service")
        tgt = e.get("target_service")
        if not src or not tgt or src == tgt:
            continue
        callers.setdefault(tgt, set()).add(src)
        callees.setdefault(src, set()).add(tgt)

    cards: list[str] = []
    for svc in services:
        sid = svc.get("id")
        if not sid:
            continue
        slc = _sysmap_service_slice(data, sid)
        sel = _sysmap_select(slc, enrichment)
        if sel is None:
            continue  # no product (non-vendored) nodes for this service
        if not sel["bands"].get("frontend") and not sel["bands"].get("backend"):
            continue
        layout = _sysmap_layout(sel, compact_max_w=SYSMAP_FACET_MAX_W)
        edges = _sysmap_edges(slc, layout)

        # Crop the viewBox to the actual content extent + margin so the facet
        # isn't 1120px of mostly-empty canvas. Fold in EDGE x-extents too:
        # stacked same-band import brackets bow out to a right-gutter spine
        # (gx = right + 24 + lane*step) that can land far past the box edges,
        # so a node/store/cluster-only crop would clip those arcs.
        edge_max_x = 0.0
        for e in edges:
            xs = [e.get("x1", 0), e.get("x2", 0)]
            for (cx, cy) in (e.get("ctrl") or []):
                xs.append(cx)
            edge_max_x = max([edge_max_x] + xs)
        content_max_x = max(
            [edge_max_x]
            + [p["x"] + p["w"] for p in layout["placed"].values()]
            + [sp["x"] + sp["w"] for sp in layout["stores"].values()]
            + [c["x"] + c["w"] for c in layout["clusters"]]
        )
        view_w = content_max_x + SYSMAP_MARGIN_X

        svg = _sysmap_emit_svg(layout, edges, sel, enrichment, view_w=view_w)

        # Caption: name + one-line stat + optional cross-service text.
        n_mod = sum(len(b) for b in sel["bands"].values())
        n_imp = sum(1 for e in edges if e["kind"] == "import")
        n_store = len(sel["stores"])
        stat = (f"{n_mod} module{'s' if n_mod != 1 else ''} · "
                f"{n_imp} import{'s' if n_imp != 1 else ''} · "
                f"{n_store} store{'s' if n_store != 1 else ''}")

        rel_bits: list[str] = []
        cb = sorted(callers.get(sid, set()))
        cl = sorted(callees.get(sid, set()))
        if cb:
            rel_bits.append("called by " + ", ".join(escape(c) for c in cb))
        if cl:
            rel_bits.append("calls " + ", ".join(escape(c) for c in cl))
        rel_html = (f'<span class="sysmap-facet-rel">{" · ".join(rel_bits)}</span>'
                    if rel_bits else "")

        name = escape(svc.get("name") or sid)
        cards.append(
            f'<figure class="sysmap-facet-card">'
            f'<figcaption><strong>{name}</strong> '
            f'<span class="sysmap-facet-stat">{escape(stat)}</span>'
            f'{rel_html}</figcaption>'
            f'{svg}</figure>'
        )

    if len(cards) < 2:
        return ""

    return (
        '<div class="sysmap-facets">'
        '<h3>Per-service views</h3>'
        '<p class="section-intro">Each service in isolation: its own modules and '
        'internal imports, plus the data stores it writes to. Cross-service calls '
        'are summarized in each caption rather than drawn.</p>'
        '<div class="sysmap-facet-grid">' + "".join(cards) + '</div>'
        '</div>'
    )


# Inline focus behaviour for the System Map. Plain (non-f) string so its JS
# braces survive interpolation; referenced as {SYSMAP_JS} inside the f-string
# section. Dependency-free IIFE (no framework/CDN/import/require). It only
# toggles CSS classes — never touches innerHTML — so it degrades to the full
# static map when JS is off, and the print stylesheet restores opacity anyway.
#
# SCOPING: deliberately bound to the ONE overview svg at
# `#codemap-sysmap-section .sysmap-frame .sysmap-svg`. The per-service facet
# svgs (Task 5) live OUTSIDE `.sysmap-frame`, so this JS never touches them —
# they stay static small-multiples.
SYSMAP_JS = """
<script>
(function () {
  'use strict';
  var svg = document.querySelector(
    '#codemap-sysmap-section .sysmap-frame .sysmap-svg');
  if (!svg) return;  // graceful no-op if the overview map is absent

  var nodes = Array.prototype.slice.call(svg.querySelectorAll('.sysmap-node'));
  var clusters = Array.prototype.slice.call(
    svg.querySelectorAll('.sysmap-cluster'));
  var stores = Array.prototype.slice.call(svg.querySelectorAll('.sysmap-store'));
  var importEdges = Array.prototype.slice.call(
    svg.querySelectorAll('[data-kind="import"]'));
  var httpEdges = Array.prototype.slice.call(
    svg.querySelectorAll('[data-kind="http"]'));
  var storeEdges = Array.prototype.slice.call(
    svg.querySelectorAll('[data-kind="store"]'));

  // Index nodes/stores by id for O(1) lookup.
  var nodeById = {};
  nodes.forEach(function (n) {
    var id = n.getAttribute('data-nid');
    if (id) nodeById[id] = n;
  });
  var storeById = {};
  stores.forEach(function (s) {
    var id = s.getAttribute('data-store');
    if (id) storeById[id] = s;
  });

  // Import adjacency: node id -> { nbrs: Set(node id), edges: [path] }.
  var adj = {};
  function ensure(id) {
    if (!adj[id]) adj[id] = { nbrs: {}, edges: [] };
    return adj[id];
  }
  importEdges.forEach(function (p) {
    var s = p.getAttribute('data-src');
    var t = p.getAttribute('data-tgt');
    if (!s || !t) return;  // skip malformed edges
    ensure(s).edges.push(p);
    ensure(t).edges.push(p);
    adj[s].nbrs[t] = true;
    adj[t].nbrs[s] = true;
  });

  // A click/keyboard selection survives mouseleave. Track the pinned ELEMENT
  // (node or cluster) explicitly — NOT the shared is-active class. A pinned
  // cluster marks all its member nodes is-active, so keying the toggle off the
  // class made clicking a member node read as "re-click the pin" and clear,
  // instead of drilling into that node. With the element tracked directly:
  // re-clicking the pinned element clears; clicking a DIFFERENT element re-pins
  // (switches focus, e.g. service -> member module drill-down).
  var pinnedEl = null;

  function clearActive() {
    svg.classList.remove('has-focus');
    nodes.forEach(function (n) { n.classList.remove('is-active'); });
    clusters.forEach(function (c) { c.classList.remove('is-active'); });
    stores.forEach(function (s) { s.classList.remove('is-active'); });
    importEdges.forEach(function (e) { e.classList.remove('is-active'); });
    httpEdges.forEach(function (e) { e.classList.remove('is-active'); });
    storeEdges.forEach(function (e) { e.classList.remove('is-active'); });
  }

  function activate(el) { if (el) el.classList.add('is-active'); }

  // Node focus = the node + its import-edge neighbours + the import-edges
  // between them. Fade everything else.
  function applyNodeFocus(nid) {
    var node = nodeById[nid];
    if (!node) return;
    clearActive();
    svg.classList.add('has-focus');
    activate(node);
    var a = adj[nid];
    if (a) {
      Object.keys(a.nbrs).forEach(function (other) {
        activate(nodeById[other]);
      });
      a.edges.forEach(activate);
    }
  }

  // Cluster focus = the whole service subgraph: every node in the service,
  // every import-edge touching the service, every http/store edge from the
  // service (or http edge landing on a node in it), and the service's stores.
  function applyClusterFocus(svc) {
    if (!svc) return;
    clearActive();
    svg.classList.add('has-focus');
    var inSvc = {};
    nodes.forEach(function (n) {
      if (n.getAttribute('data-svc') === svc) {
        inSvc[n.getAttribute('data-nid')] = true;
        activate(n);
      }
    });
    clusters.forEach(function (c) {
      if (c.getAttribute('data-svc') === svc) activate(c);
    });
    importEdges.forEach(function (p) {
      if (inSvc[p.getAttribute('data-src')] || inSvc[p.getAttribute('data-tgt')]) {
        activate(p);
      }
    });
    httpEdges.forEach(function (p) {
      if (p.getAttribute('data-src-svc') === svc ||
          inSvc[p.getAttribute('data-tgt')]) {
        activate(p);
      }
    });
    storeEdges.forEach(function (p) {
      if (p.getAttribute('data-src-svc') === svc) {
        activate(p);
        activate(storeById[p.getAttribute('data-tgt-store')]);
      }
    });
  }

  function clearFocus() { pinnedEl = null; clearActive(); }

  // ---- node interactions
  // Hover previews only when nothing is pinned. Clicking the pinned node clears;
  // clicking a different node (re-)pins it — drilling in even from a pinned
  // service whose members are all is-active.
  function toggleNode(n, nid) {
    if (pinnedEl === n) {
      clearFocus();  // clicking the pinned node again clears
    } else {
      applyNodeFocus(nid);
      pinnedEl = n;
    }
  }
  nodes.forEach(function (n) {
    var nid = n.getAttribute('data-nid');
    n.addEventListener('mouseenter', function () {
      if (!pinnedEl) applyNodeFocus(nid);
    });
    n.addEventListener('mouseleave', function () {
      if (!pinnedEl) clearActive();
    });
    n.addEventListener('focus', function () {
      if (!pinnedEl) applyNodeFocus(nid);
    });
    n.addEventListener('blur', function () {
      if (!pinnedEl) clearActive();
    });
    n.addEventListener('click', function (ev) {
      ev.stopPropagation();
      toggleNode(n, nid);
    });
    n.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter' || ev.key === ' ' || ev.key === 'Spacebar') {
        ev.preventDefault();
        ev.stopPropagation();
        toggleNode(n, nid);
      }
    });
  });

  // ---- cluster interactions (pin a service subgraph)
  // Same element-keyed toggle: re-clicking the pinned cluster clears; clicking
  // a member node afterwards re-pins to that node (drill-down) because the
  // member node !== the pinned cluster element.
  function toggleCluster(c, svc) {
    if (pinnedEl === c) {
      clearFocus();
    } else {
      applyClusterFocus(svc);
      pinnedEl = c;
    }
  }
  clusters.forEach(function (c) {
    var svc = c.getAttribute('data-svc');
    c.addEventListener('click', function (ev) {
      ev.stopPropagation();
      toggleCluster(c, svc);
    });
    c.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter' || ev.key === ' ' || ev.key === 'Spacebar') {
        ev.preventDefault();
        ev.stopPropagation();
        toggleCluster(c, svc);
      }
    });
  });

  // Nothing pinned and no lingering focus → clearing is a no-op; skip the work.
  function nothingToClear() {
    return !pinnedEl && !svg.classList.contains('has-focus');
  }

  // ---- background click clears (a click that reached the svg itself)
  svg.addEventListener('click', function () {
    if (nothingToClear()) return;
    clearFocus();
  });

  // ---- Escape clears + unpins
  document.addEventListener('keydown', function (ev) {
    if (ev.key !== 'Escape' || nothingToClear()) return;
    clearFocus();
  });

  // ---- layer-toggle chips
  // Scope the chip query to the SAME frame as the overview svg so the Task 5
  // per-service facet maps (which live outside .sysmap-frame) are untouched.
  // Each chip's data-layer maps to the svg's hide-<layer> class: pressing the
  // chip removes that layer (sets aria-pressed=false + adds the hide class);
  // pressing again restores it. Class-toggle only — no innerHTML, no deps.
  var hideClassByLayer = {
    'import': 'hide-import',
    'http': 'hide-http',
    'store': 'hide-store',
    'orphan': 'hide-orphan'
  };
  var frame = svg.closest('.sysmap-frame');
  var chips = frame
    ? Array.prototype.slice.call(frame.querySelectorAll('.sysmap-chip'))
    : [];
  chips.forEach(function (chip) {
    var hideClass = hideClassByLayer[chip.getAttribute('data-layer')];
    if (!hideClass) return;
    chip.addEventListener('click', function () {
      var on = chip.getAttribute('aria-pressed') !== 'false';
      chip.setAttribute('aria-pressed', on ? 'false' : 'true');
      svg.classList.toggle(hideClass, on);  // pressing OFF hides that layer
    });
  });
})();
</script>
"""


def render_system_map(
    data: dict[str, Any], enrichment: dict[str, Any] | None = None
) -> str:
    """The 'How the system fits together' hero — layered-bands map of
    product modules. Renders deterministically; enrichment only refines
    the vendored filter and adds node tooltips."""
    sel = _sysmap_select(data, enrichment)
    if sel is None:
        return ""
    if not sel["bands"].get("frontend") and not sel["bands"].get("backend"):
        return ""
    layout = _sysmap_layout(sel)
    edges = _sysmap_edges(data, layout)
    svg = _sysmap_emit_svg(layout, edges, sel, enrichment)
    headline = _sysmap_headline(sel, edges)

    truncation_note = ""
    if sel["truncated"]:
        truncation_note = (
            f'<p class="sysmap-note">+{sel["truncated"]} smaller modules not shown '
            f'(map shows the most-connected modules; the dependency matrix below '
            f'shows everything).</p>'
        )

    legend = (
        '<div class="sysmap-legend">'
        '<span class="sysmap-leg-item"><span class="sysmap-leg-http"></span> HTTP call</span>'
        '<span class="sysmap-leg-item"><span class="sysmap-leg-import"></span> code import</span>'
        '<span class="sysmap-leg-item"><span class="sysmap-leg-store"></span> reads/writes data</span>'
        '<span class="sysmap-leg-item">▸ entry point (number = endpoints)</span>'
        '</div>'
    )

    observations_html = _render_observations(_observations_for_sysmap(sel, edges, data))
    bento_html = render_sysmap_bento(data, sel, edges)
    facets_html = render_sysmap_facets(data, enrichment)

    controls = (
        '<div class="sysmap-controls" role="group" aria-label="Map filters">'
        '<button type="button" class="sysmap-chip" data-layer="import" aria-pressed="true">Imports</button>'
        '<button type="button" class="sysmap-chip" data-layer="http" aria-pressed="true">HTTP</button>'
        '<button type="button" class="sysmap-chip" data-layer="store" aria-pressed="true">Stores</button>'
        '<button type="button" class="sysmap-chip" data-layer="orphan" aria-pressed="true">Orphans</button>'
        '<span class="sysmap-hint">hover a module to trace · click to pin · click a service to isolate</span>'
        '</div>'
    )

    return f"""
<section id="codemap-sysmap-section">
  <h2>How the system fits together</h2>
  {section_intro("sysmap")}
  <div class="sysmap-frame">
    <p class="sysmap-headline">{headline}</p>
    {controls}
    <div class="sysmap-wrap">{svg}</div>
    {legend}
    {truncation_note}
  </div>
  {observations_html}
  {bento_html}
  {facets_html}
  {SYSMAP_JS}
</section>
"""


# Kind-based service zone tints. Backend gets a warm orange, frontend a
# cool blue, library purple, anything unclassified a neutral gray. These
# match the spirit of the reference TOPOLOGY.html palette so the report
# reads as "intentionally designed" rather than "auto-generated."
SERVICE_KIND_COLORS: dict[str, str] = {
    "backend": "#cc785c",   # ember
    "frontend": "#7aa2f7",  # sky
    "library": "#bb9af7",   # lavender
    "service": "#a0a0a0",   # neutral
    "unknown": "#a0a0a0",
}


# ====================================================================
# Architect-observation bullets (shared across all hero sections)
# ====================================================================
#
# Each hero section gets an "OBSERVATIONS" block between the headline
# and the bento. The block lists 3-5 data-derived insights aimed at
# "what should I worry about" rather than "what's the story" — the
# latter is the editorial headline's job. Together they form a
# headline + concerns + bento rhythm under each diagram.

UTIL_MODULE_NAMES = {
    "common", "shared", "utils", "util", "prisma", "db", "lib",
    "core", "types", "helpers", "models", "schemas",
}


def _render_observations(items: list[str]) -> str:
    """Render a list of observation strings as an inset bullet list.

    Each item is HTML-safe author-controlled copy (never user input);
    items contain inline <strong>/<code> tags by design.
    """
    if not items:
        return ""
    bullets = "".join(f"<li>{i}</li>" for i in items)
    return (
        '<aside class="observations" role="note">'
        '<div class="observations-label">Observations</div>'
        f'<ul>{bullets}</ul>'
        '</aside>'
    )


def _observations_for_modgraph(
    matrix_nodes: list[dict[str, Any]],
    cells: list[tuple[int, int, int]],
    intra_count: int,
    cross_count: int,
    services: list[dict[str, Any]],
) -> list[str]:
    """Architect concerns derived from the module-graph matrix.

    Items emitted (when applicable):
      - highest fan-out module (imports from many others) — god-module risk
      - highest fan-in module (depended upon by many) — change blast radius
      - cross-service module imports — leaks the service boundary
      - shared-utility concentration — bus-factor risk
    """
    from collections import Counter
    obs: list[str] = []
    out_counts: Counter = Counter()
    in_counts: Counter = Counter()
    for src, tgt, _w in cells:
        if src == tgt:
            continue
        out_counts[src] += 1
        in_counts[tgt] += 1

    if out_counts:
        top_src_idx, top_out = out_counts.most_common(1)[0]
        if top_out >= 4:
            mod_name = matrix_nodes[top_src_idx].get("name") or ""
            svc = matrix_nodes[top_src_idx].get("service") or ""
            svc_suffix = f" in <code>{escape(svc)}</code>" if svc else ""
            obs.append(
                f"<strong><code>{escape(mod_name)}</code></strong>{svc_suffix} "
                f"imports from <strong>{top_out}</strong> other modules — "
                f"the highest fan-out in the codebase. Watch for "
                f"god-module drift."
            )
    if in_counts:
        top_tgt_idx, top_in = in_counts.most_common(1)[0]
        if top_in >= 4:
            mod_name = matrix_nodes[top_tgt_idx].get("name") or ""
            svc = matrix_nodes[top_tgt_idx].get("service") or ""
            svc_suffix = f" in <code>{escape(svc)}</code>" if svc else ""
            obs.append(
                f"<strong><code>{escape(mod_name)}</code></strong>{svc_suffix} "
                f"is depended on by <strong>{top_in}</strong> other modules — "
                f"any change here ripples widely; treat as a stable "
                f"interface."
            )

    if cross_count == 0 and intra_count > 0:
        obs.append(
            "<strong>Zero cross-service imports</strong> were detected — "
            "services are fully decoupled at the file level. "
            "Network calls (see the topology section) are the only "
            "inter-service contract."
        )
    elif cross_count > 0 and cross_count >= max(2, intra_count // 4):
        obs.append(
            f"<strong>{cross_count}</strong> imports cross service "
            f"boundaries — services share code at the file level, which "
            f"can complicate independent deploys and version pinning."
        )

    # Concentration of "utility hub" targets — bus-factor risk.
    util_in: Counter = Counter()
    for src, tgt, _w in cells:
        if src == tgt:
            continue
        tgt_name = (matrix_nodes[tgt].get("name") or "").lower()
        if tgt_name in UTIL_MODULE_NAMES:
            util_in[tgt] += 1
    if util_in:
        top_util_idx, top_util_in = util_in.most_common(1)[0]
        if top_util_in >= 5:
            util_name = matrix_nodes[top_util_idx].get("name") or ""
            obs.append(
                f"<strong><code>{escape(util_name)}</code></strong> is a "
                f"<em>utility hub</em> — <strong>{top_util_in}</strong> "
                f"modules depend on it. Strong consistency benefit; "
                f"also a single point of churn when its API evolves."
            )

    return obs[:5]


def _observations_for_topology(
    nodes: list[dict[str, Any]],
    pair_agg: dict[tuple[str, str], dict[str, Any]],
    tiers: dict[str, int],
    topo: dict[str, Any],
) -> list[str]:
    """Architect concerns derived from the service-topology DAG."""
    from collections import Counter
    obs: list[str] = []

    if len(nodes) >= 2 and pair_agg:
        # Hub detection: service touched by many edges.
        endpoint_degree: Counter = Counter()
        for (src, tgt), agg in pair_agg.items():
            endpoint_degree[tgt] += 1
            endpoint_degree[src] += 1
        if endpoint_degree:
            hub_id, hub_deg = endpoint_degree.most_common(1)[0]
            if hub_deg >= 2 and hub_deg > 1:
                hub_name = next(
                    (n.get("name") or n["id"]
                     for n in nodes if n["id"] == hub_id),
                    hub_id,
                )
                obs.append(
                    f"<strong>{escape(hub_name)}</strong> sits on "
                    f"<strong>{hub_deg}</strong> of the {len(pair_agg)} "
                    f"call edges — it's the network hub. Loss of this "
                    f"service breaks the most flows."
                )

    # Heaviest single edge dominance
    if pair_agg:
        total_calls = sum(b["count"] for b in pair_agg.values())
        heaviest = max(pair_agg.items(), key=lambda kv: kv[1]["count"])
        if total_calls > 0:
            share = heaviest[1]["count"] / total_calls
            if share >= 0.7 and len(pair_agg) > 1:
                src_id, tgt_id = heaviest[0]
                src_name = next(
                    (n.get("name") or n["id"]
                     for n in nodes if n["id"] == src_id),
                    src_id,
                )
                tgt_name = next(
                    (n.get("name") or n["id"]
                     for n in nodes if n["id"] == tgt_id),
                    tgt_id,
                )
                obs.append(
                    f"<strong>{share * 100:.0f}%</strong> of all "
                    f"inter-service traffic flows on a single edge: "
                    f"<strong>{escape(src_name)}</strong> → "
                    f"<strong>{escape(tgt_name)}</strong>. That edge is "
                    f"the system's primary failure-correlation surface."
                )

    # Frontends that fan out to multiple backends
    fronted_targets: dict[str, set[str]] = {}
    for (src, tgt), _agg in pair_agg.items():
        src_node = next((n for n in nodes if n["id"] == src), None)
        if src_node and (src_node.get("kind") == "frontend"):
            fronted_targets.setdefault(src, set()).add(tgt)
    for src, targets in fronted_targets.items():
        if len(targets) >= 2:
            src_name = next(
                (n.get("name") or n["id"] for n in nodes if n["id"] == src),
                src,
            )
            obs.append(
                f"<strong>{escape(src_name)}</strong> talks directly to "
                f"<strong>{len(targets)}</strong> backends — consider "
                f"whether a single API gateway would simplify the client "
                f"surface."
            )

    # Frameworks heterogeneity
    fws = topo.get("frameworks_detected") or []
    if len(fws) >= 2:
        obs.append(
            f"<strong>{len(fws)} server frameworks</strong> are in use "
            f"(<code>{escape(', '.join(fws))}</code>) — heterogeneous, "
            f"meaning observability, middleware, and request-handling "
            f"conventions differ per service."
        )

    # Unresolved calls
    unresolved = int(topo.get("unresolved_client_count") or 0)
    if unresolved >= 3:
        obs.append(
            f"<strong>{unresolved}</strong> outbound HTTP calls didn't "
            f"resolve to a known endpoint — likely external APIs, "
            f"dynamic URLs, or routes the scanner missed. They aren't "
            f"drawn in the diagram."
        )

    return obs[:5]


def _observations_for_lineage(
    stores: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    services_full: list[dict[str, Any]],
) -> list[str]:
    """Architect concerns derived from the data-lineage Sankey."""
    obs: list[str] = []
    if not stores:
        return obs

    # Single-store dominance
    store_inbound: dict[str, int] = {s["id"]: 0 for s in stores}
    for e in edges:
        sid = e.get("target_store", "")
        store_inbound[sid] = store_inbound.get(sid, 0) + int(e.get("weight") or 1)
    total_models = sum(store_inbound.values())
    if total_models > 0:
        connected = [(sid, c) for sid, c in store_inbound.items() if c > 0]
        connected.sort(key=lambda kv: -kv[1])
        if connected:
            top_store_id, top_count = connected[0]
            share = top_count / total_models
            if share >= 0.9 and total_models >= 5:
                store_name = next(
                    (s.get("name") or s["id"]
                     for s in stores if s["id"] == top_store_id),
                    top_store_id,
                )
                obs.append(
                    f"<strong>{share * 100:.0f}%</strong> of modeled writes "
                    f"go to <strong>{escape(store_name)}</strong> — "
                    f"the primary data store. No read replica or "
                    f"write/cache split was detected at the ORM level."
                )

    # Write contention: multiple services to one store
    writers_per_store: dict[str, set[str]] = {}
    for e in edges:
        writers_per_store.setdefault(e.get("target_store", ""), set()).add(
            e.get("source_service") or ""
        )
    contested = [(sid, w) for sid, w in writers_per_store.items() if len(w) >= 2]
    for sid, writers in contested:
        store_name = next(
            (s.get("name") or s["id"]
             for s in stores if s["id"] == sid),
            sid,
        )
        obs.append(
            f"<strong>{len(writers)} services</strong> write to "
            f"<strong>{escape(store_name)}</strong> "
            f"(<code>{escape(', '.join(sorted(writers)))}</code>) — "
            f"shared ownership of a data store. Watch for schema-coupling "
            f"and migration coordination overhead."
        )

    # Unmodeled stores
    unlinked = [
        s for s in stores
        if store_inbound.get(s["id"], 0) == 0
    ]
    if unlinked and edges:
        names = ", ".join(escape(s.get("name") or s["id"]) for s in unlinked[:4])
        obs.append(
            f"<strong>{len(unlinked)} store{'s' if len(unlinked) != 1 else ''}</strong> "
            f"({names}) {'are' if len(unlinked) != 1 else 'is'} referenced "
            f"in env config but no ORM models declare {'them' if len(unlinked) != 1 else 'it'} "
            f"— direct client-library usage. Add coverage by inspecting "
            f"the matching service's source for the relevant SDK calls."
        )

    # ORM diversity
    fws: set[str] = set()
    for e in edges:
        for f in e.get("frameworks") or []:
            fws.add(f)
    if len(fws) >= 2:
        obs.append(
            f"<strong>{len(fws)} ORM frameworks</strong> are in use "
            f"(<code>{escape(', '.join(sorted(fws)))}</code>) — different "
            f"migration paths, different schema-evolution tooling per "
            f"service."
        )

    # No edges but stores
    if not edges and stores:
        kinds = sorted({s.get("kind") or "unknown" for s in stores})
        obs.append(
            f"No ORM model declarations were detected. All "
            f"<strong>{len(stores)}</strong> stores "
            f"(<code>{escape(', '.join(kinds))}</code>) are reached "
            f"via raw client libraries — Redis SDK, S3 boto3, Firebase "
            f"Admin, etc. Worth confirming each is intentional."
        )

    return obs[:5]


# ====================================================================
# Bertin-style dependency matrix + supporting bento of small multiples.
# The module-graph section's hero. The matrix is a deterministic layout
# — every render of the same data produces the same picture, which makes
# it suitable for client deliverables and print.
#
# Rows and columns are modules grouped by service, then ordered by LOC
# desc within each service. A cell at (r, c) is shaded by edge weight
# (log scale) if module r imports module c. Service blocks along the
# diagonal indicate internal cohesion; off-diagonal mass indicates
# cross-service coupling.

MAX_MATRIX_NODES = 55

# Axis labels are truncated to this many characters; the full module name
# is preserved in an SVG <title> for hover. The gutters are sized from this
# bound so long names can never overflow or overprint each other.
MAX_LABEL_CHARS = 18


def _matrix_cell_size(n: int) -> int:
    """Adapt cell size to N. The floor (16px at the node cap) is kept at or
    above the label line-height so adjacent axis labels never collide
    vertically, and so the 45deg-rotated column labels keep enough
    perpendicular spacing to stay legible. Larger N yields a bigger SVG
    that scrolls on screen and scales-to-fit on the landscape PDF page."""
    if n <= 18:
        return 34
    if n <= 28:
        return 26
    if n <= 40:
        return 20
    if n <= 55:
        return 16
    return 14  # absolute floor; never below label line-height


def _module_short_name(module_id: str, leaf: str) -> str:
    """Display name for matrix axis labels.

    `leaf` is the trailing path segment (e.g. "workouts" for
    "Back-End-FitTalk/src/modules/workouts"). When two modules share
    the same leaf (rare but possible across services) we'd want to
    disambiguate, but the matrix already groups by service so the
    leaf is enough on screen.
    """
    return leaf or module_id.rsplit("/", 1)[-1]


def _truncate_label(name: str, limit: int = MAX_LABEL_CHARS) -> str:
    """Truncate a label to `limit` chars with an ellipsis. The full name is
    surfaced separately via an SVG <title>, so no information is lost."""
    return name if len(name) <= limit else name[: limit - 1] + "…"


def render_module_graph_section(data: dict[str, Any]) -> str:
    graph = data.get("module_graph") or {}
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    services = data.get("services") or []
    if not nodes:
        return ""

    # ------ Order nodes: group by service > domain > LOC desc ------
    # Domain = parent folder of the module relative to its service.
    # For `Back-End-FitTalk/src/modules/workouts` (service `Back-End-FitTalk`),
    # the domain is `src/modules`; for `Back-End-FitTalk/src/common` it's
    # `src`. Visible as faint dotted dividers within service blocks.
    service_index = {s["id"]: i for i, s in enumerate(services)}
    no_svc_idx = len(services)  # "loose" modules sort to the end

    def _domain_of(node: dict[str, Any]) -> str:
        mod_id = node.get("id") or ""
        svc = node.get("service") or ""
        if svc and mod_id.startswith(svc + "/"):
            rel = mod_id[len(svc) + 1 :]
        else:
            rel = mod_id
        if "/" in rel:
            return rel.rsplit("/", 1)[0]
        return ""

    def _sort_key(node: dict[str, Any]) -> tuple:
        svc = node.get("service")
        return (
            service_index.get(svc, no_svc_idx) if svc else no_svc_idx,
            _domain_of(node),
            -(node.get("loc") or 0),
            node.get("name") or "",
        )

    ordered = sorted(nodes, key=_sort_key)
    truncated = len(ordered) > MAX_MATRIX_NODES
    matrix_nodes = ordered[:MAX_MATRIX_NODES]
    n = len(matrix_nodes)

    # ------ Adjacency from edges (clamped to matrix subset) ------
    id_to_idx: dict[str, int] = {node["id"]: i for i, node in enumerate(matrix_nodes)}
    cells: list[tuple[int, int, int]] = []
    max_weight = 1
    intra_count = 0
    cross_count = 0
    for edge in edges:
        src = id_to_idx.get(edge.get("source", ""))
        tgt = id_to_idx.get(edge.get("target", ""))
        if src is None or tgt is None:
            continue
        weight = int(edge.get("weight") or 1)
        cells.append((src, tgt, weight))
        if weight > max_weight:
            max_weight = weight
        if matrix_nodes[src].get("service") == matrix_nodes[tgt].get("service"):
            intra_count += 1
        else:
            cross_count += 1

    # ------ Service blocks (contiguous runs in `matrix_nodes`) ------
    # Each block is (svc_id_or_None, start_idx, end_idx_exclusive, color, name)
    blocks: list[tuple[str | None, int, int, str, str]] = []
    if matrix_nodes:
        run_svc = matrix_nodes[0].get("service")
        run_start = 0
        for i in range(1, n + 1):
            if i == n or matrix_nodes[i].get("service") != run_svc:
                svc_meta = next(
                    (s for s in services if s["id"] == run_svc), None
                ) if run_svc else None
                color = (svc_meta or {}).get("color", "#9aa0a6")
                label = (svc_meta or {}).get("name") or (run_svc or "misc")
                blocks.append((run_svc, run_start, i, color, label))
                if i < n:
                    run_svc = matrix_nodes[i].get("service")
                    run_start = i

    # ------ Domain sub-dividers (within each service block) ------
    # Only emit a domain line when a service block contains more than
    # one domain — otherwise the line carries no information.
    domain_dividers: list[int] = []
    for _svc_id, start, end, _color, _name in blocks:
        run_dom = _domain_of(matrix_nodes[start])
        domains_in_block: set[str] = {run_dom}
        candidate_dividers: list[int] = []
        for i in range(start + 1, end):
            d = _domain_of(matrix_nodes[i])
            if d != run_dom:
                candidate_dividers.append(i)
                run_dom = d
                domains_in_block.add(d)
        # Only emit if the service actually has multiple domains.
        if len(domains_in_block) >= 2:
            domain_dividers.extend(candidate_dividers)

    # ------ Geometry ------
    cell = _matrix_cell_size(n)
    label_font_size = 11 if cell >= 16 else 10
    band = 8          # service-color stripe on the outer edges
    grid_size = n * cell

    # Size the label gutters from the longest *displayed* (truncated) name so
    # labels are always fully contained — no clipping at the left edge, no
    # rotated label overrunning the top axis title or the right edge.
    char_px = label_font_size * 0.62  # ~monospace glyph advance
    longest_label = max(
        (
            len(_truncate_label(_module_short_name(nd.get("id", ""), nd.get("name", ""))))
            for nd in matrix_nodes
        ),
        default=8,
    )
    label_px = longest_label * char_px
    diag_px = label_px * 0.7071        # 45deg projection of a label
    # Dedicated outer strip for the axis titles, OUTSIDE the module-label
    # gutters. Without it the rotated "IMPORTING" title and the long module
    # row-labels share the same space and overprint each other. Because the
    # labels are anchored to the grid edge (right edge of the left gutter,
    # bottom of the top gutter), widening each gutter by axis_pad shifts the
    # labels along with the grid and frees a clean strip at the far edge for
    # the title to sit in on its own.
    axis_pad = 30
    axis_title_fs = label_font_size + 4   # noticeably larger than the module labels
    label_w = int(label_px) + 14 + axis_pad      # left gutter: Y labels + title strip
    label_h_top = int(diag_px) + 22 + axis_pad   # top gutter: rotated X labels + title strip
    right_pad = int(diag_px) + 8       # rotated X labels extend up-and-right

    svg_w = label_w + band + grid_size + right_pad
    svg_h = label_h_top + band + grid_size + 28  # +28 for x-axis title at bottom

    grid_x0 = label_w + band
    grid_y0 = label_h_top + band

    # ------ Cell-opacity scale (log) ------
    log_denom = math.log(max(2, max_weight) + 1)
    def _opacity(w: int) -> float:
        # Clamp to [0.18, 0.95] so even weight=1 reads, max never blacks out.
        v = math.log(w + 1) / log_denom
        return round(0.18 + 0.77 * v, 3)

    # ------ Build SVG pieces ------
    accent = "var(--accent)"

    parts: list[str] = []
    parts.append(
        f'<svg class="modgraph-matrix" '
        f'viewBox="0 0 {svg_w} {svg_h}" '
        f'width="{svg_w}" '
        f'role="img" '
        f'aria-label="Module dependency matrix">'
    )
    parts.append(f"<title>Module dependency matrix · {n} modules · {len(cells)} edges</title>")

    # Background of the grid area (subtle off-white to delimit the matrix box).
    parts.append(
        f'<rect x="{grid_x0}" y="{grid_y0}" '
        f'width="{grid_size}" height="{grid_size}" '
        f'fill="var(--bg)" />'
    )

    # Service-color outer bands (top and left).
    for svc_id, start, end, color, _name in blocks:
        block_px_start = start * cell
        block_px_size = (end - start) * cell
        parts.append(
            f'<rect class="modgraph-svc-bar" '
            f'x="{grid_x0 + block_px_start}" y="{label_h_top}" '
            f'width="{block_px_size}" height="{band - 2}" '
            f'fill="{escape(color)}" fill-opacity="0.85" />'
        )
        parts.append(
            f'<rect class="modgraph-svc-bar" '
            f'x="{label_w}" y="{grid_y0 + block_px_start}" '
            f'width="{band - 2}" height="{block_px_size}" '
            f'fill="{escape(color)}" fill-opacity="0.85" />'
        )

    # Row hover-highlight bands (one per row, hidden until JS sets data-active).
    for i in range(n):
        y = grid_y0 + i * cell
        parts.append(
            f'<rect class="modgraph-row-band" data-row="{i}" '
            f'x="{grid_x0}" y="{y}" '
            f'width="{grid_size}" height="{cell}" />'
        )
    # Column hover-highlight bands.
    for i in range(n):
        x = grid_x0 + i * cell
        parts.append(
            f'<rect class="modgraph-col-band" data-col="{i}" '
            f'x="{x}" y="{grid_y0}" '
            f'width="{cell}" height="{grid_size}" />'
        )

    # Diagonal "this module exists" markers.
    for i in range(n):
        parts.append(
            f'<rect class="modgraph-diag" '
            f'x="{grid_x0 + i * cell + 1}" '
            f'y="{grid_y0 + i * cell + 1}" '
            f'width="{cell - 2}" height="{cell - 2}" '
            f'rx="1.5" />'
        )

    # Edge cells.
    for src, tgt, weight in cells:
        if src == tgt:
            continue  # self-imports are not interesting
        op = _opacity(weight)
        # Source row, target column: cell (row=src, col=tgt)
        parts.append(
            f'<rect class="modgraph-cell" '
            f'data-row="{src}" data-col="{tgt}" data-weight="{weight}" '
            f'x="{grid_x0 + tgt * cell + 1}" '
            f'y="{grid_y0 + src * cell + 1}" '
            f'width="{cell - 2}" height="{cell - 2}" '
            f'rx="1.5" '
            f'fill="{accent}" fill-opacity="{op}">'
            f'<title>{escape(matrix_nodes[src].get("name") or "")} → '
            f'{escape(matrix_nodes[tgt].get("name") or "")} · '
            f'{weight} import{"s" if weight != 1 else ""}</title>'
            f'</rect>'
        )

    # Domain sub-divider lines (drawn first so service lines overlay them).
    for idx in domain_dividers:
        x_or_y = idx * cell
        parts.append(
            f'<line class="modgraph-domain-line" '
            f'x1="{grid_x0 + x_or_y}" y1="{label_h_top}" '
            f'x2="{grid_x0 + x_or_y}" y2="{grid_y0 + grid_size}" />'
        )
        parts.append(
            f'<line class="modgraph-domain-line" '
            f'x1="{label_w}" y1="{grid_y0 + x_or_y}" '
            f'x2="{grid_x0 + grid_size}" y2="{grid_y0 + x_or_y}" />'
        )

    # Service-block divider lines.
    for _svc_id, start, end, _color, _name in blocks:
        if start > 0:
            x_or_y = start * cell
            # vertical line at column boundary
            parts.append(
                f'<line class="modgraph-svc-line" '
                f'x1="{grid_x0 + x_or_y}" y1="{label_h_top}" '
                f'x2="{grid_x0 + x_or_y}" y2="{grid_y0 + grid_size}" />'
            )
            # horizontal line at row boundary
            parts.append(
                f'<line class="modgraph-svc-line" '
                f'x1="{label_w}" y1="{grid_y0 + x_or_y}" '
                f'x2="{grid_x0 + grid_size}" y2="{grid_y0 + x_or_y}" />'
            )

    # Frame around the entire grid.
    parts.append(
        f'<rect x="{grid_x0}" y="{grid_y0}" '
        f'width="{grid_size}" height="{grid_size}" '
        f'fill="none" stroke="var(--border)" stroke-width="1" />'
    )

    # Row labels (left, right-aligned). Truncated for layout; full name in <title>.
    for i, node in enumerate(matrix_nodes):
        y = grid_y0 + i * cell + cell / 2 + label_font_size * 0.35
        full = _module_short_name(node.get("id", ""), node.get("name", ""))
        shown = _truncate_label(full)
        title = f"<title>{escape(full)}</title>" if shown != full else ""
        parts.append(
            f'<text class="modgraph-label" data-row="{i}" '
            f'x="{label_w - 6}" y="{y:.1f}" '
            f'text-anchor="end" '
            f'font-size="{label_font_size}">'
            f'{escape(shown)}{title}</text>'
        )

    # Column labels (top, rotated -45°). Truncated for layout; full name in <title>.
    for i, node in enumerate(matrix_nodes):
        x = grid_x0 + i * cell + cell / 2
        y = label_h_top - 6
        full = _module_short_name(node.get("id", ""), node.get("name", ""))
        shown = _truncate_label(full)
        title = f"<title>{escape(full)}</title>" if shown != full else ""
        parts.append(
            f'<text class="modgraph-label" data-col="{i}" '
            f'x="{x:.1f}" y="{y:.1f}" '
            f'text-anchor="start" '
            f'font-size="{label_font_size}" '
            f'transform="rotate(-45 {x:.1f} {y:.1f})">'
            f'{escape(shown)}{title}</text>'
        )

    # Axis titles — placed in the dedicated outer strip (see axis_pad above) so
    # they never collide with the module row/column labels, and sized larger
    # than the labels for a clear "this is the axis" hierarchy.
    x_title_y = axis_pad / 2 + 5
    y_title_x = axis_pad / 2
    parts.append(
        f'<text class="modgraph-axis-title" '
        f'x="{grid_x0 + grid_size / 2:.1f}" y="{x_title_y:.1f}" text-anchor="middle" '
        f'font-size="{axis_title_fs}" font-weight="600">'
        f'IMPORTS → (target module)</text>'
    )
    parts.append(
        f'<text class="modgraph-axis-title" '
        f'x="{y_title_x:.1f}" y="{grid_y0 + grid_size / 2:.1f}" '
        f'text-anchor="middle" '
        f'font-size="{axis_title_fs}" font-weight="600" '
        f'transform="rotate(-90 {y_title_x:.1f} {grid_y0 + grid_size / 2:.1f})">'
        f'← IMPORTING module (source)</text>'
    )

    parts.append("</svg>")
    svg = "".join(parts)

    # ------ Headline sentence (the editorial lede) ------
    total_edges_in_matrix = intra_count + cross_count
    if total_edges_in_matrix == 0:
        headline = (
            "No inter-module imports were detected in this codebase — modules look "
            "fully self-contained, or the import scanner doesn’t yet parse the "
            "languages they’re written in."
        )
    elif cross_count == 0:
        headline = (
            f"<strong>{intra_count} import relationship"
            f"{'s' if intra_count != 1 else ''}</strong> were detected, "
            f"<strong>all of them staying inside a single service</strong>. "
            f"Visually that’s the block-diagonal pattern below — a sign of "
            f"clean service boundaries."
        )
    else:
        share_intra = intra_count / total_edges_in_matrix
        if share_intra >= 0.85:
            tone = (
                "Most stay within their own service — a healthy block-diagonal pattern."
            )
        elif share_intra >= 0.6:
            tone = (
                "The diagonal blocks are visible, but off-diagonal cells reveal "
                "cross-service coupling worth a closer look."
            )
        else:
            tone = (
                "Off-diagonal mass dominates the picture — services are heavily "
                "entangled rather than independent."
            )
        headline = (
            f"<strong>{total_edges_in_matrix} import relationship"
            f"{'s' if total_edges_in_matrix != 1 else ''}</strong> detected "
            f"(<strong>{intra_count}</strong> intra-service, "
            f"<strong>{cross_count}</strong> cross-service). {tone}"
        )

    # ------ Truncation note ------
    notes_html = ""
    if truncated:
        notes_html = (
            f'<p class="diagram-note">Showing the top {MAX_MATRIX_NODES} modules by '
            f'lines-of-code. {len(ordered) - MAX_MATRIX_NODES} smaller modules are '
            f'omitted from the matrix; they still appear in the module list below.</p>'
        )

    unparsed = graph.get("languages_unparsed") or []
    if unparsed:
        parsed = graph.get("languages_parsed") or []
        supported = ", ".join(parsed) if parsed else "Python, JavaScript, TypeScript, Go, Elixir"
        notes_html += (
            f'<p class="diagram-note">This matrix maps <strong>code imports</strong>, so it '
            f'only parses languages that have them — here, <strong>{escape(supported)}</strong>. '
            f'These were also found but sit outside the import map: '
            f'<em>{escape(", ".join(unparsed))}</em>. Those are configuration, data, markup, '
            f'documentation, and styling formats; they don’t express module-to-module code '
            f'dependencies, so feeding them into this diagram would add noise rather than signal.</p>'
        )

    # ------ Hover-interaction JS (graceful degradation if disabled) ------
    matrix_js = r"""
(function () {
  var frame = document.getElementById('codemap-modgraph-section');
  if (!frame) return;
  var svg = frame.querySelector('.modgraph-matrix');
  if (!svg) return;
  var rowBands = svg.querySelectorAll('.modgraph-row-band');
  var colBands = svg.querySelectorAll('.modgraph-col-band');
  var labels = svg.querySelectorAll('.modgraph-label');
  var tip = frame.querySelector('.modgraph-tip');

  function setActive(row, col) {
    if (row == null && col == null) {
      svg.classList.remove('modgraph-hovered');
      rowBands.forEach(function (el) { el.removeAttribute('data-active'); });
      colBands.forEach(function (el) { el.removeAttribute('data-active'); });
      labels.forEach(function (el) { el.classList.remove('is-active'); });
      if (tip) tip.style.opacity = 0;
      return;
    }
    svg.classList.add('modgraph-hovered');
    rowBands.forEach(function (el) {
      el.setAttribute('data-active', el.getAttribute('data-row') === String(row) ? '1' : '0');
    });
    colBands.forEach(function (el) {
      el.setAttribute('data-active', el.getAttribute('data-col') === String(col) ? '1' : '0');
    });
    labels.forEach(function (el) {
      var r = el.getAttribute('data-row');
      var c = el.getAttribute('data-col');
      var active = (r != null && r === String(row)) || (c != null && c === String(col));
      el.classList.toggle('is-active', active);
    });
  }

  // Safe tooltip construction: build the DOM nodes with createElement +
  // textContent so a module name like `<img onerror=...>` (which would
  // have round-tripped through escape() → SVG text → .textContent and
  // come back un-escaped) can never be re-interpreted as HTML here.
  function buildTipContent(rowName, colName, weight) {
    var frag = document.createDocumentFragment();
    var srcStrong = document.createElement('strong');
    srcStrong.textContent = rowName;
    var arrow = document.createElement('span');
    arrow.className = 't-arrow';
    arrow.textContent = ' imports ';
    var tgtStrong = document.createElement('strong');
    tgtStrong.textContent = colName;
    var br = document.createElement('br');
    var meta = document.createElement('span');
    meta.className = 't-meta';
    meta.textContent = weight + ' import' + (weight === 1 ? '' : 's');
    frag.appendChild(srcStrong);
    frag.appendChild(arrow);
    frag.appendChild(tgtStrong);
    frag.appendChild(br);
    frag.appendChild(meta);
    return frag;
  }

  svg.addEventListener('mouseover', function (e) {
    var t = e.target;
    if (!(t instanceof Element)) return;
    var cell = t.closest('.modgraph-cell');
    if (cell) {
      var row = parseInt(cell.getAttribute('data-row'), 10);
      var col = parseInt(cell.getAttribute('data-col'), 10);
      var weight = parseInt(cell.getAttribute('data-weight'), 10) || 0;
      setActive(row, col);
      if (tip) {
        var rowLabel = svg.querySelector('.modgraph-label[data-row="' + row + '"]');
        var colLabel = svg.querySelector('.modgraph-label[data-col="' + col + '"]');
        var rowName = rowLabel ? rowLabel.textContent : '#' + row;
        var colName = colLabel ? colLabel.textContent : '#' + col;
        // Clear and repopulate via DOM API — never innerHTML.
        while (tip.firstChild) tip.removeChild(tip.firstChild);
        tip.appendChild(buildTipContent(rowName, colName, weight));
        tip.style.opacity = 1;
      }
    }
  });
  svg.addEventListener('mousemove', function (e) {
    if (!tip || tip.style.opacity === '0') return;
    var rect = frame.getBoundingClientRect();
    tip.style.left = (e.clientX - rect.left + 14) + 'px';
    tip.style.top  = (e.clientY - rect.top + 14) + 'px';
  });
  svg.addEventListener('mouseleave', function () { setActive(null, null); });
})();
"""

    bento_html = render_module_section_bento(data, matrix_nodes, services)
    observations_html = _render_observations(
        _observations_for_modgraph(
            matrix_nodes, cells, intra_count, cross_count, services
        )
    )

    return f"""
<section id="codemap-modgraph-section">
  <h2>How the modules connect</h2>
  {section_intro("modgraph")}
  <div class="modgraph-frame" style="position: relative;">
    <p class="modgraph-headline">{headline}</p>
    <div class="modgraph-matrix-wrap">{svg}</div>
    <div class="modgraph-tip" role="status" aria-live="polite"></div>
  </div>
  {notes_html}
  {observations_html}
  {bento_html}
</section>
<script>{matrix_js}</script>
"""


def render_module_section_bento(
    data: dict[str, Any],
    matrix_nodes: list[dict[str, Any]],
    services: list[dict[str, Any]],
) -> str:
    """2x2 small-multiples beneath the matrix.

    The matrix shows structure; the bento adds the long-tail detail
    the matrix intentionally compresses (per-service magnitudes,
    top inter-service edges, entry points, languages).
    """
    graph = data.get("module_graph") or {}
    edges = graph.get("edges", [])
    topo = data.get("http_topology") or {}
    entry_modules = topo.get("entry_modules", []) or []

    # ---------- Tile 1: Service composition donut ----------
    svc_with_loc = [
        s for s in services if (s.get("loc") or 0) > 0
    ]
    total_svc_loc = sum((s.get("loc") or 0) for s in svc_with_loc) or 1
    donut_html = _render_service_donut(svc_with_loc, total_svc_loc)

    # ---------- Tile 2: Top inter-service edges ----------
    # Aggregate edges by (source_service, target_service), counting weight.
    node_svc: dict[str, str | None] = {
        n["id"]: n.get("service") for n in graph.get("nodes", [])
    }
    node_name: dict[str, str] = {
        n["id"]: n.get("name", "") for n in graph.get("nodes", [])
    }
    # Top edges by weight, ranked. Show top 10.
    # Always annotate each row with the service so "nutrition → common"
    # doesn't read as an ambiguous bare leaf-name pair. If the top targets
    # include well-known shared-utility names, append a footnote that
    # explains the pattern (so non-engineer readers understand *why*
    # "common" tops the chart).
    ranked_edges = sorted(edges, key=lambda e: -(e.get("weight") or 0))[:10]
    UTIL_NAMES = {"common", "shared", "utils", "util", "prisma",
                  "db", "lib", "core", "types", "helpers"}
    show_util_foot = False
    if ranked_edges:
        rows = []
        for e in ranked_edges:
            src_id = e.get("source", "")
            tgt_id = e.get("target", "")
            src_name = node_name.get(src_id, src_id.rsplit("/", 1)[-1])
            tgt_name = node_name.get(tgt_id, tgt_id.rsplit("/", 1)[-1])
            src_svc = node_svc.get(src_id) or ""
            tgt_svc = node_svc.get(tgt_id) or ""
            if (tgt_name or "").lower() in UTIL_NAMES:
                show_util_foot = True
            same_svc = src_svc == tgt_svc
            if same_svc and src_svc:
                # Intra-service: show one service name as muted suffix.
                svc_label = f' <span class="svc">{escape(src_svc)}</span>'
            elif src_svc and tgt_svc:
                # Cross-service: show the arc through services explicitly.
                svc_label = (
                    f' <span class="svc is-cross">'
                    f'{escape(src_svc)} → {escape(tgt_svc)}'
                    f'</span>'
                )
            else:
                svc_label = ""
            rows.append(
                f'<li>'
                f'<span class="arc">'
                f'<strong>{escape(src_name)}</strong>'
                f'<span class="arrow">→</span>'
                f'<strong>{escape(tgt_name)}</strong>'
                f'{svc_label}'
                f'</span>'
                f'<span class="weight">{e.get("weight") or 0}</span>'
                f'</li>'
            )
        util_foot = ""
        if show_util_foot:
            util_foot = (
                '<p class="modgraph-tile-foot">'
                'Modules named <code>common</code>, <code>shared</code>, '
                '<code>prisma</code>, <code>utils</code>, or <code>core</code> '
                'are within-service infrastructure libraries — '
                'the database client, type definitions, validation helpers, '
                'and so on. Every other module in the same service usually '
                'imports from them, which is why they top the rankings.'
                '</p>'
            )
        edges_body = (
            f'<ul class="modgraph-edge-list">{"".join(rows)}</ul>'
            f'{util_foot}'
        )
    else:
        edges_body = '<p class="modgraph-empty">No imports detected between modules.</p>'

    # ---------- Tile 3: Entry-point modules ----------
    entries_sorted = sorted(
        entry_modules, key=lambda em: -(em.get("endpoint_count") or 0)
    )[:8]
    if entries_sorted:
        rows = []
        for em in entries_sorted:
            mod_path = em.get("module", "")
            mod_leaf = mod_path.rsplit("/", 1)[-1] if mod_path else "?"
            svc = em.get("service") or ""
            count = em.get("endpoint_count") or 0
            rows.append(
                f'<li>'
                f'<span class="mod-name">{escape(mod_leaf)}'
                f'<span class="mod-svc">{escape(svc)}</span></span>'
                f'<span class="count">{count} endpoint{"s" if count != 1 else ""}</span>'
                f'</li>'
            )
        entries_body = f'<ul class="modgraph-entry-list">{"".join(rows)}</ul>'
    else:
        entries_body = (
            '<p class="modgraph-empty">No HTTP entry-point modules detected.</p>'
        )

    # ---------- Tile 4: Languages chip cloud (top languages in modules) ----------
    lang_loc: dict[str, tuple[int, str]] = {}
    for n in graph.get("nodes", []):
        lang = n.get("primary_language")
        if not lang:
            continue
        loc = n.get("loc") or 0
        prev_loc, prev_color = lang_loc.get(lang, (0, n.get("color") or "#888"))
        lang_loc[lang] = (prev_loc + loc, prev_color)
    total_lang_loc = sum(v[0] for v in lang_loc.values()) or 1
    sorted_langs = sorted(lang_loc.items(), key=lambda kv: -kv[1][0])
    if sorted_langs:
        pills = []
        for lang, (loc, color) in sorted_langs:
            share = (loc * 100) / total_lang_loc
            pills.append(
                f'<span class="lang-pill">'
                f'<span class="swatch" style="background:{escape(color)};"></span>'
                f'{escape(lang)}'
                f'<span class="share">{share:.0f}%</span>'
                f'</span>'
            )
        langs_body = f'<div class="modgraph-langs-cloud">{"".join(pills)}</div>'
    else:
        langs_body = (
            '<p class="modgraph-empty">No language metadata on graph nodes.</p>'
        )

    return f"""
<div class="modgraph-bento">
  <div class="modgraph-tile is-donut">
    <div class="tile-label">Composition</div>
    <div class="tile-headline">Lines of code by service</div>
    <div class="tile-body" style="width:100%;">{donut_html}</div>
  </div>
  <div class="modgraph-tile">
    <div class="tile-label">Hottest edges</div>
    <div class="tile-headline">Top imports between modules</div>
    <div class="tile-body">{edges_body}</div>
  </div>
  <div class="modgraph-tile">
    <div class="tile-label">Entry points</div>
    <div class="tile-headline">Modules exposing HTTP endpoints</div>
    <div class="tile-body">{entries_body}</div>
  </div>
  <div class="modgraph-tile">
    <div class="tile-label">Languages</div>
    <div class="tile-headline">Used inside the modules above</div>
    <div class="tile-body">{langs_body}</div>
  </div>
</div>
"""


def _render_service_donut(
    services_with_loc: list[dict[str, Any]],
    total: int,
) -> str:
    """Static SVG donut showing % LOC per service.

    Pure stroke-dasharray on a single circle: each service is a stroke
    arc of the right length. No animation, no JS, prints perfectly.
    """
    if not services_with_loc or total <= 0:
        return '<p class="modgraph-empty">No service metadata.</p>'

    size = 160
    cx = size / 2
    cy = size / 2
    r = 60
    stroke_w = 22
    circumference = 2 * math.pi * r

    arcs: list[str] = []
    legend_rows: list[str] = []
    offset = 0.0
    # We rotate -90deg so the first arc starts at 12 o'clock.
    for s in services_with_loc:
        loc = s.get("loc") or 0
        share = loc / total
        arc_len = share * circumference
        gap_len = circumference - arc_len
        color = s.get("color") or "#888"
        # `pathLength` would simplify this but we rely on raw values for
        # broader SVG renderer compatibility (older Chromium for print).
        arcs.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" '
            f'fill="none" '
            f'stroke="{escape(color)}" '
            f'stroke-width="{stroke_w}" '
            f'stroke-dasharray="{arc_len:.3f} {gap_len:.3f}" '
            f'stroke-dashoffset="{-offset:.3f}" '
            f'transform="rotate(-90 {cx} {cy})">'
            f'<title>{escape(s.get("name") or s["id"])} · '
            f'{fmt_num(loc)} LOC · {share * 100:.1f}%</title>'
            f'</circle>'
        )
        legend_rows.append(
            f'<div class="donut-legend-row">'
            f'<span class="swatch" style="background:{escape(color)};"></span>'
            f'<span class="name">{escape(s.get("name") or s["id"])}</span>'
            f'<span class="pct">{share * 100:.1f}%</span>'
            f'</div>'
        )
        offset += arc_len

    total_label = f"{fmt_num(total)}"
    center_text = (
        f'<text x="{cx}" y="{cy - 2}" text-anchor="middle" '
        f'font-family="var(--font-serif)" font-size="20" font-weight="600" '
        f'fill="var(--ink)">{total_label}</text>'
        f'<text x="{cx}" y="{cy + 14}" text-anchor="middle" '
        f'font-family="var(--font-mono)" font-size="9" '
        f'letter-spacing="0.08em" fill="var(--muted)">LOC TOTAL</text>'
    )
    svg = (
        f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" '
        f'role="img" aria-label="Service composition donut">'
        f'{"".join(arcs)}{center_text}</svg>'
    )
    return f'<div style="display:flex; flex-direction:column; align-items:center;">{svg}<div class="donut-legend">{"".join(legend_rows)}</div></div>'


# C4-style service topology — replacement for the force-directed
# `render_service_topology` below. Services are rendered as cards in
# left-to-right tiers based on longest-path call-direction depth.
# Edges are aggregated per (source_svc, target_svc) and drawn as
# orthogonal arrows with weight labels.

TOPOV2_BOX_W = 220
TOPOV2_BOX_H = 120
TOPOV2_TIER_GAP = 70
TOPOV2_ROW_GAP = 24
TOPOV2_STRIPE_H = 5


def _topov2_assign_tiers(
    node_ids: list[str],
    edges: list[tuple[str, str]],
) -> dict[str, int]:
    """Longest-path tier assignment.

    Nodes with no incoming edge are tier 0. Every other node sits at
    `max(predecessor_tier) + 1`. Iterates until fixed-point so even
    multi-hop diamonds settle correctly. Cycles aren't expected in
    aggregated service graphs; if one appears we silently cap iteration.
    """
    incoming: dict[str, list[str]] = {nid: [] for nid in node_ids}
    for src, tgt in edges:
        if src in incoming and tgt in incoming:
            incoming[tgt].append(src)
    tiers: dict[str, int] = {nid: 0 for nid in node_ids}
    # Up to N iterations is enough for any DAG of length N.
    for _ in range(len(node_ids) + 1):
        changed = False
        for nid in node_ids:
            preds = incoming[nid]
            if not preds:
                continue
            new_tier = max(tiers[p] for p in preds) + 1
            if new_tier > tiers[nid]:
                tiers[nid] = new_tier
                changed = True
        if not changed:
            break
    return tiers


def _topov2_kind_chip_label(kind: str | None) -> str:
    """Short, all-caps chip label per service kind."""
    if not kind:
        return "SERVICE"
    k = kind.lower()
    mapping = {
        "backend": "BACKEND",
        "frontend": "FRONTEND",
        "worker": "WORKER",
        "library": "LIBRARY",
        "service": "SERVICE",
        "store": "STORE",
        "unknown": "SERVICE",
    }
    return mapping.get(k, kind.upper()[:10])


def _topov2_truncate(s: str, max_chars: int) -> str:
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 1].rstrip() + "…"


def render_service_topology_v2(data: dict[str, Any]) -> str:
    topo = data.get("http_topology") or {}
    raw_edges = topo.get("edges") or []
    services_full = data.get("services") or []
    if not raw_edges or len(services_full) < 2:
        return ""

    # ------ Aggregate per (source, target) ------
    pair_agg: dict[tuple[str, str], dict[str, Any]] = {}
    for e in raw_edges:
        s = e.get("source_service")
        t = e.get("target_service")
        if not s or not t:
            continue
        key = (s, t)
        bucket = pair_agg.setdefault(key, {"count": 0, "routes": []})
        bucket["count"] += int(e.get("weight") or 1)
        bucket["routes"].append({
            "method": e.get("method"),
            "path": e.get("path"),
            "weight": e.get("weight"),
        })
    if not pair_agg:
        return ""

    # ------ Filter to referenced services, in input order ------
    referenced: set[str] = set()
    for s, t in pair_agg.keys():
        referenced.add(s)
        referenced.add(t)
    nodes = [s for s in services_full if s["id"] in referenced]
    if len(nodes) < 2:
        return ""

    node_ids = [n["id"] for n in nodes]
    tiers = _topov2_assign_tiers(node_ids, list(pair_agg.keys()))

    # ------ Group services by tier; preserve input order within tier ------
    tier_groups: dict[int, list[dict[str, Any]]] = {}
    for n in nodes:
        tier_groups.setdefault(tiers[n["id"]], []).append(n)
    max_tier = max(tier_groups.keys())
    max_rows = max(len(g) for g in tier_groups.values())

    # ------ Position boxes ------
    # Center the whole grid horizontally. Width budget is determined by
    # the longest tier (most boxes side-by-side); the SVG's viewBox is
    # sized to fit whatever the data demands and overflow-x scrolls
    # on small viewports.
    cols = max_tier + 1
    rows = max_rows
    grid_w = cols * TOPOV2_BOX_W + (cols - 1) * TOPOV2_TIER_GAP
    grid_h = rows * TOPOV2_BOX_H + (rows - 1) * TOPOV2_ROW_GAP

    pad_x = 20
    pad_top = 16
    pad_bot = 32  # leave room for edge labels below boxes if any
    svg_w = grid_w + 2 * pad_x
    svg_h = grid_h + pad_top + pad_bot

    pos: dict[str, dict[str, float]] = {}
    for tier, group in tier_groups.items():
        # Center each tier's column of boxes vertically within grid_h.
        col_h = len(group) * TOPOV2_BOX_H + (len(group) - 1) * TOPOV2_ROW_GAP
        y_start = pad_top + (grid_h - col_h) / 2
        for i, n in enumerate(group):
            pos[n["id"]] = {
                "x": pad_x + tier * (TOPOV2_BOX_W + TOPOV2_TIER_GAP),
                "y": y_start + i * (TOPOV2_BOX_H + TOPOV2_ROW_GAP),
                "tier": tier,
            }

    # ------ Edge stroke-width scale (log) ------
    max_count = max(b["count"] for b in pair_agg.values())
    log_denom = math.log(max(2, max_count) + 1)

    def _stroke_w(c: int) -> float:
        v = math.log(c + 1) / log_denom
        return round(1.5 + 5.0 * v, 2)

    # ------ Build SVG ------
    parts: list[str] = [
        f'<svg class="topov2-svg" viewBox="0 0 {svg_w:.0f} {svg_h:.0f}" '
        f'width="{svg_w:.0f}" role="img" aria-label="Service topology">'
    ]
    parts.append(
        '<defs>'
        '<marker id="topov2-arrow" viewBox="0 -5 10 10" '
        'refX="9" refY="0" markerWidth="7" markerHeight="7" '
        'orient="auto" markerUnits="userSpaceOnUse">'
        '<path d="M0,-5L10,0L0,5" fill="oklch(38% 0.012 250 / 0.7)"/>'
        '</marker>'
        '</defs>'
    )

    # ----- Edges first (so boxes overlap any stray joins) -----
    edge_labels_html: list[str] = []
    for (src_id, tgt_id), agg in pair_agg.items():
        a = pos.get(src_id)
        b = pos.get(tgt_id)
        if not a or not b:
            continue
        # Right-side mid of source → left-side mid of target.
        # For back-edges (a.tier > b.tier) we still route this way; the
        # path will visibly cross the source. v1 doesn't handle back-edges
        # specially; we expect call-graphs to be acyclic.
        ax = a["x"] + TOPOV2_BOX_W
        ay = a["y"] + TOPOV2_BOX_H / 2
        bx = b["x"]
        by = b["y"] + TOPOV2_BOX_H / 2

        if abs(ay - by) < 2:
            # Same Y: straight line.
            d = f"M{ax:.1f},{ay:.1f} L{bx - 4:.1f},{by:.1f}"
            mid_x = (ax + bx) / 2
            mid_y = ay
        else:
            # L-shape with smoothed corner at the horizontal midpoint.
            midx = (ax + bx) / 2
            # Slight curve at the corner for visual ease.
            d = (
                f"M{ax:.1f},{ay:.1f} "
                f"H{midx - 6:.1f} "
                f"Q{midx:.1f},{ay:.1f} {midx:.1f},{ay + (6 if by > ay else -6):.1f} "
                f"V{by - (6 if by > ay else -6):.1f} "
                f"Q{midx:.1f},{by:.1f} {midx + 6:.1f},{by:.1f} "
                f"H{bx - 4:.1f}"
            )
            mid_x = midx
            mid_y = (ay + by) / 2

        sw = _stroke_w(agg["count"])
        parts.append(
            f'<path class="topov2-edge" d="{d}" '
            f'stroke-width="{sw}" '
            f'marker-end="url(#topov2-arrow)">'
            f'<title>{escape(src_id)} → {escape(tgt_id)} · '
            f'{agg["count"]} call{"s" if agg["count"] != 1 else ""}</title>'
            f'</path>'
        )

        # Edge weight label — drawn as a small pill near the midpoint
        # of the long horizontal segment. We center text and size the
        # background rect to fit, approximating text width by char count.
        label_text = f'{agg["count"]} call{"s" if agg["count"] != 1 else ""}'
        # Rough char-width estimate at 10px mono.
        text_w = max(40, len(label_text) * 6 + 12)
        text_h = 18
        rect_x = mid_x - text_w / 2
        rect_y = mid_y - text_h / 2
        parts.append(
            f'<rect class="topov2-edge-label-bg" '
            f'x="{rect_x:.1f}" y="{rect_y:.1f}" '
            f'width="{text_w}" height="{text_h}" rx="9" />'
        )
        parts.append(
            f'<text class="topov2-edge-label" '
            f'x="{mid_x:.1f}" y="{mid_y + 3.5:.1f}" '
            f'text-anchor="middle">{escape(label_text)}</text>'
        )

    # ----- Service cards -----
    for n in nodes:
        p = pos[n["id"]]
        x, y = p["x"], p["y"]
        color = SERVICE_KIND_COLORS.get(n.get("kind") or "unknown", "#a0a0a0")
        # Background card
        parts.append(
            f'<rect class="topov2-node-bg" '
            f'x="{x:.1f}" y="{y:.1f}" '
            f'width="{TOPOV2_BOX_W}" height="{TOPOV2_BOX_H}" '
            f'rx="10" />'
        )
        # Top stripe in kind color
        parts.append(
            f'<rect class="topov2-node-stripe" '
            f'x="{x:.1f}" y="{y:.1f}" '
            f'width="{TOPOV2_BOX_W}" height="{TOPOV2_STRIPE_H}" '
            f'rx="10" '
            f'fill="{escape(color)}" />'
        )
        # The stripe's bottom corners shouldn't be rounded; cover them
        # with a flat-bottom rect of the same color.
        parts.append(
            f'<rect '
            f'x="{x:.1f}" y="{y + TOPOV2_STRIPE_H - 3:.1f}" '
            f'width="{TOPOV2_BOX_W}" height="3" '
            f'fill="{escape(color)}" />'
        )

        # Title (truncated if needed)
        title_max = 22 if cols <= 3 else 18
        title = _topov2_truncate(n.get("name") or n["id"], title_max)
        title_x = x + 16
        title_y = y + TOPOV2_STRIPE_H + 28
        parts.append(
            f'<text class="topov2-node-title" '
            f'x="{title_x:.1f}" y="{title_y:.1f}" '
            f'font-size="14.5">{escape(title)}</text>'
        )

        # Kind chip (top-right inside the card)
        chip_label = _topov2_kind_chip_label(n.get("kind"))
        chip_w = max(48, len(chip_label) * 6 + 12)
        chip_h = 16
        chip_x = x + TOPOV2_BOX_W - chip_w - 12
        chip_y = y + TOPOV2_STRIPE_H + 14
        parts.append(
            f'<rect class="topov2-kind-chip" '
            f'x="{chip_x:.1f}" y="{chip_y:.1f}" '
            f'width="{chip_w}" height="{chip_h}" rx="4" '
            f'fill="{escape(color)}" />'
        )
        parts.append(
            f'<text class="topov2-kind-chip-text" '
            f'x="{chip_x + chip_w / 2:.1f}" y="{chip_y + 11.5:.1f}" '
            f'text-anchor="middle">{escape(chip_label)}</text>'
        )

        # Stack line
        stack = " · ".join(n.get("stack") or [])
        if stack:
            stack_disp = _topov2_truncate(stack, 30 if cols <= 3 else 24)
            parts.append(
                f'<text class="topov2-node-stack" '
                f'x="{title_x:.1f}" y="{title_y + 18:.1f}" '
                f'font-size="11">{escape(stack_disp)}</text>'
            )

        # Stat line (LOC + files)
        loc = n.get("loc") or 0
        files = n.get("file_count") or 0
        # Format LOC compactly: 79908 → "79.9k LOC"
        if loc >= 1000:
            loc_disp = f"{loc / 1000:.1f}k LOC"
        else:
            loc_disp = f"{loc} LOC"
        stat = f"{loc_disp} · {fmt_num(files)} files"
        parts.append(
            f'<text class="topov2-node-stat" '
            f'x="{title_x:.1f}" y="{y + TOPOV2_BOX_H - 16:.1f}" '
            f'font-size="10.5">{escape(stat)}</text>'
        )

    parts.append("</svg>")
    svg = "".join(parts)

    # ------ Headline sentence (data-derived editorial lede) ------
    n_services = len(nodes)
    n_edges = len(pair_agg)
    is_linear_chain = (
        n_services >= 2
        and n_edges == n_services - 1
        and all(len(g) == 1 for g in tier_groups.values())
    )
    if is_linear_chain:
        chain = sorted(nodes, key=lambda x: tiers[x["id"]])
        chain_html = " → ".join(
            f'<strong>{escape(s.get("name") or s["id"])}</strong>' for s in chain
        )
        # Identify the heaviest edge so we can mention it.
        heaviest = max(pair_agg.items(), key=lambda kv: kv[1]["count"])
        h_src = next((n for n in nodes if n["id"] == heaviest[0][0]), None)
        h_count = heaviest[1]["count"]
        h_name = (h_src or {}).get("name") or heaviest[0][0]
        headline = (
            f'<strong>{n_services} services</strong> form a linear chain: '
            f'{chain_html}. <strong>{escape(h_name)}</strong> drives the '
            f'bulk of the traffic with <strong>{h_count} call'
            f'{"s" if h_count != 1 else ""}</strong> to its downstream.'
        )
    else:
        total_calls = sum(b["count"] for b in pair_agg.values())
        heaviest = max(pair_agg.items(), key=lambda kv: kv[1]["count"])
        h_src_id, h_tgt_id = heaviest[0]
        h_src = next((n for n in nodes if n["id"] == h_src_id), None)
        h_tgt = next((n for n in nodes if n["id"] == h_tgt_id), None)
        headline = (
            f'<strong>{n_services} services</strong> exchange '
            f'<strong>{n_edges} call relationship'
            f'{"s" if n_edges != 1 else ""}</strong> '
            f'(<strong>{total_calls}</strong> total). The heaviest flow is '
            f'<strong>{escape((h_src or {}).get("name") or h_src_id)}</strong> '
            f'→ <strong>{escape((h_tgt or {}).get("name") or h_tgt_id)}</strong> '
            f'with <strong>{heaviest[1]["count"]}</strong> calls.'
        )

    # ------ Notes (unresolved calls, missing frameworks, etc.) ------
    notes: list[str] = []
    unresolved = int(topo.get("unresolved_client_count") or 0)
    if unresolved:
        notes.append(
            f'<strong>{unresolved}</strong> outbound HTTP call'
            f'{"s" if unresolved != 1 else ""} couldn\'t be matched to a '
            'known endpoint — likely external APIs, dynamic URLs, or routes '
            'the scanner didn\'t pick up. They\'re not drawn above.'
        )
    notes_html = "".join(f'<p class="diagram-note">{n}</p>' for n in notes)

    bento_html = render_topology_v2_bento(data, pair_agg, nodes)
    observations_html = _render_observations(
        _observations_for_topology(nodes, pair_agg, tiers, topo)
    )

    return f"""
<section id="codemap-topov2-section">
  <h2>How the services talk to each other</h2>
  {section_intro("topology")}
  <div class="topov2-frame">
    <p class="topov2-headline">{headline}</p>
    <div class="topov2-wrap">{svg}</div>
  </div>
  {notes_html}
  {observations_html}
  {bento_html}
</section>
"""


def render_topology_v2_bento(
    data: dict[str, Any],
    pair_agg: dict[tuple[str, str], dict[str, Any]],
    nodes: list[dict[str, Any]],
) -> str:
    """Bento beneath the topology hero.

    Four tiles: (1) service call relationships (per-service inbound +
    outbound neighbours), (2) entry-point modules per service, (3)
    server frameworks detected, (4) HTTP client libraries detected
    plus unresolved-call summary.
    """
    topo = data.get("http_topology") or {}
    name_by_id = {n["id"]: (n.get("name") or n["id"]) for n in nodes}

    # ---------- Tile 1: Service call relationships ----------
    inbound: dict[str, list[tuple[str, int]]] = {n["id"]: [] for n in nodes}
    outbound: dict[str, list[tuple[str, int]]] = {n["id"]: [] for n in nodes}
    for (src_id, tgt_id), agg in pair_agg.items():
        if tgt_id in inbound:
            inbound[tgt_id].append((src_id, agg["count"]))
        if src_id in outbound:
            outbound[src_id].append((tgt_id, agg["count"]))
    # Sort each neighbour list by count desc.
    for d in (inbound, outbound):
        for nid in d:
            d[nid].sort(key=lambda kv: -kv[1])

    rels_rows: list[str] = []
    for n in nodes:
        ins = inbound[n["id"]]
        outs = outbound[n["id"]]
        if not ins and not outs:
            continue
        in_rows = "".join(
            f'<div class="row">'
            f'<span>← {escape(name_by_id.get(s, s))}</span>'
            f'<span class="count">{c}</span>'
            f'</div>'
            for s, c in ins
        )
        out_rows = "".join(
            f'<div class="row">'
            f'<span>→ {escape(name_by_id.get(t, t))}</span>'
            f'<span class="count">{c}</span>'
            f'</div>'
            for t, c in outs
        )
        neighbours = in_rows + out_rows
        rels_rows.append(
            f'<li>'
            f'<div class="svc-name">{escape(n.get("name") or n["id"])}</div>'
            f'<div class="neighbours">{neighbours}</div>'
            f'</li>'
        )
    if rels_rows:
        rels_body = f'<ul class="topov2-call-list">{"".join(rels_rows)}</ul>'
    else:
        rels_body = '<p class="topov2-empty">No call relationships detected.</p>'

    # ---------- Tile 2: Entry-point modules per service ----------
    entry_modules = topo.get("entry_modules", []) or []
    by_svc: dict[str, list[dict[str, Any]]] = {}
    for em in entry_modules:
        by_svc.setdefault(em.get("service") or "", []).append(em)
    for svc_id in by_svc:
        by_svc[svc_id].sort(key=lambda em: -(em.get("endpoint_count") or 0))

    em_rows: list[str] = []
    for n in nodes:
        ems = by_svc.get(n["id"], [])[:3]  # top 3 per service
        if not ems:
            continue
        rows = "".join(
            f'<div class="row">'
            f'<span>{escape((em.get("module") or "").rsplit("/", 1)[-1])}</span>'
            f'<span class="count">{em.get("endpoint_count") or 0}</span>'
            f'</div>'
            for em in ems
        )
        em_rows.append(
            f'<li>'
            f'<div class="svc-name">{escape(n.get("name") or n["id"])}</div>'
            f'<div class="neighbours">{rows}</div>'
            f'</li>'
        )
    if em_rows:
        entries_body = f'<ul class="topov2-call-list">{"".join(em_rows)}</ul>'
    else:
        entries_body = (
            '<p class="topov2-empty">No HTTP entry-point modules detected.</p>'
        )

    # ---------- Tile 3: Server frameworks detected ----------
    frameworks = topo.get("frameworks_detected") or []
    if frameworks:
        fw_pills = "".join(
            f'<span class="fw-pill">{escape(f)}</span>' for f in frameworks
        )
        fw_body = f'<div class="topov2-fw-cloud">{fw_pills}</div>'
    else:
        fw_body = (
            '<p class="topov2-empty">No web-framework endpoints detected.</p>'
        )

    # ---------- Tile 4: HTTP clients + unresolved summary ----------
    clients = topo.get("clients_detected") or []
    unresolved = int(topo.get("unresolved_client_count") or 0)
    total_resolved = sum(b["count"] for b in pair_agg.values())
    if clients:
        client_pills = "".join(
            f'<span class="fw-pill">{escape(c)}</span>' for c in clients
        )
        clients_chunk = f'<div class="topov2-fw-cloud">{client_pills}</div>'
    else:
        clients_chunk = (
            '<p class="topov2-empty">No HTTP client libraries detected.</p>'
        )
    stats_chunk = (
        f'<div class="topov2-stat-row">'
        f'<span class="k">Resolved calls</span>'
        f'<span class="v">{total_resolved}</span>'
        f'</div>'
        f'<div class="topov2-stat-row">'
        f'<span class="k">Unresolved calls</span>'
        f'<span class="v {"" if unresolved else "muted"}">{unresolved}</span>'
        f'</div>'
    )

    return f"""
<div class="topov2-bento">
  <div class="topov2-tile">
    <div class="tile-label">Call relationships</div>
    <div class="tile-headline">Who each service talks to</div>
    <div class="tile-body">{rels_body}</div>
  </div>
  <div class="topov2-tile">
    <div class="tile-label">Entry points</div>
    <div class="tile-headline">Modules exposing HTTP endpoints per service</div>
    <div class="tile-body">{entries_body}</div>
  </div>
  <div class="topov2-tile">
    <div class="tile-label">Server frameworks</div>
    <div class="tile-headline">Detected from route declarations</div>
    <div class="tile-body">{fw_body}</div>
  </div>
  <div class="topov2-tile">
    <div class="tile-label">HTTP clients</div>
    <div class="tile-headline">Libraries used to make outbound calls</div>
    <div class="tile-body">
      {clients_chunk}
      <div style="margin-top: var(--space-3); padding-top: var(--space-3); border-top: 1px solid var(--border);">
        {stats_chunk}
      </div>
    </div>
  </div>
</div>
"""


# Color tints for store kinds — match common UI conventions: postgres
# elephant blue, redis red, mongo green, etc. Keeps the diagram legible
# without a legend lookup.
STORE_KIND_COLORS: dict[str, str] = {
    "postgres": "#336791",
    "mysql": "#00758f",
    "mongodb": "#13aa52",
    "redis": "#d82c20",
    "elasticsearch": "#fec514",
    "kafka": "#231f20",
    "rabbitmq": "#ff6600",
    "clickhouse": "#ffcc01",
    "cassandra": "#1287b1",
    "dynamodb": "#4053d6",
    "sqlite": "#0f80cc",
    "s3": "#e25444",
    "supabase": "#3ecf8e",
    "firebase": "#ffa611",
    "unknown": "#888888",
}


# ====================================================================
# Critical paths (behavioural view) — what happens when a request flows
# through the system, traced from caller(s) → entry module → key code
# dependencies → data store. One row per entry-point module gives a
# near-complete coverage of the HTTP-exposed surface.
# ====================================================================

MAX_CPATHS_ROWS = 20


HTTP_METHOD_COLORS: dict[str, str] = {
    "GET":    "#16a34a",
    "POST":   "#2563eb",
    "PUT":    "#f59e0b",
    "PATCH":  "#ca8a04",
    "DELETE": "#dc2626",
    "ANY":    "#6b7280",
    "HEAD":   "#94a3b8",
    "OPTIONS": "#94a3b8",
}


def _path_prefix(path: str, depth: int = 3) -> str:
    """Return the leading `depth` segments of a URL path.

    e.g. /api/v1/workouts/schedule/week  →  /api/v1/workouts
    """
    if not path:
        return ""
    parts = path.strip("/").split("/")
    keep = []
    for p in parts:
        if len(keep) >= depth:
            break
        # Skip pure parameter segments (e.g. ":id")
        keep.append(p)
    return "/" + "/".join(keep) if keep else "/"


def _observations_for_cpaths(
    paths: list[dict[str, Any]],
    services: list[dict[str, Any]],
    topo: dict[str, Any],
) -> list[str]:
    """Architect concerns from the critical-paths view."""
    from collections import Counter
    obs: list[str] = []
    if not paths:
        return obs

    # 1. The codebase's most-exposed module
    top = max(paths, key=lambda p: p["endpoint_count"])
    if top["endpoint_count"] >= 8:
        obs.append(
            f"<strong><code>{escape(top['module_leaf'])}</code></strong> "
            f"in <code>{escape(top['service'])}</code> exposes "
            f"<strong>{top['endpoint_count']}</strong> HTTP endpoints — "
            f"the largest single attack surface in this codebase."
        )

    # 2. Modules with no detected callers
    orphans = [p for p in paths if not p["callers"]]
    if orphans:
        names = ", ".join(
            f"<code>{escape(p['module_leaf'])}</code>" for p in orphans[:4]
        )
        plural = "s" if len(orphans) != 1 else ""
        obs.append(
            f"<strong>{len(orphans)} entry module{plural}</strong> "
            f"({names}) have no detected callers in this codebase — "
            f"either called from outside (mobile apps, webhooks, "
            f"scheduled jobs) or dead code worth confirming."
        )

    # 3. Shared utility concentration
    util_users: Counter = Counter()
    for p in paths:
        for d in p["deps"]:
            if d.lower() in UTIL_MODULE_NAMES:
                util_users[d.lower()] += 1
    if util_users:
        top_util, top_use = util_users.most_common(1)[0]
        if top_use >= max(3, len(paths) // 3):
            obs.append(
                f"<strong>{top_use}</strong> of the {len(paths)} entry "
                f"modules depend on <code>{escape(top_util)}</code> — "
                f"a strong consistency win, but any breaking change to "
                f"<code>{escape(top_util)}</code> ripples across most "
                f"of the HTTP surface."
            )

    # 4. Path uniformity (all paths look the same)
    store_set = {p["store_id"] for p in paths if p["store_id"]}
    if len(store_set) == 1 and len(paths) >= 5:
        the_store = next(iter(store_set))
        store_name = (the_store or "").upper()
        obs.append(
            f"<strong>Every traced flow</strong> ultimately writes to "
            f"<strong>{escape(store_name)}</strong> — uniform persistence "
            f"makes reasoning about transactions easier, but also means "
            f"the database is the single point of contention under load."
        )

    # 5. Coverage gap
    n_endpoints_total = sum(p["endpoint_count"] for p in paths)
    n_topo_edges = len(topo.get("edges") or [])
    if n_endpoints_total > 0 and n_topo_edges:
        coverage = n_topo_edges / n_endpoints_total
        if coverage < 0.4:
            obs.append(
                f"Only <strong>{n_topo_edges} of {n_endpoints_total} "
                f"endpoints</strong> ({coverage * 100:.0f}%) were matched "
                f"to a caller in the scan — most endpoints have no "
                f"detected internal client, suggesting external callers "
                f"(mobile/web apps) or unscanned consumers."
            )

    return obs[:5]


def render_critical_paths_section(data: dict[str, Any]) -> str:
    topo = data.get("http_topology") or {}
    em_list = topo.get("entry_modules") or []
    endpoints = topo.get("endpoints") or []
    topo_edges = topo.get("edges") or []
    services = data.get("services") or []
    mg = data.get("module_graph") or {}
    mg_edges = mg.get("edges") or []
    lineage = data.get("data_lineage") or {}
    lineage_edges = lineage.get("edges") or []
    stores = lineage.get("stores") or []

    if not em_list:
        return ""

    # ------ Build per-entry-module path data ------
    # Endpoints keyed by their declaring module so we can pick a sample
    # and find callers cheaply.
    eps_by_module: dict[str, list[dict[str, Any]]] = {}
    for ep in endpoints:
        eps_by_module.setdefault(ep.get("module") or "", []).append(ep)

    # Outbound module-graph edges by source for fast deps lookup.
    deps_by_mod: dict[str, list[tuple[str, int]]] = {}
    for e in mg_edges:
        deps_by_mod.setdefault(e.get("source") or "", []).append(
            (e.get("target") or "", int(e.get("weight") or 1))
        )

    # Lineage edges keyed by source service.
    lineage_by_svc: dict[str, list[dict[str, Any]]] = {}
    for e in lineage_edges:
        lineage_by_svc.setdefault(e.get("source_service") or "", []).append(e)

    paths: list[dict[str, Any]] = []
    for em in em_list:
        svc = em.get("service") or ""
        mod_id = em.get("module") or ""
        mod_leaf = mod_id.rsplit("/", 1)[-1] if mod_id else ""
        ep_count = int(em.get("endpoint_count") or 0)

        my_eps = eps_by_module.get(mod_id, [])

        # Pick a representative endpoint: prefer one with a caller.
        sample = None
        callers: set[str] = set()
        for ep in my_eps:
            for te in topo_edges:
                if (te.get("target_service") == svc
                    and te.get("method") == ep.get("method")
                    and te.get("path") == ep.get("path")):
                    callers.add(te.get("source_service") or "")
                    if sample is None:
                        sample = ep
        if sample is None and my_eps:
            sample = my_eps[0]

        # Top deps for this module by weight desc; map to leaf names.
        deps_raw = sorted(deps_by_mod.get(mod_id, []), key=lambda kv: -kv[1])
        deps_leaves = [t.rsplit("/", 1)[-1] for (t, _w) in deps_raw]

        # Primary store for this service (heaviest lineage edge).
        store_id = None
        store_models = 0
        svc_lineage = lineage_by_svc.get(svc, [])
        if svc_lineage:
            best = max(svc_lineage, key=lambda e: int(e.get("weight") or 0))
            store_id = best.get("target_store")
            store_models = int(best.get("weight") or 0)

        paths.append({
            "service": svc,
            "module_id": mod_id,
            "module_leaf": mod_leaf,
            "endpoint_count": ep_count,
            "sample_method": (sample or {}).get("method") or "",
            "sample_path": (sample or {}).get("path") or "",
            "callers": sorted(callers - {""}),
            "deps": deps_leaves,
            "store_id": store_id,
            "store_models": store_models,
        })

    # Sort paths by endpoint count desc; cap visible to MAX_CPATHS_ROWS.
    paths.sort(key=lambda p: -p["endpoint_count"])
    truncated = len(paths) > MAX_CPATHS_ROWS
    visible = paths[:MAX_CPATHS_ROWS]

    # ------ Geometry ------
    col_widths = [130, 220, 280, 130]
    col_gap = 24
    row_h = 50
    header_h = 30
    pad_x = 16
    pad_top = 18
    pad_bot = 16
    grid_w = sum(col_widths) + col_gap * (len(col_widths) - 1)
    svg_w = pad_x + grid_w + pad_x
    svg_h = pad_top + header_h + len(visible) * row_h + pad_bot

    col_x: list[int] = []
    x_cursor = pad_x
    for w in col_widths:
        col_x.append(x_cursor)
        x_cursor += w + col_gap

    # ------ Build SVG ------
    parts: list[str] = [
        f'<svg class="cpaths-svg" viewBox="0 0 {svg_w} {svg_h}" '
        f'width="{svg_w}" role="img" aria-label="Critical paths">',
        '<defs><marker id="cpaths-arrow" viewBox="0 -5 10 10" '
        'refX="6" refY="0" markerWidth="6" markerHeight="6" '
        'orient="auto" markerUnits="userSpaceOnUse">'
        '<path d="M0,-5L10,0L0,5" fill="oklch(38% 0.012 250 / 0.55)"/>'
        '</marker></defs>',
    ]

    # Column headers
    header_y = pad_top + 12
    headers = ["CALLERS", "ENTRY MODULE", "KEY DEPENDENCIES", "STORE"]
    for i, label in enumerate(headers):
        cx = col_x[i] + col_widths[i] / 2
        parts.append(
            f'<text class="cpaths-header-text" '
            f'x="{cx:.1f}" y="{header_y:.1f}" text-anchor="middle">'
            f'{label}</text>'
        )

    # Row backgrounds (zebra striping for legibility)
    for i, _p in enumerate(visible):
        y = pad_top + header_h + i * row_h
        parity = "is-even" if i % 2 == 0 else "is-odd"
        parts.append(
            f'<rect class="cpaths-row-stripe {parity}" '
            f'x="{pad_x}" y="{y:.1f}" '
            f'width="{grid_w}" height="{row_h}" rx="6" />'
        )

    # Row contents
    for i, p in enumerate(visible):
        y_mid = pad_top + header_h + i * row_h + row_h / 2

        # ----- COL 1: Callers -----
        callers = p["callers"]
        if callers:
            # Stack up to 2 caller pills.
            shown = callers[:2]
            total = len(shown)
            for j, c in enumerate(shown):
                c_node = next(
                    (s for s in services if s["id"] == c), None
                )
                c_kind = (c_node or {}).get("kind") or "unknown"
                c_color = SERVICE_KIND_COLORS.get(c_kind, "#a0a0a0")
                c_name = (c_node or {}).get("name") or c
                c_disp = _topov2_truncate(c_name, 16)
                pill_w = min(col_widths[0] - 4, max(80, len(c_disp) * 6.2 + 14))
                pill_h = 18
                pill_x = col_x[0]
                # Centre the stack vertically.
                pill_y = y_mid - pill_h / 2 - (total - 1) * 11 + j * 22
                parts.append(
                    f'<rect class="cpaths-caller-pill" '
                    f'x="{pill_x}" y="{pill_y:.1f}" '
                    f'width="{pill_w:.1f}" height="{pill_h}" rx="9" '
                    f'fill="{escape(c_color)}" />'
                )
                parts.append(
                    f'<text class="cpaths-caller-text" '
                    f'x="{pill_x + pill_w / 2:.1f}" '
                    f'y="{pill_y + 12.5:.1f}" '
                    f'text-anchor="middle">{escape(c_disp)}</text>'
                )
            if len(callers) > 2:
                parts.append(
                    f'<text class="cpaths-dep-overflow" '
                    f'x="{col_x[0] + 4}" '
                    f'y="{y_mid + 22:.1f}">'
                    f'+{len(callers) - 2} more</text>'
                )
        else:
            parts.append(
                f'<text class="cpaths-empty-cell" '
                f'x="{col_x[0] + col_widths[0] / 2:.1f}" '
                f'y="{y_mid + 3:.1f}" text-anchor="middle">'
                f'— no caller detected</text>'
            )

        # Arrow 1 → 2
        a_start = col_x[0] + col_widths[0]
        a_end = col_x[1]
        parts.append(
            f'<path class="cpaths-arrow" d="M{a_start} {y_mid:.1f} '
            f'L{a_end - 4} {y_mid:.1f}" marker-end="url(#cpaths-arrow)" />'
        )

        # ----- COL 2: Entry module card -----
        card_x = col_x[1]
        card_y = y_mid - row_h / 2 + 6
        card_h = row_h - 12
        parts.append(
            f'<rect class="cpaths-entry-bg" '
            f'x="{card_x}" y="{card_y:.1f}" '
            f'width="{col_widths[1]}" height="{card_h:.1f}" rx="6" />'
        )
        leaf_disp = _topov2_truncate(p["module_leaf"], 20)
        parts.append(
            f'<text class="cpaths-entry-name" '
            f'x="{card_x + 10}" y="{card_y + 17:.1f}">'
            f'{escape(leaf_disp)}</text>'
        )
        # Endpoint badge in top-right of the card.
        badge_text = (
            f'{p["endpoint_count"]} endpoints'
            if p["endpoint_count"] != 1 else '1 endpoint'
        )
        bw = max(64, len(badge_text) * 5.4 + 12)
        bh = 14
        bx = card_x + col_widths[1] - bw - 6
        by = card_y + 4
        parts.append(
            f'<rect class="cpaths-ep-badge" '
            f'x="{bx:.1f}" y="{by:.1f}" '
            f'width="{bw:.1f}" height="{bh}" rx="7" />'
        )
        parts.append(
            f'<text class="cpaths-ep-badge-text" '
            f'x="{bx + bw / 2:.1f}" y="{by + 10.5:.1f}" '
            f'text-anchor="middle">{badge_text}</text>'
        )
        # Sample endpoint line beneath name
        if p["sample_method"]:
            sample_text = f'{p["sample_method"]} {p["sample_path"]}'
            sample_disp = _topov2_truncate(sample_text, 34)
            parts.append(
                f'<text class="cpaths-entry-sample" '
                f'x="{card_x + 10}" y="{card_y + 33:.1f}">'
                f'{escape(sample_disp)}</text>'
            )

        # Arrow 2 → 3
        a_start = card_x + col_widths[1]
        a_end = col_x[2]
        parts.append(
            f'<path class="cpaths-arrow" d="M{a_start} {y_mid:.1f} '
            f'L{a_end - 4} {y_mid:.1f}" marker-end="url(#cpaths-arrow)" />'
        )

        # ----- COL 3: Key deps pills -----
        deps = p["deps"]
        pill_x_cursor = col_x[2]
        col3_right_bound = col_x[2] + col_widths[2]
        shown_count = 0
        for d_name in deps:
            d_disp = _topov2_truncate(d_name, 14)
            d_w = min(110, max(48, len(d_disp) * 6.5 + 12))
            d_h = 18
            if pill_x_cursor + d_w + 38 > col3_right_bound:
                # Reserve ~38px on the right for the "+N" overflow.
                break
            is_shared = (d_name.lower() in UTIL_MODULE_NAMES)
            css_extra = " is-shared" if is_shared else ""
            parts.append(
                f'<rect class="cpaths-dep-pill{css_extra}" '
                f'x="{pill_x_cursor:.1f}" y="{y_mid - 9:.1f}" '
                f'width="{d_w:.1f}" height="{d_h}" rx="9" />'
            )
            parts.append(
                f'<text class="cpaths-dep-pill-text" '
                f'x="{pill_x_cursor + d_w / 2:.1f}" '
                f'y="{y_mid + 3.5:.1f}" '
                f'text-anchor="middle">{escape(d_disp)}</text>'
            )
            pill_x_cursor += d_w + 6
            shown_count += 1
        overflow_n = len(deps) - shown_count
        if overflow_n > 0:
            parts.append(
                f'<text class="cpaths-dep-overflow" '
                f'x="{pill_x_cursor + 2:.1f}" y="{y_mid + 3.5:.1f}">'
                f'+{overflow_n}</text>'
            )
        if not deps:
            parts.append(
                f'<text class="cpaths-empty-cell" '
                f'x="{col_x[2] + col_widths[2] / 2:.1f}" '
                f'y="{y_mid + 3.5:.1f}" text-anchor="middle">'
                f'— no internal imports</text>'
            )

        # Arrow 3 → 4
        a_start = col_x[2] + col_widths[2]
        a_end = col_x[3]
        parts.append(
            f'<path class="cpaths-arrow" d="M{a_start} {y_mid:.1f} '
            f'L{a_end - 4} {y_mid:.1f}" marker-end="url(#cpaths-arrow)" />'
        )

        # ----- COL 4: Store pill -----
        if p["store_id"]:
            store_obj = next(
                (s for s in stores if s["id"] == p["store_id"]), None
            )
            store_name = (store_obj or {}).get("name") or p["store_id"]
            store_kind = (store_obj or {}).get("kind") or "unknown"
            store_color = STORE_KIND_COLORS.get(store_kind, "#888")
            store_disp = _topov2_truncate(store_name, 14)
            pill_w = min(col_widths[3] - 4, max(80, len(store_disp) * 6.5 + 14))
            pill_h = 20
            pill_x = col_x[3]
            pill_y = y_mid - pill_h / 2
            parts.append(
                f'<rect class="cpaths-store-pill" '
                f'x="{pill_x}" y="{pill_y:.1f}" '
                f'width="{pill_w:.1f}" height="{pill_h}" rx="10" '
                f'fill="{escape(store_color)}" />'
            )
            parts.append(
                f'<text class="cpaths-store-text" '
                f'x="{pill_x + pill_w / 2:.1f}" '
                f'y="{pill_y + 13.5:.1f}" '
                f'text-anchor="middle">{escape(store_disp)}</text>'
            )
        else:
            parts.append(
                f'<text class="cpaths-empty-cell" '
                f'x="{col_x[3] + col_widths[3] / 2:.1f}" '
                f'y="{y_mid + 3.5:.1f}" text-anchor="middle">'
                f'— no ORM store</text>'
            )

    parts.append("</svg>")
    svg = "".join(parts)

    # ------ Headline ------
    n_total = len(em_list)
    n_visible = len(visible)
    fully_traced = sum(
        1 for p in visible if p["callers"] and p["deps"] and p["store_id"]
    )
    headline = (
        f'<strong>{n_total} entry-point module'
        f'{"s" if n_total != 1 else ""}</strong> expose HTTP endpoints '
        f'in this codebase. The rows below trace each one from <em>caller</em> '
        f'to <em>data store</em>; <strong>{fully_traced}</strong> '
        f'{"have" if fully_traced != 1 else "has"} a complete '
        f'caller→deps→store chain detected.'
    )
    if n_total > MAX_CPATHS_ROWS:
        headline += (
            f' Showing the top <strong>{MAX_CPATHS_ROWS}</strong> by '
            f'endpoint count.'
        )

    overflow_note = ""
    if truncated:
        overflow_note = (
            f'<p class="cpaths-overflow-note">'
            f'… and <strong>{n_total - MAX_CPATHS_ROWS}</strong> more '
            f'entry-point module'
            f'{"s" if (n_total - MAX_CPATHS_ROWS) != 1 else ""} '
            f'omitted from this view.'
            f'</p>'
        )

    observations_html = _render_observations(
        _observations_for_cpaths(paths, services, topo)
    )

    bento_html = render_cpaths_bento(data, paths, services, stores)

    return f"""
<section id="codemap-cpaths-section">
  <h2>What happens when a request flows through</h2>
  {section_intro("cpaths")}
  <div class="cpaths-frame">
    <p class="cpaths-headline">{headline}</p>
    <div class="cpaths-wrap">{svg}</div>
    {overflow_note}
  </div>
  {observations_html}
  {bento_html}
</section>
"""


def render_cpaths_bento(
    data: dict[str, Any],
    paths: list[dict[str, Any]],
    services: list[dict[str, Any]],
    stores: list[dict[str, Any]],
) -> str:
    """Bento beneath the critical-paths swimlane.

    Tiles:
      1. HTTP method distribution (horizontal mini-bars per method)
      2. Top URL path prefixes (which resource families exist)
      3. Endpoints per service (so you see the surface size at a glance)
      4. Coverage stat (traced/total) and unresolved-call count
    """
    from collections import Counter

    topo = data.get("http_topology") or {}
    endpoints = topo.get("endpoints") or []
    topo_edges = topo.get("edges") or []

    # ---------- Tile 1: HTTP method distribution ----------
    method_counts: Counter = Counter()
    for ep in endpoints:
        method_counts[(ep.get("method") or "ANY").upper()] += 1
    max_m = max(method_counts.values()) if method_counts else 1
    if method_counts:
        rows = []
        # Render methods in conventional order
        order = ["GET", "POST", "PUT", "PATCH", "DELETE", "ANY", "HEAD", "OPTIONS"]
        for m in order:
            c = method_counts.get(m, 0)
            if c == 0:
                continue
            color = HTTP_METHOD_COLORS.get(m, "#6b7280")
            pct = (c * 100) / max_m
            rows.append(
                f'<div class="row">'
                f'<span class="method" style="background:{escape(color)};">'
                f'{m}</span>'
                f'<span class="bar"><span '
                f'style="width:{pct:.1f}%;background:{escape(color)};">'
                f'</span></span>'
                f'<span class="num">{c}</span>'
                f'</div>'
            )
        # Catch any methods that weren't in `order` (custom verbs)
        for m, c in method_counts.items():
            if m in order:
                continue
            color = HTTP_METHOD_COLORS.get(m, "#6b7280")
            pct = (c * 100) / max_m
            rows.append(
                f'<div class="row">'
                f'<span class="method" style="background:{escape(color)};">'
                f'{escape(m[:6])}</span>'
                f'<span class="bar"><span '
                f'style="width:{pct:.1f}%;background:{escape(color)};">'
                f'</span></span>'
                f'<span class="num">{c}</span>'
                f'</div>'
            )
        methods_body = (
            f'<div class="cpaths-method-bars">{"".join(rows)}</div>'
        )
    else:
        methods_body = (
            '<p class="cpaths-empty">No HTTP endpoints detected.</p>'
        )

    # ---------- Tile 2: Top URL path prefixes ----------
    prefix_counts: Counter = Counter()
    for ep in endpoints:
        prefix_counts[_path_prefix(ep.get("path") or "")] += 1
    top_prefixes = prefix_counts.most_common(10)
    if top_prefixes:
        prefix_rows = "".join(
            f'<li><span class="prefix">{escape(p)}</span>'
            f'<span class="count">{c}</span></li>'
            for p, c in top_prefixes
        )
        prefixes_body = (
            f'<ul class="cpaths-prefix-list">{prefix_rows}</ul>'
        )
    else:
        prefixes_body = (
            '<p class="cpaths-empty">No URL paths detected.</p>'
        )

    # ---------- Tile 3: Endpoints per service ----------
    eps_by_svc: Counter = Counter()
    for ep in endpoints:
        eps_by_svc[ep.get("service") or "unknown"] += 1
    if eps_by_svc:
        svc_rows = []
        for svc_id, c in eps_by_svc.most_common(8):
            svc_node = next(
                (s for s in services if s["id"] == svc_id), None
            )
            kind_color = SERVICE_KIND_COLORS.get(
                (svc_node or {}).get("kind") or "unknown", "#a0a0a0"
            )
            svc_name = (svc_node or {}).get("name") or svc_id
            svc_rows.append(
                f'<li>'
                f'<span class="svc">'
                f'<span class="swatch" '
                f'style="background:{escape(kind_color)};"></span>'
                f'{escape(svc_name)}</span>'
                f'<span class="count" style="background:var(--accent-soft); '
                f'color:var(--accent-deep); padding:0 7px; border-radius:999px; '
                f'font-size:0.78rem;">'
                f'{c}</span></li>'
            )
        svcs_body = (
            f'<ul class="cpaths-svc-list">{"".join(svc_rows)}</ul>'
        )
    else:
        svcs_body = (
            '<p class="cpaths-empty">No services with endpoints detected.</p>'
        )

    # ---------- Tile 4: Trace-coverage stat ----------
    n_endpoints = len(endpoints)
    n_resolved = len(topo_edges)
    n_unresolved = int(topo.get("unresolved_client_count") or 0)
    fully_traced_rows = sum(
        1 for p in paths
        if p["callers"] and p["deps"] and p["store_id"]
    )
    coverage_body = (
        f'<div class="cpaths-coverage-stat">'
        f'{fully_traced_rows}'
        f'<span class="denom"> / {len(paths)}</span>'
        f'</div>'
        f'<div class="cpaths-coverage-label">Fully traced rows</div>'
        f'<div style="margin-top: var(--space-3); padding-top: var(--space-3); '
        f'border-top: 1px solid var(--border);">'
        f'<div class="topov2-stat-row">'
        f'<span class="k">HTTP endpoints declared</span>'
        f'<span class="v">{n_endpoints}</span>'
        f'</div>'
        f'<div class="topov2-stat-row">'
        f'<span class="k">Resolved inter-service edges</span>'
        f'<span class="v">{n_resolved}</span>'
        f'</div>'
        f'<div class="topov2-stat-row">'
        f'<span class="k">Unresolved client calls</span>'
        f'<span class="v {"" if n_unresolved else "muted"}">'
        f'{n_unresolved}</span>'
        f'</div>'
        f'</div>'
    )

    return f"""
<div class="cpaths-bento">
  <div class="cpaths-tile">
    <div class="tile-label">Methods</div>
    <div class="tile-headline">HTTP verb distribution across endpoints</div>
    <div class="tile-body">{methods_body}</div>
  </div>
  <div class="cpaths-tile">
    <div class="tile-label">Resource families</div>
    <div class="tile-headline">Top URL path prefixes</div>
    <div class="tile-body">{prefixes_body}</div>
  </div>
  <div class="cpaths-tile">
    <div class="tile-label">Per-service surface</div>
    <div class="tile-headline">Endpoints declared by each service</div>
    <div class="tile-body">{svcs_body}</div>
  </div>
  <div class="cpaths-tile">
    <div class="tile-label">Coverage</div>
    <div class="tile-headline">How much of the HTTP surface is fully traced</div>
    <div class="tile-body">{coverage_body}</div>
  </div>
</div>
"""


# Sankey-style data lineage — replacement for the older bipartite
# render_data_lineage below. Services sit in a column on the left,
# data stores as cylinders on the right. Each service→store edge is
# rendered as a weighted ribbon (Sankey band) whose stroke width
# encodes the number of distinct data models on that edge.
#
# A key design choice: we render ALL detected stores, not only the
# ones with ORM model declarations. Stores that appear only in
# environment config (no ORM models) are drawn at reduced opacity
# with a "no ORM models declared" annotation — those stores are
# usually real infrastructure accessed via raw client libraries,
# not noise, and hiding them lies about the architecture.

LINEAGE2_SVC_W = 200
LINEAGE2_SVC_H = 88
LINEAGE2_STORE_W = 150
LINEAGE2_STORE_H = 100
LINEAGE2_COL_GAP = 32  # vertical gap between cards in each column
LINEAGE2_MIDDLE = 280  # horizontal channel for the Sankey bands


def _lineage2_kind_chip_label(kind: str | None) -> str:
    if not kind:
        return "STORE"
    return kind.upper()[:14]


def _lineage2_emit_cylinder(
    x: float, y: float, w: float, h: float, color: str
) -> str:
    """SVG group rendering a database cylinder glyph.

    Two ellipses (top + bottom) plus side lines = the universal
    "database" icon every architecture diagram uses. The top ellipse
    is filled with a slightly darker shade than the body so the cap
    reads as the visible 'top' of the cylinder.
    """
    rx = w / 2
    ry = 8
    cx = x + w / 2
    body_top_y = y + ry
    body_bot_y = y + h - ry
    # Compose darker shade for cap by simply layering with reduced
    # opacity black overlay — but we can keep it simple: use color
    # directly and let visual unity carry it.
    return (
        # Body (rectangle, stroked sides only).
        f'<rect '
        f'x="{x:.1f}" y="{body_top_y:.1f}" '
        f'width="{w}" height="{h - 2 * ry:.1f}" '
        f'fill="{escape(color)}" fill-opacity="0.88" />'
        # Bottom ellipse (closed bottom of cylinder).
        f'<ellipse cx="{cx:.1f}" cy="{body_bot_y:.1f}" '
        f'rx="{rx}" ry="{ry}" '
        f'fill="{escape(color)}" fill-opacity="0.88" />'
        # Cap (top ellipse, drawn last so its top half overlays body).
        f'<ellipse cx="{cx:.1f}" cy="{body_top_y:.1f}" '
        f'rx="{rx}" ry="{ry}" '
        f'fill="{escape(color)}" fill-opacity="1" />'
        # Left + right strokes (no top/bottom lines — ellipses cover them).
        f'<line class="lineage2-cyl-stroke" '
        f'x1="{x:.1f}" y1="{body_top_y:.1f}" '
        f'x2="{x:.1f}" y2="{body_bot_y:.1f}" '
        f'stroke="oklch(20% 0.012 250 / 0.18)" />'
        f'<line class="lineage2-cyl-stroke" '
        f'x1="{x + w:.1f}" y1="{body_top_y:.1f}" '
        f'x2="{x + w:.1f}" y2="{body_bot_y:.1f}" '
        f'stroke="oklch(20% 0.012 250 / 0.18)" />'
        # Top ellipse stroke (visible curve around the cap).
        f'<ellipse cx="{cx:.1f}" cy="{body_top_y:.1f}" '
        f'rx="{rx}" ry="{ry}" '
        f'fill="none" stroke="oklch(20% 0.012 250 / 0.22)" '
        f'stroke-width="1" />'
        # Bottom ellipse: only the front-facing arc gets a stroke (so
        # the cylinder reads as 3D — no stroke around the back arc).
        f'<path '
        f'd="M{x:.1f},{body_bot_y:.1f} '
        f'A{rx},{ry} 0 0 0 {x + w:.1f},{body_bot_y:.1f}" '
        f'fill="none" stroke="oklch(20% 0.012 250 / 0.22)" '
        f'stroke-width="1" />'
    )


def render_data_lineage_v2(data: dict[str, Any]) -> str:
    lineage = data.get("data_lineage") or {}
    stores = lineage.get("stores") or []
    edges = lineage.get("edges") or []
    services_full = data.get("services") or []

    if not stores and not edges:
        return ""

    # ------ Build store list (show ALL detected stores) ------
    # Map of store_id -> incoming model count (0 if no ORM edges link to it).
    incoming_count: dict[str, int] = {s["id"]: 0 for s in stores}
    incoming_services: dict[str, list[tuple[str, int, list[str]]]] = {
        s["id"]: [] for s in stores
    }
    for e in edges:
        sid = e.get("target_store", "")
        src = e.get("source_service", "")
        w = int(e.get("weight") or 1)
        incoming_count[sid] = incoming_count.get(sid, 0) + w
        incoming_services.setdefault(sid, []).append(
            (src, w, e.get("frameworks") or [])
        )

    # ------ Build service list (only services that have edges) ------
    src_ids_used: set[str] = {e.get("source_service", "") for e in edges}
    nodes_svc = [s for s in services_full if s["id"] in src_ids_used]

    # If there are no ORM edges but stores were detected, we still
    # render the section: a "stores detected only via env config" view.
    has_modeled_flow = bool(edges and nodes_svc)

    # ------ Ordering passes (barycentric, single pass) ------
    if has_modeled_flow:
        # Order services by total outbound weight desc (heaviest at top).
        svc_total: dict[str, int] = {
            s["id"]: sum(int(e.get("weight") or 1) for e in edges
                         if e.get("source_service") == s["id"])
            for s in nodes_svc
        }
        nodes_svc.sort(key=lambda s: -svc_total[s["id"]])
        # Order stores: connected stores first (sorted by total inbound
        # weight desc), then unconnected stores in input order.
        connected = [s for s in stores if incoming_count[s["id"]] > 0]
        connected.sort(key=lambda s: -incoming_count[s["id"]])
        unconnected = [s for s in stores if incoming_count[s["id"]] == 0]
        ordered_stores = connected + unconnected
    else:
        ordered_stores = list(stores)

    # ------ Sizing ------
    rows_left = max(1, len(nodes_svc))
    rows_right = max(1, len(ordered_stores))
    col_h_left = rows_left * LINEAGE2_SVC_H + (rows_left - 1) * LINEAGE2_COL_GAP
    col_h_right = rows_right * LINEAGE2_STORE_H + (rows_right - 1) * LINEAGE2_COL_GAP
    pad_x = 20
    pad_top = 36
    pad_bot = 28
    svg_h = max(col_h_left, col_h_right) + pad_top + pad_bot
    svg_w = (
        pad_x + LINEAGE2_SVC_W + LINEAGE2_MIDDLE + LINEAGE2_STORE_W + pad_x
    )

    # Column anchor X coords.
    left_x = pad_x
    right_x = pad_x + LINEAGE2_SVC_W + LINEAGE2_MIDDLE

    # Position services + stores. Each column is vertically centred
    # within its own column height; the SVG is sized to the larger.
    svc_pos: dict[str, dict[str, float]] = {}
    y_start_left = pad_top + (svg_h - pad_top - pad_bot - col_h_left) / 2
    for i, s in enumerate(nodes_svc):
        svc_pos[s["id"]] = {
            "x": left_x,
            "y": y_start_left + i * (LINEAGE2_SVC_H + LINEAGE2_COL_GAP),
            "cy": y_start_left + i * (LINEAGE2_SVC_H + LINEAGE2_COL_GAP)
                  + LINEAGE2_SVC_H / 2,
        }
    store_pos: dict[str, dict[str, float]] = {}
    y_start_right = pad_top + (svg_h - pad_top - pad_bot - col_h_right) / 2
    for i, s in enumerate(ordered_stores):
        store_pos[s["id"]] = {
            "x": right_x,
            "y": y_start_right + i * (LINEAGE2_STORE_H + LINEAGE2_COL_GAP),
            "cy": y_start_right + i * (LINEAGE2_STORE_H + LINEAGE2_COL_GAP)
                  + LINEAGE2_STORE_H / 2,
        }

    # ------ Band stroke-width (log scale by model count) ------
    max_w = max([int(e.get("weight") or 1) for e in edges] + [1])
    log_denom = math.log(max(2, max_w) + 1)

    def _band_w(c: int) -> float:
        v = math.log(c + 1) / log_denom
        return round(6 + 32 * v, 2)

    parts: list[str] = [
        f'<svg class="lineage2-svg" '
        f'viewBox="0 0 {svg_w:.0f} {svg_h:.0f}" '
        f'width="{svg_w:.0f}" '
        f'role="img" aria-label="Data lineage Sankey">'
    ]

    # Axis titles
    parts.append(
        f'<text class="lineage2-axis-title" '
        f'x="{left_x + LINEAGE2_SVC_W / 2:.1f}" y="18" '
        f'text-anchor="middle">SERVICES</text>'
    )
    parts.append(
        f'<text class="lineage2-axis-title" '
        f'x="{right_x + LINEAGE2_STORE_W / 2:.1f}" y="18" '
        f'text-anchor="middle">DATA STORES</text>'
    )

    # ----- Bands (drawn first so cards/cylinders overlay any joins) -----
    for e in edges:
        src_id = e.get("source_service", "")
        tgt_id = e.get("target_store", "")
        sp = svc_pos.get(src_id)
        tp = store_pos.get(tgt_id)
        if not sp or not tp:
            continue
        ax = sp["x"] + LINEAGE2_SVC_W
        ay = sp["cy"]
        bx = tp["x"]
        by = tp["cy"]
        sw = _band_w(int(e.get("weight") or 1))
        store_color = STORE_KIND_COLORS.get(
            next((s for s in stores if s["id"] == tgt_id), {}).get("kind") or "unknown",
            "#888",
        )
        midx = (ax + bx) / 2
        d = (
            f"M{ax:.1f},{ay:.1f} "
            f"C{midx:.1f},{ay:.1f} "
            f"{midx:.1f},{by:.1f} "
            f"{bx:.1f},{by:.1f}"
        )
        parts.append(
            f'<path class="lineage2-band" d="{d}" '
            f'stroke="{escape(store_color)}" '
            f'stroke-opacity="0.55" '
            f'stroke-width="{sw}">'
            f'<title>{escape(src_id)} → {escape(tgt_id)} · '
            f'{e.get("weight") or 0} model'
            f'{"s" if (e.get("weight") or 0) != 1 else ""}'
            f' via {", ".join(e.get("frameworks") or []) or "ORM"}</title>'
            f'</path>'
        )
        # Mid-pill label
        weight = e.get("weight") or 0
        label = f'{weight} model{"s" if weight != 1 else ""}'
        text_w = max(60, len(label) * 6 + 14)
        text_h = 18
        rect_x = midx - text_w / 2
        rect_y = (ay + by) / 2 - text_h / 2
        parts.append(
            f'<rect class="lineage2-band-label-bg" '
            f'x="{rect_x:.1f}" y="{rect_y:.1f}" '
            f'width="{text_w}" height="{text_h}" rx="9" />'
        )
        parts.append(
            f'<text class="lineage2-band-label" '
            f'x="{midx:.1f}" y="{(ay + by) / 2 + 3.5:.1f}" '
            f'text-anchor="middle">{escape(label)}</text>'
        )

    # ----- Service cards (left column) -----
    for s in nodes_svc:
        p = svc_pos[s["id"]]
        x, y = p["x"], p["y"]
        kind_color = SERVICE_KIND_COLORS.get(
            s.get("kind") or "unknown", "#a0a0a0"
        )
        parts.append(
            f'<rect class="lineage2-svc-bg" '
            f'x="{x:.1f}" y="{y:.1f}" '
            f'width="{LINEAGE2_SVC_W}" height="{LINEAGE2_SVC_H}" '
            f'rx="10" />'
        )
        # Left-side accent stripe in kind color.
        parts.append(
            f'<rect '
            f'x="{x:.1f}" y="{y:.1f}" '
            f'width="5" height="{LINEAGE2_SVC_H}" '
            f'rx="10" '
            f'fill="{escape(kind_color)}" />'
        )
        # Cover stripe's right-curved bit so it reads as a flat tab.
        parts.append(
            f'<rect '
            f'x="{x + 2:.1f}" y="{y:.1f}" '
            f'width="3" height="{LINEAGE2_SVC_H}" '
            f'fill="{escape(kind_color)}" />'
        )
        title = _topov2_truncate(s.get("name") or s["id"], 22)
        parts.append(
            f'<text class="lineage2-svc-title" '
            f'x="{x + 14:.1f}" y="{y + 26:.1f}" '
            f'font-size="14">{escape(title)}</text>'
        )
        # Outgoing model count + frameworks
        total_models = sum(
            int(e.get("weight") or 1) for e in edges
            if e.get("source_service") == s["id"]
        )
        fwks = sorted({
            f for e in edges if e.get("source_service") == s["id"]
            for f in (e.get("frameworks") or [])
        })
        meta = f"{total_models} model{'s' if total_models != 1 else ''}"
        if fwks:
            meta += " · " + ", ".join(fwks)
        parts.append(
            f'<text class="lineage2-svc-meta" '
            f'x="{x + 14:.1f}" y="{y + 46:.1f}" '
            f'font-size="11">{escape(_topov2_truncate(meta, 26))}</text>'
        )
        # Kind chip in bottom-left
        chip_label = _topov2_kind_chip_label(s.get("kind"))
        chip_w = max(50, len(chip_label) * 6 + 12)
        chip_h = 15
        parts.append(
            f'<rect '
            f'x="{x + 14:.1f}" y="{y + LINEAGE2_SVC_H - 22:.1f}" '
            f'width="{chip_w}" height="{chip_h}" rx="3" '
            f'fill="{escape(kind_color)}" />'
        )
        parts.append(
            f'<text class="topov2-kind-chip-text" '
            f'x="{x + 14 + chip_w / 2:.1f}" '
            f'y="{y + LINEAGE2_SVC_H - 22 + 11:.1f}" '
            f'text-anchor="middle">{escape(chip_label)}</text>'
        )

    # ----- Store cylinders (right column) -----
    for s in ordered_stores:
        p = store_pos[s["id"]]
        x, y = p["x"], p["y"]
        kind = s.get("kind") or "unknown"
        color = STORE_KIND_COLORS.get(kind, "#888888")
        unlinked = incoming_count.get(s["id"], 0) == 0
        group_class = "lineage2-cyl" + (" is-unlinked" if unlinked else "")
        parts.append(f'<g class="{group_class}">')
        # Cylinder body
        parts.append(_lineage2_emit_cylinder(
            x, y, LINEAGE2_STORE_W, LINEAGE2_STORE_H, color
        ))
        # Name (inside the body, near top). The cylinder is 150px wide
        # so we can comfortably fit ~22 chars of 13.5px serif before
        # truncating — names like "Firebase / Firestore" should fit.
        name = _topov2_truncate(s.get("name") or s["id"], 22)
        parts.append(
            f'<text class="lineage2-cyl-name" '
            f'x="{x + LINEAGE2_STORE_W / 2:.1f}" '
            f'y="{y + LINEAGE2_STORE_H / 2:.1f}" '
            f'text-anchor="middle" '
            f'style="fill: white; paint-order: stroke; '
            f'stroke: oklch(20% 0.012 250 / 0.35); stroke-width: 3px; '
            f'stroke-linejoin: round;">{escape(name)}</text>'
        )
        # Kind label below the name
        parts.append(
            f'<text class="lineage2-cyl-kind" '
            f'x="{x + LINEAGE2_STORE_W / 2:.1f}" '
            f'y="{y + LINEAGE2_STORE_H / 2 + 15:.1f}" '
            f'text-anchor="middle" '
            f'style="fill: white; opacity: 0.9;">'
            f'{escape(kind.upper())}</text>'
        )
        # Below the cylinder: model count or "no ORM models" note
        if unlinked:
            below = "no ORM models declared"
        else:
            n = incoming_count[s["id"]]
            below = f"{n} model{'s' if n != 1 else ''}"
        parts.append(
            f'<text class="lineage2-cyl-models" '
            f'x="{x + LINEAGE2_STORE_W / 2:.1f}" '
            f'y="{y + LINEAGE2_STORE_H + 14:.1f}" '
            f'text-anchor="middle">{escape(below)}</text>'
        )
        parts.append("</g>")

    parts.append("</svg>")
    svg = "".join(parts)

    # ------ Headline ------
    # Pieces:
    #  - N services persist to M stores via [frameworks]
    #  - Heaviest edge: service X with N models to store Y
    #  - K stores detected but unmodeled (footnote)
    fw_set: set[str] = set()
    for e in edges:
        for f in e.get("frameworks") or []:
            fw_set.add(f)
    n_modeled_stores = sum(1 for c in incoming_count.values() if c > 0)
    n_unlinked = sum(1 for c in incoming_count.values() if c == 0)
    if edges:
        heaviest = max(edges, key=lambda e: int(e.get("weight") or 0))
        h_src = heaviest.get("source_service", "")
        h_tgt = heaviest.get("target_store", "")
        h_w = int(heaviest.get("weight") or 0)
        h_fw = ", ".join(heaviest.get("frameworks") or []) or "ORM"
        svc_name = next(
            (s.get("name") or s["id"] for s in services_full if s["id"] == h_src),
            h_src,
        )
        store_name = next(
            (s.get("name") or s["id"] for s in stores if s["id"] == h_tgt),
            h_tgt,
        )
        fw_phrase = (
            f' via <em>{escape(", ".join(sorted(fw_set)))}</em>'
            if fw_set else ""
        )
        unlinked_phrase = (
            f' <strong>{n_unlinked}</strong> additional store'
            f'{"s are" if n_unlinked != 1 else " is"} referenced in env '
            f'config but no ORM models link to '
            f'{"them" if n_unlinked != 1 else "it"}.'
            if n_unlinked else ""
        )
        headline = (
            f'<strong>{len(nodes_svc)} service'
            f'{"s" if len(nodes_svc) != 1 else ""}</strong> persist data to '
            f'<strong>{n_modeled_stores} store'
            f'{"s" if n_modeled_stores != 1 else ""}</strong>{fw_phrase}. '
            f'The largest footprint is <strong>{escape(svc_name)}</strong> with '
            f'<strong>{h_w}</strong> models in <strong>{escape(store_name)}</strong>.'
            f'{unlinked_phrase}'
        )
    else:
        # No ORM edges, but stores were detected.
        kinds = sorted({(s.get("kind") or "unknown") for s in stores})
        headline = (
            f'No ORM model declarations were found. '
            f'<strong>{len(stores)} data store'
            f'{"s" if len(stores) != 1 else ""}</strong> '
            f'(<em>{escape(", ".join(kinds))}</em>) '
            f'{"were" if len(stores) != 1 else "was"} detected via '
            f'environment config — these are likely accessed by raw '
            f'client libraries (e.g. <code>redis</code>, <code>boto3</code>) '
            f'rather than through an ORM.'
        )

    bento_html = render_lineage_v2_bento(data, stores, edges, services_full)
    observations_html = _render_observations(
        _observations_for_lineage(stores, edges, services_full)
    )

    return f"""
<section id="codemap-lineage2-section">
  <h2>Where each service stores its data</h2>
  {section_intro("lineage")}
  <div class="lineage2-frame">
    <p class="lineage2-headline">{headline}</p>
    <div class="lineage2-wrap">{svg}</div>
  </div>
  {observations_html}
  {bento_html}
</section>
"""


def render_lineage_v2_bento(
    data: dict[str, Any],
    stores: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    services_full: list[dict[str, Any]],
) -> str:
    """Bento beneath the Sankey hero.

    Four tiles:
      1. Per-store fan-in (who writes here + how many models)
      2. ORM frameworks detected (chips)
      3. Top "hot" models (most-frequent models across services)
      4. Detected store kinds (chips with brand colors)
    """
    lineage = data.get("data_lineage") or {}
    models = lineage.get("models") or []
    name_by_svc = {s["id"]: (s.get("name") or s["id"]) for s in services_full}

    # ---------- Tile 1: Per-store fan-in ----------
    incoming: dict[str, list[dict[str, Any]]] = {s["id"]: [] for s in stores}
    for e in edges:
        sid = e.get("target_store", "")
        if sid in incoming:
            incoming[sid].append(e)
    for sid in incoming:
        incoming[sid].sort(key=lambda e: -int(e.get("weight") or 0))

    fan_rows: list[str] = []
    # Show connected stores first (rich data), then unconnected ones.
    connected_first = sorted(
        stores, key=lambda s: -sum(int(e.get("weight") or 0)
                                    for e in incoming.get(s["id"], []))
    )
    for s in connected_first:
        color = STORE_KIND_COLORS.get(s.get("kind") or "unknown", "#888")
        ev = incoming.get(s["id"], [])
        if ev:
            sources_rows = "".join(
                f'<div class="row">'
                f'<span>← {escape(name_by_svc.get(e.get("source_service",""), e.get("source_service","")))}</span>'
                f'<span class="count">{e.get("weight") or 0} model'
                f'{"s" if (e.get("weight") or 0) != 1 else ""}</span>'
                f'</div>'
                for e in ev
            )
            sources_block = f'<div class="sources">{sources_rows}</div>'
        else:
            sources_block = (
                f'<div class="sources"><div class="row is-unlinked">'
                f'<span class="reason">Detected via env config</span>'
                f'<span class="count">0 models</span></div></div>'
            )
        fan_rows.append(
            f'<li>'
            f'<div class="store-head">'
            f'<span class="swatch" style="background:{escape(color)};"></span>'
            f'{escape(s.get("name") or s["id"])}'
            f'<span class="kind">{escape((s.get("kind") or "").upper())}</span>'
            f'</div>'
            f'{sources_block}'
            f'</li>'
        )
    fan_body = (
        f'<ul class="lineage2-store-list">{"".join(fan_rows)}</ul>'
        if fan_rows
        else '<p class="lineage2-empty">No data stores detected.</p>'
    )

    # ---------- Tile 2: ORM frameworks ----------
    fw_set: set[str] = set()
    for e in edges:
        for f in e.get("frameworks") or []:
            fw_set.add(f)
    if fw_set:
        fw_pills = "".join(
            f'<span class="orm-pill">{escape(f)}</span>' for f in sorted(fw_set)
        )
        orm_body = f'<div class="lineage2-orm-cloud">{fw_pills}</div>'
        orm_foot = (
            '<p class="lineage2-tile-foot">'
            'Frameworks were inferred from ORM model declarations '
            '(<code>@Entity</code>, <code>Base</code> subclasses, '
            '<code>model</code> blocks in <code>schema.prisma</code>, etc.) '
            'in the scanned source files.'
            '</p>'
        )
    else:
        orm_body = (
            '<p class="lineage2-empty">No ORM frameworks detected '
            'in the scanned source.</p>'
        )
        orm_foot = ""

    # ---------- Tile 3: Top "hot" models ----------
    # Group all model entries by model name; count how many service-store
    # combos declare each. Top by frequency (proxy for "central entity").
    from collections import Counter
    model_count: Counter = Counter()
    model_meta: dict[str, dict[str, set[str]]] = {}
    for m in models:
        nm = m.get("model")
        if not nm:
            continue
        model_count[nm] += 1
        meta = model_meta.setdefault(nm, {"services": set(), "frameworks": set()})
        if m.get("service"):
            meta["services"].add(m["service"])
        if m.get("framework"):
            meta["frameworks"].add(m["framework"])
    top_models = model_count.most_common(8)
    if top_models:
        rows = []
        for nm, c in top_models:
            meta = model_meta.get(nm, {"services": set(), "frameworks": set()})
            svc_str = ", ".join(
                sorted(name_by_svc.get(s, s) for s in meta["services"])
            )
            rows.append(
                f'<li>'
                f'<span class="model-name">{escape(nm)}</span>'
                f'<span class="meta">{escape(svc_str)}</span>'
                f'</li>'
            )
        hot_body = f'<ul class="lineage2-hot-list">{"".join(rows)}</ul>'
    else:
        hot_body = (
            '<p class="lineage2-empty">No models detected.</p>'
        )

    # ---------- Tile 4: Detected store kinds ----------
    if stores:
        kind_pills_html = []
        for s in stores:
            kind = s.get("kind") or "unknown"
            color = STORE_KIND_COLORS.get(kind, "#888")
            ev_count = len(s.get("evidence") or [])
            kind_pills_html.append(
                f'<span class="orm-pill" '
                f'style="border-left: 4px solid {escape(color)};">'
                f'{escape(s.get("name") or s["id"])}'
                f' <span style="color: var(--muted); margin-left: 4px;">'
                f'{ev_count} ref{"s" if ev_count != 1 else ""}</span>'
                f'</span>'
            )
        kinds_body = (
            f'<div class="lineage2-orm-cloud">'
            f'{"".join(kind_pills_html)}'
            f'</div>'
        )
        kinds_foot = (
            '<p class="lineage2-tile-foot">'
            'Each pill is a data store detected somewhere in the codebase '
            '— connection strings in <code>.env</code> files, '
            '<code>docker-compose</code> services, or SDK initialisations. '
            'The number is how many distinct references were found.'
            '</p>'
        )
    else:
        kinds_body = '<p class="lineage2-empty">No data stores detected.</p>'
        kinds_foot = ""

    return f"""
<div class="lineage2-bento">
  <div class="lineage2-tile">
    <div class="tile-label">Fan-in</div>
    <div class="tile-headline">Which services write to each store</div>
    <div class="tile-body">{fan_body}</div>
  </div>
  <div class="lineage2-tile">
    <div class="tile-label">ORM frameworks</div>
    <div class="tile-headline">Used to declare data models</div>
    <div class="tile-body">{orm_body}{orm_foot}</div>
  </div>
  <div class="lineage2-tile">
    <div class="tile-label">Hot models</div>
    <div class="tile-headline">Most-referenced entities</div>
    <div class="tile-body">{hot_body}</div>
  </div>
  <div class="lineage2-tile">
    <div class="tile-label">Detected stores</div>
    <div class="tile-headline">All data stores found in this codebase</div>
    <div class="tile-body">{kinds_body}{kinds_foot}</div>
  </div>
</div>
"""


def render_deps(data: dict[str, Any]) -> str:
    deps = data.get("deps", [])
    if not deps:
        return ""
    blocks = []
    for eco in deps:
        items = "".join(
            f'<div class="dep"><span class="dep-name">{escape(p["name"])}</span>'
            f'<span class="ver">{escape(p.get("version", "*"))}</span></div>'
            for p in eco["packages"]
        )
        blocks.append(f"""
        <div class="deps-eco">
          <div class="title">
            <h3 style="margin: 0;">{escape(eco['ecosystem'].title())} <span style="color: var(--muted); font-weight: 400; font-size: 0.85em;">({fmt_num(eco['count'])})</span></h3>
            <span class="file">{escape(eco['file'])}</span>
          </div>
          <div class="deps-list">{items}</div>
        </div>
        """)
    # A "*" version is our fallback when the manifest pins no version — explain it.
    has_star = any(
        p.get("version", "*") == "*" for eco in deps for p in eco.get("packages", [])
    )
    star_note = (
        '<p class="diagram-note">A version shown as <code>*</code> means the manifest '
        'doesn’t pin one — an unspecified “any version” entry, or a path / git dependency '
        'that carries no version number (not necessarily the latest release).</p>'
        if has_star else ""
    )
    return f"""
<section>
  <h2>External dependencies</h2>
  {section_intro("deps")}
  {star_note}
  {''.join(blocks)}
</section>
"""


def render_entry_points(data: dict[str, Any]) -> str:
    eps = data.get("entry_points", [])
    if not eps:
        return ""
    items = "".join(
        f'<li><span class="path">{escape(e["path"])}</span><span class="kind">{escape(e["kind"])}</span></li>'
        for e in eps
    )
    return f"""
<section>
  <h2>Entry points</h2>
  {section_intro("entries")}
  <ul class="entries">{items}</ul>
</section>
"""


def render_overview(data: dict[str, Any], enrichment: dict[str, Any] | None = None) -> str:
    """Prominent LLM-authored 'what this is' opener. Renders only when
    enrichment is present; otherwise empty (deterministic-only report)."""
    if not enrichment or not enrichment.get("overview"):
        return ""
    ov = enrichment["overview"]
    stack = "".join(
        f'<span class="tag">{escape(s)}</span>' for s in ov.get("primary_stack", [])
    )
    caveat_html = ""
    caveats = ov.get("caveats", [])
    if caveats:
        items = "".join(f"<li>{escape(c)}</li>" for c in caveats)
        caveat_html = (
            f'<div class="overview-caveats"><div class="group-label">Caveats</div>'
            f'<ul>{items}</ul></div>'
        )
    conf = escape(ov.get("confidence", ""))
    return f"""
<section class="overview">
  <h2>What this codebase is</h2>
  <p class="overview-lede">{escape(ov.get('what_it_is', ''))}</p>
  <div class="overview-body">
    <p>{escape(ov.get('what_it_does', ''))}</p>
    <p>{escape(ov.get('how_it_works', ''))}</p>
  </div>
  <div class="overview-stack"><span class="group-label">Stack</span> {stack}</div>
  {caveat_html}
  <p class="overview-conf">Assessed from the source by an LLM · confidence: {conf}</p>
</section>
"""


def render_readme(data: dict[str, Any], enrichment: dict[str, Any] | None = None) -> str:
    r = data.get("readme") or {}
    if not r.get("file"):
        return ""
    first_para = r.get("first_paragraph")
    if not first_para:
        # Without a first paragraph there's nothing meaningful to render;
        # the headings-only chip cloud felt like decontextualized noise.
        return ""
    # When the LLM overview is present, the README is demoted to a small
    # secondary aside. Without enrichment, emit the original markup exactly
    # (byte-identical) so the deterministic report is unchanged.
    if enrichment and enrichment.get("overview"):
        section_open = '<section class="readme-section readme-demoted">'
        heading = "What the README says"
        # The LLM Overview above is now the authoritative summary, so frame
        # the README as secondary (a README is often a roadmap or aspiration
        # rather than a description of what the code actually does).
        intro = ('<p class="section-intro">The author’s own words from the project '
                 'README. Treat this as secondary — the Overview above is derived from '
                 'the code itself, which is the more reliable description.</p>')
    else:
        section_open = "<section>"
        heading = f"From {escape(r['file'])}"
        intro = section_intro("readme")
    return f"""
{section_open}
  <h2>{heading}</h2>
  {intro}
  <blockquote class="readme-quote">{escape(first_para)}</blockquote>
</section>
"""


def render_glossary(data: dict[str, Any], enrichment: dict[str, Any] | None = None) -> str:
    """Render a glossary section that only includes terms relevant to
    this scan (languages detected, ecosystems present, the always-on
    structural terms, and any tools/libraries/services actually mentioned
    in the report's text)."""
    detected_langs = {l["name"] for l in data.get("languages", [])}
    detected_ecos = {d["ecosystem"] for d in data.get("deps", [])}

    lang_entries = sorted(
        (k, v) for k, v in GLOSSARY_LANGUAGES.items()
        if k in detected_langs
    )
    eco_entries = sorted(
        (k, v) for k, v in GLOSSARY_ECOSYSTEMS.items()
        if k in detected_ecos
    )
    # Structural terms always appear — they're referenced in every report.
    term_entries = list(GLOSSARY_TERMS.items())
    # Tools/libraries/services are auto-detected from the report's prose + data.
    tech_entries = glossary_tech_hits(data, enrichment)

    if not (lang_entries or eco_entries or term_entries or tech_entries):
        return ""

    def _group(label: str, entries: list[tuple[str, str]]) -> str:
        if not entries:
            return ""
        items = "".join(
            f"<dt>{escape(name)}</dt><dd>{escape(definition)}</dd>"
            for name, definition in entries
        )
        return f"""
        <div class="glossary-group">
          <div class="group-label">{escape(label)}</div>
          <dl>{items}</dl>
        </div>
        """

    return f"""
<section class="glossary">
  <h2>Glossary</h2>
  <p class="section-intro">Plain-English definitions for the technical terms used above. Only includes entries relevant to what was found in this codebase.</p>
  {_group("Concepts", term_entries)}
  {_group("Tools, libraries & services", tech_entries)}
  {_group("Programming languages", lang_entries)}
  {_group("Package ecosystems", eco_entries)}
</section>
"""


def render_footer(data: dict[str, Any]) -> str:
    return f"""
<footer>
  Generated by <span class="brand">smokeyp-codebase-mapper</span> v{escape(data.get('tool_version', '0.1.0'))}
</footer>
"""


# -------- Key flows (LLM evaluation) -----------------------------------
#
# The flows aren't a connected graph — each is an independent way the system
# gets kicked off. So the section is laid out as a "board" of lanes, one per
# flow KIND (bootstrap / request / scheduled / …), each holding its flows as
# collapsible cards. Per kind: (display label, plain-English meaning, accent).
FLOW_KIND_META: dict[str, tuple[str, str, str]] = {
    "bootstrap":     ("Bootstrap",     "Runs once, when the system starts up.",               "#bb9af7"),
    "request":       ("Request",       "Driven by a user action or an incoming API call.",    "#7aa2f7"),
    "scheduled":     ("Scheduled",     "Kicked off automatically on a timer or schedule.",    "#cc785c"),
    "background":    ("Background",    "Async work run off the main request path.",           "#5fa463"),
    "state-machine": ("State machine", "Moves an entity through a series of defined states.", "#e0af68"),
    "pipeline":      ("Pipeline",      "A multi-stage data transformation, stage to stage.",  "#56b6c2"),
}
DEFAULT_FLOW_KIND: tuple[str, str, str] = ("Flow", "An end-to-end path through the system.", "#9aa0a6")
# Lane display order; kinds not listed fall to the end in discovery order.
FLOW_KIND_ORDER = ["bootstrap", "request", "scheduled", "background", "state-machine", "pipeline"]

def _render_flow_trace(flow: dict[str, Any]) -> str:
    """The expanded detail: narration + a numbered, cited step list.

    Each step carries its own number badge inside its grid row, so the numbers
    stay aligned with their text no matter how tall a step grows (long notes
    wrap freely). The connecting line between badges is a CSS pseudo-element,
    so it survives the no-JS print path. Badge colour comes from the lane via
    --lane-color."""
    rows = []
    for i, s in enumerate(flow.get("steps", [])):
        cite = escape(s.get("file", ""))
        sym = escape(s.get("symbol", ""))
        line = f':{escape(str(s["line"]))}' if s.get("line") else ""
        note = escape(s.get("note", ""))
        note_html = f'<div class="flow-step-note">{note}</div>' if note else ""
        rows.append(
            f'<li class="flow-step">'
            f'<span class="flow-step-num">{i + 1}</span>'
            f'<div class="flow-step-main">'
            f'<div class="flow-step-label">{escape(s.get("label", "") or sym)}</div>'
            f'<div class="flow-step-cite"><code>{cite}{line}</code> · <code>{sym}</code></div>'
            f'{note_html}'
            f'</div>'
            f'</li>'
        )
    narration = escape(flow.get("narration", ""))
    narration_html = f'<p class="flow-narration">{narration}</p>' if narration else ""
    ends = escape(flow.get("terminates", ""))
    ends_html = f'<div class="flow-ends"><strong>Ends:</strong> {ends}</div>' if ends else ""
    return (
        f'{narration_html}'
        f'<ol class="flow-steps">{"".join(rows)}</ol>'
        f'{ends_html}'
    )


def _render_flow_card(flow: dict[str, Any], idx: int) -> str:
    """One collapsible flow: an always-visible summary button (name + a
    'trigger → ends' preview + step count) that expands to the full trace."""
    name = escape(flow.get("name", "") or "Flow")
    trigger = escape(flow.get("trigger", ""))
    ends = escape(flow.get("terminates", ""))
    nsteps = len(flow.get("steps", []))
    rid = f"flow-detail-{idx}"
    oneline = ""
    if trigger or ends:
        arrow = '<span class="flow-arrow">→</span>' if (trigger and ends) else ""
        oneline = f'<div class="flow-oneline">{trigger}{arrow}{ends}</div>'
    return (
        f'<div class="flow-card">'
        f'<button class="flow-summary" type="button" aria-expanded="false" aria-controls="{rid}">'
        f'<span class="flow-caret" aria-hidden="true">▸</span>'
        f'<span class="flow-summary-main"><span class="flow-name">{name}</span>{oneline}</span>'
        f'<span class="flow-stepn">{nsteps} step{"" if nsteps == 1 else "s"}</span>'
        f'</button>'
        f'<div class="flow-detail" id="{rid}">{_render_flow_trace(flow)}</div>'
        f'</div>'
    )


# Expand/collapse behaviour + expand-all/collapse-all. Plain (non-f) string so
# its braces survive; referenced as {FLOWS_JS}. Degrades gracefully: with no JS
# the cards just don't toggle on screen, and the print stylesheet expands them.
FLOWS_JS = """
<script>
(function () {
  var section = document.getElementById('codemap-key-flows');
  if (!section) return;
  function setOpen(card, open) {
    card.classList.toggle('is-open', open);
    var btn = card.querySelector('.flow-summary');
    if (btn) btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  }
  section.querySelectorAll('.flow-summary').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var card = btn.closest('.flow-card');
      setOpen(card, !card.classList.contains('is-open'));
    });
  });
  section.querySelectorAll('.flows-btn[data-flows-action]').forEach(function (b) {
    b.addEventListener('click', function () {
      var open = b.getAttribute('data-flows-action') === 'expand';
      section.querySelectorAll('.flow-card').forEach(function (c) { setOpen(c, open); });
    });
  });
})();
</script>
"""


def render_key_flows(data: dict[str, Any], enrichment: dict[str, Any] | None = None) -> str:
    """Render LLM-derived end-to-end flows as an interactive board, grouped by
    kind into colour-coded lanes. Empty without flows."""
    flows = (enrichment or {}).get("flows") or []
    if not flows:
        return ""

    # Group by kind, preserving original order within each group.
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for f in flows:
        by_kind.setdefault(f.get("kind", ""), []).append(f)
    ordered_kinds = [k for k in FLOW_KIND_ORDER if k in by_kind]
    ordered_kinds += [k for k in by_kind if k not in FLOW_KIND_ORDER]

    idx = 0
    lanes = []
    for kind in ordered_kinds:
        label, meaning, color = FLOW_KIND_META.get(kind, DEFAULT_FLOW_KIND)
        group = by_kind[kind]
        cards = []
        for f in group:
            cards.append(_render_flow_card(f, idx))
            idx += 1
        lanes.append(
            f'<div class="flow-lane" style="--lane-color: {color}">'
            f'<div class="flow-lane-head">'
            f'<div class="flow-lane-kind">{escape(label)} '
            f'<span class="flow-lane-count">· {len(group)}</span></div>'
            f'<div class="flow-lane-meaning">{escape(meaning)}</div>'
            f'</div>'
            f'{"".join(cards)}'
            f'</div>'
        )
    board = "".join(lanes)
    return f"""
<section class="key-flows" id="codemap-key-flows">
  <h2>Key flows</h2>
  {section_intro("flows")}
  <p class="module-note">Each card is one way the system springs into action, grouped by what sets it off — startup, a request, a schedule, or background work. Click any flow to expand its full step-by-step trace.</p>
  <div class="flows-toolbar">
    <button class="flows-btn" type="button" data-flows-action="expand">Expand all</button>
    <button class="flows-btn" type="button" data-flows-action="collapse">Collapse all</button>
  </div>
  <div class="flow-board">{board}</div>
  {FLOWS_JS}
</section>
"""


# -------- page assembly ------------------------------------------------

def render_document(data: dict[str, Any], enrichment: dict[str, Any] | None = None) -> str:
    project_name = escape(data["project"]["name"])
    body = (
        render_cover(data)
        + render_overview(data, enrichment)
        # System map: the orienting big-picture hero. Sits first among the
        # diagrams so the reader sees the whole system before drilling in.
        + render_system_map(data, enrichment)
        + render_readme(data, enrichment)
        + render_languages(data)
        + render_modules(data, enrichment)
        # Module-graph section: dependency-matrix hero + bento.
        + render_module_graph_section(data)
        # Topology section: C4-style hero + bento.
        + render_service_topology_v2(data)
        # Critical paths: a behavioural view that traces each entry-point
        # module from caller → entry → key deps → store. Where the three
        # other diagrams above show structure, this one shows what *happens*
        # when a request flows through. Sits between topology (call graph)
        # and lineage (persistence) because it bridges the two.
        + render_critical_paths_section(data)
        # Key flows: LLM-derived end-to-end stories (renders only with enrichment).
        + render_key_flows(data, enrichment)
        # Lineage section: Sankey hero with cylinder store glyphs + bento.
        + render_data_lineage_v2(data)
        + render_entry_points(data)
        + render_deps(data)
        + render_tree(data)
        + render_glossary(data, enrichment)
        + render_footer(data)
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{project_name} — Codebase Map</title>
<style>{CSS}</style>
</head>
<body>
<main>
{body}
</main>
</body>
</html>
"""


# -------- CLI ----------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Render a codemap HTML report from JSON.")
    parser.add_argument("--in", dest="inp", required=True, help="Path to codemap.json")
    parser.add_argument("--out", required=True, help="Path to output HTML file")
    parser.add_argument("--enrichment", default=None, help="Optional codemap.enrichment.json")
    args = parser.parse_args()

    inp = Path(args.inp).expanduser().resolve()
    if not inp.is_file():
        print(f"error: not a file: {inp}", file=sys.stderr)
        return 2
    try:
        data = json.loads(inp.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"error: invalid JSON in {inp}: {e}", file=sys.stderr)
        return 2

    enrichment = None
    if args.enrichment:
        ep = Path(args.enrichment).expanduser().resolve()
        if ep.is_file():
            try:
                enrichment = json.loads(ep.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                print(f"warning: ignoring invalid enrichment {ep}: {e}", file=sys.stderr)
        else:
            print(f"warning: enrichment not found, rendering without it: {ep}", file=sys.stderr)

    html = render_document(data, enrichment)
    out = Path(args.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"rendered -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
