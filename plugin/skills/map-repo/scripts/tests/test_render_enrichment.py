import json
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import render

FIX = Path(__file__).resolve().parent / "fixtures"
FITTALK = Path("/home/mckechniep/projects/fittalk-monorepo/.codemap/codemap.json")


def _body(html: str) -> str:
    """The rendered <main> body, excluding the <head>/<style>.

    The degradation invariant is that NO new content sections appear when
    no enrichment is passed — not that the stylesheet never grows. Later
    tasks add inert CSS (rules whose elements only exist with enrichment),
    so we compare the body region rather than the whole document.
    """
    return html[html.index("<main>"):html.index("</main>")]


class DegradationTest(unittest.TestCase):
    def test_no_enrichment_matches_golden(self):
        data = json.loads(FITTALK.read_text())
        html = render.render_document(data)            # no enrichment arg
        golden = (FIX / "golden_fittalk.html").read_text()
        self.assertEqual(_body(html), _body(golden))

    def test_none_enrichment_matches_golden(self):
        data = json.loads(FITTALK.read_text())
        html = render.render_document(data, enrichment=None)
        golden = (FIX / "golden_fittalk.html").read_text()
        self.assertEqual(_body(html), _body(golden))


def _enr():
    return {
        "schema_version": 1,
        "overview": {
            "what_it_is": "A travel recommendation service.",
            "what_it_does": "Curates trips and serves them via GraphQL.",
            "how_it_works": "Elixir backend plus a React Native app.",
            "primary_stack": ["Elixir/Phoenix", "React Native"],
            "confidence": "high",
            "caveats": ["The root README is a roadmap, not a description."],
        },
        "classification": {"products": [], "vendored": []},
        "module_descriptions": [],
        "flows": [],
    }


class OverviewTest(unittest.TestCase):
    def test_overview_renders_narrative(self):
        html = render.render_overview({"project": {"name": "x"}}, _enr())
        self.assertIn("A travel recommendation service.", html)
        self.assertIn("Elixir/Phoenix", html)
        self.assertIn("roadmap, not a description", html)

    def test_overview_empty_without_enrichment(self):
        self.assertEqual(render.render_overview({"project": {"name": "x"}}, None), "")


class ModulesTest(unittest.TestCase):
    def _data(self):
        return {"modules": [
            {"path": "apps/web", "file_count": 3, "loc": 100,
             "languages": ["TypeScript"], "description": "scanner guess"},
            {"path": "vendor-lib-master", "file_count": 2, "loc": 5000,
             "languages": ["JavaScript"], "description": "vendor guess"},
        ]}

    def _enr(self):
        return {
            "schema_version": 1,
            "overview": {"what_it_is": "x", "what_it_does": "y", "how_it_works": "z",
                         "primary_stack": [], "confidence": "low", "caveats": []},
            "classification": {
                "products": [{"module_id": "apps/web", "role": "frontend", "why": "w"}],
                "vendored": [{"module_id": "vendor-lib-master",
                              "kind": "vendored-framework", "source": "x", "why": "w"}],
            },
            "module_descriptions": [
                {"module_id": "apps/web", "description": "The web dashboard.", "is_product": True}
            ],
            "flows": [],
        }

    def test_product_uses_llm_description_and_sorts_first(self):
        html = render.render_modules(self._data(), self._enr())
        self.assertIn("The web dashboard.", html)
        self.assertLess(html.index("apps/web"), html.index("vendor-lib-master"))

    def test_vendored_is_badged(self):
        html = render.render_modules(self._data(), self._enr())
        self.assertIn("vendored", html.lower())

    def test_modules_unchanged_without_enrichment(self):
        html = render.render_modules(self._data(), None)
        self.assertIn("scanner guess", html)
        self.assertNotIn("The web dashboard.", html)

    def test_heuristic_vendored_without_enrichment(self):
        """vendored_guess alone (no enrichment) badges, dims, and sorts last."""
        data = {"modules": [
            {"path": "glib-master", "file_count": 2, "loc": 9000,
             "languages": ["JavaScript"], "description": "clone",
             "vendored_guess": True},
            {"path": "apps/web", "file_count": 3, "loc": 100,
             "languages": ["TypeScript"], "description": "product",
             "vendored_guess": False},
        ]}
        html = render.render_modules(data, None)
        self.assertIn("vendored", html.lower())
        self.assertIn("is-vendored", html)
        # Product sorts before the (larger) vendored module.
        self.assertLess(html.index("apps/web"), html.index("glib-master"))

    def test_enrichment_product_rescues_heuristic_false_positive(self):
        """classification.products beats vendored_guess=True."""
        data = {"modules": [
            {"path": "tools/build-main", "file_count": 3, "loc": 100,
             "languages": ["TypeScript"], "description": "our build tool",
             "vendored_guess": True},
        ]}
        enr = {
            "schema_version": 1,
            "overview": {"what_it_is": "x", "what_it_does": "y", "how_it_works": "z",
                         "primary_stack": [], "confidence": "low", "caveats": []},
            "classification": {
                "products": [{"module_id": "tools/build-main", "role": "tooling", "why": "ours"}],
                "vendored": [],
            },
            "module_descriptions": [],
            "flows": [],
        }
        html = render.render_modules(data, enr)
        self.assertNotIn("is-vendored", html)

    def test_legacy_data_without_flag_renders_unchanged(self):
        """Module dicts with no vendored_guess key (pre-0.8.0 codemap.json)
        behave exactly as before."""
        data = {"modules": [
            {"path": "apps/web", "file_count": 3, "loc": 100,
             "languages": ["TypeScript"], "description": "product"},
        ]}
        html = render.render_modules(data, None)
        self.assertNotIn("is-vendored", html)
        self.assertNotIn("vendored-badge", html)


class FlowsTest(unittest.TestCase):
    def _enr(self):
        return {"schema_version": 1, "overview": {}, "classification": {},
                "module_descriptions": [],
                "flows": [
                    {"name": "User signup", "kind": "request",
                     "trigger": "GraphQL mutation signUp", "narration": "Creates an account.",
                     "terminates": "auth token returned",
                     "steps": [
                        {"label": "sign_up/2", "file": "backend/lib/x.ex",
                         "symbol": "sign_up/2", "line": 28, "note": "validates + delegates"},
                        {"label": "Repo.transact", "file": "backend/lib/y.ex",
                         "symbol": "create_account/1", "note": "inserts account"},
                     ]},
                ]}

    def test_flows_render_with_citations(self):
        html = render.render_key_flows({}, self._enr())
        self.assertIn("User signup", html)
        self.assertIn("sign_up/2", html)
        self.assertIn("backend/lib/x.ex", html)
        self.assertIn("GraphQL mutation signUp", html)

    def test_no_flows_no_section(self):
        self.assertEqual(render.render_key_flows({}, None), "")
        self.assertEqual(render.render_key_flows({}, {"flows": []}), "")


if __name__ == "__main__":
    unittest.main()
