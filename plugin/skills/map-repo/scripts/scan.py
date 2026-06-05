#!/usr/bin/env python3
"""Repository scanner for smokeyp-codebase-mapper.

Walks a target directory and emits a JSON data model describing the
codebase: languages, directory tree, top-level modules, external
dependencies, entry points, and README extract.

Stdlib only. Python 3.10+.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import evidence
# Optional sibling module: when missing (e.g. scan.py deployed standalone),
# extraction falls back to the built-in regexes exactly as when the ast-grep
# binary is absent.
try:
    import astgrep_imports
except ImportError:
    astgrep_imports = None  # type: ignore[assignment]
try:
    import astgrep_handlers
except ImportError:
    astgrep_handlers = None  # type: ignore[assignment]

TOOL_VERSION = "0.7.0"

# Language detection by extension. Color values are the GitHub linguist
# palette so downstream charts feel familiar.
LANGUAGES: dict[str, tuple[str, str]] = {
    ".ts": ("TypeScript", "#3178c6"),
    ".tsx": ("TypeScript", "#3178c6"),
    ".js": ("JavaScript", "#f1e05a"),
    ".jsx": ("JavaScript", "#f1e05a"),
    ".mjs": ("JavaScript", "#f1e05a"),
    ".cjs": ("JavaScript", "#f1e05a"),
    ".py": ("Python", "#3572A5"),
    ".pyi": ("Python", "#3572A5"),
    ".go": ("Go", "#00ADD8"),
    ".rs": ("Rust", "#dea584"),
    ".java": ("Java", "#b07219"),
    ".kt": ("Kotlin", "#A97BFF"),
    ".kts": ("Kotlin", "#A97BFF"),
    ".swift": ("Swift", "#F05138"),
    ".rb": ("Ruby", "#701516"),
    ".ex": ("Elixir", "#6e4a7e"),
    ".exs": ("Elixir", "#6e4a7e"),
    ".php": ("PHP", "#4F5D95"),
    ".c": ("C", "#555555"),
    ".h": ("C", "#555555"),
    ".cpp": ("C++", "#f34b7d"),
    ".cc": ("C++", "#f34b7d"),
    ".hpp": ("C++", "#f34b7d"),
    ".cs": ("C#", "#178600"),
    ".scala": ("Scala", "#c22d40"),
    ".css": ("CSS", "#563d7c"),
    ".scss": ("SCSS", "#c6538c"),
    ".less": ("Less", "#1d365d"),
    ".html": ("HTML", "#e34c26"),
    ".vue": ("Vue", "#41b883"),
    ".svelte": ("Svelte", "#ff3e00"),
    ".md": ("Markdown", "#083fa1"),
    ".mdx": ("MDX", "#fcb32c"),
    ".sh": ("Shell", "#89e051"),
    ".bash": ("Shell", "#89e051"),
    ".zsh": ("Shell", "#89e051"),
    ".sql": ("SQL", "#e38c00"),
    ".yaml": ("YAML", "#cb171e"),
    ".yml": ("YAML", "#cb171e"),
    ".json": ("JSON", "#292929"),
    ".toml": ("TOML", "#9c4221"),
}

# Directories we never descend into.
SKIP_DIRS: frozenset[str] = frozenset({
    ".git", ".hg", ".svn",
    "node_modules", "bower_components",
    ".venv", "venv", "env", ".env",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
    "dist", "build", "out", "target",
    ".next", ".nuxt", ".svelte-kit", ".astro",
    ".cache", ".turbo", ".parcel-cache",
    "coverage", ".nyc_output",
    ".codemap",
    ".idea", ".vscode", ".gradle",
    "vendor",
})

# Conventional source roots — we look here first for top-level modules.
SOURCE_ROOTS: tuple[str, ...] = (
    "src", "lib", "app", "apps", "packages", "cmd",
    "internal", "pkg", "services", "modules",
)

# -------- vendored-code heuristics --------------------------------------
#
# Deterministic counterpart of the SKILL.md Step 1.5 prose rules: modules
# that look like copied-in third-party code get vendored_guess=True. The
# LLM enrichment can override in BOTH directions at render time
# (classification.products rescues false positives; classification.vendored
# catches what these heuristics miss).

VENDORED_DIR_SUFFIXES: tuple[str, ...] = ("-master", "-develop", "-main")
# Conventional vendor dirs (vendor/, node_modules/) are already excluded upstream
# by SKIP_DIRS before _vendored_guess is ever called, so this set only needs the
# path segments SKIP_DIRS doesn't catch.
# NOTE: "external" was deliberately excluded — DDD / layered architectures commonly
# use external/ as an architectural layer (external-facing APIs, integrations), not
# as vendored code. False-positive risk is too high.
VENDORED_PATH_SEGMENTS: frozenset[str] = frozenset({
    "third_party", "third-party", "extern",
})


def _vendored_guess(module_dir: Path, rel_path: str, root_name: str) -> bool:
    """Heuristic: does this module look like vendored third-party code?

    Checks, cheapest first:
      1. A conventional vendor directory segment anywhere in the path.
      2. A git-archive clone suffix (-master/-develop/-main) on any segment.
      3. A package.json whose repository URL doesn't reference this repo.
    """
    parts = [p.lower() for p in Path(rel_path).parts]
    if any(p in VENDORED_PATH_SEGMENTS for p in parts):
        return True
    if any(p.endswith(VENDORED_DIR_SUFFIXES) for p in parts):
        return True
    pkg = module_dir / "package.json"
    if pkg.is_file():
        try:
            meta = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError):
            return False
        if isinstance(meta, dict):
            repo = meta.get("repository")
            if isinstance(repo, dict):
                repo = repo.get("url") or ""
            if isinstance(repo, str) and repo.strip():
                if root_name.lower() not in repo.lower():
                    return True
    return False


# Files that signal a project entry point.
ENTRY_PATTERNS: tuple[tuple[str, str], ...] = (
    ("main.py", "Python main"),
    ("__main__.py", "Python module entry"),
    ("app.py", "Python app"),
    ("manage.py", "Django manage"),
    ("index.ts", "TypeScript module entry"),
    ("index.tsx", "TypeScript React entry"),
    ("index.js", "JavaScript module entry"),
    ("index.jsx", "JavaScript React entry"),
    ("index.mjs", "JavaScript ESM entry"),
    ("server.ts", "TypeScript server"),
    ("server.js", "JavaScript server"),
    ("main.go", "Go main"),
    ("main.rs", "Rust main"),
    ("lib.rs", "Rust library"),
    ("Cargo.toml", "Rust crate root"),
    ("Makefile", "Make build"),
    ("Dockerfile", "Container build"),
    ("docker-compose.yml", "Docker Compose"),
    ("docker-compose.yaml", "Docker Compose"),
)

# Manifest files we parse for external dependencies.
DEP_MANIFESTS: tuple[tuple[str, str], ...] = (
    ("package.json", "npm"),
    ("requirements.txt", "pip"),
    ("requirements.in", "pip"),
    ("pyproject.toml", "python"),
    ("Pipfile", "pipenv"),
    ("go.mod", "go"),
    ("Cargo.toml", "cargo"),
    ("Gemfile", "bundler"),
    ("composer.json", "composer"),
    ("pom.xml", "maven"),
    ("build.gradle", "gradle"),
    ("build.gradle.kts", "gradle"),
    ("mix.exs", "hex"),
)

# Max bytes we'll read from any single file for LOC counting.
# Anything larger we count as "1 line" to keep memory bounded.
MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MiB


def is_binary(path: Path) -> bool:
    """Cheap heuristic: read first 1KB, declare binary if null byte present."""
    try:
        with path.open("rb") as f:
            chunk = f.read(1024)
        return b"\x00" in chunk
    except OSError:
        return True


def count_lines(path: Path) -> int:
    """Count newlines in a file with bounded memory."""
    try:
        size = path.stat().st_size
    except OSError:
        return 0
    if size == 0:
        return 0
    if size > MAX_FILE_BYTES:
        return 1
    try:
        with path.open("rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def detect_language(path: Path) -> tuple[str, str] | None:
    """Return (language_name, color) or None for unrecognized."""
    if path.name == "Dockerfile":
        return ("Dockerfile", "#384d54")
    if path.name == "Makefile":
        return ("Makefile", "#427819")
    return LANGUAGES.get(path.suffix.lower())


def walk_tree(root: Path, max_depth: int | None) -> dict[str, Any]:
    """Build the nested directory tree.

    max_depth=None means unlimited.
    Returns a node with file_count/loc rolled up from descendants.
    """
    def _walk(node_path: Path, depth: int) -> dict[str, Any]:
        node: dict[str, Any] = {
            "name": node_path.name or str(node_path),
            "type": "dir",
            "file_count": 0,
            "loc": 0,
        }

        if max_depth is not None and depth >= max_depth:
            # Truncate but still roll up the counts from below.
            for child in iter_files(node_path):
                node["file_count"] += 1
                node["loc"] += count_lines(child) if not is_binary(child) else 0
            node["truncated"] = True
            return node

        children: list[dict[str, Any]] = []
        try:
            entries = sorted(node_path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except OSError:
            return node

        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name in SKIP_DIRS or entry.name.startswith("."):
                    if entry.name not in (".github",):
                        continue
                child_node = _walk(entry, depth + 1)
                if child_node["file_count"] > 0:
                    children.append(child_node)
                    node["file_count"] += child_node["file_count"]
                    node["loc"] += child_node["loc"]
            elif entry.is_file():
                lang = detect_language(entry)
                loc = count_lines(entry) if not is_binary(entry) else 0
                children.append({
                    "name": entry.name,
                    "type": "file",
                    "language": lang[0] if lang else None,
                    "loc": loc,
                })
                node["file_count"] += 1
                node["loc"] += loc
        node["children"] = children
        return node

    return _walk(root, 0)


def iter_files(root: Path):
    """Yield all non-binary files under root, honoring skip rules."""
    for entry in root.rglob("*"):
        if entry.is_symlink():
            continue
        if not entry.is_file():
            continue
        if any(part in SKIP_DIRS for part in entry.parts):
            continue
        if any(part.startswith(".") and part not in (".github",)
               for part in entry.relative_to(root).parts[:-1]):
            continue
        yield entry


def aggregate_languages(root: Path) -> list[dict[str, Any]]:
    """Roll up file count + LOC per language."""
    totals: dict[str, dict[str, Any]] = {}
    for f in iter_files(root):
        lang = detect_language(f)
        if not lang:
            continue
        name, color = lang
        if is_binary(f):
            continue
        loc = count_lines(f)
        bucket = totals.setdefault(name, {"name": name, "color": color, "files": 0, "loc": 0})
        bucket["files"] += 1
        bucket["loc"] += loc
    return sorted(totals.values(), key=lambda b: b["loc"], reverse=True)


# -------- Service / container detection (monorepo-aware) ------------

# Files that mark a directory as its own packaged service/app/library —
# i.e. it has its own dependency manifest, so it's a self-contained unit
# of code even if it lives inside a larger repo.
SERVICE_MANIFESTS: tuple[str, ...] = (
    "package.json", "pyproject.toml", "requirements.txt", "setup.py",
    "Pipfile", "go.mod", "Cargo.toml", "Gemfile", "composer.json",
    "pom.xml", "build.gradle", "build.gradle.kts", "build.sbt",
    "mix.exs", "stack.yaml", "deno.json",
)

# Detection heuristics for "what kind of service is this?" — used to
# style the topology diagram. The intent is "what would you call this if
# someone asked, in one word." Frontend, backend, library, or just a
# generic service when we can't tell.
FRONTEND_FRAMEWORK_HINTS: tuple[str, ...] = (
    "react", "react-dom", "react-native", "expo", "next", "remix",
    "vue", "nuxt", "@vue/", "svelte", "@sveltejs/", "astro",
    "@angular/", "preact", "solid-js", "qwik",
    "vite", "webpack",  # build tools that strongly imply frontend
)
BACKEND_FRAMEWORK_HINTS: tuple[str, ...] = (
    # JS/TS backends
    "@nestjs/", "express", "fastify", "koa", "hono", "@hapi/",
    # Python backends
    "fastapi", "flask", "django", "starlette", "aiohttp", "tornado",
    "bottle", "sanic", "quart", "litestar",
    # Go backends (detected from go.mod)
    "github.com/gin-gonic/gin", "github.com/labstack/echo", "github.com/go-chi/chi",
    "github.com/gorilla/mux", "github.com/gofiber/fiber",
    # Ruby
    "rails", "sinatra",
    # PHP
    "laravel/", "symfony/",
    # Java
    "org.springframework.boot", "io.quarkus", "io.micronaut",
)


def _read_manifest_text(container: Path) -> tuple[str, str] | None:
    """Return (manifest_filename, full_text) for the first manifest found, or None."""
    for name in SERVICE_MANIFESTS:
        p = container / name
        if p.is_file():
            return (name, safe_read(p, limit=64 * 1024))
    return None


def _classify_service(container: Path) -> tuple[str, list[str]]:
    """Return (kind, stack[]) for a service container.

    kind ∈ {'frontend', 'backend', 'library', 'service', 'unknown'}
    stack is a deduped, sorted list of detected framework hints.
    """
    manifest = _read_manifest_text(container)
    if not manifest:
        return ("unknown", [])
    _name, text = manifest
    lower = text.lower()
    found_frontend: list[str] = []
    found_backend: list[str] = []
    for hint in FRONTEND_FRAMEWORK_HINTS:
        if hint.lower() in lower:
            found_frontend.append(hint)
    for hint in BACKEND_FRAMEWORK_HINTS:
        if hint.lower() in lower:
            found_backend.append(hint)
    stack = sorted(set(found_frontend + found_backend))

    if found_backend and not found_frontend:
        return ("backend", stack)
    if found_frontend and not found_backend:
        # Build-tool-only matches (vite/webpack) without an actual framework
        # are weak signals; classify as 'frontend' anyway, the user can
        # override visually if it's wrong.
        return ("frontend", stack)
    if found_frontend and found_backend:
        # Full-stack framework (Next.js + API routes etc.) — call it backend
        # since the topology diagram cares about whether it serves endpoints.
        return ("backend", stack)
    # Has a manifest but no framework hits → probably a library or shared package
    return ("library", stack)


def _is_service_container(dir_path: Path) -> bool:
    """A 'service container' is a dir worth descending into for module
    detection. Either it has a manifest, or it has at least one
    conventional source root child (src/, app/, lib/, packages/, modules/)."""
    if any((dir_path / m).is_file() for m in SERVICE_MANIFESTS):
        return True
    for sr in SOURCE_ROOTS:
        if (dir_path / sr).is_dir():
            return True
    return False


def _measure_dir(d: Path) -> tuple[int, int, set[str]]:
    """Roll up file_count, loc, and language set under a directory."""
    fc = 0
    loc = 0
    langs: set[str] = set()
    for f in iter_files(d):
        if is_binary(f):
            continue
        fc += 1
        loc += count_lines(f)
        lang = detect_language(f)
        if lang:
            langs.add(lang[0])
    return (fc, loc, langs)


def _modules_within(container: Path, root: Path, service_id: str | None) -> list[dict[str, Any]]:
    """Return the visible modules inside a container.

    A 'visible module' is the next folder-level unit a contributor would
    pick to work on. Algorithm:
      1. If `container` has any conventional source-root child
         (src/, app/, lib/, packages/, modules/, internal/, ...) we
         descend through it.
      2. When we iterate a parent's children, any child that is *itself*
         named like a source root is descended through recursively
         instead of being treated as one module. This handles common
         shapes like `src/modules/<feature>`, `apps/<app>/src/<module>`,
         `packages/<pkg>/src/<feature>`, where the nesting carries no
         architectural meaning.
      3. Otherwise each child directory becomes one module.
    """
    seen: set[Path] = set()
    out: list[dict[str, Any]] = []

    def emit_module(d: Path) -> None:
        if d in seen:
            return
        seen.add(d)
        fc, loc, langs = _measure_dir(d)
        if fc == 0:
            return
        out.append({
            "path": str(d.relative_to(root)),
            "name": d.name,
            "service": service_id,
            "file_count": fc,
            "loc": loc,
            "languages": sorted(langs),
            "description": guess_module_description(d),
            "vendored_guess": _vendored_guess(d, str(d.relative_to(root)), root.name),
        })

    def descend(parent: Path, depth_remaining: int) -> None:
        try:
            entries = sorted(parent.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            return
        for entry in entries:
            if not entry.is_dir():
                continue
            if entry.name in SKIP_DIRS or entry.name.startswith("."):
                continue
            # If this child is itself a "container-shaped" name AND we
            # haven't exhausted the recursion budget, drill through it
            # instead of treating it as one module.
            if depth_remaining > 0 and entry.name in SOURCE_ROOTS:
                descend(entry, depth_remaining - 1)
            else:
                emit_module(entry)

    # Find source-root children to seed from. If none, treat container itself
    # as the parent (Expo-style flat repos: components/, services/, etc. live
    # directly at the container root).
    seeded = False
    for sr in SOURCE_ROOTS:
        sub = container / sr
        if sub.is_dir():
            # Allow up to 2 levels of nested source-root descent
            # (e.g. apps/<app>/src/<module> in pnpm-style monorepos).
            descend(sub, depth_remaining=2)
            seeded = True
    if not seeded:
        descend(container, depth_remaining=2)

    return out


def detect_services_and_modules(
    root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Detect services (monorepo apps) and modules (units of code inside them).

    Returns (services, modules). The pair is computed together because
    they share traversal logic and one informs the other.

    Strategy:
      1. Look at root's direct children. Any dir that has its own manifest
         or its own conventional source root is a 'service container'.
      2. If we found >=1 service container, the repo is treated as
         multi-service (monorepo). Each container's internal modules are
         detected and tagged with that container as `service`.
      3. Top-level dirs that aren't containers but have code (e.g. `docs`,
         `scripts`, `analysis`) are also kept as plain modules at the
         repo root (no service tag).
      4. If we found ZERO service containers AND the root itself has a
         manifest or a source root, treat the root as a single service
         and use the same `_modules_within` logic against it.
      5. If neither: single-service repo, treat root as the service.
    """
    services: list[dict[str, Any]] = []
    modules: list[dict[str, Any]] = []

    # Pass 1: discover root-level containers.
    container_dirs: list[Path] = []
    loose_dirs: list[Path] = []
    try:
        entries = sorted(root.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        entries = []
    for entry in entries:
        if not entry.is_dir():
            continue
        if entry.name in SKIP_DIRS or entry.name.startswith("."):
            if entry.name not in (".github",):
                continue
        if _is_service_container(entry):
            container_dirs.append(entry)
        else:
            loose_dirs.append(entry)

    # Pass 2: build services
    if container_dirs:
        # Monorepo case.
        for container in container_dirs:
            service_id = str(container.relative_to(root))
            kind, stack = _classify_service(container)
            fc, loc, langs = _measure_dir(container)
            if fc == 0:
                continue
            primary_lang_name = None
            primary_color = None
            # Determine primary language by re-measuring per-language (small extra cost)
            by_lang: dict[str, tuple[str, int]] = {}
            for f in iter_files(container):
                lang = detect_language(f)
                if not lang or is_binary(f):
                    continue
                lname, lcolor = lang
                prev = by_lang.get(lname, (lcolor, 0))
                by_lang[lname] = (lcolor, prev[1] + count_lines(f))
            if by_lang:
                primary_lang_name, (primary_color, _) = max(
                    by_lang.items(), key=lambda kv: kv[1][1]
                )
            services.append({
                "id": service_id,
                "name": container.name,
                "kind": kind,
                "stack": stack,
                "file_count": fc,
                "loc": loc,
                "primary_language": primary_lang_name,
                "color": primary_color or "#888888",
                "description": guess_module_description(container),
            })
            sub = _modules_within(container, root, service_id)
            if sub:
                modules.extend(sub)
            else:
                # Service container with no internal structure (flat repo or
                # leaf service): emit the container itself as its own module so
                # it remains visible in the module layer and graph.
                modules.append({
                    "path": service_id,
                    "name": container.name,
                    "service": service_id,
                    "file_count": fc,
                    "loc": loc,
                    "languages": sorted(langs),
                    "description": guess_module_description(container),
                    "vendored_guess": _vendored_guess(
                        container, service_id, root.name
                    ),
                })

        # Loose top-level dirs (docs/, scripts/, analysis/, etc.) — also
        # appear as modules so they're not invisible, but they don't get
        # a service. Source-root-named loose dirs (apps/, packages/, src/,
        # etc.) are recursed with _modules_within so their children become
        # individual modules; other loose dirs are emitted as flat entries.
        for loose in loose_dirs:
            fc, loc, langs = _measure_dir(loose)
            if fc == 0:
                continue
            if loose.name in SOURCE_ROOTS:
                sub = _modules_within(loose, root, None)
                if sub:
                    modules.extend(sub)
                    continue
            modules.append({
                "path": str(loose.relative_to(root)),
                "name": loose.name,
                "service": None,
                "file_count": fc,
                "loc": loc,
                "languages": sorted(langs),
                "description": guess_module_description(loose),
                "vendored_guess": _vendored_guess(loose, str(loose.relative_to(root)), root.name),
            })
    else:
        # Single-service repo. Root itself is the service.
        service_id = root.name or "."
        kind, stack = _classify_service(root)
        fc, loc, _ = _measure_dir(root)
        by_lang: dict[str, tuple[str, int]] = {}
        for f in iter_files(root):
            lang = detect_language(f)
            if not lang or is_binary(f):
                continue
            lname, lcolor = lang
            prev = by_lang.get(lname, (lcolor, 0))
            by_lang[lname] = (lcolor, prev[1] + count_lines(f))
        primary_lang_name = None
        primary_color = None
        if by_lang:
            primary_lang_name, (primary_color, _) = max(
                by_lang.items(), key=lambda kv: kv[1][1]
            )
        services.append({
            "id": service_id,
            "name": root.name,
            "kind": kind,
            "stack": stack,
            "file_count": fc,
            "loc": loc,
            "primary_language": primary_lang_name,
            "color": primary_color or "#888888",
            "description": None,  # root's README extract is shown separately
        })
        modules.extend(_modules_within(root, root, service_id))

    # Sort modules globally by LOC for downstream consumers that truncate.
    modules.sort(key=lambda m: m["loc"], reverse=True)
    services.sort(key=lambda s: s["loc"], reverse=True)
    return services, modules


def detect_modules(root: Path, max_modules: int | None) -> list[dict[str, Any]]:
    """Backwards-compatible wrapper. Returns the module list only.

    Most call sites just want modules; service info is consumed in
    build_data_model directly via detect_services_and_modules().
    """
    _services, modules = detect_services_and_modules(root)
    if max_modules is not None:
        modules = modules[:max_modules]
    return modules


def guess_module_description(module_root: Path) -> str | None:
    """Best-effort module description.

    Preference order: package.json "description" (curated, single line) >
    module README first prose paragraph > Python __init__.py docstring.
    package.json is checked first for JS/TS packages because their READMEs
    routinely open with a shields.io badge row rather than a real
    sentence; the curated manifest description is more reliable."""
    # package.json description — curated and reliable for JS/TS packages.
    pj = module_root / "package.json"
    if pj.is_file():
        try:
            data = json.loads(pj.read_text(encoding="utf-8", errors="replace"))
            if isinstance(data, dict) and data.get("description"):
                desc = str(data["description"]).strip()
                if desc:
                    return desc
        except (json.JSONDecodeError, OSError):
            pass
    # Module-local README — first prose paragraph (badges/links filtered).
    for readme_name in ("README.md", "readme.md", "README"):
        rp = module_root / readme_name
        if rp.is_file():
            text = safe_read(rp, limit=4096)
            if text:
                para = first_paragraph(text)
                if para:
                    return para
    # Python __init__.py docstring.
    init = module_root / "__init__.py"
    if init.is_file():
        text = safe_read(init, limit=2048)
        if text:
            m = re.search(r'^"""(.+?)"""', text, flags=re.DOTALL | re.MULTILINE)
            if m:
                para = first_paragraph(m.group(1).strip())
                if para:
                    return para
    return None


def safe_read(path: Path, limit: int = 65536) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except OSError:
        return ""


# Markdown/HTML noise that is never a real description line.
_BADGE_RE = re.compile(r"\[!\[")               # [![alt][ref]] / [![alt](src)] badge
_LINKREF_RE = re.compile(r"^\[[^\]]+\]:\s*\S+")  # [ref]: https://...  link definition
_HTML_TAG_RE = re.compile(r"^<[^>]+>")          # <p align=...>, <div>, <img ...>, <a ...>
_HTML_COMMENT_RE = re.compile(r"^<!--")         # <!-- comment -->
_IMAGE_RE = re.compile(r"^!\[")                 # ![alt](src) bare image
_URL_RE = re.compile(r"https?://\S+")


def _looks_like_prose(line: str) -> bool:
    """True if a line reads like a sentence rather than markup/badges/links."""
    s = line.strip()
    if not s:
        return False
    if (
        s.startswith("#")
        or _BADGE_RE.search(s)
        or _LINKREF_RE.match(s)
        or _HTML_TAG_RE.match(s)
        or _HTML_COMMENT_RE.match(s)
        or _IMAGE_RE.match(s)
    ):
        return False
    # Strip links/images, inline code, emphasis, and URLs, then require that
    # real letters dominate what remains — i.e. it's a sentence, not a
    # cluster of brackets and links.
    cleaned = _URL_RE.sub("", s)
    cleaned = re.sub(r"!?\[[^\]]*\]\([^)]*\)", "", cleaned)  # [text](url) / ![alt](src)
    cleaned = re.sub(r"!?\[[^\]]*\]\[[^\]]*\]", "", cleaned)  # [text][ref]
    cleaned = cleaned.replace("`", "").replace("*", "").replace("_", "")
    letters = sum(c.isalpha() for c in cleaned)
    return letters >= 12  # at least a few real words


def first_paragraph(text: str) -> str:
    """Return the first paragraph that reads like prose.

    Skips headings, shields.io badge rows, link-reference definitions,
    HTML wrappers (e.g. <p align="center">), and bare image lines — the
    markup that commonly opens an OSS README before any real sentence."""
    paragraphs = re.split(r"\n\s*\n", text.strip())
    for p in paragraphs:
        # A paragraph may mix a badge/logo line with a real sentence; keep
        # only the prose lines within it.
        prose_lines = [ln for ln in p.splitlines() if _looks_like_prose(ln)]
        if prose_lines:
            joined = " ".join(prose_lines)
            return re.sub(r"\s+", " ", joined).strip()[:500]
    return ""


def find_dependencies(root: Path, max_per_ecosystem: int | None) -> list[dict[str, Any]]:
    """Discover manifest files anywhere under root and aggregate per ecosystem.

    Monorepos keep manifests in subdirectories (apps/api/package.json, a backend
    mix.exs, services/*/pyproject.toml, …), so we walk the whole tree via
    iter_files (which honours SKIP_DIRS, so node_modules etc. are excluded)
    rather than only checking the repo root. All manifests of one ecosystem
    collapse into a single entry with merged, deduped packages."""
    manifest_map = dict(DEP_MANIFESTS)
    # ecosystem -> {"basenames": [...], "rel_files": [...], "packages": {name: version}}
    buckets: dict[str, dict[str, Any]] = {}
    for f in iter_files(root):
        ecosystem = manifest_map.get(f.name)
        if ecosystem is None:
            continue
        b = buckets.setdefault(
            ecosystem, {"basenames": [], "rel_files": [], "packages": {}})
        b["basenames"].append(f.name)
        b["rel_files"].append(str(f.relative_to(root)))
        for pkg in parse_manifest(f, ecosystem):
            # Dedupe by name; keep the first non-"*" version we encounter.
            existing = b["packages"].get(pkg["name"])
            if existing is None or existing == "*":
                b["packages"][pkg["name"]] = pkg["version"]

    deps: list[dict[str, Any]] = []
    for ecosystem, b in buckets.items():
        packages = [{"name": n, "version": v}
                    for n, v in sorted(b["packages"].items())]
        if not packages:
            continue
        if max_per_ecosystem is not None:
            packages = packages[:max_per_ecosystem]
        rel_files = b["rel_files"]
        if len(rel_files) == 1:
            file_label = rel_files[0]
        else:
            file_label = f"{b['basenames'][0]} ×{len(rel_files)}"
        deps.append({
            "ecosystem": ecosystem,
            "file": file_label,
            "count": len(packages),
            "packages": packages,
        })
    return sorted(deps, key=lambda e: e["ecosystem"])


def parse_manifest(path: Path, ecosystem: str) -> list[dict[str, str]]:
    """Lightweight, best-effort manifest parsing. Stdlib only."""
    text = safe_read(path, limit=512 * 1024)
    if not text:
        return []
    name = path.name
    try:
        if name == "package.json":
            data = json.loads(text)
            pkgs: list[dict[str, str]] = []
            for key in ("dependencies", "peerDependencies"):
                for n, v in (data.get(key) or {}).items():
                    pkgs.append({"name": n, "version": str(v)})
            return pkgs
        if name == "composer.json":
            data = json.loads(text)
            return [{"name": n, "version": str(v)}
                    for n, v in (data.get("require") or {}).items()
                    if n != "php"]
        if name in ("requirements.txt", "requirements.in"):
            out: list[dict[str, str]] = []
            for line in text.splitlines():
                line = line.split("#", 1)[0].strip()
                if not line or line.startswith("-"):
                    continue
                m = re.match(r"^([A-Za-z0-9_.\-]+)\s*([<>=!~][^;]*)?", line)
                if m:
                    out.append({"name": m.group(1), "version": (m.group(2) or "").strip() or "*"})
            return out
        if name == "pyproject.toml":
            # Crude TOML scan — pull [project] dependencies and [tool.poetry.dependencies]
            out: list[dict[str, str]] = []
            for m in re.finditer(r'"([A-Za-z0-9_.\-]+)\s*([<>=!~][^"]*)?"', text):
                if m.group(1).lower() in {"python"}:
                    continue
                out.append({"name": m.group(1), "version": (m.group(2) or "*").strip()})
            # Deduplicate while preserving order
            seen: set[str] = set()
            dedup: list[dict[str, str]] = []
            for p in out:
                if p["name"] in seen:
                    continue
                seen.add(p["name"])
                dedup.append(p)
            return dedup
        if name == "Pipfile":
            out = []
            for line in text.splitlines():
                m = re.match(r'^([A-Za-z0-9_.\-]+)\s*=\s*"([^"]+)"', line)
                if m:
                    out.append({"name": m.group(1), "version": m.group(2)})
            return out
        if name == "go.mod":
            out = []
            in_block = False
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("require ("):
                    in_block = True
                    continue
                if in_block and line == ")":
                    in_block = False
                    continue
                if in_block or line.startswith("require "):
                    parts = line.replace("require ", "").split()
                    if len(parts) >= 2:
                        out.append({"name": parts[0], "version": parts[1]})
            return out
        if name == "Cargo.toml":
            out = []
            section = None
            for line in text.splitlines():
                s = line.strip()
                if s.startswith("["):
                    section = s
                    continue
                if section in ("[dependencies]", "[dev-dependencies]", "[build-dependencies]"):
                    m = re.match(r'^([A-Za-z0-9_\-]+)\s*=\s*(.+)$', s)
                    if m:
                        v = m.group(2)
                        ver_match = re.search(r'"([^"]+)"', v)
                        out.append({"name": m.group(1), "version": ver_match.group(1) if ver_match else v})
            return out
        if name == "Gemfile":
            return [{"name": m.group(1), "version": m.group(2) or "*"}
                    for m in re.finditer(r"gem\s+['\"]([^'\"]+)['\"](?:\s*,\s*['\"]([^'\"]+)['\"])?", text)]
        if name == "mix.exs":
            # Pull {:name, ...} tuples from the deps function block. The version
            # is the first string literal in the tuple (e.g. "~> 1.7"); path:/
            # github:/git: deps carry a path/URL string instead, so those fall
            # back to "*".
            m = re.search(r'\bdef(?:p)?\s+deps\b.*?\bdo\b(.*?)\bend\b',
                          text, flags=re.DOTALL)
            block = m.group(1) if m else text
            out = []
            for tm in re.finditer(r'\{\s*:([A-Za-z_]\w*)\s*,(.*?)\}',
                                  block, flags=re.DOTALL):
                rest = tm.group(2)
                vm = re.search(r'"([^"]+)"', rest)
                if vm and not re.search(
                        r'\b(path|github|git|branch|tag|ref|organization|hex)\s*:\s*$',
                        rest[:vm.start()].rstrip()):
                    version = vm.group(1)
                else:
                    version = "*"
                out.append({"name": tm.group(1), "version": version})
            return out
        if name == "pom.xml":
            return [{"name": f"{g.group(1)}:{g.group(2)}", "version": g.group(3) or "*"}
                    for g in re.finditer(r"<groupId>([^<]+)</groupId>\s*<artifactId>([^<]+)</artifactId>(?:\s*<version>([^<]+)</version>)?", text)]
        if name in ("build.gradle", "build.gradle.kts"):
            return [{"name": m.group(1), "version": m.group(2)}
                    for m in re.finditer(r"['\"]([a-zA-Z0-9_.\-]+:[a-zA-Z0-9_.\-]+):([^'\"]+)['\"]", text)]
    except (json.JSONDecodeError, OSError, AttributeError):
        return []
    return []


def detect_entry_points(root: Path) -> list[dict[str, str]]:
    """Find conventional entry-point files at root or in obvious places."""
    found: list[dict[str, str]] = []
    seen: set[Path] = set()

    # Direct hits at the root
    for name, kind in ENTRY_PATTERNS:
        for candidate in (root / name, root / "src" / name, root / "cmd" / name):
            if candidate.is_file() and candidate not in seen:
                seen.add(candidate)
                found.append({
                    "path": str(candidate.relative_to(root)),
                    "kind": kind,
                })

    # bin/ scripts
    bin_dir = root / "bin"
    if bin_dir.is_dir():
        for entry in sorted(bin_dir.iterdir()):
            if entry.is_file() and entry not in seen:
                seen.add(entry)
                found.append({
                    "path": str(entry.relative_to(root)),
                    "kind": "CLI script",
                })

    # cmd/<service>/main.go style (Go convention)
    cmd_dir = root / "cmd"
    if cmd_dir.is_dir():
        for sub in sorted(cmd_dir.iterdir()):
            if sub.is_dir():
                main_go = sub / "main.go"
                if main_go.is_file() and main_go not in seen:
                    seen.add(main_go)
                    found.append({
                        "path": str(main_go.relative_to(root)),
                        "kind": f"Go service: {sub.name}",
                    })

    return found


def extract_readme(root: Path) -> dict[str, Any]:
    """Pull the first paragraph and headings from the project README."""
    for name in ("README.md", "readme.md", "README.MD", "Readme.md", "README"):
        rp = root / name
        if rp.is_file():
            text = safe_read(rp, limit=128 * 1024)
            headings = [m.group(2).strip()
                        for m in re.finditer(r"^(#{1,3})\s+(.+)$", text, flags=re.MULTILINE)]
            return {
                "file": name,
                "first_paragraph": first_paragraph(text),
                "headings": headings[:25],
            }
    return {"file": None, "first_paragraph": "", "headings": []}


# -------- Module-level import graph -----------------------------------
#
# We aggregate file-level imports up to module-level edges. The reason: a
# repo has thousands of files but ~10-30 top-level modules. A file graph
# is unreadable spaghetti; a module graph is the architecture diagram you
# actually want. Edge weight = count of file-level imports rolled up.

GRAPH_LANGUAGES: frozenset[str] = frozenset({"Python", "JavaScript", "TypeScript", "Go", "Elixir"})

PY_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+(\.{0,2})([\w.]*)\s+import|import\s+([\w.]+))",
    re.MULTILINE,
)

