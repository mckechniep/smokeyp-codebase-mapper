#!/usr/bin/env python3
"""HTML renderer for smokeyp-codebase-mapper.

Reads the JSON data model produced by scan.py and emits a single
self-contained HTML file. No external dependencies, no CDNs.
"""

from __future__ import annotations

import argparse
import json
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
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: var(--space-2) var(--space-4);
  font-family: var(--font-mono);
  font-size: 0.83rem;
}
.deps-list .dep .ver { color: var(--muted); margin-left: 6px; }

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
  max-width: 62ch;
  margin: 0 0 var(--space-5);
}

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

/* ---- Print ---- */
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
  @page { size: Letter; margin: 0.6in; }
}
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
    "languages": "Programming languages are the rules and vocabulary used to write code. "
                 "A codebase usually has one primary language plus several supporting ones "
                 "(configuration files, documentation, build scripts).",
    "modules":  "A module is a self-contained folder of related code that handles one job. "
                "Splitting a codebase into modules lets different people work on different "
                "parts at the same time without stepping on each other.",
    "entries":  "An entry point is the file the program starts running from. Different "
                "languages have different conventions — “main.py” for Python, "
                "“index.js” for JavaScript, “main.go” for Go.",
    "deps":     "Software packages are pre-written, reusable chunks of code published by "
                "other developers. Listing a package as a dependency means this codebase "
                "uses it instead of writing the same functionality from scratch.",
    "tree":     "The directory tree is the physical layout of folders and files on disk. "
                "Folder names usually hint at what lives inside; file names usually hint "
                "at purpose.",
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
}

GLOSSARY_TERMS: dict[str, str] = {
    "Module": "A self-contained folder of related code that handles one responsibility — for example an 'auth' module handles login, a 'billing' module handles payments. Most codebases split work into modules so contributors can focus on one area at a time.",
    "Package": "A piece of reusable code published by someone else that this codebase depends on. Adding a package is faster and safer than re-writing the same code from scratch.",
    "Dependency": "An external package this project needs to run. The dependency listing is essentially the project's shopping list of outside code.",
    "Entry point": "The specific file the program starts running from when launched. Languages have different conventions: Python uses `main.py`, JavaScript uses `index.js`, Go uses `main.go`, Rust uses `main.rs`.",
    "Manifest": "A small file at the project's root that declares its dependencies and metadata. Examples: `package.json`, `requirements.txt`, `Cargo.toml`, `go.mod`.",
    "LOC (Lines of code)": "A rough size indicator — *not* a quality measure. A 100-LOC module isn't necessarily worse than a 1,000-LOC one. Use LOC for orientation, not judgement.",
    "Source root": "A directory holding the main program code, kept separate from configuration, tests, and build artifacts. Common names: `src`, `lib`, `app`, `cmd`, `pkg`.",
}


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
  <strong>New to reading codebase maps?</strong> {REPORT_EXPLAINER}
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
    rows = "".join(
        f"""
        <tr>
          <td><span class="lang-swatch" style="background: {escape(l['color'])};"></span>{escape(l['name'])}</td>
          <td class="mono">{fmt_num(l['files'])}</td>
          <td class="mono">{fmt_num(l['loc'])}</td>
          <td class="mono">{pct(l['loc'], total_loc):.1f}%</td>
        </tr>
        """
        for l in langs
    )
    return f"""
<section>
  <h2>Languages</h2>
  {section_intro("languages")}
  <div class="lang-bar">{bar}</div>
  <table class="lang-table">
    <thead><tr><th>Language</th><th>Files</th><th>Lines</th><th>Share</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
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


def render_modules(data: dict[str, Any]) -> str:
    mods = data.get("modules", [])
    if not mods:
        return ""
    cards = "".join(
        f"""
        <div class="card">
          <div class="head">
            <div class="name">{escape(m['path'])}</div>
            <div class="meta">{fmt_num(m['file_count'])} files · {fmt_num(m['loc'])} LOC</div>
          </div>
          {('<p class="desc">' + escape(m['description']) + '</p>') if m.get('description') else ''}
          <div class="langs">
            {''.join(f'<span class="tag">{escape(l)}</span>' for l in m.get('languages', []))}
          </div>
        </div>
        """
        for m in mods
    )
    return f"""
<section>
  <h2>Top-level modules</h2>
  {section_intro("modules")}
  <div class="card-grid">{cards}</div>
</section>
"""


def render_deps(data: dict[str, Any]) -> str:
    deps = data.get("deps", [])
    if not deps:
        return ""
    blocks = []
    for eco in deps:
        items = "".join(
            f'<div class="dep">{escape(p["name"])}<span class="ver">{escape(p.get("version", "*"))}</span></div>'
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
    return f"""
<section>
  <h2>External dependencies</h2>
  {section_intro("deps")}
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


def render_readme(data: dict[str, Any]) -> str:
    r = data.get("readme") or {}
    if not r.get("file"):
        return ""
    quote = f'<blockquote class="readme-quote">{escape(r["first_paragraph"])}</blockquote>' if r.get("first_paragraph") else ""
    headings = r.get("headings") or []
    h_list = ""
    if headings:
        h_items = "".join(f"<li>{escape(h)}</li>" for h in headings)
        h_list = f'<ul class="readme-headings">{h_items}</ul>'
    return f"""
<section>
  <h2>From {escape(r['file'])}</h2>
  {section_intro("readme")}
  {quote}
  {h_list}
</section>
"""


def render_glossary(data: dict[str, Any]) -> str:
    """Render a glossary section that only includes terms relevant to
    this scan (languages detected, ecosystems present, plus the always-on
    structural terms)."""
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

    if not (lang_entries or eco_entries or term_entries):
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


# -------- page assembly ------------------------------------------------

def render_document(data: dict[str, Any]) -> str:
    project_name = escape(data["project"]["name"])
    body = (
        render_cover(data)
        + render_readme(data)
        + render_languages(data)
        + render_modules(data)
        + render_entry_points(data)
        + render_deps(data)
        + render_tree(data)
        + render_glossary(data)
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

    html = render_document(data)
    out = Path(args.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"rendered -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
