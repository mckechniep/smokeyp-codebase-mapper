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
        errors, warnings = ve.validate(_valid(), repo_root=FIXTURE)
        self.assertEqual(errors, [])

    def test_missing_overview_field_fails(self):
        d = _valid(); del d["overview"]["what_it_is"]
        errors, warnings = ve.validate(d, repo_root=FIXTURE)
        self.assertTrue(any("what_it_is" in e for e in errors))

    def test_flow_step_requires_file_and_symbol(self):
        d = _valid(); del d["flows"][0]["steps"][0]["symbol"]
        errors, warnings = ve.validate(d, repo_root=FIXTURE)
        self.assertTrue(any("symbol" in e for e in errors))

    def test_broken_citation_detected(self):
        d = _valid(); d["flows"][0]["steps"][0]["file"] = "nope/missing.ts"
        errors, warnings = ve.validate(d, repo_root=FIXTURE)
        self.assertTrue(any("missing.ts" in e for e in errors))

    def test_drop_invalid_flows_keeps_valid(self):
        d = _valid()
        d["flows"].append({"name": "bad", "kind": "request", "trigger": "t",
                           "narration": "n", "terminates": "e",
                           "steps": [{"label": "x", "file": "nope.ts",
                                      "symbol": "y", "note": "z"}]})
        cleaned = ve.drop_invalid_flows(d, repo_root=FIXTURE)
        self.assertEqual(len(cleaned["flows"]), 1)
        self.assertEqual(cleaned["flows"][0]["name"], "f")

    def test_valid_enrichment_has_no_errors_or_warnings(self):
        errors, warnings = ve.validate(_valid(), FIXTURE)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_known_skeleton_id_ok(self):
        enr = _valid()
        enr["flows"][0]["skeleton_id"] = "apps/web"
        errors, warnings = ve.validate(enr, FIXTURE, skeleton_ids={"apps/web"})
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_unknown_skeleton_id_warns_not_fails(self):
        enr = _valid()
        enr["flows"][0]["skeleton_id"] = "does/not/exist"
        errors, warnings = ve.validate(enr, FIXTURE, skeleton_ids={"apps/web"})
        self.assertEqual(errors, [])
        self.assertTrue(any("does/not/exist" in w for w in warnings))

    def test_no_skeleton_id_field_is_always_clean(self):
        # A flow without skeleton_id (the _valid() fixture) never warns, even
        # when a non-empty skeleton-id set is supplied — guards the `sid` truthy check.
        errors, warnings = ve.validate(_valid(), FIXTURE, skeleton_ids={"apps/web"})
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
