# -*- coding: utf-8 -*-
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "pipelines"))

from rebuild_customer_matrix import load_accepted_roles


class RebuildCustomerMatrixTest(unittest.TestCase):
    def test_only_high_confidence_non_review_roles_are_accepted(self):
        payload = {
            "records": {
                "a_1": {"ok": True, "customer_ch": "R", "needs_review": False},
                "b_1": {"ok": True, "customer_ch": "L", "needs_review": True},
                "c_1": {"ok": False, "customer_ch": None, "needs_review": True},
            },
            "failures": {"c_1": {"error": "missing"}},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "roles.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            accepted, records, failures, overrides = load_accepted_roles(path)
        self.assertEqual(set(accepted), {"a_1"})
        self.assertEqual(len(records), 3)
        self.assertEqual(set(failures), {"c_1"})
        self.assertEqual(overrides, {})

    def test_manual_override_replaces_role_and_preserves_original(self):
        payload = {
            "records": {
                "a_1": {
                    "ok": True, "customer_ch": "L", "agent_ch": "R",
                    "confidence": "高", "needs_review": False,
                },
            },
            "failures": {},
        }
        overrides = {
            "a_1": {
                "customer_ch": "R", "agent_ch": "L",
                "review_basis": "双声道ASR文本人工复核",
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            role_path = Path(temp_dir) / "roles.json"
            override_path = Path(temp_dir) / "overrides.json"
            role_path.write_text(json.dumps(payload), encoding="utf-8")
            override_path.write_text(json.dumps(overrides), encoding="utf-8")
            accepted, records, failures, loaded = load_accepted_roles(
                role_path, override_path)
        self.assertEqual(accepted["a_1"]["customer_ch"], "R")
        self.assertEqual(records["a_1"]["manual_override"]["original_customer_ch"], "L")
        self.assertEqual(loaded, overrides)


if __name__ == "__main__":
    unittest.main()
