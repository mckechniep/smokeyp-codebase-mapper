import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scan


def _topo():
    return {
        "entry_modules": [
            {"service": "api", "module": "api/workouts", "endpoint_count": 3},
            {"service": "api", "module": "api/auth", "endpoint_count": 1},
            {"service": "api", "module": "vendor/lib-master", "endpoint_count": 5},
        ],
        "endpoints": [
            {"service": "api", "module": "api/workouts", "file": "api/workouts/w.controller.ts",
             "framework": "NestJS", "method": "GET", "path": "/api/v1/workouts"},
            {"service": "api", "module": "api/workouts", "file": "api/workouts/w.controller.ts",
             "framework": "NestJS", "method": "POST", "path": "/api/v1/workouts"},
            {"service": "api", "module": "api/workouts", "file": "api/workouts/extra.ts",
             "framework": "NestJS", "method": "GET", "path": "/api/v1/workouts/stats"},
            {"service": "api", "module": "api/auth", "file": "api/auth/a.controller.ts",
             "framework": "NestJS", "method": "POST", "path": "/api/v1/auth/login"},
            {"service": "api", "module": "vendor/lib-master", "file": "vendor/lib-master/x.ts",
             "framework": "NestJS", "method": "GET", "path": "/v/x"},
        ],
    }


def _graph():
    return {"edges": [
        {"source": "api/workouts", "target": "api/common", "weight": 9},
        {"source": "api/workouts", "target": "vendor/lib-master", "weight": 7},
        {"source": "api/workouts", "target": "api/notifications", "weight": 2},
    ]}


def _lineage():
    return {"edges": [{"source_service": "api", "target_store": "postgres",
                       "models": ["User"], "frameworks": ["Prisma"], "weight": 1}]}


def _modules():
    return [
        {"path": "api/workouts", "vendored_guess": False},
        {"path": "api/auth", "vendored_guess": False},
        {"path": "api/common", "vendored_guess": False},
        {"path": "api/notifications", "vendored_guess": False},
        {"path": "vendor/lib-master", "vendored_guess": True},
    ]


class FlowSkeletonTest(unittest.TestCase):
    def build(self, depth="full"):
        return scan.build_flow_skeletons(_topo(), _graph(), _lineage(), _modules(), depth)

    def test_one_skeleton_per_product_entry_module(self):
        ids = [s["id"] for s in self.build()]
        self.assertEqual(ids, ["api/workouts", "api/auth"])  # vendored excluded, ordered by endpoint count

    def test_trigger_has_route_prefix_and_method_counts(self):
        wk = next(s for s in self.build() if s["id"] == "api/workouts")
        self.assertIn("/api/v1/workouts", wk["trigger"])
        self.assertIn("3 endpoints", wk["trigger"])
        self.assertIn("GET×2", wk["trigger"])
        self.assertIn("POST×1", wk["trigger"])

    def test_entry_file_is_top_contributor(self):
        wk = next(s for s in self.build() if s["id"] == "api/workouts")
        self.assertEqual(wk["entry"]["file"], "api/workouts/w.controller.ts")
        self.assertEqual(wk["entry"]["symbols"], [])  # no handler extraction yet

    def test_key_deps_sorted_capped_and_exclude_vendored(self):
        wk = next(s for s in self.build() if s["id"] == "api/workouts")
        targets = [d["module"] for d in wk["key_deps"]]
        self.assertEqual(targets, ["api/common", "api/notifications"])  # vendor target dropped
        self.assertEqual(wk["key_deps"][0]["weight"], 9)

    def test_stores_from_service_lineage(self):
        wk = next(s for s in self.build() if s["id"] == "api/workouts")
        self.assertEqual(wk["stores"], ["postgres"])

    def test_depth_caps(self):
        self.assertEqual(len(scan.build_flow_skeletons(_topo(), _graph(), _lineage(), _modules(), "full")), 2)
        self.assertEqual(scan.DEPTH_TIERS["shallow"]["max_flow_skeletons"], 10)
        self.assertEqual(scan.DEPTH_TIERS["medium"]["max_flow_skeletons"], 30)
        self.assertIsNone(scan.DEPTH_TIERS["full"]["max_flow_skeletons"])

    def test_entry_file_none_when_no_file_keys(self):
        # Endpoints with no 'file' key -> entry_file None, symbols [] (no crash).
        topo = {
            "entry_modules": [{"service": "api", "module": "api/auth"}],
            "endpoints": [
                {"service": "api", "module": "api/auth", "method": "POST", "path": "/auth/login"},
            ],
        }
        result = scan.build_flow_skeletons(
            topo, {"edges": []}, {"edges": []},
            [{"path": "api/auth", "vendored_guess": False}], "full")
        self.assertIsNone(result[0]["entry"]["file"])
        self.assertEqual(result[0]["entry"]["symbols"], [])

    def test_handler_symbols_populate_entry_symbols(self):
        # Locks the handler_symbols contract before ast-grep wiring (Task 7).
        skels = scan.build_flow_skeletons(
            _topo(), _graph(), _lineage(), _modules(), "full",
            handler_symbols={"api/workouts/w.controller.ts": ["getAll", "create"]})
        wk = next(s for s in skels if s["id"] == "api/workouts")
        self.assertEqual(wk["entry"]["symbols"], ["getAll", "create"])

    def test_route_prefix_edge_cases(self):
        self.assertEqual(scan._longest_common_route_prefix([]), "/")
        self.assertEqual(scan._longest_common_route_prefix(["/a/b", "/c/d"]), "/")


if __name__ == "__main__":
    unittest.main()
