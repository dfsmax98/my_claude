# -*- coding: utf-8 -*-
import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "src" / "pipelines" / "refresh_recent_voiceprints_v2.py"
spec = importlib.util.spec_from_file_location("refresh_recent_voiceprints_v2", SCRIPT)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class RefreshRecentVoiceprintsV2Test(unittest.TestCase):
    def test_embedding_cache_key_contains_recording_channel_and_model(self):
        self.assertEqual(
            module.embedding_cache_key("vp_abc", "R", "campp_v1"),
            "vp_abc__R__campp_v1",
        )
        with self.assertRaisesRegex(ValueError, "customer_channel"):
            module.embedding_cache_key("vp_abc", "X")

    def test_formal_index_requires_valid_identified_margin_and_identity(self):
        role = {
            "quality_status": "valid_dialogue",
            "status": "identified",
            "customer_ch": "R",
            "agent_ch": "L",
            "margin": 0.9,
            "threshold": 0.817575,
            "needs_review": False,
        }
        self.assertTrue(module.formal_index_eligible(role, "hash"))
        self.assertFalse(module.formal_index_eligible({**role, "margin": 0.1}, "hash"))
        self.assertFalse(module.formal_index_eligible({**role, "status": "needs_review"}, "hash"))
        self.assertFalse(module.formal_index_eligible({**role, "quality_status": "one_sided"}, "hash"))
        self.assertFalse(module.formal_index_eligible(role, ""))

    def test_validate_embedding_checks_shape_finite_and_norm(self):
        valid = np.ones(192, dtype=np.float32)
        valid /= np.linalg.norm(valid)
        self.assertTrue(module.validate_embedding(valid))
        invalid = valid.copy()
        invalid[0] = np.nan
        self.assertFalse(module.validate_embedding(invalid))
        self.assertFalse(module.validate_embedding(np.ones(191, dtype=np.float32)))
        self.assertFalse(module.validate_embedding(np.zeros(192, dtype=np.float32)))

    def test_select_manifest_rows_supports_ids_and_limit(self):
        rows = [
            {"recording_id": "a"},
            {"recording_id": "b"},
            {"recording_id": "c"},
        ]
        selected = module.select_manifest_rows(rows, {"b", "c"}, 1)
        self.assertEqual([row["recording_id"] for row in selected], ["b"])


if __name__ == "__main__":
    unittest.main()
