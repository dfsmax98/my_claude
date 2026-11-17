# -*- coding: utf-8 -*-
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "src" / "pipelines" / "export_review_asr_sample.py"
spec = importlib.util.spec_from_file_location("export_review_asr_sample", SCRIPT)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class ExportReviewAsrSampleTest(unittest.TestCase):
    def test_selects_five_middle_and_five_low_conflicts(self):
        samples = module.select_samples(
            ROOT / "data" / "processed" / "recent_voiceprints_10k_20260819"
            / "adaptive_roles.json",
            ROOT / "reports" / "recent_voiceprints_role_audit_20260820"
            / "role_review_queue.csv",
            5,
            5,
        )
        self.assertEqual(len(samples), 10)
        self.assertEqual(sum(row["sample_group"] == "中置信" for row in samples), 5)
        self.assertEqual(sum(row["sample_group"] == "低置信" for row in samples), 5)
        self.assertTrue(all(
            row["predicted_customer_ch"] != row["direction_expected_customer_ch"]
            for row in samples
        ))


if __name__ == "__main__":
    unittest.main()
