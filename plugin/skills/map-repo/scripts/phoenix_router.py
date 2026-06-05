"""Deterministic Phoenix `router.ex` parser.

Pure, dependency-free, never raises. Parses a Phoenix router into a flat list
of HTTP endpoints: ``{"framework", "method", "path"}``. Handles verb macros,
``forward``, ``live``, nested ``scope`` path prefixes, and (a later task) full
``resources`` expansion. Anything it cannot cleanly expand emits the base
route(s) it can and logs to stderr — it never silently drops, and on any
internal error it returns the routes collected so far rather than raising.
Known limitation: a ``scope`` whose head is split across lines (path on one
line, ``do`` on the next) loses its path prefix (degrades to a neutral frame)
rather than composing it.
"""
from __future__ import annotations

import re
import sys

_VERB_RE = re.compile(r'^(get|post|put|patch|delete|head|options)\s+"([^"]*)"')
_FORWARD_RE = re.compile(r'^forward\s+"([^"]*)"\s*,\s*([A-Za-z0-9_.]+)')
_LIVE_RE = re.compile(r'^live\s+"([^"]*)"')
_SCOPE_RE = re.compile(r'^scope\b')
_SCOPE_PATH_RE = re.compile(r'"(/[^"]*)"')
_OPENS_BLOCK_RE = re.compile(r'\bdo\s*$')
_END_RE = re.compile(r'^end\b')

_RESOURCES_RE = re.compile(r'^resources\s+"([^"]*)"\s*(?:,\s*[A-Za-z0-9_.]+)?(.*)$')
_ONLY_RE = re.compile(r'only:\s*\[([^\]]*)\]')
_EXCEPT_RE = re.compile(r'except:\s*\[([^\]]*)\]')
_PARAM_RE = re.compile(r'param:\s*"([^"]*)"')
_SINGLETON_RE = re.compile(r'singleton:\s*true')

# (method, suffix, action). ':id' is substituted with the configured param.
_RESOURCE_ROUTES = [
    ("GET", "", "index"), ("GET", "/new", "new"), ("POST", "", "create"),
    ("GET", "/:id", "show"), ("GET", "/:id/edit", "edit"),
    ("PATCH", "/:id", "update"), ("PUT", "/:id", "update"),
    ("DELETE", "/:id", "delete"),
]
_SINGLETON_ROUTES = [  # singleton: no index, no :id segment
    ("GET", "/new", "new"), ("POST", "", "create"), ("GET", "", "show"),
    ("GET", "/edit", "edit"), ("PATCH", "", "update"), ("PUT", "", "update"),
    ("DELETE", "", "delete"),
]


def _singularize(base: str) -> str:
    name = base.strip("/").split("/")[-1]
    return name[:-1] if name.endswith("s") else name


def _atoms(group: str) -> set:
    return {a.strip().lstrip(":").strip() for a in group.split(",") if a.strip()}


def _expand_resources(prefix: str, base: str, opts: str) -> list:
    base_seg = _norm_seg(base)
    table = _SINGLETON_ROUTES if _SINGLETON_RE.search(opts) else _RESOURCE_ROUTES
    only = _ONLY_RE.search(opts)
    keep = _atoms(only.group(1)) if only else None
    exc = _EXCEPT_RE.search(opts)
    drop = _atoms(exc.group(1)) if exc else set()
    pm = _PARAM_RE.search(opts)
    id_seg = pm.group(1) if pm else "id"

    out: list = []
    for method, suffix, action in table:
        if keep is not None and action not in keep:
            continue
        if action in drop:
            continue
        path = (prefix + base_seg + suffix.replace(":id", ":" + id_seg)) or "/"
        out.append({"framework": "Phoenix", "method": method, "path": path})
    return out


def _norm_seg(p: str) -> str:
    """Normalize a path piece to '/foo' with no trailing slash; '/' -> ''."""
    p = (p or "").strip()
    if not p or p == "/":
        return ""
    if not p.startswith("/"):
        p = "/" + p
    return p.rstrip("/")


def parse_router(text: str) -> list[dict]:
    endpoints: list[dict] = []
    try:
        _parse(text, endpoints)
    except Exception as exc:  # never raise — return what we have
        print(f"[phoenix_router] parse error ({type(exc).__name__}); "
              "returning partial routes", file=sys.stderr)
    return endpoints


def _parse(text: str, endpoints: list[dict]) -> None:
    frames: list[str] = []  # stack of path-prefix contributions ("" = neutral)

    def prefix() -> str:
        return "".join(frames)

    def add(framework: str, method: str, path: str) -> None:
        endpoints.append({"framework": framework, "method": method,
                          "path": (prefix() + _norm_seg(path)) or "/"})

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        opens = bool(_OPENS_BLOCK_RE.search(line))

        m = _VERB_RE.match(line)
        if m:
            add("Phoenix", m.group(1).upper(), m.group(2))
            if opens:
                frames.append("")
            continue

        m = _LIVE_RE.match(line)
        if m:
            add("Phoenix LiveView", "GET", m.group(1))
            if opens:
                frames.append("")
            continue

        m = _FORWARD_RE.match(line)
        if m:
            plug = m.group(2)
            add("Absinthe" if "Absinthe" in plug else "Phoenix", "ALL", m.group(1))
            if opens:
                frames.append("")
            continue

        if _SCOPE_RE.match(line) and opens:
            pm = _SCOPE_PATH_RE.search(line)
            frames.append(_norm_seg(pm.group(1)) if pm else "")
            continue

        m = _RESOURCES_RE.match(line)
        if m:
            base, opts = m.group(1), (m.group(2) or "")
            endpoints.extend(_expand_resources(prefix(), base, opts))
            if opens:  # nested resources: children get '/base/:singular_id'
                frames.append(_norm_seg(base) + "/:" + _singularize(base) + "_id")
            continue
        if line.startswith("resources ") and not m:  # log-don't-drop
            print(f"[phoenix_router] could not parse resources line: {line[:80]!r}",
                  file=sys.stderr)

        if opens:  # any other block opener (pipeline/def/defmodule/…)
            frames.append("")
            continue

        if _END_RE.match(line):
            if frames:
                frames.pop()
            continue
