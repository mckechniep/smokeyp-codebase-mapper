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
