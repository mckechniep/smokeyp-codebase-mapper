"""Validate a codemap.enrichment.json sidecar: structural schema checks
plus verification that every flow-step citation points at a real file.

Importable (validate / drop_invalid_flows) and runnable as a CLI that
exits non-zero on structural errors.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

CONFIDENCE = {"high", "medium", "low"}
FLOW_KINDS = {"request", "background", "scheduled", "state-machine", "pipeline", "bootstrap"}
SERVICE_KINDS = {"frontend", "backend", "library", "service"}


def _require(obj: dict, key: str, where: str, errors: list[str]) -> bool:
    if key not in obj or obj[key] in (None, ""):
        errors.append(f"{where}: missing required '{key}'")
        return False
    return True


_STEP_EDGE_READ_CAP = 256 * 1024


def _module_from_file(file: str) -> str:
    """Derive a PascalCase module name from a file path's basename.

    ``lib/brevity/stripe_handler.ex`` -> ``StripeHandler``. snake_case -> Pascal
    is Elixir-friendly; for files that aren't snake_case the result may simply
    not match, and the symbol-token check carries the verification instead."""
    stem = Path(file).stem
    parts = [p for p in re.split(r"[._]", stem) if p]
    return "".join(p[:1].upper() + p[1:] for p in parts)


def _read_capped(path: Path) -> str:
    """Read up to the cap; empty string on any failure (never raises)."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return fh.read(_STEP_EDGE_READ_CAP)
    except OSError:
        return ""


def _symbol_in(symbol: str, content: str) -> bool:
    """Whole-identifier search for a step symbol in file content.

    Anchors the left with a word boundary always; requires a right word
    boundary only when the symbol ends in a word char. Elixir predicate/bang
    names (``valid?``, ``save!``) end in ``\\W`` and could never satisfy a
    trailing ``\\b``, so the right boundary is dropped for them (the ``?``/``!``
    is its own terminator). For ordinary names the right ``\\b`` is kept so
    ``handle`` does not match ``handler``."""
    last = symbol[-1:]
    right = r"\b" if (last.isalnum() or last == "_") else ""
    return re.search(r"\b" + re.escape(symbol) + right, content) is not None


def _verify_step_edges(flow: dict[str, Any], repo_root: Path) -> list[str]:
    """Warn when consecutive flow steps are not connected in code.

    For each (prev, cur) pair, prev's file must textually reference cur — either
    cur's ``symbol`` as a whole word, or the module name derived from cur's
    file. If neither appears, the steps are merely co-located, not called, so a
    warning is emitted. The first step has no predecessor and is skipped.
    Warning, not error: indirect calls (message passing, Oban enqueue, pub/sub,
    behaviour callbacks) legitimately won't match a textual reference."""
    out: list[str] = []
    steps = flow.get("steps") or []
    for i in range(1, len(steps)):
        prev, cur = steps[i - 1], steps[i]
        prev_file = prev.get("file")
        cur_symbol = (cur.get("symbol") or "").strip()
        if not prev_file or not cur_symbol:
            continue  # missing-citation errors are reported by the step loop
        content = _read_capped(repo_root / prev_file)
        if not content:
            continue
        module = _module_from_file(cur.get("file") or "")
        symbol_hit = _symbol_in(cur_symbol, content)
        module_hit = bool(module) and re.search(
            r"\b" + re.escape(module) + r"\b", content)
        if not symbol_hit and not module_hit:
            out.append(
                f"step {i}→{i + 1}: {prev_file} does not reference "
                f"{cur_symbol!r} (co-location is not a call — verify the edge)"
            )
    return out


