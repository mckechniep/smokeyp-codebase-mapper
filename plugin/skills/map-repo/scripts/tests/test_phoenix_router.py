import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import phoenix_router


def routes(text):
    return {(e["method"], e["path"]) for e in phoenix_router.parse_router(text)}


class VerbAndScopeTest(unittest.TestCase):
    def test_bare_verb_route(self):
        r = routes('get "/health", HealthController, :index\n')
        self.assertIn(("GET", "/health"), r)

    def test_scope_prefix_composes(self):
        text = ('scope "/api", AppWeb do\n'
                '  post "/login", AuthController, :login\n'
                'end\n')
        self.assertIn(("POST", "/api/login"), routes(text))

    def test_nested_scope_prefixes_stack(self):
        text = ('scope "/api", AppWeb do\n'
                '  scope "/v1" do\n'
                '    get "/me", UserController, :me\n'
                '  end\n'
                'end\n')
        self.assertIn(("GET", "/api/v1/me"), routes(text))

    def test_forward_graphql_is_absinthe(self):
        text = 'forward "/graphql", Absinthe.Plug, schema: App.Schema\n'
        eps = phoenix_router.parse_router(text)
        gql = [e for e in eps if e["path"] == "/graphql"]
        self.assertTrue(gql)
        self.assertEqual(gql[0]["framework"], "Absinthe")

    def test_live_route(self):
        text = 'live "/admin/dashboard", DashboardLive\n'
        eps = phoenix_router.parse_router(text)
        live = [e for e in eps if e["path"] == "/admin/dashboard"]
        self.assertTrue(live)
        self.assertEqual(live[0]["method"], "GET")
        self.assertEqual(live[0]["framework"], "Phoenix LiveView")

    def test_pipeline_block_does_not_corrupt_scope_stack(self):
        text = ('pipeline :browser do\n'
                '  plug :accepts, ["html"]\n'
                'end\n'
                'scope "/api" do\n'
                '  get "/ping", PingController, :ping\n'
                'end\n')
        self.assertIn(("GET", "/api/ping"), routes(text))

    def test_never_raises_on_garbage(self):
        self.assertEqual(phoenix_router.parse_router("@#$%^ not elixir {{{"), [])
        self.assertEqual(phoenix_router.parse_router(""), [])

    def test_end_with_trailing_paren_does_not_corrupt_stack(self):
        text = ('scope "/api" do\n'
                '  get "/a", Ctrl, :a\n'
                'end)\n'
                'get "/b", Ctrl, :b\n')
        r = routes(text)
        self.assertIn(("GET", "/b"), r)        # must NOT be /api/b
        self.assertIn(("GET", "/api/a"), r)

    def test_forward_non_absinthe_plug_is_phoenix(self):
        eps = phoenix_router.parse_router('forward "/uploads", UploadPlug\n')
        self.assertEqual(eps[0]["framework"], "Phoenix")


if __name__ == "__main__":
    unittest.main()
