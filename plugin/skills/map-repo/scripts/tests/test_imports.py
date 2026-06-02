import unittest
import tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scan


class LanguageDetectionTest(unittest.TestCase):
    def test_elixir_detected(self):
        self.assertEqual(scan.detect_language(Path("lib/app.ex"))[0], "Elixir")
        self.assertEqual(scan.detect_language(Path("lib/app.exs"))[0], "Elixir")


class ElixirImportTest(unittest.TestCase):
    def test_defmodules(self):
        text = "defmodule Brevity.Trips do\n  def x, do: 1\nend\n"
        self.assertEqual(scan._elixir_defmodules(text), ["Brevity.Trips"])

    def test_reference_targets_alias_import_use(self):
        text = ("defmodule A do\n"
                "  alias Brevity.Repo\n"
                "  import Brevity.Web.Helpers\n"
                "  use BrevityWeb, :controller\n"
                "end\n")
        t = scan._elixir_reference_targets(text)
        self.assertIn("Brevity.Repo", t)
        self.assertIn("Brevity.Web.Helpers", t)
        self.assertIn("BrevityWeb", t)

    def test_multi_alias(self):
        text = "  alias Brevity.{Trips, Accounts}\n"
        t = scan._elixir_reference_targets(text)
        self.assertIn("Brevity.Trips", t)
        self.assertIn("Brevity.Accounts", t)


class WorkspacePkgTest(unittest.TestCase):
    def test_scoped(self):
        self.assertEqual(scan._pkg_name_of_specifier("@g.frame/core"), "@g.frame/core")
        self.assertEqual(scan._pkg_name_of_specifier("@g.frame/core/sub"), "@g.frame/core")

    def test_unscoped(self):
        self.assertEqual(scan._pkg_name_of_specifier("lodash"), "lodash")
        self.assertEqual(scan._pkg_name_of_specifier("lodash/fp"), "lodash")

    def test_relative_is_none(self):
        self.assertIsNone(scan._pkg_name_of_specifier("./foo"))
        self.assertIsNone(scan._pkg_name_of_specifier("../bar"))


class JstsBareSpecifierTest(unittest.TestCase):
    def test_returns_paths_and_bare(self):
        text = ('import a from "./local";\n'
                'import b from "@g.frame/core";\n'
                'import c from "lodash";\n')
        paths, bare = scan._jsts_import_targets(Path("/tmp/x/file.ts"), text)
        self.assertTrue(any(str(p).endswith("local") for p in paths))
        self.assertIn("@g.frame/core", bare)
        self.assertIn("lodash", bare)


class PythonImportTest(unittest.TestCase):
    """Pins _python_import_targets — the regex fallback contract."""

    def test_plain_and_dotted_imports_return_first_segment(self):
        text = "import os\nimport os.path\nimport numpy as np\n"  # `os` and `os.path` both pin first segment "os"
        self.assertEqual(scan._python_import_targets(text),
                         ["os", "os", "numpy"])

    def test_from_imports_return_first_segment(self):
        text = "from collections import defaultdict\nfrom a.b.c import d\n"
        self.assertEqual(scan._python_import_targets(text), ["collections", "a"])

    def test_relative_imports_are_skipped(self):
        text = "from . import sibling\nfrom ..pkg import other\n"
        self.assertEqual(scan._python_import_targets(text), [])

    def test_indented_imports_inside_functions_are_found(self):
        text = "def f():\n    import json\n    return json\n"
        self.assertEqual(scan._python_import_targets(text), ["json"])


class GoImportTest(unittest.TestCase):
    """Pins _go_import_targets + _read_go_module_prefix — the regex fallback contract."""

    GO = (
        'package main\n\n'
        'import "fmt"\n\n'
        'import (\n'
        '\t"context"\n'
        '\t"github.com/myorg/myapp/auth"\n'
        '\tsvc "github.com/myorg/myapp/service"\n'
        ')\n'
    )

    def test_internal_imports_have_prefix_stripped(self):
        targets = scan._go_import_targets(self.GO, "github.com/myorg/myapp")
        self.assertCountEqual(targets, ["auth", "service"])

    def test_external_imports_are_dropped(self):
        targets = scan._go_import_targets(self.GO, "github.com/myorg/myapp")
        self.assertNotIn("fmt", targets)
        self.assertNotIn("context", targets)

    def test_no_module_prefix_returns_empty(self):
        self.assertEqual(scan._go_import_targets(self.GO, None), [])

    def test_module_root_import_yields_empty_string(self):
        text = 'package main\n\nimport "github.com/myorg/myapp"\n'
        targets = scan._go_import_targets(text, "github.com/myorg/myapp")
        self.assertEqual(targets, [""])

    def test_read_go_module_prefix(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "go.mod").write_text("module github.com/x/y\n\ngo 1.21\n")
            self.assertEqual(scan._read_go_module_prefix(root), "github.com/x/y")
            self.assertIsNone(scan._read_go_module_prefix(root / "nope"))


if __name__ == "__main__":
    unittest.main()
