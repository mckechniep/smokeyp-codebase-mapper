"""Build a bounded, deterministic 'evidence pack' from a scanned data
model so an LLM can evaluate a repo without reading all of it.

The pack is a curated slice: the module list, plus truncated contents of
high-signal files (entry points, manifests, READMEs, route/schema files,
a representative file per top module), within a byte budget. Selection is
deterministic so the pack is reproducible.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# Per-file truncation and overall pack budget.
PER_FILE_BYTES = 6000
DEFAULT_BUDGET_BYTES = 200_000

MANIFEST_NAMES = (
    "package.json", "mix.exs", "go.mod", "pyproject.toml", "requirements.txt",
    "docker-compose.yml", "compose.yml", ".env.example", "Gemfile", "pom.xml",
    "build.gradle", "Cargo.toml", "composer.json",
)
README_NAMES = ("README.md", "readme.md", "README")
ROUTE_FILE_RE = re.compile(
    r"(router\.(ex|rb|ts|js)|urls\.py|routes\.rb|schema\.(ex|prisma|graphql|ts)"
    r"|\.graphql$|route\.(ts|js)$)"
)
ARCH_DOC_RE = re.compile(r"(ARCHITECTURE|CODEBASE_MAP)", re.IGNORECASE)


def _read_truncated(path: Path, limit: int = PER_FILE_BYTES) -> str | None:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except OSError:
        return None


def _rel(root: Path, p: Path) -> str:
    try:
        return str(p.relative_to(root))
    except ValueError:
        return str(p)


def _candidate_paths(root: Path, data: dict[str, Any]) -> list[Path]:
    """Deterministically ordered candidate files, most valuable first."""
    seen: set[Path] = set()
    ordered: list[Path] = []

    def add(p: Path) -> None:
        if p.is_file() and p not in seen:
            seen.add(p)
            ordered.append(p)

    # 1. Root README + root manifests + arch docs.
    for name in README_NAMES:
        add(root / name)
    for name in MANIFEST_NAMES:
        add(root / name)
    for p in sorted(root.glob("docs/*")):
        if p.is_file() and ARCH_DOC_RE.search(p.name):
            add(p)

    # 2. Entry points (already detected by the scanner).
    for ep in data.get("entry_points", []):
        f = ep.get("file")
        if f:
            add((root / f))

    # 3. Per-module manifests + READMEs (direct and nested sub-packages).
    for m in data.get("modules", []):
        mpath = m.get("path")
        if not mpath:
            continue
        mdir = root / mpath
        # Direct match (module root has the file).
        for name in README_NAMES:
            add(mdir / name)
        for name in MANIFEST_NAMES:
            add(mdir / name)
        # Sub-package walk: modules are often grouped dirs (e.g. "apps/")
        # containing multiple sub-packages each with their own manifest/README.
        manifest_set = set(README_NAMES) | set(MANIFEST_NAMES)
        for p in sorted(mdir.rglob("*")):
            if p.is_file() and p.name in manifest_set:
                add(p)

    # 4. Entry-point source files not caught above (index.ts, main.ts, etc.).
    ENTRY_RE = re.compile(r"^(index|main)\.(ts|tsx|js|jsx|py|go|rb|ex)$")
    for p in sorted(root.rglob("*")):
        if len(ordered) > 400:
            break
        if p.is_file() and ENTRY_RE.match(p.name):
            add(p)

    # 5. Route/schema files anywhere (bounded by sorted walk).
    for p in sorted(root.rglob("*")):
        if len(ordered) > 400:
            break
        if p.is_file() and ROUTE_FILE_RE.search(p.name):
            add(p)

    return ordered


def build_evidence_pack(
    root: Path, data: dict[str, Any], budget_bytes: int = DEFAULT_BUDGET_BYTES
) -> dict[str, Any]:
    """Return a deterministic, budget-capped evidence pack."""
    files: list[dict[str, Any]] = []
    used = 0
    omitted = 0
    for p in _candidate_paths(root, data):
        content = _read_truncated(p)
        if content is None:
            continue
        size = len(content.encode("utf-8"))
        if used and used + size > budget_bytes:
            omitted += 1
            continue
        files.append({"path": _rel(root, p), "content": content})
        used += size

    modules = [
        {
            "path": m.get("path"),
            "loc": m.get("loc"),
            "file_count": m.get("file_count"),
            "languages": m.get("languages", []),
            "current_description": m.get("description") or "",
        }
        for m in data.get("modules", [])
    ]

    return {
        "schema_version": 1,
        "project": data.get("project", {}),
        "modules": modules,
        "files": files,
        "signals_in_codemap": [
            "module_graph", "http_topology", "data_lineage", "deps", "services",
        ],
        "budget": {
            "budget_bytes": budget_bytes,
            "used_bytes": used,
            "omitted_count": omitted,
        },
    }
