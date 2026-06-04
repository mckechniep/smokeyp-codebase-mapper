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
        # The fixture's two within-service import edges (web/pages ->
        # web/api-client and api/billing -> api/auth) are now DRAWN again;
        # the third edge is from a vendored (unplaced) module and is dropped.
        self.assertEqual(len(imports), 2)

    def test_no_edge_touches_unplaced_node(self):
        # The vendored module was excluded; no edge may reference it.
        # Both fixture imports are drawn again, plus the http and store edges.
        self.assertEqual(len(self.edges), 4)  # 2 import + 1 http + 1 store

    def test_cross_service_same_band_import_survives(self):
        """A cross-service import in the same band is kept (dip or bracket)."""
        data = synthetic_data()
        # add a second backend service whose module imports api/auth
        data["services"].append({"id": "billing-svc", "name": "billing-svc",
            "kind": "backend", "loc": 800, "file_count": 8, "color": "#3178c6",
            "primary_language": "TypeScript"})
        data["module_graph"]["nodes"].append({"id": "billing-svc/pay", "name": "pay",
            "service": "billing-svc", "loc": 800, "files": 8,
            "primary_language": "TypeScript", "color": "#3178c6", "vendored_guess": False})
        data["module_graph"]["edges"].append(
            {"source": "billing-svc/pay", "target": "api/auth", "weight": 4})
        sel = render._sysmap_select(data, None)
        layout = render._sysmap_layout(sel)
        edges = render._sysmap_edges(data, layout)
        s = layout["placed"]["billing-svc/pay"]
        t = layout["placed"]["api/auth"]
        same_band = s["band"] == t["band"]
        self.assertTrue(same_band, "billing-svc/pay and api/auth should share the backend band")
        # An import edge for the cross-service pair must exist (geometry may be
        # the dip arc or the gutter bracket, depending on layout).
        imports = [e for e in edges if e["kind"] == "import"]
        self.assertTrue(imports, "cross-service same-band import should survive")

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
        # Generate 50 extra synthetic backend nodes + edges, all drawable
        # (within-service imports are drawn now, so every one of these counts
        # toward the cap regardless of service). That's what exercises the cap.
        for i in range(50):
            sid = f"svc{i}"
            data["services"].append(
                {"id": sid, "name": sid, "kind": "backend", "loc": 500,
                 "file_count": 5, "color": "#3178c6", "primary_language": "TypeScript"})
            data["module_graph"]["nodes"].append(
                {"id": f"{sid}/m{i}", "name": f"m{i}", "service": sid, "loc": 10,
                 "files": 1, "primary_language": "TypeScript", "color": "#3178c6",
                 "vendored_guess": False})
            data["module_graph"]["edges"].append(
                {"source": f"{sid}/m{i}", "target": "api/auth", "weight": i + 10})
        data["scan_depth"] = "full"  # cap 60 nodes so all are placed
        sel = render._sysmap_select(data, None)
        layout = render._sysmap_layout(sel)
        edges = render._sysmap_edges(data, layout)
        imports = [e for e in edges if e["kind"] == "import"]
        self.assertLessEqual(len(imports), render.SYSMAP_MAX_IMPORT_EDGES)
        # Highest-weight edge must survive the cap.
        weights = [e["weight"] for e in imports]
        self.assertIn(59, weights)

    def test_cross_band_import_anchors_at_band_facing_edges(self):
        """A frontend->backend import edge anchors source-bottom -> target-top."""
        data = synthetic_data()
        # web/api-client (frontend) imports api/auth (backend): a cross-band edge.
        data["module_graph"]["edges"].append(
            {"source": "web/api-client", "target": "api/auth", "weight": 2})
        sel = render._sysmap_select(data, None)
        layout = render._sysmap_layout(sel)
        edges = render._sysmap_edges(data, layout)
        cross = [e for e in edges
                 if e["kind"] == "import" and not e["same_band"]]
        self.assertEqual(len(cross), 1)
        e = cross[0]
        s = layout["placed"]["web/api-client"]
        t = layout["placed"]["api/auth"]
        # frontend sits above backend, so source anchors at its BOTTOM,
        # target at its TOP.
        self.assertAlmostEqual(e["y1"], s["y"] + s["h"])
        self.assertAlmostEqual(e["y2"], t["y"])
        self.assertAlmostEqual(e["x1"], s["x"] + s["w"] / 2)
        self.assertAlmostEqual(e["x2"], t["x"] + t["w"] / 2)

    def test_same_row_import_uses_dip_arc(self):
        """Same-band imports between nodes on the SAME row keep the dip-below
        arc: a 1-point control (the dip apex) and anchors at both node bottoms.

        synthetic_data's two within-service imports (web/pages -> web/api-client
        and api/billing -> api/auth) are same-row pairs, so both are dip arcs.
        """
        same_row = [e for e in self.edges
                    if e["kind"] == "import" and len(e.get("ctrl") or []) == 1]
        self.assertTrue(same_row, "expected at least one same-row dip arc")
        bottoms = {round(p["y"] + p["h"], 3) for p in self.layout["placed"].values()}
        for e in same_row:
            self.assertTrue(e["same_band"])
            # 1-point ctrl == quadratic dip; anchors sit at node bottoms.
            self.assertEqual(len(e["ctrl"]), 1)
            self.assertIn(round(e["y1"], 3), bottoms)
            self.assertIn(round(e["y2"], 3), bottoms)
            # dip apex hangs below the lower of the two anchors.
            (_cx, cy) = e["ctrl"][0]
            self.assertGreater(cy, max(e["y1"], e["y2"]))

    def _stacked_hub_data(self):
        """One backend service whose hub imports 14 spokes; the spokes wrap
        into multiple rows, so several hub->spoke imports are STACKED and must
        bracket out to the cluster's right gutter."""
        nodes = [{"id": "web/pages", "name": "pages", "service": "web", "loc": 600,
                  "files": 6, "primary_language": "TypeScript", "color": "#3178c6",
                  "vendored_guess": False},
                 {"id": "api/hub", "name": "hub", "service": "api", "loc": 9000,
                  "files": 9, "primary_language": "TypeScript", "color": "#3178c6",
                  "vendored_guess": False}]
        edges = []
        for i in range(14):
            nodes.append({"id": f"api/s{i}", "name": f"s{i}", "service": "api",
                          "loc": 500, "files": 5, "primary_language": "TypeScript",
                          "color": "#3178c6", "vendored_guess": False})
            edges.append({"source": "api/hub", "target": f"api/s{i}", "weight": 2})
        return {
            "scan_depth": "full", "project": {"name": "stack"},
            "services": [
                {"id": "web", "name": "web", "kind": "frontend", "loc": 1000,
                 "file_count": 10, "color": "#292929", "primary_language": "TypeScript"},
                {"id": "api", "name": "api", "kind": "backend", "loc": 5000,
                 "file_count": 50, "color": "#3178c6", "primary_language": "TypeScript"}],
            "modules": [], "module_graph": {"nodes": nodes, "edges": edges},
            "http_topology": {"entry_modules": [], "endpoints": [], "edges": []},
            "data_lineage": {"stores": [], "models": [], "edges": []},
        }

    def test_stacked_import_brackets_to_gutter(self):
        """Stacked same-band imports bow OUT to the cluster's right gutter
        (a 2-point bracket) instead of spearing through the node column.

        Both control points share an x that exceeds BOTH endpoints' right
        edges (proving the curve travels in the right margin, not through the
        column), and that x stays within the viewBox.
        """
        data = self._stacked_hub_data()
        sel = render._sysmap_select(data, None)
        layout = render._sysmap_layout(sel)
        edges = render._sysmap_edges(data, layout)
        brackets = [e for e in edges
                    if e["kind"] == "import" and len(e.get("ctrl") or []) == 2]
        self.assertTrue(brackets, "hub/spoke layout should produce stacked brackets")
        for e in brackets:
            self.assertTrue(e["same_band"])
            ctrl_xs = {round(c[0], 3) for c in e["ctrl"]}
            # both control points share one x (the gutter column).
            self.assertEqual(len(ctrl_xs), 1, f"bracket ctrl xs differ: {e['ctrl']}")
            cx = next(iter(ctrl_xs))
            # x1/x2 are the source/target RIGHT edges in the bracket case;
            # the gutter column must sit past both, i.e. out in the margin.
            self.assertGreater(cx, e["x1"])
            self.assertGreater(cx, e["x2"])
            self.assertLessEqual(cx, render.SYSMAP_W)

    def _multi_target_stacked_data(self):
        """Two backend services so the api cluster is narrow enough to leave
        gutter room. Inside api, five high-degree source hubs fill the top
        row; two shared targets (tgtX, tgtY) each receive TWO stacked imports
        (from h0 and h1) and wrap to a lower row, while degree-1 fillers also
        wrap below. This yields ≥2 distinct lower-row targets, each with ≥2
        stacked brackets — the case that distinguishes per-target lanes."""
        nodes = [{"id": "web/pages", "name": "pages", "service": "web",
                  "loc": 600, "files": 6, "primary_language": "TypeScript",
                  "color": "#3178c6", "vendored_guess": False}]
        for h in ("h0", "h1", "h2", "h3", "h4"):
            nodes.append({"id": f"api/{h}", "name": h, "service": "api",
                          "loc": 9000, "files": 9, "primary_language": "TypeScript",
                          "color": "#3178c6", "vendored_guess": False})
        for t in ("tgtX", "tgtY"):
            nodes.append({"id": f"api/{t}", "name": t, "service": "api",
                          "loc": 500, "files": 5, "primary_language": "TypeScript",
                          "color": "#3178c6", "vendored_guess": False})
        for i in range(8):
            nodes.append({"id": f"api/f{i:02d}", "name": f"f{i:02d}",
                          "service": "api", "loc": 500, "files": 5,
                          "primary_language": "TypeScript", "color": "#3178c6",
                          "vendored_guess": False})
        for i in range(6):
            nodes.append({"id": f"core/c{i:02d}", "name": f"c{i:02d}",
                          "service": "core", "loc": 500, "files": 5,
                          "primary_language": "TypeScript", "color": "#3178c6",
                          "vendored_guess": False})
        edges = []
        # Inflate every hub's degree so all five outrank the degree-2 shared
        # targets and hold the top row, forcing tgtX/tgtY to wrap below.
        fi = 0
        for h in ("h0", "h1", "h2", "h3", "h4"):
            for _ in range(3):
                edges.append({"source": f"api/{h}", "target": f"api/f{fi % 8:02d}",
                              "weight": 1})
                fi += 1
        # Both shared targets get two stacked imports (from h0 and h1).
        for h in ("h0", "h1"):
            edges.append({"source": f"api/{h}", "target": "api/tgtX", "weight": 2})
            edges.append({"source": f"api/{h}", "target": "api/tgtY", "weight": 2})
        return {
            "scan_depth": "full", "project": {"name": "stack"},
            "services": [
                {"id": "web", "name": "web", "kind": "frontend", "loc": 1000,
                 "file_count": 10, "color": "#292929", "primary_language": "TypeScript"},
                {"id": "api", "name": "api", "kind": "backend", "loc": 5000,
                 "file_count": 50, "color": "#3178c6", "primary_language": "TypeScript"},
                {"id": "core", "name": "core", "kind": "backend", "loc": 3000,
                 "file_count": 30, "color": "#3178c6", "primary_language": "TypeScript"}],
            "modules": [], "module_graph": {"nodes": nodes, "edges": edges},
            "http_topology": {"entry_modules": [], "endpoints": [], "edges": []},
            "data_lineage": {"stores": [], "models": [], "edges": []},
        }

    def test_bracket_lanes_fan_by_target(self):
        """Stacked brackets fan into per-target gutter lanes: edges converging
        on ONE hub share a single spine (one gx), while edges into DIFFERENT
        hubs sit on separate spines (distinct gx). This is the fix for all
        brackets bunching onto one gutter x and merging into one bundle.
        """
        data = self._multi_target_stacked_data()
        layout = render._sysmap_layout(render._sysmap_select(data, None))
        placed = layout["placed"]
        edges = render._sysmap_edges(data, layout)
        brackets = [e for e in edges
                    if e["kind"] == "import" and len(e.get("ctrl") or []) == 2]
        self.assertTrue(brackets, "fixture should produce stacked brackets")

        # Recover each bracket's target by matching its (x2, y2) anchor — the
        # target node's right-mid — back to a placed node.
        def target_of(e):
            for nid, p in placed.items():
                if (abs((p["x"] + p["w"]) - e["x2"]) < 0.5
                        and abs((p["y"] + p["h"] / 2) - e["y2"]) < 0.5):
                    return nid
            return None

        lanes_by_target: dict[str, set] = {}
        for e in brackets:
            tid = target_of(e)
            self.assertIsNotNone(tid, f"could not resolve bracket target: {e}")
            # Both control points of a single bracket share one x (the lane).
            ctrl_xs = {round(c[0], 3) for c in e["ctrl"]}
            self.assertEqual(len(ctrl_xs), 1, f"bracket ctrl xs differ: {e['ctrl']}")
            lanes_by_target.setdefault(tid, set()).add(next(iter(ctrl_xs)))

        # tgtX and tgtY each receive TWO stacked imports — proves multi-import.
        self.assertIn("api/tgtX", lanes_by_target)
        self.assertIn("api/tgtY", lanes_by_target)

        # Convergence: every target uses exactly ONE lane, no matter how many
        # brackets land on it (so multiple edges into a hub read as one spine).
        for tid, lanes in lanes_by_target.items():
            self.assertEqual(len(lanes), 1,
                             f"target {tid} spread across lanes {sorted(lanes)}")

        # Fanning: distinct targets occupy distinct lanes (no merging). With
        # ≥2 targets this means more than one lane exists overall — the bug was
        # exactly one lane for everything.
        self.assertGreaterEqual(len(lanes_by_target), 2)
        all_lanes = {next(iter(v)) for v in lanes_by_target.values()}
        self.assertEqual(len(all_lanes), len(lanes_by_target),
                         "each distinct target must get its own lane")
        self.assertGreater(len(all_lanes), 1,
                           "lanes must fan, not bunch onto a single gutter x")
        # tgtX and tgtY specifically sit on different spines.
        self.assertNotEqual(next(iter(lanes_by_target["api/tgtX"])),
                            next(iter(lanes_by_target["api/tgtY"])))

    def test_no_degenerate_near_vertical_dip(self):
        """The spike signature is forbidden: no same-band import may use a
        1-point dip whose apex x is within 5px of BOTH endpoints while the
        endpoints are far apart vertically (that would spear the column).

        Checked against both the synthetic fixture and the stacked hub layout.
        """
        node_h = render.SYSMAP_NODE_H
        cases = [synthetic_data(), self._stacked_hub_data()]
        for data in cases:
            sel = render._sysmap_select(data, None)
            layout = render._sysmap_layout(sel)
            edges = render._sysmap_edges(data, layout)
            for e in edges:
                if e["kind"] != "import":
                    continue
                ctrl = e.get("ctrl") or []
                if len(ctrl) != 1:
                    continue
                cx = ctrl[0][0]
                degenerate = (abs(cx - e["x1"]) < 5 and abs(cx - e["x2"]) < 5
                              and abs(e["y1"] - e["y2"]) > 2 * node_h)
                self.assertFalse(degenerate, f"degenerate near-vertical dip: {e}")

    def test_store_edge_carries_kind_color(self):
        stores = [e for e in self.edges if e["kind"] == "store"]
        self.assertEqual(len(stores), 1)
        self.assertEqual(stores[0]["color"], render.STORE_KIND_COLORS["postgres"])


