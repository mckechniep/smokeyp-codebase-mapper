"""Lock-step guard for the two hand-maintained flow-kind lists.

`validate_enrichment.FLOW_KINDS` is the canonical set of valid kind strings;
`render.FLOW_KIND_META` (presentation) and `render.FLOW_KIND_ORDER` (lane order)
must cover exactly that set. They live in separate modules and are edited by
hand, so without this guard a new kind added to one but not the others would
either fail validation or render with the default fallback label silently.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import render
import validate_enrichment


class FlowKindConsistencyTest(unittest.TestCase):
    def test_render_meta_covers_exactly_the_validator_kinds(self):
        self.assertEqual(
            set(render.FLOW_KIND_META), validate_enrichment.FLOW_KINDS,
            "render.FLOW_KIND_META keys drifted from validate_enrichment.FLOW_KINDS",
        )

    def test_render_order_covers_exactly_the_validator_kinds(self):
        self.assertEqual(
            set(render.FLOW_KIND_ORDER), validate_enrichment.FLOW_KINDS,
            "render.FLOW_KIND_ORDER drifted from validate_enrichment.FLOW_KINDS",
        )


if __name__ == "__main__":
    unittest.main()
