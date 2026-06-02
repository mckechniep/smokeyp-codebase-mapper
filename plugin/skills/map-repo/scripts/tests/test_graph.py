"""Integration tests for build_module_graph on the graph_repo fixture.

The fixture has real cross-module imports:
  - apps/web -> packages/shared   (TS workspace package import "@graph/shared")
  - services/api -> services/core (Python first-segment import "core")

The same expected edges must hold in BOTH extraction modes (regex fallback
and ast-grep). This file pins regex mode; the ast-grep mode test is added
by Task 5 of docs/superpowers/plans/2026-06-01-astgrep-import-extraction.md.
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
    @classmethod
    def setUpClass(cls):
        cls.graph = build_graph()

    def test_workspace_package_import_creates_edge(self):
        self.assertIn(("apps/web", "packages/shared"), edge_set(self.graph))

    def test_python_first_segment_import_creates_edge(self):
        self.assertIn(("services/api", "services/core"), edge_set(self.graph))

    def test_no_self_loops(self):
        edges = self.graph["edges"]
        self.assertTrue(edges, "fixture produced no edges — test is vacuous")
        for e in edges:
            self.assertNotEqual(e["source"], e["target"])


import os
import shutil

HAVE_ASTGREP = shutil.which("ast-grep") is not None


@unittest.skipUnless(HAVE_ASTGREP, "ast-grep not installed")
class GraphRepoAstGrepModeTest(unittest.TestCase):
    """The same fixture must produce the same edges via ast-grep extraction.

    Why edges match despite the documented Elixir divergence (see
    astgrep_imports.elixir_reference_targets): the regex path's extra bare-base
    reference (`Exapp`) resolves to the module that declares `defmodule Exapp`
    — which is the same module doing the referencing, so _bump_edge skips it
    as a self-loop. Net edges are identical on this fixture.
    """

    @classmethod
    def setUpClass(cls):
        cls.graph = build_graph()  # ast-grep auto-detected -> used

    def test_same_edges_as_regex_mode(self):
        edges = edge_set(self.graph)
        self.assertIn(("apps/web", "packages/shared"), edges)
        self.assertIn(("services/api", "services/core"), edges)

    def test_extraction_mode_is_reported(self):
        self.assertEqual(self.graph.get("extraction"), "ast-grep")


class GraphRepoForcedFallbackTest(unittest.TestCase):
    """With ast-grep unavailable, regex fallback produces the same edges."""

    @classmethod
    def setUpClass(cls):
        os.environ["AST_GREP_BIN"] = "/nonexistent/ast-grep"
        try:
            cls.graph = build_graph()
        finally:
            del os.environ["AST_GREP_BIN"]

    def test_same_edges_with_fallback(self):
        edges = edge_set(self.graph)
        self.assertIn(("apps/web", "packages/shared"), edges)
        self.assertIn(("services/api", "services/core"), edges)

    def test_extraction_mode_is_regex(self):
        self.assertEqual(self.graph.get("extraction"), "regex")


if __name__ == "__main__":
    unittest.main()