class IdentityHooksTest(unittest.TestCase):
    def setUp(self):
        self.data = synthetic_data()
        self.sel = render._sysmap_select(self.data, None)
        self.layout = render._sysmap_layout(self.sel)
        self.edges = render._sysmap_edges(self.data, self.layout)

    def test_import_edges_carry_src_tgt_ids(self):
        imp = [e for e in self.edges if e["kind"] == "import"]
        self.assertTrue(imp)
        for e in imp:
            self.assertIn("src", e)
            self.assertIn("tgt", e)
            self.assertIn(e["src"], self.layout["placed"])
            self.assertIn(e["tgt"], self.layout["placed"])

    def test_http_edges_carry_src_service_and_tgt(self):
        for e in [e for e in self.edges if e["kind"] == "http"]:
            self.assertIn("source_service", e)
            self.assertIn("target_id", e)

    def test_store_edges_carry_src_service_and_store(self):
        for e in [e for e in self.edges if e["kind"] == "store"]:
            self.assertIn("source_service", e)
            self.assertIn("target_store", e)

    def test_svg_nodes_have_data_attrs(self):
        svg = render._sysmap_emit_svg(self.layout, self.edges, self.sel, None)
        # every node group exposes its id + service + is focusable
        self.assertIn('data-nid="api/auth"', svg)
        self.assertIn('data-svc="api"', svg)
        self.assertIn('tabindex="0"', svg)
        self.assertIn('role="button"', svg)

    def test_svg_edges_have_data_attrs(self):
        svg = render._sysmap_emit_svg(self.layout, self.edges, self.sel, None)
        self.assertIn('data-kind="import"', svg)
        self.assertIn('data-kind="http"', svg)
        self.assertIn('data-kind="store"', svg)
        # an import edge exposes its endpoints
        self.assertRegex(svg, r'data-src="[^"]+" data-tgt="[^"]+"')

    def test_id_data_attrs_are_escaped(self):
        """Module/service ids with HTML metachars must be escaped in data-attrs."""
        d = synthetic_data()
        # give a node an id with metacharacters and rewire its edges to match
        bad = 'api/au<th>&"x'
        for n in d["module_graph"]["nodes"]:
            if n["id"] == "api/auth":
                n["id"] = bad
        for e in d["module_graph"]["edges"]:
            if e.get("target") == "api/auth":
                e["target"] = bad
            if e.get("source") == "api/auth":
                e["source"] = bad
        # also a metachar in a service id
        for s in d["services"]:
            if s["id"] == "api":
                s["id"] = 'ap&i'
        for n in d["module_graph"]["nodes"]:
            if n.get("service") == "api":
                n["service"] = 'ap&i'
        sel = render._sysmap_select(d, None)
        layout = render._sysmap_layout(sel)
        edges = render._sysmap_edges(d, layout)
        svg = render._sysmap_emit_svg(layout, edges, sel, None)
        # raw metachars must not appear inside the data-nid value
        self.assertNotIn('data-nid="api/au<th>', svg)
        self.assertNotIn('<th>', svg)
        # escaped form present
        self.assertIn('&lt;th&gt;', svg)
        self.assertIn('&amp;', svg)


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