JSTS_IMPORT_RE = re.compile(
    r"""(?:
        \bimport\s+(?:[^"';]*?\s+from\s+)?["']([^"']+)["']
      | \bexport\s+[^"';]*?\s+from\s+["']([^"']+)["']
      | \brequire\s*\(\s*["']([^"']+)["']\s*\)
      | \bimport\s*\(\s*["']([^"']+)["']\s*\)
    )""",
    re.MULTILINE | re.VERBOSE,
)

GO_IMPORT_SINGLE_RE = re.compile(
    r'^\s*import\s+(?:[a-zA-Z_]\w*\s+)?"([^"]+)"', re.MULTILINE
)
GO_IMPORT_BLOCK_RE = re.compile(r'^\s*import\s*\(\s*([\s\S]*?)\)', re.MULTILINE)
GO_IMPORT_LINE_RE = re.compile(r'(?:[a-zA-Z_]\w*\s+)?"([^"]+)"')


def _read_go_module_prefix(root: Path) -> str | None:
    """Return the module path declared in go.mod, e.g. 'github.com/x/y'."""
    gomod = root / "go.mod"
    if not gomod.is_file():
        return None
    text = safe_read(gomod, limit=4096)
    if not text:
        return None
    m = re.search(r"^\s*module\s+(\S+)", text, re.MULTILINE)
    return m.group(1) if m else None


