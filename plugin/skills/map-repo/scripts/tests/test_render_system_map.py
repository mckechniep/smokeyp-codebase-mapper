"""Tests for the System Map hero section (selection, layout, edges, render)."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import render

FITTALK = Path("/home/mckechniep/projects/fittalk-monorepo/.codemap/codemap.json")


def synthetic_data():
    """Small controlled codemap: 1 frontend svc (2 modules), 1 backend svc
    (3 modules, one vendored), 1 store."""
    return {
        "scan_depth": "medium",
        "project": {"name": "synth"},
        "services": [
            {"id": "web", "name": "web", "kind": "frontend", "loc": 1000,
             "file_count": 10, "color": "#292929", "primary_language": "TypeScript"},
            {"id": "api", "name": "api", "kind": "backend", "loc": 5000,
             "file_count": 50, "color": "#3178c6", "primary_language": "TypeScript"},
        ],
        "modules": [],
        "module_graph": {
            "nodes": [
                {"id": "web/pages", "name": "pages", "service": "web", "loc": 600,
                 "files": 6, "primary_language": "TypeScript", "color": "#3178c6",
                 "vendored_guess": False},
                {"id": "web/api-client", "name": "api-client", "service": "web", "loc": 400,
                 "files": 4, "primary_language": "TypeScript", "color": "#3178c6",
                 "vendored_guess": False},
                {"id": "api/auth", "name": "auth", "service": "api", "loc": 2000,
                 "files": 20, "primary_language": "TypeScript", "color": "#3178c6",
                 "vendored_guess": False},
                {"id": "api/billing", "name": "billing", "service": "api", "loc": 1500,
                 "files": 15, "primary_language": "TypeScript", "color": "#3178c6",
                 "vendored_guess": False},
                {"id": "api/copied-lib-master", "name": "copied-lib-master", "service": "api",
                 "loc": 9000, "files": 90, "primary_language": "JavaScript",
                 "color": "#f1e05a", "vendored_guess": True},
            ],
            "edges": [
                {"source": "web/pages", "target": "web/api-client", "weight": 5},
                {"source": "api/billing", "target": "api/auth", "weight": 3},
                {"source": "api/copied-lib-master", "target": "api/auth", "weight": 1},
            ],
        },
        "http_topology": {
            "entry_modules": [
                {"service": "api", "module": "api/auth", "endpoint_count": 7},
            ],
            "endpoints": [
                {"service": "api", "module": "api/auth", "file": "api/auth/c.ts",
                 "framework": "NestJS", "method": "POST", "path": "/api/login"},
            ],
            "edges": [
                {"source_service": "web", "target_service": "api",
                 "method": "POST", "path": "/api/login", "weight": 4},
            ],
        },
        "data_lineage": {
            "stores": [{"id": "postgres", "kind": "postgres", "name": "PostgreSQL",
                        "evidence": ["api/.env"]}],
            "models": [],
            "edges": [{"source_service": "api", "target_store": "postgres",
                       "models": ["User"], "frameworks": ["Prisma"], "weight": 1}],
        },
    }


class SelectTest(unittest.TestCase):
    def test_vendored_node_excluded(self):
        sel = render._sysmap_select(synthetic_data(), None)
        all_ids = [n["id"] for nodes in sel["bands"].values() for n in nodes]
        self.assertNotIn("api/copied-lib-master", all_ids)
        self.assertEqual(sel["excluded_vendored"], 1)

    def test_band_assignment_by_service_kind(self):
        sel = render._sysmap_select(synthetic_data(), None)
        frontend_ids = {n["id"] for n in sel["bands"]["frontend"]}
        backend_ids = {n["id"] for n in sel["bands"]["backend"]}
        self.assertEqual(frontend_ids, {"web/pages", "web/api-client"})
        self.assertEqual(backend_ids, {"api/auth", "api/billing"})

    def test_enrichment_rescue_overrides_heuristic(self):
        enr = {"classification": {
            "products": [{"module_id": "api/copied-lib-master", "role": "x", "why": "y"}],
            "vendored": []}}
        sel = render._sysmap_select(synthetic_data(), enr)
        all_ids = [n["id"] for nodes in sel["bands"].values() for n in nodes]
        self.assertIn("api/copied-lib-master", all_ids)

    def test_enrichment_vendored_catches_unflagged(self):
        enr = {"classification": {
            "products": [],
            "vendored": [{"module_id": "api/billing", "kind": "vendored-lib",
                          "source": "x", "why": "y"}]}}
        sel = render._sysmap_select(synthetic_data(), enr)
        all_ids = [n["id"] for nodes in sel["bands"].values() for n in nodes]
        self.assertNotIn("api/billing", all_ids)

    def test_entry_modules_survive_truncation(self):
        """Entry-point modules outrank bigger non-entry modules under a tight cap."""
        data = synthetic_data()
        data["scan_depth"] = "shallow"  # cap = 20, no truncation here, but pin rank order
        sel = render._sysmap_select(data, None)
        backend = [n["id"] for n in sel["bands"]["backend"]]
        self.assertEqual(backend[0], "api/auth")  # entry module ranks first

    def test_empty_data_returns_none(self):
        self.assertIsNone(render._sysmap_select({"module_graph": {"nodes": []}}, None))
        self.assertIsNone(render._sysmap_select({}, None))


class LayoutTest(unittest.TestCase):
    def setUp(self):
        self.sel = render._sysmap_select(synthetic_data(), None)
        self.layout = render._sysmap_layout(self.sel)

    def test_every_visible_node_is_placed(self):
        visible_ids = {n["id"] for nodes in self.sel["bands"].values() for n in nodes}
        self.assertEqual(set(self.layout["placed"].keys()), visible_ids)

    def test_frontend_band_above_backend_band(self):
        front_y = self.layout["bands"]["frontend"]["y"]
        back_y = self.layout["bands"]["backend"]["y"]
        self.assertLess(front_y, back_y)

    def test_stores_below_backend(self):
        back = self.layout["bands"]["backend"]
        data_band = self.layout["bands"]["data"]
        self.assertGreater(data_band["y"], back["y"] + back["h"])

    def test_no_nan_or_negative_coordinates(self):
        for nid, p in self.layout["placed"].items():
            for k in ("x", "y", "w", "h"):
                self.assertEqual(p[k], p[k], f"NaN {k} on {nid}")  # NaN != NaN
                self.assertGreaterEqual(p[k], 0, f"negative {k} on {nid}")

    def test_nodes_fit_within_viewbox(self):
        for nid, p in self.layout["placed"].items():
            self.assertLessEqual(p["x"] + p["w"], render.SYSMAP_W, f"{nid} overflows")

    def test_no_node_overlap_within_band(self):
        boxes = list(self.layout["placed"].values())
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                overlap = not (a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"]
                               or a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"])
                self.assertFalse(overlap, f"nodes overlap: {a} vs {b}")

    def test_one_cluster_per_service_per_band(self):
        keys = {(c["band"], c["service_id"]) for c in self.layout["clusters"]}
        self.assertEqual(keys, {("frontend", "web"), ("backend", "api")})

    def test_deterministic(self):
        layout2 = render._sysmap_layout(render._sysmap_select(synthetic_data(), None))
        self.assertEqual(
            sorted(self.layout["placed"].keys()), sorted(layout2["placed"].keys()))
        for nid in self.layout["placed"]:
            self.assertEqual(self.layout["placed"][nid]["x"], layout2["placed"][nid]["x"])
            self.assertEqual(self.layout["placed"][nid]["y"], layout2["placed"][nid]["y"])


class EdgesTest(unittest.TestCase):
    def setUp(self):
        self.data = synthetic_data()
        self.sel = render._sysmap_select(self.data, None)
        self.layout = render._sysmap_layout(self.sel)
        self.edges = render._sysmap_edges(self.data, self.layout)

    def kinds(self):
        return [e["kind"] for e in self.edges]

    def test_import_edge_between_visible_nodes(self):
        imports = [e for e in self.edges if e["kind"] == "import"]
        # web/pages -> web/api-client and api/billing -> api/auth are drawable;
        # the edge from the vendored module is NOT (source not placed).
        self.assertEqual(len(imports), 2)

    def test_no_edge_touches_unplaced_node(self):
        # The vendored module was excluded; no edge may reference it.
        # (All returned edges carry coordinates, so this is implicitly true;
        # pin it by checking edge count above and total here.)
        self.assertEqual(len(self.edges), 4)  # 2 import + 1 http + 1 store

    def test_http_edge_resolves_target_module(self):
        https = [e for e in self.edges if e["kind"] == "http"]
        self.assertEqual(len(https), 1)
        # Target anchor must be the api/auth node's top edge.
        auth = self.layout["placed"]["api/auth"]
        self.assertAlmostEqual(https[0]["x2"], auth["x"] + auth["w"] / 2)
        self.assertAlmostEqual(https[0]["y2"], auth["y"])

    def test_store_edge_anchors_to_cylinder(self):
        stores = [e for e in self.edges if e["kind"] == "store"]
        self.assertEqual(len(stores), 1)
        pg = self.layout["stores"]["postgres"]
        self.assertAlmostEqual(stores[0]["x2"], pg["x"] + pg["w"] / 2)

    def test_import_edge_cap(self):
        """More than SYSMAP_MAX_IMPORT_EDGES drawable edges -> capped, highest weight kept."""
        data = synthetic_data()
        # Generate 50 extra synthetic backend nodes + edges, all drawable.
        for i in range(50):
            data["module_graph"]["nodes"].append(
                {"id": f"api/m{i}", "name": f"m{i}", "service": "api", "loc": 10,
                 "files": 1, "primary_language": "TypeScript", "color": "#3178c6",
                 "vendored_guess": False})
            data["module_graph"]["edges"].append(
                {"source": f"api/m{i}", "target": "api/auth", "weight": i + 10})
        data["scan_depth"] = "full"  # cap 60 nodes so all are placed
        sel = render._sysmap_select(data, None)
        layout = render._sysmap_layout(sel)
        edges = render._sysmap_edges(data, layout)
        imports = [e for e in edges if e["kind"] == "import"]
        self.assertLessEqual(len(imports), render.SYSMAP_MAX_IMPORT_EDGES)
        # Highest-weight edge must survive the cap.
        weights = [e["weight"] for e in imports]
        self.assertIn(59, weights)


class LayoutStressTest(unittest.TestCase):
    def _many_service_data(self, n_services=15):
        """One frontend svc + n_services single-module backend svcs + 1 store."""
        services = [{"id": "web", "name": "web", "kind": "frontend", "loc": 1000,
                     "file_count": 10, "color": "#292929", "primary_language": "TypeScript"}]
        nodes = [{"id": "web/pages", "name": "pages", "service": "web", "loc": 600,
                  "files": 6, "primary_language": "TypeScript", "color": "#3178c6",
                  "vendored_guess": False}]
        edges = []
        for i in range(n_services):
            sid = f"svc{i}"
            services.append({"id": sid, "name": sid, "kind": "backend", "loc": 500,
                             "file_count": 5, "color": "#3178c6", "primary_language": "TypeScript"})
            nodes.append({"id": f"{sid}/core", "name": "core", "service": sid, "loc": 500,
                          "files": 5, "primary_language": "TypeScript", "color": "#3178c6",
                          "vendored_guess": False})
        return {
            "scan_depth": "full", "project": {"name": "many"},
            "services": services, "modules": [],
            "module_graph": {"nodes": nodes, "edges": edges},
            "http_topology": {"entry_modules": [], "endpoints": [], "edges": []},
            "data_lineage": {"stores": [], "models": [], "edges": []},
        }

    def test_many_services_fit_within_viewbox(self):
        layout = render._sysmap_layout(render._sysmap_select(self._many_service_data(15), None))
        for nid, p in layout["placed"].items():
            self.assertLessEqual(p["x"] + p["w"], render.SYSMAP_W, f"{nid} overflows viewbox")
            self.assertGreaterEqual(p["x"], 0, f"{nid} negative x")

    def test_many_services_no_overlap(self):
        layout = render._sysmap_layout(render._sysmap_select(self._many_service_data(15), None))
        boxes = list(layout["placed"].values())
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                overlap = not (a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"]
                               or a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"])
                self.assertFalse(overlap, f"overlap at scale: {a} vs {b}")

    def test_many_services_clusters_wrap_to_rows(self):
        """15 backend clusters can't fit one row at min width -> multiple y levels."""
        layout = render._sysmap_layout(render._sysmap_select(self._many_service_data(15), None))
        backend_cluster_ys = sorted({round(c["y"], 1) for c in layout["clusters"]
                                     if c["band"] == "backend"})
        self.assertGreater(len(backend_cluster_ys), 1, "backend clusters did not wrap")

    def test_many_services_deterministic(self):
        a = render._sysmap_layout(render._sysmap_select(self._many_service_data(15), None))
        b = render._sysmap_layout(render._sysmap_select(self._many_service_data(15), None))
        self.assertEqual([c["service_id"] for c in a["clusters"]],
                         [c["service_id"] for c in b["clusters"]])
        for nid in a["placed"]:
            self.assertEqual(a["placed"][nid]["x"], b["placed"][nid]["x"])
            self.assertEqual(a["placed"][nid]["y"], b["placed"][nid]["y"])


class FittalkSmokeTest(unittest.TestCase):
    """Integration smoke test against the real fittalk codemap."""

    @unittest.skipUnless(FITTALK.is_file(), "fittalk test data not present")
    def test_fittalk_selects_and_lays_out(self):
        data = json.loads(FITTALK.read_text())
        sel = render._sysmap_select(data, None)
        self.assertIsNotNone(sel)
        layout = render._sysmap_layout(sel)
        # fittalk: 37 graph nodes, none flagged (old codemap) -> capped at 40
        self.assertGreater(len(layout["placed"]), 10)
        self.assertLessEqual(len(layout["placed"]), 40)
        # 3 services -> at least 3 clusters
        self.assertGreaterEqual(len(layout["clusters"]), 3)
        # 4 stores -> 4 cylinders
        self.assertEqual(len(layout["stores"]), 4)


if __name__ == "__main__":
    unittest.main()
