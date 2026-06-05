# Elixir/Phoenix Support + Enrichment Overrides Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the mapper produce a correct System Architecture diagram on Elixir/Phoenix (and other non-JS/TS/Python) codebases — by teaching the deterministic scanner to read Elixir manifests and Phoenix routers, and by giving the LLM enrichment layer a lever to correct a service's tier and assert HTTP edges it can see.

**Architecture:** Same deterministic-core / LLM-overlay seam as the existing evaluation layer. `scan.py` gets structured manifest token-matching (kills substring false positives like `expo` matching `:export_gql_schema`), Elixir/BEAM backend hints, and a new `phoenix_router.py` endpoint extractor wired through `_scan_endpoints_file`. `validate_enrichment.py` accepts two new optional fields (`classification.services` for a kind override, top-level `http_edges` for LLM-asserted edges) with warn-on-unknown. `render.py` applies those overrides as a pure data transform at the top of `render_document`, and draws inferred edges with a distinct (dotted/faint) modifier. `render.py` also widens the dependency-matrix frame to the System Map's full-bleed width.

**Tech Stack:** Python 3.10+ stdlib only, stdlib `unittest`, inline dependency-free JS/CSS in the rendered HTML. No new third-party dependencies.

**Spec:** `docs/superpowers/specs/2026-06-05-elixir-phoenix-and-enrichment-overrides-design.md`

**Test runner:** `cd plugin/skills/map-repo/scripts && python3 -m unittest discover -s tests -t . -q`
Single module: `python3 -m unittest tests.<module> -v`

---

## File Structure

All paths under `plugin/skills/map-repo/`.

| File | Change | Responsibility |
|---|---|---|
| `scripts/scan.py` | Modify | `_manifest_tokens` + `_hit` helpers; rewrite `_classify_service` matching; add BEAM hints; lift `SCANNABLE` to module-level + add `Elixir`; Elixir branch in `_scan_endpoints_file`. |
| `scripts/phoenix_router.py` | **Create** | Pure Phoenix `router.ex` parser: verbs, `forward`, `live`, `scope` nesting, full `resources` expansion. Never raises; logs-don't-drops. |
| `scripts/validate_enrichment.py` | Modify | Accept optional `classification.services` (kind override) + top-level `http_edges`; warn on unknown service ids; CLI loads service ids from codemap. |
| `scripts/render.py` | Modify | `_apply_enrichment_overrides` (kind + edge injection) at top of `render_document`; carry `inferred` through `_sysmap_edges`; distinct emit class in `_sysmap_emit_svg`; CSS for inferred edge + legend note; widen `.modgraph-frame`. |
| `SKILL.md` | Modify | Teach Step 1.5 to emit `classification.services` + `http_edges`. |
| `.claude-plugin/plugin.json` | Modify | Version `0.8.0` → `0.9.0`. |
| `scripts/tests/test_classify_service.py` | **Create** | Token matching, `expo` regression, scope/full-id forms, Phoenix/lib classification. |
| `scripts/tests/test_phoenix_router.py` | **Create** | Verbs, forward, live, scope nesting, full `resources` expansion, never-raise. |
| `scripts/tests/test_scan_elixir_endpoints.py` | **Create** | `SCANNABLE` includes Elixir; `_scan_endpoints_file` parses a router.ex. |
| `scripts/tests/test_render_overrides.py` | **Create** | `_apply_enrichment_overrides` kind + edge injection; inferred edge distinct render. |
| `scripts/tests/test_validate_enrichment.py` | Modify | `classification.services` + `http_edges` accepted; bad kind errors; unknown id warns. |
| `scripts/tests/test_render_system_map.py` | Modify (maybe) | Width-frame assertion; regenerate expectations only if a deterministic change is intended. |

---

# SLICE 1 — Classification correctness + diagram width

## Task 1: Structured manifest token matching

**Files:**
- Modify: `plugin/skills/map-repo/scripts/scan.py` (add helpers near `_classify_service` at lines 365-407; rewrite the match loop)
- Test: `plugin/skills/map-repo/scripts/tests/test_classify_service.py` (create)

`scan.py` already imports `json`, `re`, and `Counter` at the top (lines 15-19) — no new imports needed.

- [ ] **Step 1: Write the failing test**

Create `tests/test_classify_service.py`:

```python
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scan


class ManifestTokenTest(unittest.TestCase):
    def test_package_json_reads_dependency_keys(self):
        text = '{"dependencies": {"react": "^18"}, "devDependencies": {"vite": "^5"}}'
        toks = scan._manifest_tokens("package.json", text)
        self.assertIn("react", toks)
        self.assertIn("vite", toks)

    def test_package_json_ignores_script_bodies_and_versions(self):
        text = '{"scripts": {"build": "vite build"}, "dependencies": {"left-pad": "1.0.0"}}'
        toks = scan._manifest_tokens("package.json", text)
        self.assertIn("left-pad", toks)
        self.assertNotIn("vite", toks)  # vite appears only in a script body, not a dep

    def test_mix_exs_tokenizes_atoms_not_substrings(self):
        text = ("compilers: [:boundary, :phoenix, :gettext] ++ [:export_gql_schema]\n"
                "{:absinthe, \"~> 1.7\"}")
        toks = scan._manifest_tokens("mix.exs", text)
        self.assertIn("phoenix", toks)
        self.assertIn("absinthe", toks)
        self.assertIn("export_gql_schema", toks)  # the whole token survives
        self.assertNotIn("expo", toks)             # NOT a substring of export_gql_schema


class HitTest(unittest.TestCase):
    def test_bare_name_is_exact(self):
        self.assertTrue(scan._hit("react", {"react"}))
        self.assertFalse(scan._hit("expo", {"export_gql_schema"}))

    def test_scope_prefix(self):
        self.assertTrue(scan._hit("@nestjs/", {"@nestjs/core"}))
        self.assertFalse(scan._hit("@nestjs/", {"nestjs"}))

    def test_full_module_id(self):
        self.assertTrue(scan._hit("github.com/gin-gonic/gin",
                                  {"github.com/gin-gonic/gin"}))


class ClassifyServiceTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _write(self, name, text):
        (self.dir / name).write_text(text)

    def test_phoenix_mix_exs_is_not_frontend(self):
        # The brevity regression: expo must NOT match inside :export_gql_schema.
        self._write("mix.exs",
                    "compilers: [:phoenix, :gettext] ++ [:export_gql_schema]\n")
        kind, _stack = scan._classify_service(self.dir)
        self.assertNotEqual(kind, "frontend")

    def test_react_package_json_is_frontend(self):
        self._write("package.json", '{"dependencies": {"react": "^18", "react-dom": "^18"}}')
        kind, _stack = scan._classify_service(self.dir)
        self.assertEqual(kind, "frontend")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_classify_service -v`