def _build_module_index(modules: list[dict[str, Any]], root: Path) -> list[tuple[Path, str]]:
    """Sorted list of (abs_path, module_id) — longest path first.

    Used for longest-prefix file→module lookup.
    """
    out: list[tuple[Path, str]] = []
    for m in modules:
        abs_path = (root / m["path"]).resolve()
        out.append((abs_path, m["path"]))
    out.sort(key=lambda t: len(t[0].parts), reverse=True)
    return out


def _module_for(file_path: Path, index: list[tuple[Path, str]]) -> str | None:
    try:
        fp = file_path.resolve()
    except (OSError, RuntimeError):
        return None
    for abs_path, mid in index:
        try:
            fp.relative_to(abs_path)
            return mid
        except ValueError:
            continue
    return None


def _python_import_targets(text: str) -> list[str]:
    """First-segment package names from `import X` / `from X import ...`."""
    targets: list[str] = []
    for m in PY_IMPORT_RE.finditer(text):
        dots, frommod, plainmod = m.group(1), m.group(2), m.group(3)
        if dots:
            # Relative — stays within own package, would just be a self-loop.
            continue
        modpath = frommod or plainmod or ""
        if not modpath:
            continue
        first = modpath.split(".")[0]
        if first:
            targets.append(first)
    return targets


