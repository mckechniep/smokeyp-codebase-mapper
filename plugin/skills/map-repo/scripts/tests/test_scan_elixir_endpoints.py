import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scan

ROUTER = (
    'defmodule AppWeb.Router do\n'
    '  use AppWeb, :router\n'
    '  scope "/api", AppWeb do\n'
    '    post "/login", AuthController, :login\n'
    '    forward "/graphql", Absinthe.Plug, schema: App.Schema\n'
    '  end\n'
    'end\n'
)


class ScannableTest(unittest.TestCase):
    def test_elixir_is_scannable(self):
        self.assertIn("Elixir", scan.SCANNABLE_LANGUAGES)


class ElixirEndpointTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.rel = "lib/app_web/router.ex"
        p = self.dir / self.rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(ROUTER)
        self.path = p

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_scan_endpoints_file_parses_phoenix_router(self):
        eps, fws = scan._scan_endpoints_file(self.path, "Elixir", self.rel, "app", "app")
        paths = {e["path"] for e in eps}
        self.assertIn("/api/login", paths)
        self.assertIn("/api/graphql", paths)
        self.assertIn("Absinthe", fws)

    def test_non_router_elixir_file_emits_nothing(self):
        other = self.dir / "lib/app/foo.ex"
        other.parent.mkdir(parents=True, exist_ok=True)
        other.write_text('get "/x", C, :i\n')  # not a router.ex -> ignored
        eps, _fws = scan._scan_endpoints_file(other, "Elixir", "lib/app/foo.ex", "app", "app")
        self.assertEqual(eps, [])


if __name__ == "__main__":
    unittest.main()
