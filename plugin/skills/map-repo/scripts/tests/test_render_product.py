import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import render


def _data():
    return {
        "project": {"name": "p", "total_files": 100, "total_loc": 12000,
                    "total_files_all": 700, "total_loc_all": 1300000,
                    "primary_language": "Elixir"},
        "languages": [{"name": "Elixir", "color": "#6e4a7e", "files": 100, "loc": 12000}],
        "languages_all": [{"name": "HTML", "color": "#e34c26", "files": 600, "loc": 1288000},
                          {"name": "Elixir", "color": "#6e4a7e", "files": 100, "loc": 12000}],
        "deps": [{"ecosystem": "hex", "file": "mix.exs", "count": 1,
                  "packages": [{"name": "phoenix", "version": "~> 1.6"}]}],
        "deps_all": [{"ecosystem": "hex", "file": "mix.exs ×84", "count": 119,
                      "packages": [{"name": "phoenix", "version": "~> 1.4"}]}],
    }


class ProductLeadTest(unittest.TestCase):
    def test_cover_leads_with_product_loc(self):
        html = render.render_cover(_data())
        self.assertIn("12,000", html)            # product LOC leads
        self.assertIn("incl. dependencies", html)  # repo-wide secondary line
        self.assertIn("1,300,000", html)           # repo-wide secondary number

    def test_languages_section_leads_product(self):
        html = render.render_languages(_data())
        self.assertIn("Elixir", html)
        self.assertIn("incl. dependencies", html)

    def test_secondary_hidden_when_product_equals_repo_wide(self):
        d = _data()
        d["project"]["total_files_all"] = d["project"]["total_files"]
        d["project"]["total_loc_all"] = d["project"]["total_loc"]
        d["languages_all"] = d["languages"]
        d["deps_all"] = d["deps"]
        self.assertNotIn("incl. dependencies", render.render_cover(d))
        self.assertNotIn("incl. dependencies", render.render_languages(d))
        self.assertNotIn("incl. dependencies", render.render_deps(d))

    def test_deps_secondary_appears_then_hidden(self):
        d = _data()                         # product hex count 1, repo-wide 119
        self.assertIn("incl. dependencies", render.render_deps(d))
        d["deps_all"] = d["deps"]           # now equal
        self.assertNotIn("incl. dependencies", render.render_deps(d))


if __name__ == "__main__":
    unittest.main()
