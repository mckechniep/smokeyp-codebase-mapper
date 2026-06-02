"""Tests for the ast-grep bridge.

Real-binary tests are skipped when ast-grep is not installed (the bridge is
optional by design). The unavailability test always runs.
"""

import shutil
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import astgrep_imports

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "graph_repo"
HAVE_ASTGREP = shutil.which("ast-grep") is not None


class AvailabilityTest(unittest.TestCase):
    def test_collect_returns_none_when_binary_missing(self):
        # Point the bridge at a binary that does not exist.
        result = astgrep_imports.collect(
            FIXTURE.resolve(), bin_path="/nonexistent/ast-grep")
        self.assertIsNone(result)

    @unittest.skipUnless(HAVE_ASTGREP, "ast-grep not installed")
    def test_collect_returns_bridge_when_available(self):
        result = astgrep_imports.collect(FIXTURE.resolve())
        self.assertIsNotNone(result)


@unittest.skipUnless(HAVE_ASTGREP, "ast-grep not installed")
class CollectionTest(unittest.TestCase):
    def setUp(self):
        self.root = FIXTURE.resolve()
        self.ag = astgrep_imports.collect(self.root)

    def test_finds_hits_in_ts_file(self):
        f = self.root / "apps" / "web" / "index.ts"
        self.assertTrue(self.ag.has_file(f))

    def test_unknown_file_has_no_hits(self):
        f = self.root / "does" / "not" / "exist.ts"
        self.assertFalse(self.ag.has_file(f))


if __name__ == "__main__":
    unittest.main()
