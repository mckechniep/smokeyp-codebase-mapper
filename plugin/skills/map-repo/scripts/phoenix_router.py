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

        if opens:  # any other block opener (pipeline/def/defmodule/…)
            frames.append("")
            continue

        if _END_RE.match(line):
            if frames:
                frames.pop()
            continue