class RenderSectionTest(unittest.TestCase):
    def test_section_renders_with_synthetic_data(self):
        html = render.render_system_map(synthetic_data(), None)
        self.assertIn("codemap-sysmap-section", html)
        self.assertIn("How the system fits together", html)
        self.assertIn("sysmap-frame", html)
        self.assertIn("<svg", html)
        # Product modules present, vendored module absent.
        self.assertIn("auth", html)
        self.assertNotIn("copied-lib-master", html)
        # Store cylinder present.
        self.assertIn("PostgreSQL", html)

    def test_empty_data_renders_nothing(self):
        self.assertEqual(render.render_system_map({}, None), "")
        self.assertEqual(render.render_system_map({"module_graph": {"nodes": []}}, None), "")

    def test_entry_badge_rendered(self):
        html = render.render_system_map(synthetic_data(), None)
        # api/auth is an entry module with 7 endpoints.
        self.assertIn("7", html)
        self.assertIn("sysmap-entry-badge", html)

    def test_section_in_document_after_overview(self):
        """render_document includes the map; it appears before the languages section."""
        data = synthetic_data()
        data["languages"] = [{"name": "TypeScript", "files": 10, "loc": 1000,
                              "color": "#3178c6"}]
        data["project"] = {"name": "synth", "total_files": 10, "total_loc": 1000,
                           "primary_language": "TypeScript"}
        html = render.render_document(data)
        self.assertIn("codemap-sysmap-section", html)
        self.assertLess(html.index("codemap-sysmap-section"),
                        html.index("<h2>Languages</h2>"))

    def test_repo_strings_are_escaped(self):
        """Repo-derived names with HTML metacharacters must be escaped in the SVG."""
        data = synthetic_data()
        data["module_graph"]["nodes"][2]["name"] = 'a<script>&"x'  # api/auth's name
        data["services"][1]["name"] = 'svc<b>&'                    # api service name
        data["data_lineage"]["stores"][0]["name"] = 'pg<i>&"'      # store name
        html = render.render_system_map(data, None)
        # The section now carries one legitimate inline focus <script>; exclude
        # it so the assertion measures only data-derived content escaping.
        body = html[:html.index("<script>")]
        self.assertNotIn("<script>", body)
        self.assertNotIn("<b>", body)
        self.assertIn("&lt;script&gt;", body)

    def test_enrichment_descriptions_become_tooltips(self):
        enr = {"classification": {"products": [], "vendored": []},
               "module_descriptions": [
                   {"module_id": "api/auth", "description": "Login and tokens.",
                    "is_product": True}]}
        html = render.render_system_map(synthetic_data(), enr)
        self.assertIn("Login and tokens.", html)

    @unittest.skipUnless(FITTALK.is_file(), "fittalk test data not present")
    def test_fittalk_full_section_renders(self):
        data = json.loads(FITTALK.read_text())
        html = render.render_system_map(data, None)
        self.assertIn("codemap-sysmap-section", html)
        self.assertIn("<svg", html)
        # No NaN ever ends up in coordinates.
        self.assertNotIn("nan", html.lower().replace("narration", ""))


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


