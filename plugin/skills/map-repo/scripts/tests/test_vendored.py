"""Tests for deterministic vendored-module heuristics.

The mini_repo fixture has a product module (apps/web) and a vendored
git-archive clone (vendor-lib-master). The heuristic must tell them apart
without any LLM involvement, and the flag must propagate to both the
module dicts and the module-graph nodes.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scan

MINI = Path(__file__).resolve().parent / "fixtures" / "mini_repo"


class VendoredHeuristicTest(unittest.TestCase):
    """Unit tests for scan._vendored_guess (pure function)."""

    def test_master_suffix_is_vendored(self):
        self.assertTrue(scan._vendored_guess(
            MINI / "vendor-lib-master", "vendor-lib-master", "mini_repo"))

    def test_develop_suffix_is_vendored(self):
        # Directory need not exist for the path-segment heuristics.
        self.assertTrue(scan._vendored_guess(
            MINI / "g.frame-develop", "g.frame-develop", "mini_repo"))

    def test_extern_path_segment_is_vendored(self):
        self.assertTrue(scan._vendored_guess(
            MINI / "extern" / "lib", "extern/lib", "mini_repo"))

    def test_third_party_segment_is_vendored(self):
        self.assertTrue(scan._vendored_guess(
            MINI / "third_party" / "lib", "third_party/lib", "mini_repo"))

    def test_nested_master_segment_is_vendored(self):
        self.assertTrue(scan._vendored_guess(
            MINI / "google_ads-master" / "lib" / "google",
            "google_ads-master/lib/google", "mini_repo"))

    def test_product_module_is_not_vendored(self):
        self.assertFalse(scan._vendored_guess(
            MINI / "apps" / "web", "apps/web", "mini_repo"))

    def test_main_named_product_dir_is_not_vendored(self):
        # "main" as a directory NAME is fine; only the "-main" SUFFIX flags.
        self.assertFalse(scan._vendored_guess(
            MINI / "src" / "main", "src/main", "mini_repo"))

    def test_foreign_repository_url_is_vendored(self):
        # ext-pkg/package.json has a repository URL belonging to other-org,
        # not this repo — check 3 should flag it as vendored.
        self.assertTrue(scan._vendored_guess(
            MINI / "ext-pkg", "ext-pkg", "mini_repo"))

    def test_own_repository_url_is_not_vendored(self):
        # own-pkg/package.json has a repository URL containing "mini_repo" —
        # the root_name appears in the URL so it should NOT be flagged.
        self.assertFalse(scan._vendored_guess(
            MINI / "own-pkg", "own-pkg", "mini_repo"))


class VendoredFlagPropagationTest(unittest.TestCase):
    """The flag must appear on module dicts and graph nodes."""

    @classmethod
    def setUpClass(cls):
        cls.services, cls.modules = scan.detect_services_and_modules(MINI)

    def test_modules_carry_vendored_guess_key(self):
        for m in self.modules:
            self.assertIn("vendored_guess", m, f"missing flag on {m['path']}")

    def test_vendor_clone_flagged(self):
        flagged = [m["path"] for m in self.modules if m["vendored_guess"]]
        self.assertTrue(any("vendor-lib-master" in p for p in flagged),
                        f"expected vendor-lib-master flagged, got: {flagged}")

    def test_product_not_flagged(self):
        clean = [m["path"] for m in self.modules if not m["vendored_guess"]]
        self.assertTrue(any("web" in p for p in clean),
                        f"expected web module unflagged, got: {clean}")

    def test_graph_nodes_carry_vendored_guess(self):
        graph = scan.build_module_graph(MINI, self.modules, self.services)
        for n in graph["nodes"]:
            self.assertIn("vendored_guess", n, f"missing flag on node {n['id']}")
        flags = {n["id"]: n["vendored_guess"] for n in graph["nodes"]}
        vendored_nodes = [nid for nid, f in flags.items() if f]
        self.assertTrue(any("vendor-lib-master" in nid for nid in vendored_nodes))

    def test_flat_leaf_container_self_emitted(self):
        # A flat-leaf module (no recognised source-root children) must be
        # emitted as a module whose path contains its own directory name.
        # Regression guard for the flat-leaf branch in detect_services_and_modules.
        paths = [m["path"] for m in self.modules]
        self.assertTrue(
            any("vendor-lib-master" in p for p in paths),
            f"flat-leaf vendor-lib-master not emitted as module; got: {paths}",
        )


if __name__ == "__main__":
    unittest.main()
