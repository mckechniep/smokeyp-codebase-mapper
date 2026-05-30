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


if __name__ == "__main__":
    unittest.main()
