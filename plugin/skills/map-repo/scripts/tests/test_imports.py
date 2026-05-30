import unittest
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


if __name__ == "__main__":
    unittest.main()