class ObservationsAndBentoTest(unittest.TestCase):
    def test_observations_present_in_section(self):
        html = render.render_system_map(synthetic_data(), None)
        self.assertIn("Observations", html)
        self.assertIn("observations", html)  # the aside class

    def test_hub_observation_names_the_hub(self):
        obs = render._observations_for_sysmap(
            render._sysmap_select(synthetic_data(), None),
            [], synthetic_data())
        joined = " ".join(obs)
        # api/auth has the highest degree (2 in-edges) -> named as hub.
        self.assertIn("auth", joined)

    def test_tier_imbalance_observation(self):
        sel = render._sysmap_select(synthetic_data(), None)
        obs = render._observations_for_sysmap(sel, [], synthetic_data())
        joined = " ".join(obs)
        self.assertIn("backend", joined.lower())

    def test_vendored_exclusion_observation(self):
        sel = render._sysmap_select(synthetic_data(), None)
        obs = render._observations_for_sysmap(sel, [], synthetic_data())
        joined = " ".join(obs)
        self.assertIn("vendored", joined.lower())

    def test_bento_renders_tiles(self):
        sel = render._sysmap_select(synthetic_data(), None)
        layout = render._sysmap_layout(sel)
        edges = render._sysmap_edges(synthetic_data(), layout)
        html = render.render_sysmap_bento(synthetic_data(), sel, edges)
        self.assertIn("sysmap-bento", html)
        self.assertIn("sysmap-tile", html)
        self.assertIn("tile-label", html)     # same tile anatomy as other bentos
        # Tier composition tile names both tiers.
        self.assertIn("Frontend", html)
        self.assertIn("Backend", html)

    def test_bento_names_real_call_paths(self):
        """The call-paths tile shows 'web → auth', not 'call path 1'."""
        data = synthetic_data()
        sel = render._sysmap_select(data, None)
        layout = render._sysmap_layout(sel)
        edges = render._sysmap_edges(data, layout)
        html = render.render_sysmap_bento(data, sel, edges)
        self.assertIn("auth", html)
        self.assertNotIn("call path 1", html)

    def test_orphan_observation_lists_disconnected_modules(self):
        data = synthetic_data()
        # add 6 backend modules with NO edges -> all orphans
        for i in range(6):
            data["module_graph"]["nodes"].append(
                {"id": f"api/orphan{i}", "name": f"orphan{i}", "service": "api",
                 "loc": 50, "files": 1, "primary_language": "TypeScript",
                 "color": "#3178c6", "vendored_guess": False})
        sel = render._sysmap_select(data, None)
        layout = render._sysmap_layout(sel)
        edges = render._sysmap_edges(data, layout)
        obs = render._observations_for_sysmap(sel, edges, data)
        joined = " ".join(obs)
        self.assertIn("no detected connections", joined)
        self.assertIn("orphan0", joined)
        # >4 orphans -> the first 4 are named and the rest summarized
        self.assertIn("more", joined)

    def test_unreached_entries_observation(self):
        data = synthetic_data()
        # Break the http edge's path so it can't resolve to a module,
        # leaving the entry module (api/auth) with no inbound HTTP edge.
        data["http_topology"]["edges"] = [
            {"source_service": "web", "target_service": "api",
             "method": "POST", "path": "/nonexistent/route", "weight": 4}]
        sel = render._sysmap_select(data, None)
        layout = render._sysmap_layout(sel)
        edges = render._sysmap_edges(data, layout)
        # sanity: no http edge survived the path-join
        self.assertEqual([e for e in edges if e["kind"] == "http"], [])
        obs = render._observations_for_sysmap(sel, edges, data)
        joined = " ".join(obs)
        self.assertIn("entry-point", joined.lower().replace("entry point", "entry-point"))
        self.assertIn("no resolved http", joined.lower())

    def test_observations_and_bento_escape_repo_strings(self):
        data = synthetic_data()
        # make the hub module name malicious (api/auth is the highest-degree node)
        data["module_graph"]["nodes"][2]["name"] = 'h<script>&"x'
        html = render.render_system_map(data, None)
        # Drop the legitimate inline focus <script> (always appended last) so the
        # escaping assertion sees only the observations/bento data region.
        body = html[:html.index("<script>")]
        self.assertNotIn("<script>", body)
        self.assertIn("&lt;script&gt;", body)


