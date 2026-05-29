import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import validate_enrichment as ve

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mini_repo"


def _valid():
    return {
        "schema_version": 1,
        "overview": {
            "what_it_is": "x", "what_it_does": "y", "how_it_works": "z",
            "primary_stack": ["TypeScript"], "confidence": "high", "caveats": [],
        },
        "classification": {
            "products": [{"module_id": "apps/web", "role": "frontend", "why": "w"}],
            "vendored": [{"module_id": "vendor-lib-master", "kind": "vendored-framework",
                          "source": "github.com/x", "why": "w"}],
        },
        "module_descriptions": [
            {"module_id": "apps/web", "description": "d", "is_product": True}
        ],
        "flows": [
            {"name": "f", "kind": "request", "trigger": "t", "narration": "n",
             "terminates": "end",
             "steps": [{"label": "main", "file": "apps/web/index.ts",
                        "symbol": "main", "note": "entry"}]},
        ],
    }


class ValidateTest(unittest.TestCase):
    def test_valid_passes(self):
        errors = ve.validate(_valid(), repo_root=FIXTURE)
        self.assertEqual(errors, [])

    def test_missing_overview_field_fails(self):
        d = _valid(); del d["overview"]["what_it_is"]
        self.assertTrue(any("what_it_is" in e for e in ve.validate(d, repo_root=FIXTURE)))

    def test_flow_step_requires_file_and_symbol(self):
        d = _valid(); del d["flows"][0]["steps"][0]["symbol"]
        self.assertTrue(any("symbol" in e for e in ve.validate(d, repo_root=FIXTURE)))

    def test_broken_citation_detected(self):
        d = _valid(); d["flows"][0]["steps"][0]["file"] = "nope/missing.ts"
        self.assertTrue(any("missing.ts" in e for e in ve.validate(d, repo_root=FIXTURE)))

    def test_drop_invalid_flows_keeps_valid(self):
        d = _valid()
        d["flows"].append({"name": "bad", "kind": "request", "trigger": "t",
                           "narration": "n", "terminates": "e",
                           "steps": [{"label": "x", "file": "nope.ts",
                                      "symbol": "y", "note": "z"}]})
        cleaned = ve.drop_invalid_flows(d, repo_root=FIXTURE)
        self.assertEqual(len(cleaned["flows"]), 1)
        self.assertEqual(cleaned["flows"][0]["name"], "f")


if __name__ == "__main__":
    unittest.main()
