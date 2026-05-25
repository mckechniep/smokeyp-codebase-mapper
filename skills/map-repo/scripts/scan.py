#!/usr/bin/env python3
"""Repository scanner for smokeyp-codebase-mapper.

Walks a target directory and emits a JSON data model describing the
codebase: languages, directory tree, top-level modules, external
dependencies, entry points, and README extract.

Stdlib only. Python 3.10+.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOOL_VERSION = "0.1.0"

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


def detect_modules(root: Path, max_modules: int | None) -> list[dict[str, Any]]:
    """Find top-level modules.

    Strategy: if any conventional source root exists, treat each of its
    immediate subdirectories as a module. Otherwise, treat top-level
    directories at the repo root (excluding skip set) as modules.
    """
    candidate_parents: list[Path] = []
    for sr in SOURCE_ROOTS:
        p = root / sr
        if p.is_dir():
            candidate_parents.append(p)
    if not candidate_parents:
        candidate_parents = [root]

    modules: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for parent in candidate_parents:
        try:
            entries = sorted(parent.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            continue
        for entry in entries:
            if not entry.is_dir():
                continue
            if entry.name in SKIP_DIRS or entry.name.startswith("."):
                continue
            if entry in seen:
                continue
            seen.add(entry)

            file_count = 0
            loc = 0
            languages: set[str] = set()
            for f in iter_files(entry):
                if is_binary(f):
                    continue
                file_count += 1
                loc += count_lines(f)
                if (lang := detect_language(f)):
                    languages.add(lang[0])
            if file_count == 0:
                continue

            modules.append({
                "path": str(entry.relative_to(root)),
                "name": entry.name,
                "file_count": file_count,
                "loc": loc,
                "languages": sorted(languages),
                "description": guess_module_description(entry),
            })

    modules.sort(key=lambda m: m["loc"], reverse=True)
    if max_modules is not None:
        modules = modules[:max_modules]
    return modules


def guess_module_description(module_root: Path) -> str | None:
    """Best-effort module description from README, package.json, or
    top-of-file docstring of a likely entry file."""
    # Module-local README
    for readme_name in ("README.md", "readme.md", "README"):
        rp = module_root / readme_name
        if rp.is_file():
            text = safe_read(rp, limit=4096)
            if text:
                return first_paragraph(text)
    # package.json description
    pj = module_root / "package.json"
    if pj.is_file():
        try:
            data = json.loads(pj.read_text(encoding="utf-8", errors="replace"))
            if isinstance(data, dict) and data.get("description"):
                return str(data["description"])
        except (json.JSONDecodeError, OSError):
            pass
    # Python __init__.py docstring
    init = module_root / "__init__.py"
    if init.is_file():
        text = safe_read(init, limit=2048)
        if text:
            m = re.search(r'^"""(.+?)"""', text, flags=re.DOTALL | re.MULTILINE)
            if m:
                return first_paragraph(m.group(1).strip())
    return None


def safe_read(path: Path, limit: int = 65536) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except OSError:
        return ""


def first_paragraph(text: str) -> str:
    """Return the first non-empty, non-heading paragraph (trimmed)."""
    paragraphs = re.split(r"\n\s*\n", text.strip())
    for p in paragraphs:
        stripped = p.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        # Collapse whitespace
        return re.sub(r"\s+", " ", stripped)[:500]
    return ""


def find_dependencies(root: Path, max_per_ecosystem: int | None) -> list[dict[str, Any]]:
    """Scan well-known manifest files for direct external dependencies."""
    deps: list[dict[str, Any]] = []
    for filename, ecosystem in DEP_MANIFESTS:
        mp = root / filename
        if not mp.is_file():
            continue
        packages = parse_manifest(mp, ecosystem)
        if max_per_ecosystem is not None:
            packages = packages[:max_per_ecosystem]
        if packages:
            deps.append({
                "ecosystem": ecosystem,
                "file": filename,
                "count": len(packages),
                "packages": packages,
            })
    return deps


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


def build_data_model(root: Path, depth: str) -> dict[str, Any]:
    shallow = depth == "shallow"
    max_tree_depth = 2 if shallow else None
    max_modules = 10 if shallow else None
    max_deps_per_eco = 20 if shallow else None

    tree = walk_tree(root, max_tree_depth)
    languages = aggregate_languages(root)
    modules = detect_modules(root, max_modules)
    deps = find_dependencies(root, max_deps_per_eco)
    entry_points = detect_entry_points(root)
    readme = extract_readme(root)

    total_files = sum(lang["files"] for lang in languages)
    total_loc = sum(lang["loc"] for lang in languages)
    primary = languages[0]["name"] if languages else None

    return {
        "schema_version": 1,
        "tool_version": TOOL_VERSION,
        "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scan_depth": depth,
        "project": {
            "name": root.name or str(root),
            "root": str(root),
            "total_files": total_files,
            "total_loc": total_loc,
            "primary_language": primary,
        },
        "languages": languages,
        "tree": tree,
        "modules": modules,
        "deps": deps,
        "entry_points": entry_points,
        "readme": readme,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan a repository and emit a JSON data model.")
    parser.add_argument("--path", required=True, help="Path to scan.")
    parser.add_argument("--depth", choices=("shallow", "full"), default="shallow")
    parser.add_argument("--out", required=True, help="Output JSON file path.")
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
