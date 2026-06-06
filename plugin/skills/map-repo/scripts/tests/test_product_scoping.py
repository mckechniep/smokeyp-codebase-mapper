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

    def _write(self, rel, text):
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
        self.assertEqual(sum(s["loc"] for s in lang_stats.values()),
                         sum(v["loc"] for v in lang_stats.values()))
