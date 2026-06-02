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


class NeverRaiseContractTest(unittest.TestCase):
    """collect() must return None on ANY failure — it must never raise.

    These tests mock subprocess.run so they need no real ast-grep binary.
    They use bin_path=sys.executable (a real file) so _find_binary succeeds
    and collect() reaches the subprocess layer.
    """

    class _FakeProc:
        def __init__(self, returncode=0, stdout=""):
            self.returncode = returncode
            self.stdout = stdout

    def _collect_with(self, fake_proc=None, side_effect=None):
        from unittest import mock
        with mock.patch.object(astgrep_imports.subprocess, "run",
                               return_value=fake_proc, side_effect=side_effect):
            return astgrep_imports.collect(
                FIXTURE.resolve(), bin_path=sys.executable)

    def test_non_list_json_returns_none(self):
        # ast-grep printing valid JSON that is not an array (e.g. null)
        self.assertIsNone(self._collect_with(self._FakeProc(stdout="null")))
        self.assertIsNone(self._collect_with(self._FakeProc(stdout="{}")))
        self.assertIsNone(self._collect_with(self._FakeProc(stdout='"oops"')))

    def test_malformed_json_returns_none(self):
        self.assertIsNone(self._collect_with(self._FakeProc(stdout="not json {")))

    def test_nonzero_exit_returns_none(self):
        self.assertIsNone(self._collect_with(self._FakeProc(returncode=1, stdout="[]")))

    def test_timeout_returns_none(self):
        import subprocess as sp
        self.assertIsNone(self._collect_with(
            side_effect=sp.TimeoutExpired(cmd="ast-grep", timeout=120)))

    def test_empty_match_list_returns_bridge_not_none(self):
        # Valid empty result: ast-grep ran fine, found nothing.
        result = self._collect_with(self._FakeProc(stdout="[]"))
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
