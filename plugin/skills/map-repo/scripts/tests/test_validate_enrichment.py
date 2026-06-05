import shutil
import tempfile
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


if __name__ == "__main__":
    unittest.main()
