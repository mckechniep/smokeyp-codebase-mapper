import json
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import render

FIX = Path(__file__).resolve().parent / "fixtures"
FITTALK = Path("/home/mckechniep/projects/fittalk-monorepo/.codemap/codemap.json")


class DegradationTest(unittest.TestCase):
    def test_no_enrichment_matches_golden(self):
        data = json.loads(FITTALK.read_text())
        html = render.render_document(data)            # no enrichment arg
        golden = (FIX / "golden_fittalk.html").read_text()
        self.assertEqual(html, golden)

    def test_none_enrichment_matches_golden(self):
        data = json.loads(FITTALK.read_text())
        html = render.render_document(data, enrichment=None)
        golden = (FIX / "golden_fittalk.html").read_text()
        self.assertEqual(html, golden)


if __name__ == "__main__":
    unittest.main()
