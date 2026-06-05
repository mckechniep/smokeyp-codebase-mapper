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
