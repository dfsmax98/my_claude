# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "web"))

from app import build_overview


class WebDashboardTest(unittest.TestCase):
    def test_overview_uses_aggregate_reports(self):
        overview = build_overview()
        self.assertEqual(overview["dataset"]["recordings"], 862)
        self.assertEqual(overview["dataset"]["identities"], 493)
        self.assertEqual(len(overview["black_metrics"]), 4)
        self.assertEqual(overview["gang_metrics"]["detected"], 0)

    def test_overview_does_not_expose_source_audio_or_identity_rows(self):
        payload = str(build_overview())
        self.assertNotIn("source_audio", payload)
        self.assertNotIn("segment_manifest", payload)
        self.assertNotIn("170116", payload)


if __name__ == "__main__":
    unittest.main()
