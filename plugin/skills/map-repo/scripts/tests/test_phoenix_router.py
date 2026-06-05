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


class ResourcesTest(unittest.TestCase):
    def test_base_resources_expands_to_eight_routes(self):
        r = routes('resources "/users", UserController\n')
        self.assertEqual(r, {
            ("GET", "/users"), ("GET", "/users/new"), ("POST", "/users"),
            ("GET", "/users/:id"), ("GET", "/users/:id/edit"),
            ("PATCH", "/users/:id"), ("PUT", "/users/:id"),
            ("DELETE", "/users/:id"),
        })

    def test_resources_only(self):
        r = routes('resources "/users", UserController, only: [:index, :show]\n')
        self.assertEqual(r, {("GET", "/users"), ("GET", "/users/:id")})

    def test_resources_except(self):
        r = routes('resources "/users", UserController, except: [:delete, :new, :edit]\n')
        self.assertNotIn(("DELETE", "/users/:id"), r)
        self.assertNotIn(("GET", "/users/new"), r)
        self.assertIn(("GET", "/users"), r)

    def test_resources_param(self):
        r = routes('resources "/users", UserController, param: "uuid"\n')
        self.assertIn(("GET", "/users/:uuid"), r)
        self.assertNotIn(("GET", "/users/:id"), r)

    def test_resources_singleton_drops_index_and_id(self):
        r = routes('resources "/account", AccountController, singleton: true\n')
        self.assertIn(("GET", "/account"), r)         # show, no :id
        self.assertIn(("PATCH", "/account"), r)       # update, no :id
        self.assertNotIn(("GET", "/account/:id"), r)
        self.assertNotIn(("GET", "/account/:id/edit"), r)

    def test_nested_resources_inject_parent_id(self):
        text = ('resources "/users", UserController do\n'
                '  resources "/posts", PostController, only: [:index]\n'
                'end\n')
        self.assertIn(("GET", "/users/:user_id/posts"), routes(text))

    def test_resources_under_scope(self):
        text = ('scope "/api" do\n'
                '  resources "/widgets", WidgetController, only: [:index]\n'
                'end\n')
        self.assertIn(("GET", "/api/widgets"), routes(text))

    def test_scope_then_nested_resources_compose(self):
        text = ('scope "/api" do\n'
                '  resources "/users", UserController do\n'
                '    resources "/posts", PostController, only: [:index]\n'
                '  end\n'
                'end\n')
        self.assertIn(("GET", "/api/users/:user_id/posts"), routes(text))

    def test_three_level_resource_nesting(self):
        text = ('resources "/users", U do\n'
                '  resources "/posts", P do\n'
                '    resources "/comments", C, only: [:index]\n'
                '  end\n'
                'end\n')
        self.assertIn(("GET", "/users/:user_id/posts/:post_id/comments"), routes(text))


if __name__ == "__main__":
    unittest.main()
