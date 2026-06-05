# Flow-Edge Validation (Slice A of v0.10.0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `validate_enrichment.py` refute fabricated flow wiring — warn when consecutive flow steps aren't connected in code — and teach the LLM (via SKILL.md) to confirm each step→step edge instead of chaining co-located modules.

**Architecture:** A new pure helper `_verify_step_edges(flow, repo_root)` reads each step's prior-step file and checks whether it textually references the next step (the next step's `symbol` as a whole word, or the PascalCase module name derived from the next step's filename). If neither appears, the steps are merely co-located, not called → a **warning** (never an error — indirect calls would false-negative). Wired into the existing `validate()` flows loop's warn channel. SKILL.md gains a "confirm the edge, co-location is not a call graph" instruction. No flow-schema change, no render change, no scanner change.

**Tech Stack:** Python 3.10+ stdlib only (`re`, `pathlib`), stdlib `unittest`.

**Spec:** `docs/superpowers/specs/2026-06-05-flow-edge-validation-design.md`

**Test runner:** `cd plugin/skills/map-repo/scripts && python3 -m unittest discover -s tests -t . -q`
Single module: `python3 -m unittest tests.test_validate_enrichment -v`

---

## File Structure

All paths under `plugin/skills/map-repo/`.

| File | Change | Responsibility |
|---|---|---|
| `scripts/validate_enrichment.py` | Modify | Add `import re`; add `_module_from_file` + `_read_capped` + `_verify_step_edges` helpers; call the verifier in the `validate()` flows loop, appending its results to `warnings`. |
| `scripts/tests/test_validate_enrichment.py` | Modify | New `StepEdgeVerificationTest` class: module derivation, connected-by-module, connected-by-symbol, co-located-unconnected (the fabrication shape), single-step, first-step-not-checked. |
| `SKILL.md` | Modify | Step 1.5 `flows` instructions: confirm each consecutive edge; co-location is not a call graph; act on `edge unverified` warnings. |

---

## Task 1: Step-edge verification in the validator

**Files:**
- Modify: `plugin/skills/map-repo/scripts/validate_enrichment.py`
- Test: `plugin/skills/map-repo/scripts/tests/test_validate_enrichment.py`