Expected: FAIL — `AttributeError: module 'scan' has no attribute '_manifest_tokens'` for the helper tests, and `test_phoenix_mix_exs_is_not_frontend` FAILS because the current substring code matches `expo` inside `:export_gql_schema` → returns `"frontend"`. (`test_react_package_json_is_frontend` already passes.)

- [ ] **Step 3: Implement the helpers + rewrite the matcher**

In `scan.py`, immediately before `def _classify_service` (line 374), add:

```python
_MANIFEST_TOKEN_RE = re.compile(r"[A-Za-z0-9_.@/-]+")
_JSON_DEP_KEYS = ("dependencies", "devDependencies", "peerDependencies",
                  "optionalDependencies", "require", "require-dev")


def _manifest_tokens(name: str, text: str) -> set[str]:
    """Identifier tokens to match framework hints against.

    JSON manifests (package.json / deno.json / composer.json) are parsed and
    only their dependency KEYS are returned — exact, no version strings or
    script bodies. Every other manifest format (mix.exs, go.mod, Cargo.toml,
    pyproject.toml, Gemfile, gradle, …) is tokenized on identifier boundaries,
    so ``:phoenix`` -> ``phoenix`` and ``export_gql_schema`` stays one token
    (it can never match the substring ``expo``)."""
    if name in ("package.json", "deno.json", "composer.json"):
        try:
            data = json.loads(text)
        except ValueError:
            data = {}
        toks: set[str] = set()
        if isinstance(data, dict):
            for k in _JSON_DEP_KEYS:
                d = data.get(k)
                if isinstance(d, dict):
                    toks.update(d.keys())
        return {t.lower() for t in toks}
    return {t.lower() for t in _MANIFEST_TOKEN_RE.findall(text)}


def _hit(hint: str, tokens: set[str]) -> bool:
    """True if a framework hint matches the manifest's tokens.

    ``"@nestjs/"`` (trailing slash) is a scope prefix -> any token starting
    with it. Everything else — bare names (``react``) and full module ids
    (``github.com/gin-gonic/gin``, kept whole by the tokenizer) — is an exact
    token match."""
    h = hint.lower()
    if h.endswith("/"):
        return any(t.startswith(h) for t in tokens)
    return h in tokens
```

Then replace the body of `_classify_service` (the manifest-read through the match loop, lines 380-393) so the matching uses tokens:

```python
    manifest = _read_manifest_text(container)
    if not manifest:
        return ("unknown", [])
    name, text = manifest
    tokens = _manifest_tokens(name, text)
    found_frontend = [h for h in FRONTEND_FRAMEWORK_HINTS if _hit(h, tokens)]
    found_backend = [h for h in BACKEND_FRAMEWORK_HINTS if _hit(h, tokens)]
    stack = sorted(set(found_frontend + found_backend))
```

Leave the decision tree below it (lines 395-407, `if found_backend and not found_frontend:` …) exactly as-is.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_classify_service -v`
Expected: PASS (all tests). `test_phoenix_mix_exs_is_not_frontend` now returns `"library"` (no Elixir hints yet, so neither frontend nor backend matches) — which is `!= "frontend"`, so it passes.

- [ ] **Step 5: Run the full suite**

Run: `python3 -m unittest discover -s tests -t . -q`
Expected: OK. If `test_render_system_map.py`'s fittalk-dependent or golden body test trips because token-matching legitimately *fixed* a fittalk misclassification, inspect the diff: regenerate the expectation ONLY if the change is a correct improvement, never to silence an unexpected change. (fittalk is TS-only with clean package.json deps, so no change is the expected outcome.)

- [ ] **Step 6: Commit**

```bash
git add plugin/skills/map-repo/scripts/scan.py plugin/skills/map-repo/scripts/tests/test_classify_service.py
git commit -m "feat: structured manifest token matching kills substring false positives"
```

---

## Task 2: Elixir/BEAM backend hints

**Files:**
- Modify: `plugin/skills/map-repo/scripts/scan.py:347-362` (`BACKEND_FRAMEWORK_HINTS`)
- Test: `plugin/skills/map-repo/scripts/tests/test_classify_service.py` (extend)

- [ ] **Step 1: Write the failing test**

Add to `ClassifyServiceTest` in `tests/test_classify_service.py`:

```python
    def test_phoenix_mix_exs_is_backend(self):
        self._write("mix.exs",
                    "defp deps do\n"
                    "  [{:phoenix, \"~> 1.7\"}, {:absinthe, \"~> 1.7\"},\n"
                    "   {:ecto_sql, \"~> 3.10\"}, {:oban, \"~> 2.17\"}]\n"
                    "end\n")
        kind, stack = scan._classify_service(self.dir)
        self.assertEqual(kind, "backend")
        self.assertIn("phoenix", stack)

    def test_pure_elixir_library_is_library(self):
        self._write("mix.exs",
                    "defp deps do\n  [{:jason, \"~> 1.4\"}, {:telemetry, \"~> 1.2\"}]\nend\n")
        kind, _stack = scan._classify_service(self.dir)
        self.assertEqual(kind, "library")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_classify_service -v`
Expected: FAIL — `test_phoenix_mix_exs_is_backend` returns `"library"` (no Elixir hints yet), so `assertEqual(kind, "backend")` fails. `test_pure_elixir_library_is_library` already passes.

- [ ] **Step 3: Add the BEAM hints**

In `scan.py`, append to `BACKEND_FRAMEWORK_HINTS` (inside the tuple ending at line 362), before the closing `)`:

```python
    # Elixir / Erlang (BEAM) backends — matched as exact mix.exs deps tokens
    "phoenix", "plug", "plug_cowboy", "bandit", "absinthe",
    "ecto", "ecto_sql", "oban", "broadway",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_classify_service -v`
Expected: PASS. A Phoenix `mix.exs` now matches `phoenix`/`absinthe`/`ecto_sql`/`oban` → `found_backend` non-empty, `found_frontend` empty → `backend`. A pure lib matches nothing → `library`.

- [ ] **Step 5: Run the full suite**

Run: `python3 -m unittest discover -s tests -t . -q`
Expected: OK.

- [ ] **Step 6: Commit**

```bash
git add plugin/skills/map-repo/scripts/scan.py plugin/skills/map-repo/scripts/tests/test_classify_service.py
git commit -m "feat: classify Elixir/Phoenix services as backend (BEAM framework hints)"
```

---

## Task 3: Widen the dependency-matrix frame

**Files:**
- Modify: `plugin/skills/map-repo/scripts/render.py:494-505` (`.modgraph-frame` CSS)
- Test: `plugin/skills/map-repo/scripts/tests/test_render_system_map.py` (add one test)

- [ ] **Step 1: Write the failing test**

Add this test to `test_render_system_map.py` (it can live in the existing `FocusCssTest` class, or a new small class — place it after `FocusCssTest`):

```python
class ModgraphWidthTest(unittest.TestCase):
    def _rule_body(self, css, selector):
        import re as _re
        m = _re.search(_re.escape(selector) + r"\s*\{([^}]*)\}", css)
        return m.group(1) if m else ""

    def test_modgraph_frame_uses_full_bleed_breakout(self):
        body = self._rule_body(render.CSS, ".modgraph-frame")
        self.assertIn("min(94vw, 1200px)", body)
        self.assertIn("calc(50% - min(47vw, 600px))", body)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_render_system_map.ModgraphWidthTest -v`
Expected: FAIL — current `.modgraph-frame` uses `margin-left: -56px`, so `min(94vw, 1200px)` is absent.

- [ ] **Step 3: Port the full-bleed breakout**

In `render.py`, replace the breakout lines inside `.modgraph-frame` (lines 501-504):

```css
  /* Escape past main's 780px text column on wider viewports to the same
     full-bleed canvas the System Map uses, so the matrix breathes. main is
     centered, so margin = 50% - halfWidth re-centers this wider child.
     Collapses back to 0 on narrow screens (media query below). */
  width: min(94vw, 1200px);
  margin-left: calc(50% - min(47vw, 600px));
  margin-right: calc(50% - min(47vw, 600px));
