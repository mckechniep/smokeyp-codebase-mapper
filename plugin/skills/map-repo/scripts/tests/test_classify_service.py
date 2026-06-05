import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scan


class ManifestTokenTest(unittest.TestCase):
    def test_package_json_reads_dependency_keys(self):
        text = '{"dependencies": {"react": "^18"}, "devDependencies": {"vite": "^5"}}'
        toks = scan._manifest_tokens("package.json", text)
        self.assertIn("react", toks)
        self.assertIn("vite", toks)

    def test_package_json_ignores_script_bodies_and_versions(self):
        text = '{"scripts": {"build": "vite build"}, "dependencies": {"left-pad": "1.0.0"}}'
        toks = scan._manifest_tokens("package.json", text)
        self.assertIn("left-pad", toks)
        self.assertNotIn("vite", toks)  # vite appears only in a script body, not a dep

    def test_mix_exs_tokenizes_atoms_not_substrings(self):
        text = ("compilers: [:boundary, :phoenix, :gettext] ++ [:export_gql_schema]\n"
                "{:absinthe, \"~> 1.7\"}")
        toks = scan._manifest_tokens("mix.exs", text)
        self.assertIn("phoenix", toks)
        self.assertIn("absinthe", toks)
        self.assertIn("export_gql_schema", toks)  # the whole token survives
        self.assertNotIn("expo", toks)             # NOT a substring of export_gql_schema


class HitTest(unittest.TestCase):
    def test_bare_name_is_exact(self):
        self.assertTrue(scan._hit("react", {"react"}))
        self.assertFalse(scan._hit("expo", {"export_gql_schema"}))

    def test_scope_prefix(self):
        self.assertTrue(scan._hit("@nestjs/", {"@nestjs/core"}))
        self.assertFalse(scan._hit("@nestjs/", {"nestjs"}))

    def test_full_module_id(self):
        self.assertTrue(scan._hit("github.com/gin-gonic/gin",
                                  {"github.com/gin-gonic/gin"}))


class ClassifyServiceTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _write(self, name, text):
        (self.dir / name).write_text(text)

    def test_phoenix_mix_exs_is_not_frontend(self):
        # The brevity regression: expo must NOT match inside :export_gql_schema.
        self._write("mix.exs",
                    "compilers: [:phoenix, :gettext] ++ [:export_gql_schema]\n")
        kind, _stack = scan._classify_service(self.dir)
        self.assertNotEqual(kind, "frontend")

    def test_react_package_json_is_frontend(self):
        self._write("package.json", '{"dependencies": {"react": "^18", "react-dom": "^18"}}')
        kind, _stack = scan._classify_service(self.dir)
        self.assertEqual(kind, "frontend")


if __name__ == "__main__":
    unittest.main()
