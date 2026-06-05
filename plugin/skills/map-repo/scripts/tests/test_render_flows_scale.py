import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import render


def _data():
    return {"flow_skeletons": [
        {"id": "api/workouts", "service": "Back-End", "endpoint_count": 19,
         "kind_hint": "request", "trigger": "t", "entry": {}, "key_deps": [], "stores": []},
        {"id": "web/checkout", "service": "Front-End", "endpoint_count": 4,
         "kind_hint": "request", "trigger": "t", "entry": {}, "key_deps": [], "stores": []},
        {"id": "api/auth", "service": "Back-End", "endpoint_count": 7,
         "kind_hint": "request", "trigger": "t", "entry": {}, "key_deps": [], "stores": []},
    ]}


def _enr():
    def flow(name, kind, sid=None):
        f = {"name": name, "kind": kind, "trigger": "x", "narration": "n",
             "terminates": "end", "steps": [{"label": "s", "file": "f.ts", "symbol": "h"}]}
        if sid:
            f["skeleton_id"] = sid
        return f
    return {"schema_version": 1, "flows": [
        flow("Workout tracking", "request", "api/workouts"),
        flow("Auth", "request", "api/auth"),
        flow("Checkout", "request", "web/checkout"),
        flow("Nightly cleanup", "scheduled"),
    ]}


class FlowsScaleTest(unittest.TestCase):
    def test_request_lane_groups_by_service(self):
        html = render.render_key_flows(_data(), _enr())
        self.assertIn("flow-service-group", html)
        self.assertIn("Back-End", html)
        self.assertIn("Front-End", html)

    def test_card_shows_endpoint_count_for_skeleton_flows(self):
        html = render.render_key_flows(_data(), _enr())
        self.assertIn("19 endpoints", html)
        self.assertIn("7 endpoints", html)

    def test_coverage_stat_present(self):
        html = render.render_key_flows(_data(), _enr())
        self.assertIn("3 of 3", html)
        self.assertIn("1 non-HTTP", html)

    def test_no_flows_returns_empty(self):
        self.assertEqual(render.render_key_flows(_data(), {"schema_version": 1, "flows": []}), "")
        self.assertEqual(render.render_key_flows(_data(), None), "")

    def test_request_flow_with_unknown_skeleton_lands_in_other(self):
        enr = {"schema_version": 1, "flows": [
            {"name": "Known", "kind": "request", "trigger": "x", "narration": "n",
             "terminates": "e", "steps": [{"file": "f", "symbol": "h"}], "skeleton_id": "api/auth"},
            {"name": "Orphan", "kind": "request", "trigger": "x", "narration": "n",
             "terminates": "e", "steps": [{"file": "f", "symbol": "h"}], "skeleton_id": "gone/missing"},
        ]}
        html = render.render_key_flows(_data(), enr)
        self.assertIn('class="flow-service-head">Other', html)  # unknown skeleton buckets under Other
        self.assertIn('class="flow-service-head">Back-End', html)


if __name__ == "__main__":
    unittest.main()