```

Leave the existing `@media (max-width: 880px) { .modgraph-frame { margin-left: 0; margin-right: 0; } }` block (lines 506-511) as-is — it still neutralizes the breakout on narrow screens. (Add `width: auto;` to that media block so the narrow override fully resets, matching `.sysmap-frame`'s media block at render.py:540-542.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_render_system_map.ModgraphWidthTest -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `python3 -m unittest discover -s tests -t . -q`
Expected: OK (CSS-only change; golden body unaffected because the golden compares the `<main>` body, not the `<style>` block — see `test_render_enrichment.py` `_body`).

- [ ] **Step 6: Commit**

```bash
git add plugin/skills/map-repo/scripts/render.py plugin/skills/map-repo/scripts/tests/test_render_system_map.py
git commit -m "feat: widen dependency-matrix frame to System Map full-bleed width"
```

---

# SLICE 2 — Phoenix router parser

## Task 4: `phoenix_router.py` — verbs, forward, live, scope nesting

**Files:**
- Create: `plugin/skills/map-repo/scripts/phoenix_router.py`
- Test: `plugin/skills/map-repo/scripts/tests/test_phoenix_router.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_phoenix_router.py`:

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import phoenix_router


def routes(text):
    return {(e["method"], e["path"]) for e in phoenix_router.parse_router(text)}


class VerbAndScopeTest(unittest.TestCase):
    def test_bare_verb_route(self):
        r = routes('get "/health", HealthController, :index\n')
        self.assertIn(("GET", "/health"), r)

    def test_scope_prefix_composes(self):
        text = ('scope "/api", AppWeb do\n'
                '  post "/login", AuthController, :login\n'
                'end\n')
        self.assertIn(("POST", "/api/login"), routes(text))

    def test_nested_scope_prefixes_stack(self):
        text = ('scope "/api", AppWeb do\n'
                '  scope "/v1" do\n'
                '    get "/me", UserController, :me\n'
                '  end\n'
                'end\n')
        self.assertIn(("GET", "/api/v1/me"), routes(text))

    def test_forward_graphql_is_absinthe(self):
        text = 'forward "/graphql", Absinthe.Plug, schema: App.Schema\n'
        eps = phoenix_router.parse_router(text)
        gql = [e for e in eps if e["path"] == "/graphql"]
        self.assertTrue(gql)
        self.assertEqual(gql[0]["framework"], "Absinthe")

    def test_live_route(self):
        text = 'live "/admin/dashboard", DashboardLive\n'
        eps = phoenix_router.parse_router(text)
        live = [e for e in eps if e["path"] == "/admin/dashboard"]
        self.assertTrue(live)
        self.assertEqual(live[0]["method"], "GET")
        self.assertEqual(live[0]["framework"], "Phoenix LiveView")

    def test_pipeline_block_does_not_corrupt_scope_stack(self):
        # A pipeline do/end block must push+pop a neutral frame so the scope
        # prefix that follows is not lost.
        text = ('pipeline :browser do\n'
                '  plug :accepts, ["html"]\n'
                'end\n'
                'scope "/api" do\n'
                '  get "/ping", PingController, :ping\n'
                'end\n')
        self.assertIn(("GET", "/api/ping"), routes(text))

    def test_never_raises_on_garbage(self):
        self.assertEqual(phoenix_router.parse_router("@#$%^ not elixir {{{"), [])
        self.assertEqual(phoenix_router.parse_router(""), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_phoenix_router -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'phoenix_router'`.

- [ ] **Step 3: Create `phoenix_router.py` (no resources yet)**

```python
"""Deterministic Phoenix `router.ex` parser.

Pure, dependency-free, never raises. Parses a Phoenix router into a flat list
of HTTP endpoints: ``{"framework", "method", "path"}``. Handles verb macros,
``forward``, ``live``, nested ``scope`` path prefixes, and (Task 5) full
``resources`` expansion. Anything it cannot cleanly expand emits the base
route(s) it can and logs to stderr — it never silently drops, and on any
internal error it returns the routes collected so far rather than raising.
"""
from __future__ import annotations

import re
import sys

_VERB_RE = re.compile(r'^(get|post|put|patch|delete|head|options)\s+"([^"]*)"', re.I)
_FORWARD_RE = re.compile(r'^forward\s+"([^"]*)"\s*,\s*([A-Za-z0-9_.]+)')
_LIVE_RE = re.compile(r'^live\s+"([^"]*)"')
_SCOPE_RE = re.compile(r'^scope\b')
_SCOPE_PATH_RE = re.compile(r'"(/[^"]*)"')
_OPENS_BLOCK_RE = re.compile(r'\bdo\s*$')


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

        if line == "end" or line.startswith("end "):
            if frames:
                frames.pop()
            continue
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_phoenix_router -v`
Expected: PASS (all in `VerbAndScopeTest`).

