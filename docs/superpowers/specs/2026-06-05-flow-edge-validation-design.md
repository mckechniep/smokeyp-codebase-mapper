# Flow-Edge Validation (Slice A of v0.10.0) — Design

**Date:** 2026-06-05
**Status:** Approved (design); pending spec review → plan
**Target:** 0.10.0 (Slice A of three: this slice + product-scoping + Ecto lineage)

---

## 1. Problem

`validate_enrichment.py` validates each flow step's citation by checking only that the `file` exists and the `symbol` is non-empty. It never checks that **step N actually calls step N+1**. So the LLM-enrichment step is free to chain plausible, co-located modules into a flow that reads perfectly and passes validation — a *fabricated call graph*.

Observed on brevity (both confirmed false against source):
- **"Payment card storage webhook" → `Brevity.StripeHandler`** — the card-store controller (`EnigmaVaultController.card_store/2`) only does `Repo.insert(%BrevitySchemas.PaymentMethod{})`. `StripeHandler` is an unrelated Stripe webhook handler mounted in `endpoint.ex`. The flow invented the link.
- **"Member notifications (Braze)": `Notifier` → `BrazeWorker` → `BrazeMailer`** — `Notifier.send_notification/3` POSTs to Braze directly and synchronously. `BrazeWorker` is enqueued by the domain module (`brevity.ex:1695`), not by `Notifier`. Two unrelated mechanisms conflated into one chain.

Both passed because every cited file exists. **Co-location is not a call graph**, and the validator couldn't tell the difference.

This is the highest-leverage fix in the audit: a scanner gap produces *visible absence*; an LLM fabrication produces *invisible presence* (confident fiction citing real files). The validator must be able to refute the LLM's connective tissue.

## 2. Design

Deterministic-core + LLM-overlay, validator side. Two changes: a verification check in the validator (warn channel), and an instruction change in `SKILL.md`. No flow-schema change, no new fields, no render change, no scanner change.

### 2a. `_verify_step_edges(flow, repo_root) -> list[str]` (new pure helper)

For a flow with `steps`, walk consecutive pairs `(prev, cur)` for `i` in `1..len(steps)-1`:
1. Read `prev["file"]`'s content under `repo_root` (size-capped, e.g. 256 KB; reuse the same resolution the existing file-existence check uses).
2. Compute the set of reference candidates for `cur`:
   - `cur["symbol"]` as a whole-word token (`\bsymbol\b`), and
   - the module name derived from `cur["file"]` basename: strip the extension, split on `_`, PascalCase each part (`lib/brevity/stripe_handler.ex` → `StripeHandler`). Snake-case → Pascal is Elixir-friendly; other languages fall back to the symbol token.
3. If **neither** candidate appears in `prev`'s content → emit a warning:
   `step <N>→<N+1>: <prevFile> does not reference <curSymbol> (co-location is not a call — verify the edge)`.

The helper returns relative warnings; `validate()` prefixes each with `flows[{i}]: ` (matching the existing warning style).

**Why "neither appears → warn":** require only one weak signal of connection to stay quiet (a module-qualified call `StripeHandler.handle(...)` matches the module name; an imported-function call `send_mail(...)` matches the symbol). Warn only when *no* reference exists at all — a strong signal the steps are merely co-located. This errs toward few false alarms; the `SKILL.md` instruction is the primary defense, the validator the backstop.

### 2b. Semantics — warn, never error

Unverified edges are **warnings**, not errors. Indirect calls, dynamic dispatch, message passing (`send/2`, Oban enqueue, pub/sub), and behaviour callbacks are legitimate and a pure-grep can't see them — a hard error would block valid flows. Warnings surface the suspicious edge for the LLM/user to verify without blocking the render. The **first step is never checked** (no predecessor; its "edge" is the trigger — HTTP/schedule/boot — not a code call).

Wire into the existing flows loop in `validate()`: after the per-step file/symbol checks, `for w in _verify_step_edges(f, repo_root): warnings.append(f"flows[{i}]: {w}")`. The CLI already prints `WARN:` lines to stderr.

### 2c. `SKILL.md` — make the warnings actionable

Add to the Step 1.5 `flows` instructions:
1. *"Each consecutive step pair must be a real call/reference you confirmed by reading step N's body — not two co-located modules you assume are wired. **Co-location is not a call graph.**"*
2. *"If step N+1 is triggered by something other than step N (a worker enqueued elsewhere, a webhook mounted in `endpoint.ex`, a pub/sub subscriber), it is a **separate flow** — cite the real trigger or split it. If the validator WARNs `edge unverified`, re-read the code and either fix the citation or remove the false step."*

## 3. Components & boundaries

| Unit | Responsibility | Depends on |
|---|---|---|
| `_verify_step_edges(flow, repo_root)` | Pure: given a flow + repo root, return edge-verification warnings | filesystem read (capped), stdlib `re` |
| `_module_from_file(file)` | Pure: derive a PascalCase module name from a file path | none |
| `validate()` flows loop | Calls the helper, prefixes warnings | `_verify_step_edges` |
| `SKILL.md` Step 1.5 | LLM contract: confirm edges, don't chain co-location | — |

## 4. Testing

`tests/test_validate_enrichment.py` (extend), using temp files for step content:
- **Connected by module call** (`prev` file contains `CurModule.fn(...)`) → no warning.
- **Connected by imported symbol** (`prev` file contains a bare `cur_symbol(...)`) → no warning.
- **Co-located but unconnected** (two real files, neither references the other — the fabrication shape) → warning naming the symbol.
- **Single-step flow** → no warning (nothing to verify).
- **First step never checked** → a 2-step flow only checks the 1→2 edge.
- `_module_from_file("lib/a/stripe_handler.ex") == "StripeHandler"`.
- Existing validator tests stay green; warnings never become errors.

Golden body is untouched (validator + docs only).

## 5. Out of scope / known limitations

- **Indirect-call false negatives are accepted** — message passing, Oban enqueue, pub/sub, behaviour callbacks won't textually match and will warn even when legitimate. That is the intended degradation: the LLM re-reads and confirms. We do *not* hard-fail on them.
- **No render-time drop.** Fabricated flows still render if the LLM ignores the warning; the gate is the LLM acting on the warning during enrichment, plus the human seeing `WARN:` lines. A render-time drop on a heuristic with false negatives would silently remove valid flows — rejected.
- **No flow-schema change** (no explicit per-transition call-site field). That stronger "(a)" variant is deferred; revisit only if (b) proves too coarse in practice.
