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

    def test_kind_override_when_data_has_no_http_topology(self):
        # kind-only override on data lacking http_topology must not crash and
        # must not invent an http_topology key.
        data = {"services": [{"id": "backend", "name": "backend", "kind": "frontend"}]}
        enr = {"classification": {"services": [
            {"service_id": "backend", "kind": "backend", "why": "x"}]}}
        out = render._apply_enrichment_overrides(data, enr)
        self.assertEqual(out["services"][0]["kind"], "backend")
        self.assertNotIn("http_topology", out)

    def test_unknown_service_id_override_is_noop(self):
        enr = {"classification": {"services": [
            {"service_id": "ghost", "kind": "backend", "why": "x"}]}}
        out = render._apply_enrichment_overrides(_data(), enr)
        # no service had id 'ghost'; every original kind is preserved
        self.assertEqual({s["id"]: s["kind"] for s in out["services"]},
                         {"backend": "frontend", "web": "frontend"})

    def test_kind_override_and_edge_injection_together(self):
        # The real brevity scenario: correct a service's band AND assert an edge.
        enr = {
            "classification": {"services": [
                {"service_id": "backend", "kind": "backend", "why": "phoenix"}]},
            "http_edges": [
                {"source_service": "web", "target_service": "backend",
                 "method": "POST", "path": "/api/graphql", "why": "apollo"}],
        }
        out = render._apply_enrichment_overrides(_data(), enr)
        by_id = {s["id"]: s for s in out["services"]}
        self.assertEqual(by_id["backend"]["kind"], "backend")
        edges = out["http_topology"]["edges"]
        self.assertEqual(len(edges), 2)
        self.assertTrue(any(e.get("inferred") and e["path"] == "/api/graphql" for e in edges))


if __name__ == "__main__":
    unittest.main()
