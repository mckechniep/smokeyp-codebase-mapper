"""Validate a codemap.enrichment.json sidecar: structural schema checks
plus verification that every flow-step citation points at a real file.

Importable (validate / drop_invalid_flows) and runnable as a CLI that
exits non-zero on structural errors.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

CONFIDENCE = {"high", "medium", "low"}
FLOW_KINDS = {"request", "background", "scheduled", "state-machine", "pipeline", "bootstrap"}


def _require(obj: dict, key: str, where: str, errors: list[str]) -> bool:
    if key not in obj or obj[key] in (None, ""):
        errors.append(f"{where}: missing required '{key}'")
        return False
    return True


def validate(enr: dict[str, Any], repo_root: Path,
             skeleton_ids: set[str] | None = None) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). An empty errors list means structurally valid."""
    errors: list[str] = []
    warnings: list[str] = []
    skeleton_ids = skeleton_ids or set()

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
    if args.codemap:
        try:
            cm = json.loads(Path(args.codemap).read_text(encoding="utf-8"))
            skeleton_ids = {s.get("id") for s in cm.get("flow_skeletons", []) if s.get("id")}
        except (OSError, ValueError):
            pass
    errors, warnings = validate(enr, Path(args.repo).expanduser().resolve(), skeleton_ids)
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