`validate_enrichment.py` currently imports `json, sys, pathlib.Path, typing.Any`. `validate(enr, repo_root, skeleton_ids=None, service_ids=None)` returns `(errors, warnings)`; its flows loop (around lines 62-81) validates each step's `file`/`symbol` and that the cited file exists. We add edge verification to that loop's warn channel.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_validate_enrichment.py`. The file already imports `unittest`, `Path`, `sys`, and `validate_enrichment as ve`. Add `import shutil` and `import tempfile` at the top if not present. Append this class:

```python
class StepEdgeVerificationTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _write(self, rel, text):
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return rel

    def _enr(self, steps):
        return {
            "schema_version": 1,
            "overview": {"what_it_is": "x", "what_it_does": "y",
                         "how_it_works": "z", "confidence": "high"},
            "classification": {"products": [], "vendored": []},
            "flows": [{"name": "f", "kind": "request", "trigger": "t",
                       "narration": "n", "terminates": "e", "steps": steps}],
        }

    def _edge_warnings(self, warnings):
        return [w for w in warnings if "does not reference" in w]

    def test_module_from_file(self):
        self.assertEqual(ve._module_from_file("lib/brevity/stripe_handler.ex"),
                         "StripeHandler")
        self.assertEqual(ve._module_from_file("a/b/notifier.ex"), "Notifier")

    def test_connected_by_module_call_no_warning(self):
        a = self._write("a.ex", "def go(c), do: StripeHandler.handle(c)\n")
        b = self._write("stripe_handler.ex", "def handle(c), do: c\n")
        enr = self._enr([{"label": "a", "file": a, "symbol": "go"},
                         {"label": "b", "file": b, "symbol": "handle"}])
        errors, warnings = ve.validate(enr, self.dir)
        self.assertEqual(errors, [])
        self.assertEqual(self._edge_warnings(warnings), [])

    def test_connected_by_symbol_no_warning(self):
        a = self._write("a.ex", "def go(c), do: send_mail(c)\n")
        b = self._write("mailer.ex", "def send_mail(c), do: c\n")
        enr = self._enr([{"label": "a", "file": a, "symbol": "go"},
                         {"label": "b", "file": b, "symbol": "send_mail"}])
        errors, warnings = ve.validate(enr, self.dir)
        self.assertEqual(errors, [])
        self.assertEqual(self._edge_warnings(warnings), [])

    def test_colocated_unconnected_warns(self):
        # The fabrication shape: the controller's file never references the handler.
        a = self._write("controller.ex", "def card_store(c), do: Repo.insert(pm)\n")
        b = self._write("stripe_handler.ex", "def handle(c), do: c\n")
        enr = self._enr([{"label": "a", "file": a, "symbol": "card_store"},
                         {"label": "b", "file": b, "symbol": "handle"}])
        errors, warnings = ve.validate(enr, self.dir)
        self.assertEqual(errors, [])
        self.assertTrue(any("does not reference" in w and "handle" in w
                            for w in warnings))

    def test_single_step_no_warning(self):
        a = self._write("a.ex", "def go(c), do: 1\n")
        enr = self._enr([{"label": "a", "file": a, "symbol": "go"}])
        _errors, warnings = ve.validate(enr, self.dir)
        self.assertEqual(self._edge_warnings(warnings), [])

    def test_first_step_not_checked(self):
        # Only the 1->2 edge is verified (step 1 has no predecessor); the prev
        # file references the next, so there is no warning.
        a = self._write("a.ex", "def go(c), do: Worker.run(c)\n")
        b = self._write("worker.ex", "def run(c), do: c\n")
        enr = self._enr([{"label": "a", "file": a, "symbol": "go"},
                         {"label": "b", "file": b, "symbol": "run"}])
        _errors, warnings = ve.validate(enr, self.dir)
        self.assertEqual(self._edge_warnings(warnings), [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_validate_enrichment.StepEdgeVerificationTest -v`
Expected: FAIL — `test_module_from_file` errors with `AttributeError: module 'validate_enrichment' has no attribute '_module_from_file'`; `test_colocated_unconnected_warns` fails because no edge warning is produced yet. (The "no warning" tests pass trivially since nothing warns — they lock the behavior once the feature exists.)

- [ ] **Step 3: Add `import re` and the helpers**

In `validate_enrichment.py`, add `re` to the imports (top of file, beside `import json`):

```python
import json
import re
import sys
```

Add these helpers just before `def validate(` (after the `_require` helper):

```python
_STEP_EDGE_READ_CAP = 256 * 1024


def _module_from_file(file: str) -> str:
    """Derive a PascalCase module name from a file path's basename.

    ``lib/brevity/stripe_handler.ex`` -> ``StripeHandler``. snake_case -> Pascal
    is Elixir-friendly; for files that aren't snake_case the result may simply
    not match, and the symbol-token check carries the verification instead."""
    stem = Path(file).stem
    parts = [p for p in stem.split("_") if p]
    return "".join(p[:1].upper() + p[1:] for p in parts)


def _read_capped(path: Path) -> str:
    """Read up to the cap; empty string on any failure (never raises)."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return fh.read(_STEP_EDGE_READ_CAP)
    except OSError:
        return ""


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
        symbol_hit = re.search(r"\b" + re.escape(cur_symbol) + r"\b", content)
        module_hit = bool(module) and re.search(
            r"\b" + re.escape(module) + r"\b", content)
        if not symbol_hit and not module_hit:
            out.append(
                f"step {i}→{i + 1}: {prev_file} does not reference "
                f"{cur_symbol!r} (co-location is not a call — verify the edge)"
            )
    return out
```

- [ ] **Step 4: Wire the verifier into the flows loop**

In `validate()`, the flows loop ends each flow iteration with the inner `for j, s in enumerate(steps):` step loop. Immediately after that inner loop (still inside `for i, f in enumerate(...)`), add:

```python
        for w in _verify_step_edges(f, repo_root):
            warnings.append(f"{where}: {w}")
```

(`where` is already bound to `f"flows[{i}]"` at the top of the loop. This runs only for flows with a valid non-empty `steps` list, because the loop `continue`s earlier when steps are missing/empty.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_validate_enrichment.StepEdgeVerificationTest -v`
Expected: PASS (all six).

- [ ] **Step 6: Run the full suite**

Run: `python3 -m unittest discover -s tests -t . -q`
Expected: OK. The existing `_valid()` fixture flow has a single step, so the new edge check adds no warning to it; all prior validator tests stay green.

- [ ] **Step 7: Commit**

```bash
git add plugin/skills/map-repo/scripts/validate_enrichment.py plugin/skills/map-repo/scripts/tests/test_validate_enrichment.py
git commit -m "feat: validator warns on unverified flow step->step edges (co-location is not a call)"
```
Use those exact paths only; never `git add -A` (the tree has unrelated untracked junk).

---

## Task 2: SKILL.md — confirm the edge

**Files:**
- Modify: `plugin/skills/map-repo/SKILL.md`

No automated test — the LLM contract. Verify by reading it back against the validator's warning.

- [ ] **Step 1: Add the edge-confirmation instruction**

In `SKILL.md`, find the `flows` schema paragraph that currently ends (around line 104):

```
  Every flow keeps the shape `name`, `kind` (`request`|`background`|`scheduled`|`state-machine`|`pipeline`|`bootstrap`), `trigger`, `narration`, `terminates`, `steps` (+ optional `skeleton_id`). **Every step must cite a real `file` + `symbol` you actually saw** (optional `line`, `note`). No uncited steps. There is no flow cap — coverage is the goal, the citation requirement is the quality gate.
```

Append to that paragraph (after "the citation requirement is the quality gate."):

```
 **Every consecutive step pair must be a real call you confirmed by reading step N's body** — step N must actually invoke or reference step N+1 (a module-qualified call like `StripeHandler.handle(...)`, or an imported function). **Co-location is not a call graph**: never chain modules that merely live near each other. If step N+1 is triggered by something *other* than step N (a worker enqueued elsewhere, a webhook mounted in `endpoint.ex`, a pub/sub subscriber, a scheduled job), it is a **separate flow** — cite the real trigger or split it out. If the validator prints `WARN: … does not reference …`, re-read the code and either fix the citation or remove the false step.
```

- [ ] **Step 2: Verify the wording matches the validator's warning**

Run: `grep -n "does not reference" plugin/skills/map-repo/scripts/validate_enrichment.py`
Expected: the warning string exists, so the SKILL.md reference to `WARN: … does not reference …` is accurate.

- [ ] **Step 3: Commit**

```bash
git add plugin/skills/map-repo/SKILL.md
git commit -m "docs: teach Step 1.5 to confirm each flow step->step edge (co-location is not a call)"
```

---

## Self-Review

**Spec coverage** (against `2026-06-05-flow-edge-validation-design.md`):
- §2a `_verify_step_edges` (consecutive pairs, symbol-OR-module reference, first-step skip, read cap) → Task 1. ✓
- §2a `_module_from_file` (snake→Pascal) → Task 1 (helper + `test_module_from_file`). ✓
- §2b warn-don't-fail + wired into flows-loop warn channel → Task 1 Step 4. ✓
- §2c SKILL.md two instructions → Task 2. ✓
- §4 testing matrix (connected-by-module, connected-by-symbol, co-located-unconnected, single-step, first-step-not-checked, module derivation) → Task 1 Step 1. ✓
- §5 no render change, no schema change → confirmed (only validator + docs touched). ✓

**Placeholder scan:** every code step contains real code; the `256 * 1024` cap and the exact warning string are concrete. No TODOs.

**Type consistency:** `_verify_step_edges(flow, repo_root) -> list[str]`, `_module_from_file(file) -> str`, `_read_capped(path) -> str` — same signatures in the Task 1 definition and the test references (`ve._module_from_file(...)`). The warning substring `"does not reference"` asserted by the tests matches the string emitted by `_verify_step_edges` and referenced in the SKILL.md grep check (Task 2 Step 2). The flows-loop wiring reuses the existing `where`/`warnings`/`repo_root` names already in `validate()`.

**Degradation invariant:** validator + SKILL.md only; no scanner or render change, so the golden body is untouched.