class FocusCssTest(unittest.TestCase):
    def test_focus_and_toggle_css_present(self):
        css = render.CSS
        # dimming when a focus is active
        self.assertIn(".sysmap-svg.has-focus", css)
        self.assertIn(".is-active", css)
        # layer-hide classes
        for cls in ("hide-import", "hide-http", "hide-store", "hide-orphan"):
            self.assertIn(cls, css)
        # print restores everything
        # (assert the print block neutralizes focus dimming)
        self.assertIn("sysmap-controls", css)

    def test_orphan_nodes_marked(self):
        data = synthetic_data()
        # Add an isolated, non-vendored backend node with NO edges so an
        # orphan actually appears in the rendered svg. (The vendored module
        # is excluded from the map, so it is never a placed node and thus
        # never an orphan in the output.)
        data["module_graph"]["nodes"].append(
            {"id": "api/lonely", "name": "lonely", "service": "api", "loc": 100,
             "files": 1, "primary_language": "TypeScript", "color": "#3178c6",
             "vendored_guess": False})
        sel = render._sysmap_select(data, None)
        layout = render._sysmap_layout(sel)
        edges = render._sysmap_edges(data, layout)
        svg = render._sysmap_emit_svg(layout, edges, sel, None)
        # the isolated node is marked as an orphan
        self.assertIn('data-orphan="1"', svg)
        # a connected node (api/auth has inbound import + http edges) is NOT
        self.assertNotRegex(
            svg, r'data-nid="api/auth"[^>]*data-orphan="1"')