def _jsts_import_targets(file_path: Path, text: str) -> tuple[list[Path], list[str]]:
    """Split a file's imports into (resolved relative/absolute paths,
    bare specifiers).

    Relative/absolute imports resolve to filesystem paths. Bare specifiers
    (e.g. `lodash`, `@scope/pkg`) are returned raw so the caller can decide
    whether they resolve to a workspace package (internal) or an external
    npm dependency.
    """
    parent = file_path.parent
    paths: list[Path] = []
    bare: list[str] = []
    for m in JSTS_IMPORT_RE.finditer(text):
        spec = next((g for g in m.groups() if g), None)
        if not spec:
            continue
        if spec.startswith(".") or spec.startswith("/"):
            try:
                paths.append((parent / spec).resolve())
            except (OSError, RuntimeError):
                continue
        else:
            bare.append(spec)
    return paths, bare


def _pkg_name_of_specifier(spec: str) -> str | None:
    """The npm package name a bare import specifier belongs to.

    `@scope/pkg/sub` -> `@scope/pkg`; `pkg/sub` -> `pkg`. Relative
    specifiers (starting with `.`) return None.
    """
    if not spec or spec.startswith("."):
        return None
    parts = spec.split("/")
    if spec.startswith("@"):
        return "/".join(parts[:2]) if len(parts) >= 2 else None
    return parts[0] or None


# Elixir: `defmodule Foo.Bar do` declares a module; `alias`/`import`/`use`/
# `require Foo.Bar` reference one. `alias Foo.{Bar, Baz}` references both.
ELIXIR_DEFMODULE_RE = re.compile(r"^\s*defmodule\s+([A-Z][\w.]*?)\s+do", re.MULTILINE)
ELIXIR_MULTI_ALIAS_RE = re.compile(r"^\s*alias\s+([A-Z][\w.]*?)\.\{([^}]*)\}", re.MULTILINE)
ELIXIR_REF_RE = re.compile(r"^\s*(?:alias|import|use|require)\s+([A-Z][\w.]*)", re.MULTILINE)


def _elixir_defmodules(text: str) -> list[str]:
    """Elixir module names declared in a file (`defmodule X.Y do`)."""
    return [m.group(1) for m in ELIXIR_DEFMODULE_RE.finditer(text)]


def _elixir_reference_targets(text: str) -> list[str]:
    """Elixir module names referenced via alias/import/use/require."""
    targets: list[str] = []
    for m in ELIXIR_MULTI_ALIAS_RE.finditer(text):
        base = m.group(1)
        for part in m.group(2).split(","):
            part = part.strip()
            if part:
                targets.append(f"{base}.{part}")
    for m in ELIXIR_REF_RE.finditer(text):
        name = m.group(1).rstrip(".")
        if name:
            targets.append(name)
    return targets


def _go_import_targets(text: str, module_prefix: str | None) -> list[str]:
    """Internal package paths (module prefix stripped) for a Go file."""
    if not module_prefix:
        return []
    raw: list[str] = []
    for m in GO_IMPORT_SINGLE_RE.finditer(text):
        raw.append(m.group(1))
    for blk in GO_IMPORT_BLOCK_RE.finditer(text):
        for line in GO_IMPORT_LINE_RE.finditer(blk.group(1)):
            raw.append(line.group(1))
    out: list[str] = []
    prefix = module_prefix.rstrip("/") + "/"
    for path in raw:
        if path == module_prefix:
            out.append("")
        elif path.startswith(prefix):
            out.append(path[len(prefix):])
    return out


def _bump_edge(edges: dict[tuple[str, str], int], source: str, target: str) -> None:
    if source == target:
        return
    edges[(source, target)] = edges.get((source, target), 0) + 1


def _module_primary_language(module_root: Path) -> tuple[str | None, str | None]:
    """Find the language with the most LOC in a module. Returns (name, color)."""
    by_lang: dict[str, tuple[str, int]] = {}
    for f in iter_files(module_root):
        lang = detect_language(f)
        if not lang or is_binary(f):
            continue
        loc = count_lines(f)
        name, color = lang
        prev = by_lang.get(name, (color, 0))
        by_lang[name] = (color, prev[1] + loc)
    if not by_lang:
        return (None, None)
    name, (color, _loc) = max(by_lang.items(), key=lambda kv: kv[1][1])
    return (name, color)