- [ ] **Step 5: Commit**

```bash
git add plugin/skills/map-repo/scripts/phoenix_router.py plugin/skills/map-repo/scripts/tests/test_phoenix_router.py
git commit -m "feat: Phoenix router parser (verbs, forward, live, scope nesting)"
```

---

## Task 5: `resources` expansion (full, log-don't-drop)

**Files:**
- Modify: `plugin/skills/map-repo/scripts/phoenix_router.py`
- Test: `plugin/skills/map-repo/scripts/tests/test_phoenix_router.py` (extend)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_phoenix_router.py`:

```python
class ResourcesTest(unittest.TestCase):
    def test_base_resources_expands_to_seven_actions(self):
        r = routes('resources "/users", UserController\n')
        self.assertEqual(r, {
            ("GET", "/users"), ("GET", "/users/new"), ("POST", "/users"),
            ("GET", "/users/:id"), ("GET", "/users/:id/edit"),
            ("PATCH", "/users/:id"), ("PUT", "/users/:id"),
            ("DELETE", "/users/:id"),
        })

    def test_resources_only(self):
        r = routes('resources "/users", UserController, only: [:index, :show]\n')
        self.assertEqual(r, {("GET", "/users"), ("GET", "/users/:id")})

    def test_resources_except(self):
        r = routes('resources "/users", UserController, except: [:delete, :new, :edit]\n')
        self.assertNotIn(("DELETE", "/users/:id"), r)
        self.assertNotIn(("GET", "/users/new"), r)
        self.assertIn(("GET", "/users"), r)

    def test_resources_param(self):
        r = routes('resources "/users", UserController, param: "uuid"\n')
        self.assertIn(("GET", "/users/:uuid"), r)
        self.assertNotIn(("GET", "/users/:id"), r)

    def test_resources_singleton_drops_index_and_id(self):
        r = routes('resources "/account", AccountController, singleton: true\n')
        self.assertIn(("GET", "/account"), r)         # show, no :id
        self.assertIn(("PATCH", "/account"), r)       # update, no :id
        self.assertNotIn(("GET", "/account/:id"), r)
        # singleton has no index collection route distinct from show; both are /account GET
        self.assertNotIn(("GET", "/account/:id/edit"), r)

    def test_nested_resources_inject_parent_id(self):
        text = ('resources "/users", UserController do\n'
                '  resources "/posts", PostController, only: [:index]\n'
                'end\n')
        self.assertIn(("GET", "/users/:user_id/posts"), routes(text))

    def test_resources_under_scope(self):
        text = ('scope "/api" do\n'
                '  resources "/widgets", WidgetController, only: [:index]\n'
                'end\n')
        self.assertIn(("GET", "/api/widgets"), routes(text))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_phoenix_router.ResourcesTest -v`
Expected: FAIL — `resources` lines currently match no rule and emit nothing.

- [ ] **Step 3: Implement `resources` expansion**

In `phoenix_router.py`, add these module-level constants after `_OPENS_BLOCK_RE`:

```python
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


def _atoms(group: str) -> set[str]:
    return {a.strip().lstrip(":").strip() for a in group.split(",") if a.strip()}


def _expand_resources(prefix: str, base: str, opts: str) -> list[dict]:
    base_seg = _norm_seg(base)
    table = _SINGLETON_ROUTES if _SINGLETON_RE.search(opts) else _RESOURCE_ROUTES
    only = _ONLY_RE.search(opts)
    keep = _atoms(only.group(1)) if only else None
    exc = _EXCEPT_RE.search(opts)
    drop = _atoms(exc.group(1)) if exc else set()
    pm = _PARAM_RE.search(opts)
    id_seg = pm.group(1) if pm else "id"

    out: list[dict] = []
    for method, suffix, action in table:
        if keep is not None and action not in keep:
            continue
        if action in drop:
            continue
        path = (prefix + base_seg + suffix.replace(":id", ":" + id_seg)) or "/"
        out.append({"framework": "Phoenix", "method": method, "path": path})
    return out
```

Then, in `_parse`, add a `resources` branch BEFORE the generic `if opens:` neutral-frame branch (i.e. right after the `_SCOPE_RE` block):

```python
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
```

(`_expand_resources` already composes `prefix()`, so a nested or scoped resources block inherits its ancestors' prefixes. Nesting works to any depth via the frame stack — a second nested `resources … do` pushes another `/base/:id` frame.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_phoenix_router -v`
Expected: PASS (both `VerbAndScopeTest` and `ResourcesTest`).

- [ ] **Step 5: Commit**

```bash
git add plugin/skills/map-repo/scripts/phoenix_router.py plugin/skills/map-repo/scripts/tests/test_phoenix_router.py
git commit -m "feat: full Phoenix resources expansion (only/except/param/singleton/nesting)"
```

---

## Task 6: Wire the Elixir branch into the scanner

**Files:**
- Modify: `plugin/skills/map-repo/scripts/scan.py` (lift `SCANNABLE` to module level + add `Elixir`; Elixir branch in `_scan_endpoints_file`)
- Test: `plugin/skills/map-repo/scripts/tests/test_scan_elixir_endpoints.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_scan_elixir_endpoints.py`:

```python
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scan

ROUTER = (
    'defmodule AppWeb.Router do\n'
    '  use AppWeb, :router\n'
    '  scope "/api", AppWeb do\n'
    '    post "/login", AuthController, :login\n'
    '    forward "/graphql", Absinthe.Plug, schema: App.Schema\n'
    '  end\n'
    'end\n'
)


class ScannableTest(unittest.TestCase):
    def test_elixir_is_scannable(self):
        self.assertIn("Elixir", scan.SCANNABLE_LANGUAGES)


class ElixirEndpointTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.rel = "lib/app_web/router.ex"
        p = self.dir / self.rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(ROUTER)
        self.path = p

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_scan_endpoints_file_parses_phoenix_router(self):
        eps, fws = scan._scan_endpoints_file(self.path, "Elixir", self.rel, "app", "app")
        paths = {e["path"] for e in eps}
        self.assertIn("/api/login", paths)
        self.assertIn("/api/graphql", paths)
        self.assertIn("Absinthe", fws)

    def test_non_router_elixir_file_emits_nothing(self):
        other = self.dir / "lib/app/foo.ex"
        other.parent.mkdir(parents=True, exist_ok=True)
        other.write_text('get "/x", C, :i\n')  # not a router.ex -> ignored
        eps, _fws = scan._scan_endpoints_file(other, "Elixir", "lib/app/foo.ex", "app", "app")
        self.assertEqual(eps, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_scan_elixir_endpoints -v`
