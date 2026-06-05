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

    def test_legend_note_absent_when_no_inferred(self):
        # A purely-deterministic map must NOT show the inferred legend note
        # (guards against has_inferred being computed unconditionally).
        data = self._synth()
        data["http_topology"]["edges"][0].pop("inferred", None)
        html = render.render_system_map(data, None)
        self.assertNotIn("inferred by AI", html)

    def test_deterministic_edge_not_flagged_inferred(self):
        # With the inferred flag removed, the drawn http edge model must not be
        # inferred and must not emit the distinct class.
        data = self._synth()
        data["http_topology"]["edges"][0].pop("inferred", None)
        sel = render._sysmap_select(data, None)
        layout = render._sysmap_layout(sel)
        edges = render._sysmap_edges(data, layout)
        https = [e for e in edges if e["kind"] == "http"]
        self.assertTrue(https)
        self.assertFalse(https[0].get("inferred"))
        svg = render._sysmap_emit_svg(layout, edges, sel, None)
        self.assertNotIn("sysmap-edge-http-inferred", svg)


if __name__ == "__main__":
    unittest.main()
