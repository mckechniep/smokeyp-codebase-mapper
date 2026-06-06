import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scan


class EctoModelScanTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _write(self, rel, text):
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def test_ecto_schema_named_by_module_last_segment(self):
        p = self._write(
            "recommendation.ex",
            'defmodule BrevitySchemas.Recommendation do\n'
            '  use BrevitySchemas.Base\n'
            '  schema "recommendations" do\n'
            '    field :history_lesson, :string\n'
            '    belongs_to :trip, Trip\n'
            '  end\n'
            'end\n',
        )
        out = scan._scan_data_models_file(p, "Elixir", "backend")
        self.assertEqual(
            out, [{"service": "backend", "framework": "Ecto", "model": "Recommendation"}])

    def test_ecto_schema_without_module_falls_back_to_table(self):
        p = self._write(
            "orphan.ex", 'schema "widgets" do\n  field :x, :string\nend\n')
        out = scan._scan_data_models_file(p, "Elixir", "backend")
        self.assertEqual(
            out, [{"service": "backend", "framework": "Ecto", "model": "widgets"}])

    def test_embedded_schema_not_matched(self):
        p = self._write(
            "addr.ex",
            'defmodule App.Address do\n  embedded_schema do\n    field :zip, :string\n  end\nend\n',
        )
        out = scan._scan_data_models_file(p, "Elixir", "backend")
        self.assertEqual(out, [])

    def test_ecto_default_store_is_postgres(self):
        self.assertEqual(scan.ORM_DEFAULT_STORE.get("Ecto"), "postgres")


class BuildDataLineageEctoTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def test_ecto_models_appear_in_lineage(self):
        self._write(
            "backend/lib/brevity_schemas/trip.ex",
            'defmodule BrevitySchemas.Trip do\n'
            '  schema "trips" do\n'
            '    field :name, :string\n'
            '  end\n'
            'end\n',
        )
        services = [{"id": "backend", "name": "backend", "kind": "backend"}]
        lin = scan.build_data_lineage(self.root, services)
        ecto = {m["model"] for m in lin["models"] if m["framework"] == "Ecto"}
        self.assertIn("Trip", ecto)
        self.assertTrue(any(s["kind"] == "postgres" for s in lin["stores"]))
        self.assertTrue(any(
            e["target_store"] == "postgres" and "Trip" in e["models"]
            for e in lin["edges"]))


class LineageVendoredFilterTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def test_vendored_ecto_schema_excluded(self):
        self._write(
            "backend/lib/trip.ex",
            'defmodule App.Trip do\n  schema "trips" do\n    field :x, :string\n  end\nend\n')
        self._write(
            "g.frame-develop/lib/foo.ex",
            'defmodule Foo do\n  schema "foos" do\n    field :y, :string\n  end\nend\n')
        services = [{"id": "backend", "name": "backend", "kind": "backend"}]
        lin = scan.build_data_lineage(self.root, services)
        names = {m["model"] for m in lin["models"]}
        self.assertIn("Trip", names)
        self.assertNotIn("Foo", names)  # vendored (-develop) excluded

    def test_vendored_prisma_schema_excluded(self):
        self._write(
            "app/prisma/schema.prisma", 'model Account {\n  id Int @id\n}\n')
        self._write(
            "blues-stack-main/prisma/schema.prisma", 'model User {\n  id Int @id\n}\n')
        services = [{"id": "app", "name": "app", "kind": "backend"}]
        lin = scan.build_data_lineage(self.root, services)
        names = {m["model"] for m in lin["models"]}
        self.assertIn("Account", names)
        self.assertNotIn("User", names)  # vendored (-main) prisma excluded
