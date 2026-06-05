"""Render-time safety net: flows whose citations don't resolve are dropped
before rendering (realizing SKILL.md's "dropped automatically at render time").

The drop is keyed off the repo root recorded in the codemap (project.root) and
is best-effort: a moved/portable codemap whose root is gone must NOT empty the
flows — the scan-time validator stays the primary gate.
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import render


def _flow(name, file_path):
    return {"name": name, "kind": "request", "trigger": "t", "narration": "n",
            "terminates": "e", "steps": [{"label": "s", "file": file_path, "symbol": "h"}]}


class CleanEnrichmentForRenderTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "real.ts").write_text("ok")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _data(self):
        return {"project": {"root": str(self.root)}}

    def test_drops_flow_with_unresolvable_citation(self):
        enr = {"schema_version": 1, "flows": [
            _flow("good", "real.ts"),
            _flow("bad", "ghost.ts"),
        ]}
        cleaned = render.clean_enrichment_for_render(enr, self._data())
        self.assertEqual([f["name"] for f in cleaned["flows"]], ["good"])

    def test_keeps_all_flows_when_root_missing_on_disk(self):
        data = {"project": {"root": "/nonexistent/abc123zzz"}}
        enr = {"schema_version": 1, "flows": [_flow("bad", "ghost.ts")]}
        cleaned = render.clean_enrichment_for_render(enr, data)
        self.assertEqual(len(cleaned["flows"]), 1)

    def test_none_enrichment_passes_through(self):
        self.assertIsNone(render.clean_enrichment_for_render(None, self._data()))

    def test_missing_project_root_passes_through(self):
        enr = {"schema_version": 1, "flows": [_flow("bad", "ghost.ts")]}
        cleaned = render.clean_enrichment_for_render(enr, {"project": {}})
        self.assertEqual(len(cleaned["flows"]), 1)


if __name__ == "__main__":
    unittest.main()