def validate(enr: dict[str, Any], repo_root: Path,
             skeleton_ids: set[str] | None = None,
             service_ids: set[str] | None = None) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). An empty errors list means structurally valid."""
    errors: list[str] = []
    warnings: list[str] = []
    skeleton_ids = skeleton_ids or set()
    service_ids = service_ids or set()

    if enr.get("schema_version") != 1:
        errors.append("schema_version must be 1")

    ov = enr.get("overview")
    if not isinstance(ov, dict):
        errors.append("overview: missing or not an object")
    else:
        for k in ("what_it_is", "what_it_does", "how_it_works"):
            _require(ov, k, "overview", errors)
        if ov.get("confidence") not in CONFIDENCE:
            errors.append("overview.confidence must be high|medium|low")

    cls = enr.get("classification", {})
    if not isinstance(cls, dict):
        errors.append("classification: missing or not an object")

    if isinstance(cls, dict):
        for i, s in enumerate(cls.get("services", []) or []):
            where = f"classification.services[{i}]"
            _require(s, "service_id", where, errors)
            if s.get("kind") not in SERVICE_KINDS:
                errors.append(f"{where}: kind must be one of {sorted(SERVICE_KINDS)}")
            sid = s.get("service_id")
            if sid and service_ids and sid not in service_ids:
                warnings.append(f"{where}: unknown service_id {sid!r} "
                                "(not a service in codemap.json)")

    for i, f in enumerate(enr.get("flows", [])):
        where = f"flows[{i}]"
        for k in ("name", "kind", "trigger", "terminates"):
            _require(f, k, where, errors)
        if f.get("kind") not in FLOW_KINDS:
            errors.append(f"{where}: kind must be one of {sorted(FLOW_KINDS)}")
        sid = f.get("skeleton_id")
        if sid and skeleton_ids and sid not in skeleton_ids:  # "" sentinel never warns
            warnings.append(f"{where}: unknown skeleton_id {sid!r} (not a route group in codemap.json)")
        steps = f.get("steps")
        if not isinstance(steps, list) or not steps:
            errors.append(f"{where}: must have a non-empty steps list")
            continue
        for j, s in enumerate(steps):
            sw = f"{where}.steps[{j}]"
            _require(s, "file", sw, errors)
            _require(s, "symbol", sw, errors)
            cited = s.get("file")
            if cited and not (repo_root / cited).is_file():
                errors.append(f"{sw}: cited file not found: {cited}")
        for w in _verify_step_edges(f, repo_root):
            warnings.append(f"{where}: {w}")
    for i, e in enumerate(enr.get("http_edges", []) or []):
        where = f"http_edges[{i}]"
        for k in ("source_service", "target_service", "path"):
            _require(e, k, where, errors)
        for endpoint_key in ("source_service", "target_service"):
            v = e.get(endpoint_key)
            if v and service_ids and v not in service_ids:
                warnings.append(f"{where}: unknown {endpoint_key} {v!r} "
                                "(not a service in codemap.json)")

    return errors, warnings


def drop_invalid_flows(enr: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    """Return a copy of enr with flows whose citations don't resolve removed."""
    kept = []
    for f in enr.get("flows", []):
        steps = f.get("steps") or []
        if steps and all(
            s.get("file") and (repo_root / s["file"]).is_file() and s.get("symbol")
            for s in steps
        ):
            kept.append(f)
    out = dict(enr)
    out["flows"] = kept
    return out


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="Validate codemap.enrichment.json")
    p.add_argument("--enrichment", required=True)
    p.add_argument("--repo", required=True, help="Repo root for citation checks")
    p.add_argument("--codemap", default=None,
                   help="Path to codemap.json; enables skeleton_id warnings")
    args = p.parse_args()
    enr = json.loads(Path(args.enrichment).read_text(encoding="utf-8"))
    skeleton_ids: set[str] = set()
    service_ids: set[str] = set()
    if args.codemap:
        try:
            cm = json.loads(Path(args.codemap).read_text(encoding="utf-8"))
            skeleton_ids = {s.get("id") for s in cm.get("flow_skeletons", []) if s.get("id")}
            service_ids = {s.get("id") for s in cm.get("services", []) if s.get("id")}
        except (OSError, ValueError):
            pass
    errors, warnings = validate(enr, Path(args.repo).expanduser().resolve(),
                                skeleton_ids, service_ids)
    for w in warnings:
        print(f"WARN: {w}", file=sys.stderr)
    if errors:
        for e in errors:
            print(f"INVALID: {e}", file=sys.stderr)
        return 1
    print("enrichment OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