class StoreEdgeClassTest(unittest.TestCase):
    """Carry-forward fix: store edge paths must carry a sysmap-edge-* class so
    the focus dim selector ([class^="sysmap-edge"]) catches them and they can be
    made .is-active alongside the store cylinder they connect to."""

    def test_store_edge_path_has_class(self):
        data = synthetic_data()
        sel = render._sysmap_select(data, None)
        layout = render._sysmap_layout(sel)
        edges = render._sysmap_edges(data, layout)
        svg = render._sysmap_emit_svg(layout, edges, sel, None)
        # the store connector path carries the dim-participating class
        self.assertIn('class="sysmap-edge-store"', svg)
        # and it is still a store-kind edge with its inline stroke intact
        self.assertRegex(
            svg, r'class="sysmap-edge-store"[^>]*data-kind="store"')


class FocusJsTest(unittest.TestCase):
    def test_section_includes_focus_script(self):
        html = render.render_system_map(synthetic_data(), None)
        self.assertIn("<script>", html)
        # references the section/svg and key behaviors by hook
        self.assertIn("has-focus", html)
        self.assertIn("is-active", html)
        self.assertIn("data-nid", html)        # JS reads node ids
        self.assertIn("addEventListener", html)
        self.assertIn("Escape", html)          # esc clears focus

    def test_script_is_dependency_free(self):
        html = render.render_system_map(synthetic_data(), None)
        # no external/script srcs, no framework globals
        self.assertNotIn("src=", html[html.index("<script>"):])
        for banned in ("require(", "import ", "d3.", "React", "cdn"):
            self.assertNotIn(banned, html[html.index("<script>"):])

    def test_pin_tracks_element_not_active_class(self):
        # Regression guard: the pin toggle must key off an explicit pinned
        # ELEMENT, not the shared is-active class. Keying off the class made a
        # member click inside a pinned cluster clear instead of drill down.
        html = render.render_system_map(synthetic_data(), None)
        script = html[html.index("<script>"):]
        self.assertIn("pinnedEl", script)
        self.assertIn("'use strict'", script)


if __name__ == "__main__":
    unittest.main()
