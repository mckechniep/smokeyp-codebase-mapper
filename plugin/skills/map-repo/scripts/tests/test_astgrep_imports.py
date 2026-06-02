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


@unittest.skipUnless(HAVE_ASTGREP, "ast-grep not installed")
class PythonConversionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = FIXTURE.resolve()
        cls.ag = astgrep_imports.collect(cls.root)

    def test_python_targets_match_regex_contract(self):
        f = self.root / "services" / "api" / "main.py"
        # main.py has: `import core` and `from core import models`
        # -> first segments, same as scan._python_import_targets.
        # Duplicates are intentional: one entry per import statement,
        # matching the regex extractor's contract (edge weights count them).
        self.assertCountEqual(self.ag.python_targets(f), ["core", "core"])

    def test_python_targets_for_unseen_file_is_empty(self):
        self.assertEqual(self.ag.python_targets(self.root / "nope.py"), [])


@unittest.skipUnless(HAVE_ASTGREP, "ast-grep not installed")
class JstsConversionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = FIXTURE.resolve()
        cls.ag = astgrep_imports.collect(cls.root)

    def test_jsts_targets_split_paths_and_bare(self):
        f = self.root / "apps" / "web" / "index.ts"
        paths, bare = self.ag.jsts_targets(f)
        # "./local" resolves relative to the file's parent
        self.assertIn((f.parent / "local").resolve(), [p.resolve() for p in paths])
        # "@graph/shared" is a bare workspace specifier
        self.assertIn("@graph/shared", bare)

    def test_quotes_are_stripped(self):
        f = self.root / "apps" / "web" / "index.ts"
        paths, bare = self.ag.jsts_targets(f)
        for spec in bare:
            self.assertFalse(spec.startswith("'") or spec.startswith('"'), spec)


@unittest.skipUnless(HAVE_ASTGREP, "ast-grep not installed")
class GoConversionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = FIXTURE.resolve()
        cls.ag = astgrep_imports.collect(cls.root)

    def test_go_internal_targets_strip_prefix(self):
        f = self.root / "services" / "gosvc" / "main.go"
        targets = self.ag.go_internal_targets(f, "github.com/graph/gosvc")
        self.assertEqual(targets, ["auth"])

    def test_go_external_imports_dropped(self):
        f = self.root / "services" / "gosvc" / "main.go"
        targets = self.ag.go_internal_targets(f, "github.com/graph/gosvc")
        self.assertNotIn("fmt", targets)

    def test_go_no_prefix_returns_empty(self):
        f = self.root / "services" / "gosvc" / "main.go"
        self.assertEqual(self.ag.go_internal_targets(f, None), [])

    def test_go_module_root_import_yields_empty_string(self):
        # Pin parity with scan._go_import_targets: an import of the module
        # root itself yields "" (see test_imports.py GoImportTest).
        # The fixture's main.go has no such import, so this asserts absence:
        f = self.root / "services" / "gosvc" / "main.go"
        targets = self.ag.go_internal_targets(f, "github.com/graph/gosvc")
        self.assertNotIn("", targets)


@unittest.skipUnless(HAVE_ASTGREP, "ast-grep not installed")
class ElixirConversionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = FIXTURE.resolve()
        cls.ag = astgrep_imports.collect(cls.root)

    def test_elixir_refs_include_multi_alias_expansion(self):
        f = self.root / "apps" / "exapp" / "lib" / "exapp.ex"
        refs = self.ag.elixir_reference_targets(f)
        self.assertIn("Exapp.Repo", refs)
        self.assertIn("Exapp.Worker", refs)
        self.assertIn("Exapp.Helpers", refs)
        self.assertIn("GenServer", refs)
        # Intentional divergence from the regex extractor: no bare-base
        # artifact for multi-alias lines (see elixir_reference_targets docstring).
        self.assertNotIn("Exapp", refs)

    def test_elixir_defmodules(self):
        f = self.root / "apps" / "exapp" / "lib" / "repo.ex"
        self.assertEqual(self.ag.elixir_defmodules(f), ["Exapp.Repo"])


class StripQuotesTest(unittest.TestCase):
    """_strip_quotes is pure string logic — no ast-grep binary needed."""

    def test_double_and_single_quotes(self):
        self.assertEqual(astgrep_imports.AstGrepImports._strip_quotes('"react"'), "react")
        self.assertEqual(astgrep_imports.AstGrepImports._strip_quotes("'react'"), "react")

    def test_whitespace_padding(self):
        self.assertEqual(astgrep_imports.AstGrepImports._strip_quotes('  "./local"  '), "./local")

    def test_no_quotes_passthrough(self):
        self.assertEqual(astgrep_imports.AstGrepImports._strip_quotes("bare"), "bare")

    def test_mismatched_quotes_passthrough(self):
        self.assertEqual(astgrep_imports.AstGrepImports._strip_quotes('"foo\''), '"foo\'')

    def test_degenerate_inputs(self):
        self.assertEqual(astgrep_imports.AstGrepImports._strip_quotes(""), "")
        self.assertEqual(astgrep_imports.AstGrepImports._strip_quotes('"'), '"')
        self.assertEqual(astgrep_imports.AstGrepImports._strip_quotes('""'), "")


if __name__ == "__main__":
    unittest.main()
