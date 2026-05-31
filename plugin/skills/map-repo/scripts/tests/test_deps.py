import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scan


class ParseManifestMixTest(unittest.TestCase):
    MIX = """
defmodule App.MixProject do
  use Mix.Project

  def project, do: [app: :app, deps: deps()]

  defp deps do
    [
      {:phoenix, "~> 1.7"},
      {:absinthe, "~> 1.7", override: true},
      {:sentry, "~> 8.0"},
      {:vbt, path: "../elixir_common_private"},
      {:some_dep, github: "org/repo", branch: "main"}
    ]
  end
end
"""

    def _parse(self, text: str):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "mix.exs"
            p.write_text(text, encoding="utf-8")
            return {pkg["name"]: pkg["version"]
                    for pkg in scan.parse_manifest(p, "hex")}

    def test_version_tuples(self):
        pkgs = self._parse(self.MIX)
        self.assertEqual(pkgs["phoenix"], "~> 1.7")
        self.assertEqual(pkgs["absinthe"], "~> 1.7")
        self.assertEqual(pkgs["sentry"], "~> 8.0")

    def test_path_and_git_deps_have_no_version(self):
        pkgs = self._parse(self.MIX)
        self.assertEqual(pkgs["vbt"], "*")
        self.assertEqual(pkgs["some_dep"], "*")


class FindDependenciesMonorepoTest(unittest.TestCase):
    def _write(self, root: Path, rel: str, obj: dict) -> None:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj), encoding="utf-8")

    def test_discovers_nested_manifests_and_dedupes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._write(root, "package.json", {"dependencies": {"react": "^18"}})
            self._write(root, "apps/api/package.json",
                        {"dependencies": {"express": "^4", "react": "^18"}})
            # A manifest inside node_modules must be ignored (SKIP_DIRS).
            self._write(root, "node_modules/foo/package.json",
                        {"dependencies": {"should-not-appear": "^1"}})

            deps = scan.find_dependencies(root, max_per_ecosystem=None)
            self.assertEqual(len(deps), 1)
            eco = deps[0]
            self.assertEqual(eco["ecosystem"], "npm")
            names = {p["name"] for p in eco["packages"]}
            # react deduped to a single entry; express present.
            self.assertEqual(names, {"react", "express"})
            self.assertNotIn("should-not-appear", names)
            # Two source files -> "×2" label form.
            self.assertIn("×2", eco["file"])

    def test_single_manifest_uses_relative_path_label(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._write(root, "services/web/package.json",
                        {"dependencies": {"vue": "^3"}})
            deps = scan.find_dependencies(root, max_per_ecosystem=None)
            self.assertEqual(deps[0]["file"], "services/web/package.json")

    def test_max_per_ecosystem_applies_after_merge(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._write(root, "package.json",
                        {"dependencies": {"a": "1", "b": "1", "c": "1"}})
            self._write(root, "pkg/package.json",
                        {"dependencies": {"c": "1", "d": "1"}})
            deps = scan.find_dependencies(root, max_per_ecosystem=2)
            self.assertEqual(deps[0]["count"], 2)
            self.assertEqual(len(deps[0]["packages"]), 2)


if __name__ == "__main__":
    unittest.main()