Expected: FAIL — `AttributeError: module 'scan' has no attribute 'SCANNABLE_LANGUAGES'`, and the endpoint test fails because `_scan_endpoints_file` has no Elixir branch.

- [ ] **Step 3: Lift `SCANNABLE` to module level + add `Elixir`**

In `scan.py`, near the other module-level constants (e.g. just before `def build_http_topology` at line 1909, or beside `GRAPH_LANGUAGES` at line 1012), add:

```python
SCANNABLE_LANGUAGES: frozenset[str] = frozenset({
    "TypeScript", "JavaScript", "Python", "Go", "Ruby", "Java", "Kotlin", "PHP",
    "Elixir",
})
```

Then in `build_http_topology`, delete the local `SCANNABLE = frozenset({...})` block (lines 1935-1937) and change the membership check (line 1944) to use the module constant:

```python
        if lname not in SCANNABLE_LANGUAGES:
            continue
```

- [ ] **Step 4: Add the Elixir branch in `_scan_endpoints_file`**

At the top of `scan.py`, add `import phoenix_router` beside the other sibling imports (line 24, `import evidence`):

```python
import evidence
import phoenix_router
```

In `_scan_endpoints_file`, after the `elif language == "Python":` block (ends ~line 1578), add:

```python
    elif language == "Elixir":
        # Only the Phoenix router declares routes; other .ex files contribute none.
        if rel.replace("\\", "/").endswith("router.ex"):
            for ep in phoenix_router.parse_router(text):
                emit(ep["framework"], ep["method"], ep["path"])
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m unittest tests.test_scan_elixir_endpoints -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `python3 -m unittest discover -s tests -t . -q`
Expected: OK. (fittalk has no `router.ex`, so no golden impact.)

- [ ] **Step 7: Commit**

```bash
git add plugin/skills/map-repo/scripts/scan.py plugin/skills/map-repo/scripts/tests/test_scan_elixir_endpoints.py
git commit -m "feat: scanner extracts Phoenix router endpoints (Elixir is now scannable)"
```

---

# SLICE 3 — Enrichment overrides

## Task 7: Validator accepts `classification.services` + `http_edges`

**Files:**
- Modify: `plugin/skills/map-repo/scripts/validate_enrichment.py`
- Test: `plugin/skills/map-repo/scripts/tests/test_validate_enrichment.py` (extend)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_validate_enrichment.py`:

```python
    def test_service_kind_override_ok(self):
        enr = _valid()
        enr["classification"]["services"] = [
            {"service_id": "backend", "kind": "backend", "why": "phoenix"}]
        errors, warnings = ve.validate(enr, FIXTURE, service_ids={"backend"})
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_service_kind_override_bad_kind_errors(self):
        enr = _valid()
        enr["classification"]["services"] = [
            {"service_id": "backend", "kind": "wizard", "why": "x"}]
        errors, _w = ve.validate(enr, FIXTURE, service_ids={"backend"})
        self.assertTrue(any("kind" in e for e in errors))

    def test_unknown_service_id_warns(self):
        enr = _valid()
        enr["classification"]["services"] = [
            {"service_id": "ghost", "kind": "backend", "why": "x"}]
        errors, warnings = ve.validate(enr, FIXTURE, service_ids={"backend"})
        self.assertEqual(errors, [])
        self.assertTrue(any("ghost" in w for w in warnings))

    def test_http_edge_ok(self):
        enr = _valid()
        enr["http_edges"] = [
            {"source_service": "web", "target_service": "backend",
             "method": "POST", "path": "/api/graphql", "why": "apollo"}]
        errors, warnings = ve.validate(enr, FIXTURE, service_ids={"web", "backend"})
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_http_edge_missing_target_errors(self):
        enr = _valid()
        enr["http_edges"] = [{"source_service": "web", "path": "/x"}]
        errors, _w = ve.validate(enr, FIXTURE, service_ids={"web"})
        self.assertTrue(any("target_service" in e for e in errors))

    def test_http_edge_unknown_endpoint_warns(self):
        enr = _valid()
        enr["http_edges"] = [
            {"source_service": "web", "target_service": "ghost", "path": "/x"}]
        errors, warnings = ve.validate(enr, FIXTURE, service_ids={"web"})
        self.assertEqual(errors, [])
        self.assertTrue(any("ghost" in w for w in warnings))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_validate_enrichment -v`
Expected: FAIL — `validate` has no `service_ids` kwarg (TypeError), and no `services`/`http_edges` handling.

- [ ] **Step 3: Implement validator support**

In `validate_enrichment.py`, add the kind set near the top (after `FLOW_KINDS`, line 15):

```python
SERVICE_KINDS = {"frontend", "backend", "library", "service"}
```

Change `validate`'s signature (line 25) to add `service_ids`:

```python
def validate(enr: dict[str, Any], repo_root: Path,
             skeleton_ids: set[str] | None = None,
             service_ids: set[str] | None = None) -> tuple[list[str], list[str]]:
```

Initialize it beside `skeleton_ids` (line 30):

```python
    service_ids = service_ids or set()
```

After the existing `classification` check (lines 44-46), add the service-kind-override validation:

```python
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
```

After the flows loop (after line 67, before `return errors, warnings`), add the http_edges validation:

```python
    for i, e in enumerate(enr.get("http_edges", []) or []):
        where = f"http_edges[{i}]"
        for k in ("source_service", "target_service", "path"):
            _require(e, k, where, errors)
        for endpoint_key in ("source_service", "target_service"):
            v = e.get(endpoint_key)
            if v and service_ids and v not in service_ids:
                warnings.append(f"{where}: unknown {endpoint_key} {v!r} "
                                "(not a service in codemap.json)")
```

Update the CLI `main()` to load service ids from the codemap and pass them. After the `skeleton_ids` block (lines 95-101), extend the same `cm` parse:

```python
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
```

