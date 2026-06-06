import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scan


class MeasureDirTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _write(self, rel: str, text: str) -> None:
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def test_measure_dir_returns_per_language_stats(self):
        self._write("a.py", "x = 1\ny = 2\n")        # Python, 2 loc
        self._write("b.py", "z = 3\n")                # Python, 1 loc
        self._write("c.ts", "const a = 1\n")          # TypeScript, 1 loc
        fc, loc, langs, lang_stats = scan._measure_dir(self.dir)
        self.assertEqual(fc, 3)
        self.assertEqual(lang_stats["Python"], {"files": 2, "loc": 3})
        self.assertEqual(lang_stats["TypeScript"], {"files": 1, "loc": 1})
        # langs set unchanged; per-language loc sums to the language totals
        self.assertEqual(set(langs), {"Python", "TypeScript"})
        self.assertEqual(sum(s["loc"] for s in lang_stats.values()), loc)


class FlatServiceContainerTest(unittest.TestCase):
    """Regression: flat service-container module must carry lang_stats.

    A service container with no subdirectories causes _modules_within to
    return empty, triggering the fallback path that emits the container
    itself as a module. That module must include lang_stats.
    """

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _write(self, rel: str, text: str) -> None:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def test_flat_container_module_carries_lang_stats(self) -> None:
        # api/ has a manifest (making it a service container) and source
        # files directly inside — no subdirectories — so _modules_within
        # returns empty and the container itself is emitted as a module.
        self._write("api/package.json", '{"name": "api"}')
        self._write("api/index.js", "const x = 1;\nconst y = 2;\n")   # JS, 2 loc
        self._write("api/util.js", "module.exports = {};\n")            # JS, 1 loc

        _services, modules = scan.detect_services_and_modules(self.root)

        # Find the module whose path is the api container itself
        api_modules = [m for m in modules if m["path"] == "api"]
        self.assertEqual(len(api_modules), 1, "Expected one module for the flat api/ container")
        mod = api_modules[0]

        self.assertIn("lang_stats", mod, "Flat container module must carry lang_stats")
        lang_stats = mod["lang_stats"]
        self.assertTrue(len(lang_stats) > 0, "lang_stats must not be empty")
        # Per-language loc must sum to the module's total loc
        self.assertEqual(
            sum(s["loc"] for s in lang_stats.values()),
            mod["loc"],
            "Per-language loc must sum to module loc",
        )


class SkipDirsTest(unittest.TestCase):
    def test_dependency_caches_are_skipped(self):
        for name in ("deps", "_build", "_checkouts"):
            self.assertIn(name, scan.SKIP_DIRS)

    def test_deps_dir_excluded_from_languages(self):
        d = Path(tempfile.mkdtemp())
        try:
            (d / "lib").mkdir()
            (d / "lib" / "app.ex").write_text("defmodule App do\nend\n")
            (d / "deps").mkdir()
            (d / "deps" / "phoenix").mkdir()
            (d / "deps" / "phoenix" / "lib.ex").write_text("x\n" * 500)
            langs = scan.aggregate_languages(d)
            elixir = next((l for l in langs if l["name"] == "Elixir"), None)
            self.assertIsNotNone(elixir)
            self.assertEqual(elixir["files"], 1)  # only lib/app.ex, not deps/
        finally:
            shutil.rmtree(d, ignore_errors=True)


