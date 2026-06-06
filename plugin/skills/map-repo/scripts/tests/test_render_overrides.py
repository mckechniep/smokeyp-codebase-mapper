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

    def test_inferred_edge_is_red_dashed_and_thicker(self):
        # Was faint dotted (1 4, opacity 0.5); now a red, dashed, thicker line
        # so it reads as clearly as the deterministic HTTP calls.
        import re as _re
        m = _re.search(r"\.sysmap-edge-http-inferred\s*\{([^}]*)\}", render.CSS)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("var(--accent)", body)   # red, from the palette token
        self.assertIn("6 4", body)              # dashed like the deterministic 5 4
        self.assertIn("!important", body)       # overrides the thin inline stroke-width
        self.assertNotIn("1 4", body)           # no longer the faint dotted pattern

    def test_inferred_legend_says_red_dashed(self):
        html = render.render_system_map(self._synth(), None)
        self.assertIn("Red dashed", html)
        self.assertIn("inferred by AI", html)

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


class ProductRefinementTest(unittest.TestCase):
    def _data(self):
        return {
            "project": {"name": "p", "total_files": 10, "total_loc": 1700,
                        "total_files_all": 10, "total_loc_all": 1700,
                        "primary_language": "Elixir"},
            "languages": [{"name": "Elixir", "color": "#6e4a7e", "files": 10, "loc": 1700}],
            "languages_all": [{"name": "Elixir", "color": "#6e4a7e", "files": 10, "loc": 1700}],
            "modules": [
                {"path": "backend", "vendored_guess": False,
                 "lang_stats": {"Elixir": {"files": 3, "loc": 200}}},
                {"path": "copied-lib", "vendored_guess": False,
                 "lang_stats": {"Elixir": {"files": 7, "loc": 1500}}},
            ],
        }

    def test_enrichment_vendored_reclassification_shrinks_product(self):
        # The LLM marks 'copied-lib' vendored (the heuristic missed it).
        enr = {"classification": {"products": [],
               "vendored": [{"module_id": "copied-lib", "kind": "vendored-lib",
                             "source": "x", "why": "y"}]}}
        out = render._apply_enrichment_overrides(self._data(), enr)
        # product Elixir loc drops from 1700 to 200 (copied-lib subtracted)
        elixir = next(l for l in out["languages"] if l["name"] == "Elixir")
        self.assertEqual(elixir["loc"], 200)
        self.assertEqual(out["project"]["total_loc"], 200)

    def test_no_enrichment_leaves_deterministic_product(self):
        d = self._data()
        out = render._apply_enrichment_overrides(d, None)
        self.assertEqual(out["project"]["total_loc"], 1700)

    def test_enrichment_product_rescue_keeps_module_in_product(self):
        # Heuristic flags 'actually-product-master' vendored (vendored_guess=True);
        # the LLM rescues it as product, so nothing is subtracted.
        data = {
            "project": {"name": "p", "total_files": 10, "total_loc": 1700,
                        "total_files_all": 10, "total_loc_all": 1700,
                        "primary_language": "Elixir"},
            "languages": [{"name": "Elixir", "color": "#6e4a7e", "files": 10, "loc": 1700}],
            "languages_all": [{"name": "Elixir", "color": "#6e4a7e", "files": 10, "loc": 1700}],
            "modules": [
                {"path": "backend", "vendored_guess": False,
                 "lang_stats": {"Elixir": {"files": 3, "loc": 200}}},
                {"path": "actually-product-master", "vendored_guess": True,
                 "lang_stats": {"Elixir": {"files": 7, "loc": 1500}}},
            ],
        }
        enr = {"classification": {
            "products": [{"module_id": "actually-product-master", "role": "backend", "why": "w"}],
            "vendored": []}}
        out = render._apply_enrichment_overrides(data, enr)
        elixir = next(l for l in out["languages"] if l["name"] == "Elixir")
        self.assertEqual(elixir["loc"], 1700)   # rescued -> nothing subtracted
        self.assertEqual(out["project"]["total_loc"], 1700)

    def test_enrichment_only_http_edges_leaves_product_untouched(self):
        d = self._data()
        enr = {"http_edges": [{"source_service": "a", "target_service": "b"}]}
        out = render._apply_enrichment_overrides(d, enr)
        # No classification -> no product refinement; product stays deterministic.
        self.assertEqual(out["project"]["total_loc"], 1700)
        elixir = next(l for l in out["languages"] if l["name"] == "Elixir")
        self.assertEqual(elixir["loc"], 1700)


if __name__ == "__main__":
    unittest.main()
