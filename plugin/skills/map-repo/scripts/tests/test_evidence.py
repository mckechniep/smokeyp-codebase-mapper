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

    def test_pack_forwards_vendored_guess(self):
        data = dict(self.data)
        data["modules"] = [
            {"path": "apps/web", "loc": 10, "file_count": 1, "languages": ["TypeScript"],
             "description": "d", "vendored_guess": False},
            {"path": "vendor/lib-master", "loc": 99, "file_count": 9, "languages": ["JavaScript"],
             "description": "", "vendored_guess": True},
        ]
        pack = evidence.build_evidence_pack(FIXTURE, data)
        by_path = {m["path"]: m for m in pack["modules"]}
        self.assertFalse(by_path["apps/web"]["vendored_guess"])
        self.assertTrue(by_path["vendor/lib-master"]["vendored_guess"])


class EvidenceCliTest(unittest.TestCase):
    def test_cli_writes_evidence_when_requested(self):
        import subprocess, tempfile
        scripts_dir = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "codemap.json"
            ev = Path(td) / "codemap.evidence.json"
            subprocess.run(
                ["python3", str(scripts_dir / "scan.py"),
                 "--path", str(FIXTURE), "--depth", "full",
                 "--out", str(out), "--evidence-out", str(ev)],
                check=True, capture_output=True,
            )
            self.assertTrue(out.is_file())
            self.assertTrue(ev.is_file())
            pack = json.loads(ev.read_text())
            self.assertIn("files", pack)


if __name__ == "__main__":
    unittest.main()