(Replace the existing `skeleton_ids` codemap-load block + `validate(...)` call with the combined version above; don't double-parse the codemap.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_validate_enrichment -v`
Expected: PASS (new tests + all existing).

- [ ] **Step 5: Run the full suite**

Run: `python3 -m unittest discover -s tests -t . -q`
Expected: OK.

- [ ] **Step 6: Commit**

```bash
git add plugin/skills/map-repo/scripts/validate_enrichment.py plugin/skills/map-repo/scripts/tests/test_validate_enrichment.py
git commit -m "feat: validator accepts service kind overrides + LLM http_edges (warn-on-unknown)"
```

---

## Task 8: Render applies enrichment overrides (kind + edge injection)

**Files:**
- Modify: `plugin/skills/map-repo/scripts/render.py` (add `_apply_enrichment_overrides`; call it at top of `render_document`)
- Test: `plugin/skills/map-repo/scripts/tests/test_render_overrides.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_render_overrides.py`:

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import render


def _data():
    return {
        "services": [
            {"id": "backend", "name": "backend", "kind": "frontend"},
            {"id": "web", "name": "web", "kind": "frontend"},
        ],
        "http_topology": {"edges": [
            {"source_service": "web", "target_service": "backend",
             "method": "GET", "path": "/a", "weight": 2},
        ]},
    }


class ApplyOverridesTest(unittest.TestCase):
    def test_kind_override_corrects_service(self):
        enr = {"classification": {"services": [
            {"service_id": "backend", "kind": "backend", "why": "phoenix"}]}}
        out = render._apply_enrichment_overrides(_data(), enr)
        by_id = {s["id"]: s for s in out["services"]}
        self.assertEqual(by_id["backend"]["kind"], "backend")
        self.assertEqual(by_id["web"]["kind"], "frontend")  # untouched

    def test_kind_override_is_immutable(self):
        data = _data()
        enr = {"classification": {"services": [
            {"service_id": "backend", "kind": "backend", "why": "x"}]}}
        render._apply_enrichment_overrides(data, enr)
        self.assertEqual(data["services"][0]["kind"], "frontend")  # input unchanged

    def test_http_edge_injected_and_marked_inferred(self):
        enr = {"http_edges": [
            {"source_service": "web", "target_service": "backend",
             "method": "POST", "path": "/api/graphql", "why": "apollo"}]}
        out = render._apply_enrichment_overrides(_data(), enr)
        edges = out["http_topology"]["edges"]
        self.assertEqual(len(edges), 2)
        inferred = [e for e in edges if e.get("inferred")]
        self.assertEqual(len(inferred), 1)
        self.assertEqual(inferred[0]["path"], "/api/graphql")
        self.assertEqual(inferred[0]["weight"], 1)

    def test_no_enrichment_returns_data_unchanged(self):
        data = _data()
        self.assertIs(render._apply_enrichment_overrides(data, None), data)
        self.assertIs(render._apply_enrichment_overrides(data, {}), data)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_render_overrides -v`
Expected: FAIL — `AttributeError: module 'render' has no attribute '_apply_enrichment_overrides'`.

- [ ] **Step 3: Implement `_apply_enrichment_overrides`**

In `render.py`, add this function just above `def render_document` (the line edited in Task 0/earlier; it currently sits near line 7707, after `clean_enrichment_for_render`):

```python
def _apply_enrichment_overrides(data: dict[str, Any],
                                enrichment: dict[str, Any] | None) -> dict[str, Any]:
    """Apply the LLM's service-tier corrections and asserted HTTP edges onto a
    copy of the codemap, before any section renders.

    Pure (no filesystem): kind overrides re-tier services so every consumer
    (System Map bands, Topology chips) sees the corrected value from one place;
    http_edges are appended to the HTTP layer flagged ``inferred`` so the
    renderer can draw them distinctly. Returns the input unchanged when there
    is nothing to apply."""
    if not enrichment:
        return data
    cls = enrichment.get("classification") or {}
    kind_by_svc = {s.get("service_id"): s.get("kind")
                   for s in (cls.get("services") or [])
                   if s.get("service_id") and s.get("kind")}
    inject = enrichment.get("http_edges") or []
    if not kind_by_svc and not inject:
        return data

    new = dict(data)
    if kind_by_svc:
        new["services"] = [
            {**svc, "kind": kind_by_svc.get(svc.get("id"), svc.get("kind"))}
            for svc in data.get("services", [])
        ]
    if inject:
        topo = dict(data.get("http_topology") or {})
        edges = list(topo.get("edges") or [])
        for e in inject:
            edges.append({
                "source_service": e.get("source_service"),
                "target_service": e.get("target_service"),
                "method": (e.get("method") or "ALL").upper(),
                "path": e.get("path") or "/",
                "weight": 1,
                "inferred": True,
            })
        topo["edges"] = edges
        new["http_topology"] = topo
    return new
```

Then wire it in as the FIRST line of `render_document` (currently `project_name = escape(data["project"]["name"])` at line 7708):

```python
def render_document(data: dict[str, Any], enrichment: dict[str, Any] | None = None) -> str:
    data = _apply_enrichment_overrides(data, enrichment)
    project_name = escape(data["project"]["name"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_render_overrides -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `python3 -m unittest discover -s tests -t . -q`
Expected: OK. The no-enrichment golden body is unchanged (with `enrichment=None`, `_apply_enrichment_overrides` returns `data` unchanged on the very first line).

- [ ] **Step 6: Commit**

```bash
git add plugin/skills/map-repo/scripts/render.py plugin/skills/map-repo/scripts/tests/test_render_overrides.py
git commit -m "feat: render applies enrichment service-kind overrides + injected http_edges"
```

---

## Task 9: Draw inferred edges distinctly + legend note

**Files:**
- Modify: `plugin/skills/map-repo/scripts/render.py` (`_sysmap_edges` ~3733 carries `inferred`; `_sysmap_emit_svg` ~3374 adds the modifier; CSS ~588; legend in `render_system_map`)
- Test: `plugin/skills/map-repo/scripts/tests/test_render_overrides.py` (extend)

HTTP edges are already dashed (`.sysmap-edge-http { stroke-dasharray: 5 4 }`, render.py:588). Inferred edges need a *different* modifier: dotted + faint.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_render_overrides.py` (import the system-map fixture builder at the top of the file: `from tests.test_render_system_map import synthetic_data` — or, to avoid a cross-test import, inline a minimal fixture). Use the inline approach:

```python
class InferredEdgeRenderTest(unittest.TestCase):
    def _synth(self):
        return {
            "scan_depth": "medium", "project": {"name": "synth"},
            "services": [
                {"id": "web", "name": "web", "kind": "frontend", "loc": 1000,
                 "file_count": 10, "color": "#292929", "primary_language": "TypeScript"},
                {"id": "api", "name": "api", "kind": "backend", "loc": 5000,
                 "file_count": 50, "color": "#3178c6", "primary_language": "TypeScript"}],
            "modules": [],
            "module_graph": {"nodes": [
                {"id": "web/pages", "name": "pages", "service": "web", "loc": 600,
                 "files": 6, "primary_language": "TypeScript", "color": "#3178c6",
                 "vendored_guess": False},
                {"id": "api/auth", "name": "auth", "service": "api", "loc": 2000,
                 "files": 20, "primary_language": "TypeScript", "color": "#3178c6",
                 "vendored_guess": False}],
                "edges": []},
            "http_topology": {
                "entry_modules": [{"service": "api", "module": "api/auth", "endpoint_count": 1}],
                "endpoints": [{"service": "api", "module": "api/auth", "file": "api/auth/c.ts",
                               "framework": "NestJS", "method": "POST", "path": "/api/login"}],
                "edges": [{"source_service": "web", "target_service": "api",
                           "method": "POST", "path": "/api/login", "weight": 4,
                           "inferred": True}]},
            "data_lineage": {"stores": [], "models": [], "edges": []},
        }

    def test_inferred_flag_carried_through_edge_model(self):
        data = self._synth()
        sel = render._sysmap_select(data, None)
        layout = render._sysmap_layout(sel)
        edges = render._sysmap_edges(data, layout)
        https = [e for e in edges if e["kind"] == "http"]
        self.assertTrue(https)
        self.assertTrue(https[0].get("inferred"))

    def test_inferred_edge_emits_distinct_class(self):
        data = self._synth()
        sel = render._sysmap_select(data, None)
        layout = render._sysmap_layout(sel)
        edges = render._sysmap_edges(data, layout)
        svg = render._sysmap_emit_svg(layout, edges, sel, None)
        self.assertIn("sysmap-edge-http-inferred", svg)

    def test_inferred_css_rule_present(self):
        self.assertIn(".sysmap-edge-http-inferred", render.CSS)

    def test_legend_note_when_inferred_present(self):
        html = render.render_system_map(self._synth(), None)
        self.assertIn("inferred by AI", html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_render_overrides.InferredEdgeRenderTest -v`
Expected: FAIL — the `inferred` flag is dropped in `_sysmap_edges`, no modifier class, no CSS rule, no legend.

- [ ] **Step 3: Carry `inferred` through `_sysmap_edges`**

In `render.py`, find the HTTP-edge model construction in `_sysmap_edges` (the loop iterating `(data.get("http_topology") or {}).get("edges")`, ~line 3733). Where it builds each http edge model dict (the dict that ends up with `kind: "http"`, `source_service`, `target_id`, `weight`, etc.), add the flag carried from the source edge `e`:

```python
            "inferred": bool(e.get("inferred")),
```

(Add it as another key in the same dict literal that sets `"kind": "http"`. If the model is assembled across several lines, add the key beside `"weight"`.)

- [ ] **Step 4: Add the modifier class in `_sysmap_emit_svg`**

In `_sysmap_emit_svg`, the http-edge emit (render.py:3374-3381) currently writes `class="sysmap-edge-http"`. Change that class to append the inferred modifier:

```python
            http_cls = "sysmap-edge-http"
            if e.get("inferred"):
                http_cls += " sysmap-edge-http-inferred"
            parts.append(
                f'<path d="{hpath}" '
                f'class="{http_cls}" data-kind="http" '
                f'data-src-svc="{escape(e.get("source_service") or "")}" '
                f'data-tgt="{escape(e.get("target_id") or "")}" '
                f'stroke-width="{w:.1f}" fill="none" '
                f'marker-end="url(#sysmap-arrow)" />'
            )
```

- [ ] **Step 5: Add the CSS rule**

In `render.py`, after the `.sysmap-edge-http` rule (line 588), add:

```css
.sysmap-edge-http-inferred { stroke-dasharray: 1 4; stroke-opacity: 0.5; }
```

- [ ] **Step 6: Add the legend note**

In `render_system_map`, compute whether any inferred HTTP edge was drawn and emit a one-line note when so. After the edges are built (where `render_system_map` already has `edges` from `_sysmap_edges`), add:

```python
    has_inferred = any(e.get("kind") == "http" and e.get("inferred") for e in edges)
    inferred_note = ('<p class="sysmap-legend-inferred">Dotted HTTP arrows are '
                     '<strong>inferred by AI</strong> from code it read, not '
                     'matched by the scanner.</p>') if has_inferred else ""
```

Insert `{inferred_note}` into the section's returned HTML near the controls/legend (alongside the existing `sysmap-controls` block). Add a matching CSS rule after the inferred-edge rule:

```css
.sysmap-legend-inferred { font-size: 0.82rem; color: var(--ink-2); margin: var(--space-2) 0 0; }
```

(If `render_system_map` does not already hold the resolved `edges` list in scope at the point you add `has_inferred`, compute it there with `edges = _sysmap_edges(data, layout)` reusing the same `layout` the section already built — do not lay out twice.)

- [ ] **Step 7: Run test to verify it passes**

Run: `python3 -m unittest tests.test_render_overrides.InferredEdgeRenderTest -v`
Expected: PASS.

- [ ] **Step 8: Run the full suite**

Run: `python3 -m unittest discover -s tests -t . -q`
Expected: OK. No-enrichment renders draw no inferred edges (the flag is absent), so the golden body is unchanged.

- [ ] **Step 9: Commit**

```bash
git add plugin/skills/map-repo/scripts/render.py plugin/skills/map-repo/scripts/tests/test_render_overrides.py
git commit -m "feat: draw inferred HTTP edges dotted/faint with an AI-inferred legend note"
```

---

## Task 10: SKILL.md — teach the override fields

**Files:**
- Modify: `plugin/skills/map-repo/SKILL.md` (the `classification` bullet ~line 97; add an `http_edges` line)

No automated test — this is the LLM contract. Verify by reading it back against `validate_enrichment.py`'s schema.

- [ ] **Step 1: Extend the `classification` bullet**

In `SKILL.md`, find the `- **`classification`**:` bullet (~line 97) and append to it:

```
 Additionally, when the deterministic diagram mislabels a service's tier — most often a backend written in a language the scanner doesn't parse (Elixir/Phoenix, Rust, etc.) that got tagged `frontend`/`library` — add a `services` array: each `{ "service_id": "<id from codemap services[]>", "kind": "frontend"|"backend"|"library"|"service", "why": "<one line>" }`. This re-tiers the System Map band. Override only what is wrong.
```

- [ ] **Step 2: Add the `http_edges` bullet**

After the `flows` bullet block (~line 101), add a new top-level bullet:

```
- **`http_edges`** (optional): cross-service HTTP calls you traced in the code that the scanner could not resolve statically — typically a client whose target is an env-injected base URL (e.g. an Apollo `httpLink` → a GraphQL endpoint). Each `{ "source_service", "target_service" (both ids from codemap `services[]`), "method", "path", "why" }`. These render as **dotted, low-confidence** arrows labeled "inferred by AI". Only assert an edge you actually saw — this is judgment the scanner lacks, not a guess.
```

- [ ] **Step 3: Verify schema agreement**

Run: `grep -n "SERVICE_KINDS" plugin/skills/map-repo/scripts/validate_enrichment.py`
Expected: `SERVICE_KINDS = {"frontend", "backend", "library", "service"}` — the SKILL.md `kind` list must be exactly these four.

- [ ] **Step 4: Commit**

```bash
git add plugin/skills/map-repo/SKILL.md
git commit -m "docs: teach Step 1.5 to emit service kind overrides + http_edges"
```

---

## Task 11: Version bump + final verification

**Files:**
- Modify: `plugin/.claude-plugin/plugin.json`

Pre-1.0 MINOR bump for new language support + enrichment override surface. Mechanical (not a phase transition).

- [ ] **Step 1: Bump the version**

In `plugin/.claude-plugin/plugin.json`, change `"version": "0.8.0"` to `"version": "0.9.0"`.

- [ ] **Step 2: Run the entire suite**

Run: `cd plugin/skills/map-repo/scripts && python3 -m unittest discover -s tests -t . -q`
Expected: OK, all green.

- [ ] **Step 3: Smoke-test a real scan end to end (deterministic path)**

Build a throwaway Phoenix-shaped repo and scan it (writes only to a temp dir):

```bash
mkdir -p /tmp/claude/phx/backend/lib/app_web
printf 'defp deps do\n  [{:phoenix, "~> 1.7"}, {:absinthe, "~> 1.7"}]\nend\n' > /tmp/claude/phx/backend/mix.exs
printf 'defmodule AppWeb.Router do\n  scope "/api", AppWeb do\n    forward "/graphql", Absinthe.Plug, schema: App.Schema\n    resources "/users", UserController\n  end\nend\n' > /tmp/claude/phx/backend/lib/app_web/router.ex
python3 plugin/skills/map-repo/scripts/scan.py --path /tmp/claude/phx --depth full --out /tmp/claude/phx.json --evidence-out /tmp/claude/phx.evidence.json
python3 -c "import json; d=json.load(open('/tmp/claude/phx.json')); svc={s['id']:s['kind'] for s in d['services']}; print('service kinds:', svc); eps=[(e['method'],e['path']) for e in d['http_topology']['endpoints']]; print('endpoints:', sorted(eps))"
```
Expected: the `backend` service has `kind: backend`; endpoints include `('ALL', '/api/graphql')` and the seven `('*', '/api/users...')` routes from the `resources` expansion.

- [ ] **Step 4: Render it (deterministic, no LLM)**

```bash
python3 plugin/skills/map-repo/scripts/render.py --in /tmp/claude/phx.json --out /tmp/claude/phx.html
echo "rendered bytes: $(wc -c < /tmp/claude/phx.html)"
```
Expected: renders without error.

- [ ] **Step 5: Commit**

```bash
git add plugin/.claude-plugin/plugin.json
git commit -m "chore: bump plugin to 0.9.0 (Elixir/Phoenix support + enrichment overrides)"
```

---

## Self-Review

**Spec coverage** (against `2026-06-05-elixir-phoenix-and-enrichment-overrides-design.md`):
- §3A token matching → Task 1. ✓ (expo regression test included)
- §3B Elixir/BEAM hints → Task 2. ✓
- §3C dependency-graph width → Task 3. ✓
- §4 Phoenix router parser (verbs/forward/live/scope nesting) → Task 4. ✓; full `resources` expansion (only/except/param/singleton/nesting, log-don't-drop) → Task 5. ✓; wiring (`SCANNABLE` + Elixir branch) → Task 6. ✓
- §5 enrichment overrides: validator (`classification.services` + `http_edges`, warn-on-unknown) → Task 7. ✓; render kind override + edge injection → Task 8. ✓; inferred-edge distinct render + legend → Task 9. ✓; SKILL.md → Task 10. ✓
- §8 version 0.9.0 → Task 11. ✓
- Degradation invariant (no-enrichment golden body unchanged) → asserted by the full-suite step in Tasks 1, 3, 6, 8, 9; `_apply_enrichment_overrides` short-circuits on `None` (Task 8 Step 3). ✓

**Placeholder scan:** every code step contains real code. The two soft spots are flagged with concrete instructions: the exact insertion point of the `inferred` key in `_sysmap_edges` (Task 9 Step 3 — "the dict that sets `kind: http`") and the `has_inferred`/legend placement in `render_system_map` (Task 9 Step 6 — reuse the existing `layout`, do not lay out twice). Neither is a TODO; both name the function, the variable, and the change.

**Type consistency:**
- `_manifest_tokens(name, text) -> set[str]` and `_hit(hint, tokens) -> bool` — same signatures in Task 1 def and `_classify_service` call.
- `phoenix_router.parse_router(text) -> list[dict]` with keys `framework`/`method`/`path` — identical in Task 4 (def), Task 5 (resources extend), Task 6 (scanner `emit(ep["framework"], ep["method"], ep["path"])`), and all tests.
- `validate(enr, repo_root, skeleton_ids=None, service_ids=None) -> (errors, warnings)` — consistent in Task 7 def, CLI, and tests.
- `_apply_enrichment_overrides(data, enrichment) -> data` — consistent in Task 8 def, `render_document` call, and tests. Injected edge keys (`source_service`, `target_service`, `method`, `path`, `weight`, `inferred`) match the deterministic edge shape from `scan.py:2010-2019` plus `inferred`, and the `_sysmap_edges`/emit reads in Task 9.
- `SCANNABLE_LANGUAGES` (Task 6) — defined once at module level, referenced by `build_http_topology` and `test_scan_elixir_endpoints`.

**Known limitations carried (documented, not gaps):**
- Multi-line `scope`/`resources` declarations (macro split across lines) degrade to a neutral frame — best-effort, logged where detectable (Task 5). Acceptable per spec §4/§9.
- Non-JSON manifest tokenization scans the whole file, not just the deps list (Task 1) — spec §3A.
- Deterministic Apollo client-edge resolution remains out of scope; the LLM `http_edges` lever (Tasks 7-9) is the substitute, per spec §9.
