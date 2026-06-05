import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import astgrep_handlers

HAVE_AG = shutil.which("ast-grep") is not None


class HandlerExtractionTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, rel, text):
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return rel

    def test_never_raises_and_returns_dict(self):
        result = astgrep_handlers.collect(self.dir)
        self.assertIsInstance(result, dict)

    def test_bad_binary_returns_empty_dict(self):
        # Deterministic failure-path coverage independent of whether ast-grep
        # is installed: a non-runnable bin_path must yield {} without raising.
        self.assertEqual(astgrep_handlers.collect(self.dir, bin_path="/dev/null"), {})

    @unittest.skipUnless(HAVE_AG, "ast-grep binary not installed")
    def test_nestjs_decorated_methods(self):
        rel = self.write("api/w.controller.ts",
                         "@Controller('workouts')\n"
                         "export class WorkoutsController {\n"
                         "  @Get()\n  list() {}\n"
                         "  @Post()\n  create() {}\n}\n")
        result = astgrep_handlers.collect(self.dir)
        syms = result.get(rel, [])
        self.assertIn("list", syms)
        self.assertIn("create", syms)

    @unittest.skipUnless(HAVE_AG, "ast-grep binary not installed")
    def test_fastapi_route_functions(self):
        rel = self.write("svc/main.py",
                         "@app.get('/x')\ndef get_x():\n    pass\n"
                         "@router.post('/y')\ndef make_y():\n    pass\n")
        result = astgrep_handlers.collect(self.dir)
        syms = result.get(rel, [])
        self.assertIn("get_x", syms)
        self.assertIn("make_y", syms)


if __name__ == "__main__":
    unittest.main()
