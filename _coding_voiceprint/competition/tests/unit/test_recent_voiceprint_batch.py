# -*- coding: utf-8 -*-
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "src" / "pipelines" / "download_recent_voiceprints.py"
spec = importlib.util.spec_from_file_location("download_recent_voiceprints", SCRIPT)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class RecentVoiceprintBatchTest(unittest.TestCase):
    def test_candidate_sql_has_required_scope_and_stable_order(self):
        sql = module.candidate_sql(10_000)
        self.assertIn("2026-02-19 00:00:00", sql)
        self.assertIn("BETWEEN 20 AND 180", sql)
        self.assertIn("is_double_track", sql)
        self.assertIn("PARTITION BY record_file_url", sql)
        self.assertIn("ORDER BY begin_time DESC, id DESC", sql)
        self.assertTrue(sql.endswith("LIMIT 10000"))

    def test_candidate_sql_does_not_select_phone_or_name(self):
        sql = module.candidate_sql(10_000).lower()
        self.assertNotIn("call_no", sql)
        self.assertNotIn("called_no", sql)
        self.assertNotIn("customer_name", sql)


if __name__ == "__main__":
    unittest.main()
