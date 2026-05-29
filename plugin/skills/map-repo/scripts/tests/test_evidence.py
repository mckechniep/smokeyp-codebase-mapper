import json
import unittest
from pathlib import Path

# Ensure the scripts directory is importable without installation.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scan
import evidence

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mini_repo"


class EvidencePackTest(unittest.TestCase):
    def setUp(self):
        self.data = scan.build_data_model(FIXTURE, "full")

    def test_includes_manifests_and_readmes(self):
        pack = evidence.build_evidence_pack(FIXTURE, self.data, budget_bytes=200_000)
        paths = {f["path"] for f in pack["files"]}
        self.assertIn("apps/web/package.json", paths)
        self.assertIn("apps/web/README.md", paths)
        self.assertIn("README.md", paths)

    def test_includes_entry_points(self):
        pack = evidence.build_evidence_pack(FIXTURE, self.data, budget_bytes=200_000)
        paths = {f["path"] for f in pack["files"]}
        self.assertTrue(any(p.endswith("index.ts") for p in paths))

    def test_carries_module_list_with_path_key(self):
        pack = evidence.build_evidence_pack(FIXTURE, self.data, budget_bytes=200_000)
        self.assertTrue(pack["modules"])
        self.assertIn("path", pack["modules"][0])

    def test_respects_budget_and_reports_omitted(self):
        pack = evidence.build_evidence_pack(FIXTURE, self.data, budget_bytes=50)
        total = sum(len(f["content"].encode("utf-8")) for f in pack["files"])
        self.assertLessEqual(total, 50 + 8000)  # last-file slack only
        self.assertIn("omitted_count", pack["budget"])

    def test_deterministic(self):
        a = evidence.build_evidence_pack(FIXTURE, self.data, budget_bytes=200_000)
        b = evidence.build_evidence_pack(FIXTURE, self.data, budget_bytes=200_000)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