class LanguageBreakdownTest(unittest.TestCase):
    def _mod(self, path, vendored, stats):
        return {"path": path, "vendored_guess": vendored, "lang_stats": stats}

    def test_vendored_path(self):
        self.assertTrue(scan._vendored_path("google_ads-master/lib/x.ex"))
        self.assertTrue(scan._vendored_path("a/third_party/b.py"))
        self.assertFalse(scan._vendored_path("backend/lib/app.ex"))

    def test_product_is_all_minus_vendored(self):
        languages_all = [
            {"name": "Elixir", "color": "#6e4a7e", "files": 10, "loc": 1000},
            {"name": "HTML", "color": "#e34c26", "files": 5, "loc": 700},
        ]
        modules = [
            self._mod("backend", False, {"Elixir": {"files": 8, "loc": 800}}),
            self._mod("g.frame-develop", True, {"HTML": {"files": 5, "loc": 700}}),
        ]
        prod = scan.build_language_breakdown(languages_all, modules,
                                             lambda m: m["vendored_guess"])
        by = {l["name"]: l for l in prod}
        self.assertNotIn("HTML", by)
        self.assertEqual(by["Elixir"], {"name": "Elixir", "color": "#6e4a7e",
                                        "files": 10, "loc": 1000})

    def test_nested_vendored_not_double_subtracted(self):
        languages_all = [{"name": "JS", "color": "#f1e05a", "files": 10, "loc": 1000}]
        modules = [
            self._mod("ads-master", True, {"JS": {"files": 10, "loc": 1000}}),
            self._mod("ads-master/sub-master", True, {"JS": {"files": 4, "loc": 400}}),
        ]
        prod = scan.build_language_breakdown(languages_all, modules,
                                             lambda m: m["vendored_guess"])
        self.assertEqual(prod, [])  # JS fully vendored, dropped (not negative)

    def test_vendored_only_language_is_ignored(self):
        languages_all = [{"name": "Python", "color": "#3572A5", "files": 4, "loc": 400}]
        modules = [
            self._mod("vendored-master", True,
                      {"Go": {"files": 9, "loc": 900}}),  # Go not in languages_all
        ]
        prod = scan.build_language_breakdown(languages_all, modules,
                                             lambda m: m["vendored_guess"])
        names = {l["name"] for l in prod}
        self.assertNotIn("Go", names)              # orphaned vendored language ignored
        self.assertEqual(prod, [{"name": "Python", "color": "#3572A5",
                                 "files": 4, "loc": 400}])  # Python untouched


class DepsScopingTest(unittest.TestCase):
    def test_vendored_manifest_excluded_from_product_deps(self):
        d = Path(tempfile.mkdtemp())
        try:
            (d / "backend").mkdir()
            (d / "backend" / "mix.exs").write_text(
                'defp deps do\n  [{:phoenix, "~> 1.6"}]\nend\n')
            (d / "google_ads-master").mkdir()
            (d / "google_ads-master" / "mix.exs").write_text(
                'defp deps do\n  [{:grpc, "~> 0.5"}, {:google_protos, "~> 0.1"}]\nend\n')
            product = scan.find_dependencies(d, None, product_only=True)
            repo_wide = scan.find_dependencies(d, None, product_only=False)
            hex_product = next((e for e in product if e["ecosystem"] == "hex"), None)
            hex_all = next((e for e in repo_wide if e["ecosystem"] == "hex"), None)
            self.assertIsNotNone(hex_product, "hex ecosystem missing from product deps")
            self.assertIsNotNone(hex_all, "hex ecosystem missing from repo-wide deps")
            prod_names = {p["name"] for p in hex_product["packages"]}
            all_names = {p["name"] for p in hex_all["packages"]}
            self.assertIn("phoenix", prod_names)
            self.assertNotIn("grpc", prod_names)       # vendored manifest excluded
            self.assertIn("grpc", all_names)            # present repo-wide
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TreeVendoredTest(unittest.TestCase):
    def test_walk_tree_tags_vendored_dirs(self):
        d = Path(tempfile.mkdtemp())
        try:
            (d / "backend").mkdir()
            (d / "backend" / "app.ex").write_text("x\n")
            (d / "google_ads-master").mkdir()
            (d / "google_ads-master" / "x.ex").write_text("y\n" * 100)
            tree = scan.walk_tree(d, None)
            kids = {c["name"]: c for c in tree["children"]}
            self.assertTrue(kids["google_ads-master"].get("vendored"))
            self.assertFalse(kids["backend"].get("vendored", False))
        finally:
            shutil.rmtree(d, ignore_errors=True)
