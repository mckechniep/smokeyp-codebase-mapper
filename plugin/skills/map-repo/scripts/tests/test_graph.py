"""Integration tests for build_module_graph on the graph_repo fixture.

The fixture has real cross-module imports:
  - apps/web -> packages/shared   (TS workspace package import "@graph/shared")
  - services/api -> services/core (Python first-segment import "core")

The same expected edges must hold in BOTH extraction modes (regex fallback
and ast-grep). This file pins regex mode; the ast-grep mode test is added
by a later task.
"""

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scan

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "graph_repo"


def build_graph():
    root = FIXTURE.resolve()
    services, modules = scan.detect_services_and_modules(root)
    return scan.build_module_graph(root, modules, services)


def edge_set(graph):
    return {(e["source"], e["target"]) for e in graph["edges"]}


class GraphRepoRegexModeTest(unittest.TestCase):
    def test_workspace_package_import_creates_edge(self):
        edges = edge_set(build_graph())
        self.assertIn(("apps/web", "packages/shared"), edges)

    def test_python_first_segment_import_creates_edge(self):
        edges = edge_set(build_graph())
        self.assertIn(("services/api", "services/core"), edges)

    def test_no_self_loops(self):
        for e in build_graph()["edges"]:
            self.assertNotEqual(e["source"], e["target"])


if __name__ == "__main__":
    unittest.main()