def build_module_graph(
    root: Path, modules: list[dict[str, Any]], services: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build a module-level dependency graph from import statements.

    Edges are scoped:
      - JS/TS and Go use absolute-path resolution, so they work across
        services that genuinely share code via relative imports.
      - Python first-segment matching is scoped to each module's own
        service: `from auth import X` in module A resolves to A's
        service's `auth` module, not a same-named module in another
        service. This prevents spurious cross-service edges between
        services that just happen to share common module names like
        `models` or `utils`.
    """
    if not modules:
        return {
            "nodes": [], "edges": [], "services": [],
            "languages_parsed": [], "languages_unparsed": [],
            "extraction": "regex",
        }

    index = _build_module_index(modules, root)

    # Optional AST-accurate extraction: one batched ast-grep call for the
    # whole repo. None when the binary is absent or anything fails — every
    # use below falls back to the regex extractor per file.
    ag = astgrep_imports.collect(root) if astgrep_imports is not None else None

    nodes: list[dict[str, Any]] = []
    for m in modules:
        module_root = (root / m["path"]).resolve()
        lang_name, lang_color = _module_primary_language(module_root)
        nodes.append({
            "id": m["path"],
            "name": m["name"],
            "service": m.get("service"),
            "loc": m["loc"],
            "files": m["file_count"],
            "primary_language": lang_name,
            "color": lang_color or "#888888",
            "vendored_guess": bool(m.get("vendored_guess")),
        })

    edges: dict[tuple[str, str], int] = {}
    languages_parsed: set[str] = set()
    languages_unparsed: set[str] = set()

    # Per-service Python first-segment → module_id lookup.
    # Falls back to a "global" bucket for modules without a service tag.
    python_lookup: dict[str | None, dict[str, str]] = {}
    for m in modules:
        bucket = python_lookup.setdefault(m.get("service"), {})
        bucket.setdefault(m["name"], m["path"])

    # Per-service go.mod prefix (each service may have its own go module).
    go_prefix_by_service: dict[str | None, str | None] = {}
    for svc in services:
        sp = (root / svc["id"]).resolve() if svc["id"] != root.name else root
        go_prefix_by_service[svc["id"]] = _read_go_module_prefix(sp)
    # Plus a fallback for the repo root, in case the project has go.mod at
    # the root regardless of how services are arranged.
    go_prefix_by_service[None] = _read_go_module_prefix(root)

    # Workspace package name -> module_id, for resolving JS/TS imports that
    # reference a sibling package by name (e.g. `@scope/pkg`) instead of a
    # relative path. Read each module's own package.json "name".
    workspace_pkg_to_module: dict[str, str] = {}
    for m in modules:
        pj = root / m["path"] / "package.json"
        if pj.is_file():
            try:
                pjdata = json.loads(pj.read_text(encoding="utf-8", errors="replace"))
                name = pjdata.get("name") if isinstance(pjdata, dict) else None
                if name:
                    workspace_pkg_to_module.setdefault(str(name), m["path"])
            except (json.JSONDecodeError, OSError):
                pass

    # Elixir module name -> defining file, built in a pre-pass so references
    # resolve regardless of file/path naming conventions (clones, umbrellas).
    elixir_module_index: dict[str, Path] = {}
    for m in modules:
        for f in iter_files((root / m["path"]).resolve()):
            if f.suffix.lower() in (".ex", ".exs"):
                if ag is not None and ag.has_file(f):
                    names = ag.elixir_defmodules(f)
                else:
                    etext = safe_read(f, limit=256 * 1024)
                    names = _elixir_defmodules(etext) if etext else []
                for name in names:
                    elixir_module_index.setdefault(name, f)

    for m in modules:
        source_id = m["path"]
        source_service = m.get("service")
        module_root = (root / m["path"]).resolve()
        py_names = python_lookup.get(source_service, {})
        go_prefix = (
            go_prefix_by_service.get(source_service)
            or go_prefix_by_service.get(None)
        )
        for f in iter_files(module_root):
            lang = detect_language(f)
            if not lang or is_binary(f):
                continue
            lname = lang[0]
            if lname not in GRAPH_LANGUAGES:
                languages_unparsed.add(lname)
                continue
            text = safe_read(f, limit=256 * 1024)
            if not text:
                continue
            languages_parsed.add(lname)
            use_ag = ag is not None and ag.has_file(f)

            if lname == "Python":
                targets = ag.python_targets(f) if use_ag else _python_import_targets(text)
                for first in targets:
                    target_id = py_names.get(first)
                    if target_id:
                        _bump_edge(edges, source_id, target_id)
            elif lname in ("JavaScript", "TypeScript"):
                if use_ag:
                    js_paths, js_bare = ag.jsts_targets(f)
                else:
                    js_paths, js_bare = _jsts_import_targets(f, text)
                for abs_target in js_paths:
                    target_id = _module_for(abs_target, index)
                    if target_id:
                        _bump_edge(edges, source_id, target_id)
                for spec in js_bare:
                    pkg = _pkg_name_of_specifier(spec)
                    target_id = workspace_pkg_to_module.get(pkg) if pkg else None
                    if target_id:
                        _bump_edge(edges, source_id, target_id)
            elif lname == "Go":
                if use_ag:
                    internals = ag.go_internal_targets(f, go_prefix)
                else:
                    internals = _go_import_targets(text, go_prefix)
                for internal in internals:
                    candidate = (root / internal).resolve() if internal else root
                    target_id = _module_for(candidate, index)
                    if target_id:
                        _bump_edge(edges, source_id, target_id)
            elif lname == "Elixir":
                if use_ag:
                    refs = ag.elixir_reference_targets(f)
                else:
                    refs = _elixir_reference_targets(text)
                for ref in refs:
                    deffile = elixir_module_index.get(ref)
                    if deffile:
                        target_id = _module_for(deffile, index)
                        if target_id:
                            _bump_edge(edges, source_id, target_id)

    edge_list = [
        {"source": s, "target": t, "weight": w}
        for (s, t), w in sorted(edges.items(), key=lambda kv: kv[1], reverse=True)
    ]

    # Compact service summary for the renderer (just what the diagram needs).
    service_summary = [
        {
            "id": s["id"],
            "name": s["name"],
            "kind": s["kind"],
            "stack": s.get("stack", []),
            "color": s.get("color", "#888"),
        }
        for s in services
    ]

    return {
        "nodes": nodes,
        "edges": edge_list,
        "services": service_summary,
        "languages_parsed": sorted(languages_parsed),
        "languages_unparsed": sorted(languages_unparsed - languages_parsed),
        "extraction": "ast-grep" if ag is not None else "regex",
    }


# -------- HTTP topology extraction ------------------------------------
#
# Across web frameworks the shape is basically: handlers declare a
# (method, path) endpoint; clients call (method, url) somewhere else.
# If we extract both sides and match URL prefixes, we recover the
# service-to-service topology — which is the relationship that actually
# matters in modern monorepos (mobile -> backend -> AI service is HTTP,
# never imports).
#
# Coverage is broad on purpose. We support the popular frameworks /
# clients per language. URLs that are dynamic (variable / templated)
# get a `dynamic: True` flag so the renderer can show them honestly
# rather than guessing.

# ---- Endpoint regexes ---------------------------------------------------

# NestJS: @Controller('prefix') sets the class-level prefix; @Get/@Post/...
# decorate methods with the leaf path. Combine to get the full URL.
NEST_CONTROLLER_RE = re.compile(r"@Controller\(\s*['\"`]([^'\"`]*)['\"`]")
NEST_METHOD_RE = re.compile(
    r"@(Get|Post|Put|Patch|Delete|All|Head|Options)\(\s*['\"`]?([^'\"`),]*)['\"`]?\s*[,)]"
)

# Express / Koa / Fastify / Hono — all share the app.METHOD('/path', ...) shape.
JS_HTTP_ROUTE_RE = re.compile(
    r"\b(?:app|router|server|api|route|fastify|hono|koa)\."
    r"(get|post|put|patch|delete|all|head|options|use)\s*\(\s*"
    r"['\"`]([^'\"`]+)['\"`]"
)

# FastAPI: @app.METHOD('/path') or @router.METHOD('/path')
FASTAPI_METHOD_RE = re.compile(
    r"@(?:app|router|api|api_router|v1_router|v2_router|[a-zA-Z_]\w*_router)\."
    r"(get|post|put|patch|delete|head|options|websocket)\s*\(\s*"
    r"['\"`]([^'\"`]+)['\"`]"
)
# APIRouter(prefix='/foo') — module-level prefix often applied to all routes.
FASTAPI_PREFIX_RE = re.compile(
    r"APIRouter\([^)]*prefix\s*=\s*['\"`]([^'\"`]+)['\"`]", re.DOTALL
)
# include_router(other, prefix="/api/v1") — when mounted onto the app/router.
FASTAPI_INCLUDE_RE = re.compile(
    r"include_router\([^)]*prefix\s*=\s*['\"`]([^'\"`]+)['\"`]", re.DOTALL
)

# Flask: @app.route('/path', methods=['GET']) — methods defaults to ['GET'].
FLASK_ROUTE_RE = re.compile(
    r"@(?:app|bp|blueprint|[a-zA-Z_]\w*_bp|api)\.route\(\s*"
    r"['\"`]([^'\"`]+)['\"`]"
    r"(?:[^)]*methods\s*=\s*\[([^\]]+)\])?",
    re.DOTALL,
)

# Django: path('foo/', view) or re_path(r'^foo$', view) or url(...).
DJANGO_URL_RE = re.compile(
    r"\b(?:path|re_path|url)\(\s*r?['\"`]([^'\"`]+)['\"`]"
)

# Rails routes.rb: get '/path', post '/path', resources :users
RAILS_ROUTE_RE = re.compile(
    r"^\s*(get|post|put|patch|delete|match|resource|resources)\s+"
    r"['\":]([^'\"\s,]+)",
    re.MULTILINE,
)

# Spring Boot: @GetMapping("/path"), @RequestMapping(value="/path", method=...)
SPRING_MAPPING_RE = re.compile(
    r'@(Get|Post|Put|Patch|Delete|Request)Mapping\s*\(\s*'
    r'(?:value\s*=\s*)?["\']([^"\']+)["\']'
)
SPRING_CONTROLLER_RE = re.compile(
    r'@(?:RestController|Controller)[^@]*?@RequestMapping\s*\(\s*'
    r'(?:value\s*=\s*)?["\']([^"\']+)["\']',
    re.DOTALL,
)

# Laravel: Route::get('/path', ...), Route::resource('/users', ...)
LARAVEL_ROUTE_RE = re.compile(
    r'Route::(get|post|put|patch|delete|any|resource|apiResource)\s*\(\s*'
    r'["\']([^"\']+)["\']'
)

# Go stdlib: http.HandleFunc("/path", handler)
GO_STDLIB_HANDLE_RE = re.compile(
    r'\bhttp\.HandleFunc\s*\(\s*["`]([^"`]+)["`]'
)
# gin/echo/chi: r.GET("/path", ...) — the variable name is conventional
# but we accept anything short.
GO_ROUTER_RE = re.compile(
    r'\b[a-zA-Z_]\w{0,15}\.'
    r'(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|Get|Post|Put|Patch|Delete|Handle|HandleFunc)'
    r'\(\s*["`]([^"`]+)["`]'
)


def _normalize_route_path(raw: str) -> str:
    """Canonicalize a path so client URLs and endpoint declarations
    align. Converts {id} / :id / <int:id> / [id] into :id."""
    if not raw:
        return "/"
    p = raw.strip()
    if not p.startswith("/"):
        p = "/" + p
    # Strip trailing slashes (except for root).
    if len(p) > 1 and p.endswith("/"):
        p = p.rstrip("/")
    # Normalize parameter syntaxes
    p = re.sub(r"\$\{[^}]+\}", ":id", p)          # JS template literal ${x}
    p = re.sub(r"\$:[a-zA-Z_]\w*", ":id", p)      # leftover $:id artifact
    p = re.sub(r"\{[^/}]+\}", ":id", p)          # FastAPI / Spring / Express { }
    p = re.sub(r"<[a-zA-Z_]+:[^/>]+>", ":id", p)  # Django <int:pk>
    p = re.sub(r"<[^/>]+>", ":id", p)             # Django <foo>
    p = re.sub(r"\[\.\.\.[^\]]+\]", ":id", p)     # Next.js [...slug]
    p = re.sub(r"\[[^/\]]+\]", ":id", p)          # Next.js [id]
    p = re.sub(r":\w+", ":id", p)                 # Express / Rails :foo
    p = re.sub(r"\(\w+:[^)]+\)", ":id", p)        # Expo Router (group:id)
    p = re.sub(r"/+", "/", p)
    return p or "/"


def _join_prefix(prefix: str, leaf: str) -> str:
    """Combine a route prefix with a leaf path, handling extra slashes."""
    if not prefix and not leaf:
        return "/"
    if not prefix:
        return _normalize_route_path(leaf)
    if not leaf:
        return _normalize_route_path(prefix)
    return _normalize_route_path("/" + prefix.strip("/") + "/" + leaf.strip("/"))


def _scan_endpoints_file(
    f: Path, language: str, rel: str, service_id: str | None, module_id: str | None
) -> tuple[list[dict[str, Any]], set[str]]:
    """Extract HTTP endpoints declared in one file. Returns (endpoints, frameworks_seen)."""
    text = safe_read(f, limit=512 * 1024)
    if not text:
        return ([], set())
    out: list[dict[str, Any]] = []
    seen_fw: set[str] = set()

    def emit(framework: str, method: str, path: str) -> None:
        seen_fw.add(framework)
        out.append({
            "service": service_id,
            "module": module_id,
            "file": rel,
            "framework": framework,
            "method": method.upper(),
            "path": _normalize_route_path(path),
        })

    if language in ("TypeScript", "JavaScript"):
        # NestJS — controller prefix + method decorator
        ctrl_match = NEST_CONTROLLER_RE.search(text)
        nest_prefix = ctrl_match.group(1) if ctrl_match else ""
        for m in NEST_METHOD_RE.finditer(text):
            method, leaf = m.group(1), m.group(2)
            emit("NestJS", method, _join_prefix(nest_prefix, leaf))

        # Express / Koa / Fastify / Hono
        for m in JS_HTTP_ROUTE_RE.finditer(text):
            method, path = m.group(1), m.group(2)
            if method.lower() == "use":
                # app.use mounts middleware/sub-routers — too dynamic to resolve
                continue
            emit("Express", method, path)

        # Next.js: pages/api/* and app/api/*/route.ts
        if "/pages/api/" in rel.replace("\\", "/"):
            # File path becomes the route. Strip up through pages/api/.
            r = rel.replace("\\", "/").split("/pages/api/", 1)[1]
            r = re.sub(r"\.(t|j)sx?$", "", r)
            r = re.sub(r"/index$", "", r)
            emit("Next.js (Pages Router)", "GET", "/api/" + r)
        elif re.search(r"/app/api/.+/route\.(t|j)sx?$", rel.replace("\\", "/")):
            r = rel.replace("\\", "/").split("/app/api/", 1)[1]
            r = re.sub(r"/route\.(t|j)sx?$", "", r)
            # Detect which methods are exported
            for m in re.finditer(r"\bexport\s+(?:async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b", text):
                emit("Next.js (App Router)", m.group(1), "/api/" + r)

    elif language == "Python":
        # FastAPI: collect prefixes first (best-effort, file-scoped)
        prefixes = [m.group(1) for m in FASTAPI_PREFIX_RE.finditer(text)]
        prefixes += [m.group(1) for m in FASTAPI_INCLUDE_RE.finditer(text)]
        base_prefix = prefixes[0] if prefixes else ""
        for m in FASTAPI_METHOD_RE.finditer(text):
            method, leaf = m.group(1), m.group(2)
            emit("FastAPI", method, _join_prefix(base_prefix, leaf))

        # Flask
        for m in FLASK_ROUTE_RE.finditer(text):
            path = m.group(1)
            methods_raw = m.group(2)
            methods = ["GET"]
            if methods_raw:
                methods = [
                    s.strip().strip("'\"").upper()
                    for s in methods_raw.split(",")
                    if s.strip()
                ]
            for method in methods:
                emit("Flask", method, path)

        # Django (URL pattern files — method unknown without view inspection)
        if rel.endswith("urls.py") or rel.endswith("/urls.py"):
            for m in DJANGO_URL_RE.finditer(text):
                emit("Django", "ANY", m.group(1))

    elif language == "Ruby":
        # Rails routes.rb is the conventional location, but accept anywhere
        for m in RAILS_ROUTE_RE.finditer(text):
            verb, path = m.group(1), m.group(2)
            if verb in ("resource", "resources"):
                # Plural CRUD endpoints — emit the index path; deeper REST routes are implied
                emit("Rails", "ANY", "/" + path.strip(":"))
            else:
                emit("Rails", verb, path)

    elif language in ("Java", "Kotlin"):
        # Spring Boot @RestController class-level prefix
        ctrl = SPRING_CONTROLLER_RE.search(text)
        prefix = ctrl.group(1) if ctrl else ""
        for m in SPRING_MAPPING_RE.finditer(text):
            method_kind, path = m.group(1), m.group(2)
            method = "ANY" if method_kind == "Request" else method_kind.upper()
            emit("Spring Boot", method, _join_prefix(prefix, path))

    elif language == "PHP":
        for m in LARAVEL_ROUTE_RE.finditer(text):
            verb, path = m.group(1), m.group(2)
            if verb in ("resource", "apiResource"):
                emit("Laravel", "ANY", path)
            else:
                emit("Laravel", verb, path)

    elif language == "Go":
        for m in GO_STDLIB_HANDLE_RE.finditer(text):
            emit("Go net/http", "ANY", m.group(1))
        for m in GO_ROUTER_RE.finditer(text):
            method, path = m.group(1), m.group(2)
            method_u = method.upper()
            if method_u in ("HANDLE", "HANDLEFUNC"):
                method_u = "ANY"
            emit("Go router", method_u, path)

    return (out, seen_fw)


# ---- Client regexes -----------------------------------------------------

JS_AXIOS_RE = re.compile(
    r"\baxios\.(get|post|put|patch|delete|request|head|options)\s*\(\s*"
    r"['\"`]([^'\"`]+)['\"`]"
)
JS_AXIOS_OBJ_RE = re.compile(
    r"\baxios\s*\(\s*\{\s*[^}]*?url\s*:\s*['\"`]([^'\"`]+)['\"`][^}]*?\}",
    re.DOTALL,
)
JS_FETCH_RE = re.compile(
    r"\bfetch\s*\(\s*['\"`]([^'\"`]+)['\"`]"
    r"(?:\s*,\s*\{[^}]*?method\s*:\s*['\"`](\w+)['\"`])?",
    re.DOTALL,
)
JS_KY_GOT_RE = re.compile(
    r"\b(?:ky|got)\.(get|post|put|patch|delete|head|options)\s*\(\s*"
    r"['\"`]([^'\"`]+)['\"`]"
)
JS_JQUERY_RE = re.compile(
    r"\$\.(get|post|ajax)\s*\(\s*['\"`]([^'\"`]+)['\"`]"
)
JS_CLIENT_OBJ_RE = re.compile(
    r"\b(?:this\.\w+|\w*(?:Client|Service|Api|Http|Caller)|api|client|http)"
    r"\.(get|post|put|patch|delete|request|send)\s*"
    r"(?:<[^>]+>)?\s*\(\s*['\"`]([^'\"`]+)['\"`]"
)
# Bare-function HTTP calls like `post('/ai/chat', body)` — common when a
# frontend imports HTTP verbs from a local wrapper module
# (e.g. `import { post } from './client'`). Restrictive: requires the URL
# string to start with '/' and excludes obvious non-HTTP false positives.
JS_BARE_VERB_RE = re.compile(
    r"\b(get|post|put|patch|delete|del|head)\s*"
    r"(?:<[^>]+>)?\s*\(\s*[`'\"]([/][^'\"`?\s]+)[`'\"]"
)

PY_REQUESTS_RE = re.compile(
    r"\b(?:requests|httpx|client|aiohttp_client)\.(get|post|put|patch|delete|request|head|options)\s*"
    r"\(\s*['\"`]([^'\"`]+)['\"`]"
)
PY_URLLIB_RE = re.compile(
    r"\burlopen\s*\(\s*['\"`]([^'\"`]+)['\"`]"
)
PY_AIOHTTP_RE = re.compile(
    r"\b(?:session|client)\.(get|post|put|patch|delete)\s*\(\s*['\"`]([^'\"`]+)['\"`]"
)

GO_HTTP_CLIENT_RE = re.compile(
    r"\b(?:http|client)\.(Get|Post|Head|Delete|Put|Patch|NewRequest)"
    r"\s*\(\s*(?:[a-zA-Z_]\w*\s*,\s*)?[\"`]([^\"`]+)[\"`]"
)

RUBY_HTTP_RE = re.compile(
    r"(?:Net::HTTP|HTTParty|Faraday)\.(get|post|put|patch|delete|head)\s*\(\s*"
    r"['\"`]([^'\"`]+)['\"`]"
)

JAVA_HTTP_RE = re.compile(
    r'(?:restTemplate|webClient|httpClient)\.(get|post|put|patch|delete|exchange|getForObject|postForObject)'
    r'\s*\(\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)


def _scan_clients_file(
    f: Path, language: str, rel: str, service_id: str | None, module_id: str | None
) -> tuple[list[dict[str, Any]], set[str]]:
    """Extract outbound HTTP calls in one file. Returns (clients, libs_seen)."""
    text = safe_read(f, limit=512 * 1024)
    if not text:
        return ([], set())
    out: list[dict[str, Any]] = []
    libs: set[str] = set()

    def emit(client_lib: str, method: str, url: str) -> None:
        libs.add(client_lib)
        out.append({
            "service": service_id,
            "module": module_id,
            "file": rel,
            "client": client_lib,
            "method": method.upper(),
            "url": _normalize_route_path(url) if url.startswith("/") else url,
            "is_relative": url.startswith("/"),
        })

    if language in ("TypeScript", "JavaScript"):
        for m in JS_AXIOS_RE.finditer(text):
            method, url = m.group(1), m.group(2)
            method_u = method.upper() if method != "request" else "ANY"
            emit("axios", method_u, url)
        for m in JS_AXIOS_OBJ_RE.finditer(text):
            emit("axios", "ANY", m.group(1))
        for m in JS_FETCH_RE.finditer(text):
            url, method = m.group(1), (m.group(2) or "GET")
            emit("fetch", method, url)
        for m in JS_KY_GOT_RE.finditer(text):
            emit("ky/got", m.group(1), m.group(2))
        for m in JS_JQUERY_RE.finditer(text):
            method, url = m.group(1), m.group(2)
            emit("jQuery", "ANY" if method == "ajax" else method, url)
        for m in JS_CLIENT_OBJ_RE.finditer(text):
            method, url = m.group(1), m.group(2)
            method_u = method.upper() if method not in ("request", "send") else "ANY"
            emit("httpClient (custom)", method_u, url)
        # Bare-function calls (`import { post } from './client'` pattern).
        # Only emit when the source file actually imports an HTTP verb from
        # a local module — keeps us from false-firing on `validate('/foo')`
        # or `parse('/x')` calls in unrelated code.
        if re.search(
            r"^\s*import\s*\{[^}]*\b(?:get|post|put|patch|delete|del|head)\b[^}]*\}\s*from\s*['\"][\./]",
            text,
            re.MULTILINE,
        ):
            for m in JS_BARE_VERB_RE.finditer(text):
                verb, url = m.group(1), m.group(2)
                method_u = "DELETE" if verb == "del" else verb.upper()
                emit("local API wrapper", method_u, url)

    elif language == "Python":
        for m in PY_REQUESTS_RE.finditer(text):
            method, url = m.group(1), m.group(2)
            method_u = method.upper() if method != "request" else "ANY"
            emit("requests/httpx", method_u, url)
        for m in PY_URLLIB_RE.finditer(text):
            emit("urllib", "GET", m.group(1))
        for m in PY_AIOHTTP_RE.finditer(text):
            emit("aiohttp", m.group(1), m.group(2))

    elif language == "Go":
        for m in GO_HTTP_CLIENT_RE.finditer(text):
            method, url = m.group(1), m.group(2)
            emit("net/http", method.upper(), url)

    elif language == "Ruby":
        for m in RUBY_HTTP_RE.finditer(text):
            emit("Net::HTTP/HTTParty/Faraday", m.group(1), m.group(2))

    elif language in ("Java", "Kotlin"):
        for m in JAVA_HTTP_RE.finditer(text):
            emit("RestTemplate/WebClient", m.group(1).upper(), m.group(2))

    return (out, libs)


def _file_to_module_id(
    f: Path, module_index: list[tuple[Path, str]]
) -> str | None:
    return _module_for(f, module_index)


def _file_to_service_id(
    file_path: Path, root: Path, services: list[dict[str, Any]]
) -> str | None:
    """Find the service whose path is the closest ancestor of file_path."""
    best: tuple[int, str] | None = None
    for s in services:
        sid = s["id"]
        if sid in (root.name, "."):
            continue
        svc_root = (root / sid).resolve()
        try:
            rel = file_path.resolve().relative_to(svc_root)
            depth = len(svc_root.parts)
            if best is None or depth > best[0]:
                best = (depth, sid)
        except (ValueError, OSError):
            continue
    return best[1] if best else None


def _match_client_to_endpoint(
    url: str,
    endpoints: list[dict[str, Any]],
    candidate_prefixes: list[str] | None = None,
) -> dict[str, Any] | None:
    """Match a client URL to the longest-prefix endpoint declaration.

    Clients often use a baseURL (e.g. axios.create({baseURL:'/api/v1'}))
    that strips the prefix at runtime. To bridge this, we try matching
    the raw URL first, then with each candidate prefix prepended. Best
    score wins. Prefer specific (long) matches over generic (short) ones
    — `/` matches against everything but never wins over a real path.
    """
    if not url.startswith("/"):
        return None
    candidates = [url]
    if candidate_prefixes:
        for p in candidate_prefixes:
            p_clean = "/" + p.strip("/")
            if not url.startswith(p_clean + "/") and url != p_clean:
                candidates.append(p_clean + url)
    best: tuple[int, dict[str, Any]] | None = None
    for candidate in candidates:
        for ep in endpoints:
            epath = ep["path"]
            if epath == "/":
                # The root endpoint matches every URL by trivial prefix.
                # Only count it if the client URL is literally "/" — else
                # it floods the results with spurious edges to the root.
                if candidate == "/":
                    score = 101
                else:
                    continue
            elif candidate == epath:
                score = len(epath) + 100
            elif candidate.startswith(epath.rstrip("/") + "/"):
                score = len(epath)
            else:
                continue
            if best is None or score > best[0]:
                best = (score, ep)
    return best[1] if best else None


NEST_GLOBAL_PREFIX_RE = re.compile(
    r"\bsetGlobalPrefix\s*\(\s*['\"`]([^'\"`]+)['\"`]"
)
# Express: `app.use('/api', someRouter)` — the prefix applies to all routes
# in that router. We can't follow the router reference reliably, but the
# presence of a single dominant prefix is a strong hint.
EXPRESS_PREFIX_RE = re.compile(
    r"\bapp\.use\s*\(\s*['\"`](/[a-zA-Z0-9/_\-]+)['\"`]"
)
# FastAPI: `app.include_router(router, prefix='/api/v1')` at bootstrap.
FASTAPI_APP_PREFIX_RE = re.compile(
    r"\binclude_router\s*\([^)]*prefix\s*=\s*['\"`]([^'\"`]+)['\"`]",
    re.DOTALL,
)


def _detect_service_prefix(root: Path, service_id: str) -> dict[str, str]:
    """Scan a service's bootstrap files for a global URL prefix.

    Returns a dict {framework_name: prefix} so different frameworks within
    the same service can have different prefixes (rare but possible).
    """
    out: dict[str, str] = {}
    if not service_id or service_id == ".":
        return out
    svc_root = (root / service_id).resolve()
    if not svc_root.is_dir():
        return out

    bootstrap_candidates: list[Path] = []
    for name in ("main.ts", "main.js", "index.ts", "index.js", "app.ts", "app.js", "server.ts", "server.js"):
        bootstrap_candidates.extend(svc_root.glob(name))
        bootstrap_candidates.extend(svc_root.glob(f"src/{name}"))
    for name in ("main.py", "app.py", "asgi.py", "wsgi.py", "__main__.py"):
        bootstrap_candidates.extend(svc_root.glob(name))
        bootstrap_candidates.extend(svc_root.glob(f"app/{name}"))

    for f in bootstrap_candidates:
        if not f.is_file():
            continue
        text = safe_read(f, limit=64 * 1024)
        if not text:
            continue
        m = NEST_GLOBAL_PREFIX_RE.search(text)
        if m and "NestJS" not in out:
            out["NestJS"] = _normalize_route_path(m.group(1))
        m = FASTAPI_APP_PREFIX_RE.search(text)
        if m and "FastAPI" not in out:
            out["FastAPI"] = _normalize_route_path(m.group(1))
        m = EXPRESS_PREFIX_RE.search(text)
        if m and "Express" not in out:
            out["Express"] = _normalize_route_path(m.group(1))

    return out


def build_http_topology(
    root: Path, services: list[dict[str, Any]], modules: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build the cross-service HTTP topology.

    Endpoints + clients are extracted per file. Edges are resolved by
    URL-prefix matching across services (intra-service calls are dropped).
    """
    endpoints: list[dict[str, Any]] = []
    clients: list[dict[str, Any]] = []
    frameworks_seen: set[str] = set()
    clients_seen: set[str] = set()

    # Pre-compute global URL prefixes per service from bootstrap files
    # (e.g. NestJS app.setGlobalPrefix('api/v1')). These are applied to
    # endpoints after the per-file scan so we don't have to thread the
    # service map through every regex helper.
    service_prefixes: dict[str, dict[str, str]] = {}
    for svc in services:
        service_prefixes[svc["id"]] = _detect_service_prefix(root, svc["id"])

    module_index = _build_module_index(modules, root)

    # Languages we scan files for. We accept any of these regardless of
    # whether the service was classified as backend / frontend / library —
    # a "frontend" can definitely make HTTP calls, and we want those edges.
    SCANNABLE = frozenset({
        "TypeScript", "JavaScript", "Python", "Go", "Ruby", "Java", "Kotlin", "PHP",
    })

    for f in iter_files(root):
        lang = detect_language(f)
        if not lang:
            continue
        lname = lang[0]
        if lname not in SCANNABLE:
            continue
        if is_binary(f):
            continue
        try:
            rel = str(f.relative_to(root))
        except ValueError:
            continue
        service_id = _file_to_service_id(f, root, services)
        module_id = _file_to_module_id(f, module_index)

        eps, fws = _scan_endpoints_file(f, lname, rel, service_id, module_id)
        # Apply per-service global prefix per framework if one was detected.
        if service_id and service_id in service_prefixes:
            prefix_map = service_prefixes[service_id]
            for ep in eps:
                pfx = prefix_map.get(ep["framework"])
                if pfx:
                    ep["path"] = _join_prefix(pfx, ep["path"])
        endpoints.extend(eps)
        frameworks_seen.update(fws)

        cls, libs = _scan_clients_file(f, lname, rel, service_id, module_id)
        clients.extend(cls)
        clients_seen.update(libs)

    # Build the list of candidate prefixes from every service's detected
    # global prefix. When a client URL doesn't match any endpoint
    # directly, we retry with each prefix prepended — this catches the
    # common pattern of a client using `axios.create({baseURL:'/api/v1'})`
    # and then calling `client.get('/auth/me')`.
    candidate_prefixes = sorted({
        prefix
        for svc_prefixes in service_prefixes.values()
        for prefix in svc_prefixes.values()
        if prefix and prefix != "/"
    })

    # Resolve client → endpoint, drop intra-service edges, aggregate.
    edge_acc: dict[tuple[str, str, str, str], int] = {}
    unresolved_count = 0
    for c in clients:
        if not c["is_relative"]:
            # Skip absolute-URL clients here. They're not noise — they may
            # be external API calls (Stripe, OpenAI, etc.) and deserve to
            # show up as "external service" nodes in a future iteration.
            continue
        ep = _match_client_to_endpoint(c["url"], endpoints, candidate_prefixes)
        if not ep:
            unresolved_count += 1
            continue
        # Spurious-match guard: if the matched endpoint's path equals one
        # of the bare service prefixes (e.g. `/api/v1`), the client almost
        # certainly meant to call a specific sub-route we didn't extract.
        # Count it as unresolved rather than draw a misleading edge.
        if ep["path"] in (candidate_prefixes or []) or ep["path"] == "/api" or ep["path"] == "/api/v1":
            unresolved_count += 1
            continue
        if c["service"] == ep["service"]:
            # Same-service HTTP — not interesting for topology.
            continue
        if c["service"] is None or ep["service"] is None:
            continue
        key = (c["service"], ep["service"], ep["method"], ep["path"])
        edge_acc[key] = edge_acc.get(key, 0) + 1

    edges = [
        {
            "source_service": k[0],
            "target_service": k[1],
            "method": k[2],
            "path": k[3],
            "weight": w,
        }
        for k, w in sorted(edge_acc.items(), key=lambda kv: kv[1], reverse=True)
    ]

    # Per-service endpoint counts (used to highlight entry-point modules later).
    by_service_module: dict[tuple[str, str], int] = {}
    for ep in endpoints:
        if ep["service"] and ep["module"]:
            key = (ep["service"], ep["module"])
            by_service_module[key] = by_service_module.get(key, 0) + 1
    entry_modules = [
        {"service": k[0], "module": k[1], "endpoint_count": v}
        for k, v in sorted(by_service_module.items(), key=lambda kv: kv[1], reverse=True)
    ]

    return {
        "endpoints": endpoints,
        "clients": clients,
        "edges": edges,
        "entry_modules": entry_modules,
        "frameworks_detected": sorted(frameworks_seen),
        "clients_detected": sorted(clients_seen),
        "unresolved_client_count": unresolved_count,
    }


# -------- Data lineage extraction -------------------------------------
#
# What stores does the codebase talk to, and which services own which
# data models? We detect stores from docker-compose images + connection-
# string patterns, then attribute ORM model usage per service.

STORE_PATTERNS: tuple[tuple[str, str, str], ...] = (
    # (regex pattern, store kind label, default display name)
    (r"\bpostgres(?:ql)?\b", "postgres", "PostgreSQL"),
    (r"\bmysql\b|\bmariadb\b", "mysql", "MySQL"),
    (r"\bredis\b", "redis", "Redis"),
    (r"\bmongo(?:db)?\b", "mongodb", "MongoDB"),
    (r"\belasticsearch\b|\bopensearch\b", "elasticsearch", "Elasticsearch"),
    (r"\bkafka\b", "kafka", "Kafka"),
    (r"\brabbitmq\b", "rabbitmq", "RabbitMQ"),
    (r"\bclickhouse\b", "clickhouse", "ClickHouse"),
    (r"\bcassandra\b", "cassandra", "Cassandra"),
    (r"\bdynamodb\b", "dynamodb", "DynamoDB"),
    (r"\bsqlite\b", "sqlite", "SQLite"),
    (r"\bs3\b|\bminio\b", "s3", "S3 / object storage"),
    (r"\bsupabase\b", "supabase", "Supabase"),
    (r"\bfirebase\b|\bfirestore\b", "firebase", "Firebase / Firestore"),
)

PRISMA_MODEL_RE = re.compile(r"\bthis\.prisma\.(\w+)\b")
PRISMA_SCHEMA_MODEL_RE = re.compile(r"^\s*model\s+(\w+)\s*\{", re.MULTILINE)
SQLALCHEMY_CLASS_RE = re.compile(r"^\s*class\s+(\w+)\s*\([^)]*\bBase\b[^)]*\)", re.MULTILINE)
SQLALCHEMY_QUERY_RE = re.compile(r"\b(?:session\.query|select)\s*\(\s*(\w+)")
MONGOOSE_MODEL_RE = re.compile(r"mongoose\.model\(\s*['\"`](\w+)['\"`]")
DJANGO_MODEL_RE = re.compile(r"^\s*class\s+(\w+)\s*\([^)]*\bmodels\.Model\b[^)]*\)", re.MULTILINE)
DJANGO_QUERY_RE = re.compile(r"\b([A-Z]\w*)\.objects\.\w+")
ACTIVERECORD_RE = re.compile(r"^\s*class\s+(\w+)\s*<\s*ApplicationRecord", re.MULTILINE)
JPA_ENTITY_RE = re.compile(r"@Entity[^\w]*?(?:public\s+)?class\s+(\w+)", re.DOTALL)


def _detect_stores(root: Path) -> list[dict[str, Any]]:
    """Detect data stores referenced anywhere in the repo (docker-compose,
    env files, connection strings in source). Returns a deduplicated list."""
    found: dict[str, dict[str, Any]] = {}
    sources = []
    for name in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
        p = root / name
        if p.is_file():
            sources.append(("docker-compose", safe_read(p, limit=128 * 1024)))
    for name in (".env", ".env.example", ".env.local", "config/database.yml"):
        p = root / name
        if p.is_file():
            sources.append((name, safe_read(p, limit=64 * 1024)))

    # Also look at top-level env files in service containers
    for d in root.iterdir() if root.is_dir() else []:
        if d.is_dir() and d.name not in SKIP_DIRS and not d.name.startswith("."):
            for name in (".env", ".env.example"):
                p = d / name
                if p.is_file():
                    sources.append((f"{d.name}/{name}", safe_read(p, limit=64 * 1024)))

    for source_name, text in sources:
        if not text:
            continue
        lower = text.lower()
        for pat, kind, display in STORE_PATTERNS:
            if re.search(pat, lower):
                if kind not in found:
                    found[kind] = {
                        "id": kind,
                        "kind": kind,
                        "name": display,
                        "evidence": [],
                    }
                if source_name not in found[kind]["evidence"]:
                    found[kind]["evidence"].append(source_name)

    return list(found.values())


def _scan_data_models_file(
    f: Path, language: str, service_id: str | None
) -> list[dict[str, Any]]:
    """Extract data model declarations / queries in one file. Returns list
    of {service, framework, model} entries."""
    text = safe_read(f, limit=256 * 1024)
    if not text:
        return []
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def emit(framework: str, model: str) -> None:
        if (framework, model) in seen or not model:
            return
        seen.add((framework, model))
        out.append({
            "service": service_id,
            "framework": framework,
            "model": model,
        })

    if language in ("TypeScript", "JavaScript"):
        for m in PRISMA_MODEL_RE.finditer(text):
            emit("Prisma", m.group(1).capitalize())
        for m in MONGOOSE_MODEL_RE.finditer(text):
            emit("Mongoose", m.group(1))
    elif language == "Python":
        for m in SQLALCHEMY_CLASS_RE.finditer(text):
            emit("SQLAlchemy", m.group(1))
        for m in SQLALCHEMY_QUERY_RE.finditer(text):
            emit("SQLAlchemy", m.group(1))
        for m in DJANGO_MODEL_RE.finditer(text):
            emit("Django ORM", m.group(1))
        for m in DJANGO_QUERY_RE.finditer(text):
            emit("Django ORM", m.group(1))
    elif language == "Ruby":
        for m in ACTIVERECORD_RE.finditer(text):
            emit("ActiveRecord", m.group(1))
    elif language in ("Java", "Kotlin"):
        for m in JPA_ENTITY_RE.finditer(text):
            emit("Spring Data JPA", m.group(1))

    return out


# Mapping of ORM framework → likely store kind. Imperfect heuristic; a
# Prisma project COULD use MySQL or PostgreSQL — we pick the most common
# default and let the renderer note "best guess".
ORM_DEFAULT_STORE: dict[str, str] = {
    "Prisma": "postgres",
    "SQLAlchemy": "postgres",
    "Mongoose": "mongodb",
    "Django ORM": "postgres",
    "ActiveRecord": "postgres",
    "Spring Data JPA": "postgres",
}


def build_data_lineage(
    root: Path, services: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build the data lineage: stores + per-service ORM model usage +
    service↔store edges weighted by model count."""
    stores = _detect_stores(root)
    store_ids = {s["id"] for s in stores}

    # If we detected ORM usage but didn't find a matching store, infer
    # a placeholder store entry so the diagram still shows something.

    raw_models: list[dict[str, Any]] = []
    for f in iter_files(root):
        lang = detect_language(f)
        if not lang or is_binary(f):
            continue
        lname = lang[0]
        if lname not in ("TypeScript", "JavaScript", "Python", "Ruby", "Java", "Kotlin"):
            continue
        service_id = _file_to_service_id(f, root, services)
        raw_models.extend(_scan_data_models_file(f, lname, service_id))

    # Prisma's schema.prisma file is the source of truth — collect canonical
    # model names there to dedupe against the lowercase `this.prisma.x`
    # references that came from .ts files.
    for f in root.rglob("schema.prisma"):
        if any(part in SKIP_DIRS for part in f.parts):
            continue
        text = safe_read(f, limit=64 * 1024)
        if not text:
            continue
        service_id = _file_to_service_id(f, root, services)
        for m in PRISMA_SCHEMA_MODEL_RE.finditer(text):
            raw_models.append({
                "service": service_id,
                "framework": "Prisma",
                "model": m.group(1),
            })

    # Dedupe per (service, framework, model) and infer store.
    dedup: dict[tuple[str | None, str, str], None] = {}
    for m in raw_models:
        dedup[(m["service"], m["framework"], m["model"])] = None
    models = [
        {"service": k[0], "framework": k[1], "model": k[2],
         "store": ORM_DEFAULT_STORE.get(k[1], "unknown")}
        for k in dedup
    ]

    # Build edges. If a model references a store we didn't detect from
    # config files, emit a "best guess" store entry so the diagram has
    # something to point at.
    edge_acc: dict[tuple[str, str], dict[str, Any]] = {}
    for m in models:
        if not m["service"]:
            continue
        store_id = m["store"]
        if store_id not in store_ids:
            # Synthesize a placeholder store entry from the inferred default
            stores.append({
                "id": store_id, "kind": store_id,
                "name": store_id.title(),
                "evidence": ["inferred from ORM usage"],
            })
            store_ids.add(store_id)
        key = (m["service"], store_id)
        if key not in edge_acc:
            edge_acc[key] = {
                "source_service": m["service"],
                "target_store": store_id,
                "models": [],
                "frameworks": set(),
            }
        edge_acc[key]["models"].append(m["model"])
        edge_acc[key]["frameworks"].add(m["framework"])

    edges = []
    for v in edge_acc.values():
        edges.append({
            "source_service": v["source_service"],
            "target_store": v["target_store"],
            "models": sorted(set(v["models"])),
            "frameworks": sorted(v["frameworks"]),
            "weight": len(set(v["models"])),
        })
    edges.sort(key=lambda e: e["weight"], reverse=True)

    return {
        "stores": stores,
        "models": models,
        "edges": edges,
    }


# -------- Flow skeleton builder ---------------------------------------


def _longest_common_route_prefix(paths: list[str]) -> str:
    """Longest shared leading path at segment ('/') boundaries.

    ["/api/v1/workouts", "/api/v1/workouts/123"] -> "/api/v1/workouts/"
    A single path returns itself with a trailing slash. Empty -> "/".
    """
    segs = [[s for s in p.split("/") if s != ""] for p in paths if p]
    if not segs:
        return "/"
    common: list[str] = []
    for tup in zip(*segs):
        first = tup[0]
        if all(s == first for s in tup):
            common.append(first)
        else:
            break
    return "/" + "/".join(common) + ("/" if common else "")


def build_flow_skeletons(
    http_topology: dict,
    module_graph: dict,
    data_lineage: dict,
    modules: list,
    depth: str,
    handler_symbols: dict[str, list[str]] | None = None,
) -> list[dict]:
    """One flow skeleton per PRODUCT entry module, joined from data the scanner
    already has. Deterministic. ``handler_symbols`` maps a file (rel path) to
    handler names; absent -> empty symbol lists (the LLM fills them).
    """
    handler_symbols = handler_symbols or {}
    endpoints = http_topology.get("endpoints") or []
    entry_modules = http_topology.get("entry_modules") or []
    edges = module_graph.get("edges") or []
    lineage_edges = data_lineage.get("edges") or []

    vendored = {m.get("path") for m in modules if m.get("vendored_guess")}

    eps_by_key: dict[tuple, list] = {}
    for ep in endpoints:
        eps_by_key.setdefault((ep.get("service"), ep.get("module")), []).append(ep)
    deps_by_module: dict[str, list] = {}
    for e in edges:
        deps_by_module.setdefault(e.get("source"), []).append(e)
    stores_by_service: dict[str, set] = {}
    for le in lineage_edges:
        stores_by_service.setdefault(le.get("source_service"), set()).add(le.get("target_store"))

    skeletons: list[dict] = []
    for em in entry_modules:
        module_id = em.get("module")
        service = em.get("service")
        if module_id in vendored:
            continue
        eps = eps_by_key.get((service, module_id), [])
        if not eps:
            continue
        file_counts = Counter(ep.get("file") for ep in eps if ep.get("file"))
        entry_file = file_counts.most_common(1)[0][0] if file_counts else None
        # `or ""` so an explicit path=None maps to "" like an absent key (both
        # are excluded from the prefix; n/trigger still count the endpoint).
        prefix = _longest_common_route_prefix([ep.get("path") or "" for ep in eps])
        method_counts = Counter(ep.get("method", "") for ep in eps)
        method_str = ", ".join(f"{m}×{c}" for m, c in method_counts.most_common())
        n = len(eps)
        trigger = f"HTTP {prefix}* — {n} endpoint{'s' if n != 1 else ''} ({method_str})"
        deps = sorted(deps_by_module.get(module_id, []), key=lambda e: -(e.get("weight") or 0))
        key_deps = [
            {"module": e.get("target"), "weight": e.get("weight") or 0}
            for e in deps if e.get("target") not in vendored
        ][:5]
        stores = sorted(s for s in stores_by_service.get(service, set()) if s)
        skeletons.append({
            "id": module_id,
            "service": service,
            "kind_hint": "request",
            "trigger": trigger,
            "entry": {"module": module_id, "file": entry_file,
                      "symbols": list(handler_symbols.get(entry_file, [])) if entry_file else []},
            "key_deps": key_deps,
            "stores": stores,
            "endpoint_count": n,
        })

    skeletons.sort(key=lambda s: -s["endpoint_count"])
    cap = DEPTH_TIERS.get(depth, DEPTH_TIERS["medium"]).get("max_flow_skeletons")
    if cap is not None:
        skeletons = skeletons[:cap]
    return skeletons


# -------- Top-level data assembly -------------------------------------

# Depth tiers. medium is the new default — shallow truncates too
# aggressively for modern monorepos, full is overkill for casual scans.
# The diagram cap is intentionally larger than the cards cap; readers
# benefit from more nodes than they'd want as text cards.
DEPTH_TIERS: dict[str, dict[str, int | None]] = {
    "shallow": {
        "tree_depth": 2,
        "max_modules_cards": 10,
        "max_graph_modules": 30,
        "max_deps_per_eco": 20,
        "max_flow_skeletons": 10,
    },
    "medium": {
        "tree_depth": 4,
        "max_modules_cards": 25,
        "max_graph_modules": 80,
        "max_deps_per_eco": 40,
        "max_flow_skeletons": 30,
    },
    "full": {
        "tree_depth": None,
        "max_modules_cards": None,
        "max_graph_modules": None,
        "max_deps_per_eco": None,
        "max_flow_skeletons": None,
    },
}


def build_data_model(root: Path, depth: str) -> dict[str, Any]:
    tier = DEPTH_TIERS.get(depth, DEPTH_TIERS["medium"])
    max_tree_depth = tier["tree_depth"]
    max_cards = tier["max_modules_cards"]
    max_graph = tier["max_graph_modules"]
    max_deps_per_eco = tier["max_deps_per_eco"]

    tree = walk_tree(root, max_tree_depth)
    languages = aggregate_languages(root)
    # Compute the full service + module set once. Display caps and graph
    # caps are applied as slices afterward so we never drop edges to a
    # node that gets shown elsewhere in the report.
    services, all_modules = detect_services_and_modules(root)
    modules = all_modules[:max_cards] if max_cards is not None else all_modules
    graph_modules = (
        all_modules[:max_graph] if max_graph is not None else all_modules
    )
    module_graph = build_module_graph(root, graph_modules, services)
    # HTTP topology + data lineage use the FULL module set (not graph_modules)
    # so an entry-point module in a service the graph truncated is still
    # findable. These passes are independent of graph node selection.
    http_topology = build_http_topology(root, services, all_modules)
    data_lineage = build_data_lineage(root, services)
    handler_symbols = astgrep_handlers.collect(root) if astgrep_handlers is not None else {}
    flow_skeletons = build_flow_skeletons(
        http_topology, module_graph, data_lineage, all_modules, depth,
        handler_symbols=handler_symbols,
    )
    deps = find_dependencies(root, max_deps_per_eco)
    entry_points = detect_entry_points(root)
    readme = extract_readme(root)

    total_files = sum(lang["files"] for lang in languages)
    total_loc = sum(lang["loc"] for lang in languages)
    primary = languages[0]["name"] if languages else None

    return {
        "schema_version": 4,
        "tool_version": TOOL_VERSION,
        "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scan_depth": depth,
        "project": {
            "name": root.name or str(root),
            "root": str(root),
            "total_files": total_files,
            "total_loc": total_loc,
            "primary_language": primary,
            "is_monorepo": len(services) > 1,
        },
        "languages": languages,
        "services": services,
        "tree": tree,
        "modules": modules,
        "module_graph": module_graph,
        "http_topology": http_topology,
        "data_lineage": data_lineage,
        "flow_skeletons": flow_skeletons,
        "deps": deps,
        "entry_points": entry_points,
        "readme": readme,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan a repository and emit a JSON data model.")
    parser.add_argument("--path", required=True, help="Path to scan.")
    parser.add_argument("--depth", choices=("shallow", "medium", "full"), default="medium")
    parser.add_argument("--out", required=True, help="Output JSON file path.")
    parser.add_argument(
        "--evidence-out",
        default=None,
        help="If set, also write a bounded evidence pack JSON to this path "
             "(for the LLM evaluation layer).",
    )
    args = parser.parse_args()

    root = Path(args.path).expanduser().resolve()
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2

    out = Path(args.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    data = build_data_model(root, args.depth)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"scanned {data['project']['total_files']} files, {data['project']['total_loc']} LOC -> {out}")

    if args.evidence_out:
        ev = Path(args.evidence_out).expanduser().resolve()
        ev.parent.mkdir(parents=True, exist_ok=True)
        pack = evidence.build_evidence_pack(root, data)
        ev.write_text(json.dumps(pack, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"evidence pack ({pack['budget']['used_bytes']} bytes) -> {ev}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
