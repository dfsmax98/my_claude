# -*- coding: utf-8 -*-
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "src" / "pipelines" / "audit_role_text_v2.py"
spec = importlib.util.spec_from_file_location("audit_role_text_v2", SCRIPT)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class AuditRoleTextV2Test(unittest.TestCase):
    def test_expected_channel_by_direction(self):
        self.assertEqual(module.expected_channel("I"), "R")
        self.assertEqual(module.expected_channel("O"), "L")
        self.assertIsNone(module.expected_channel(""))
        self.assertIsNone(module.expected_channel("X"))

    def test_missing_direction_is_not_an_immediate_conflict(self):
        self.assertIsNone(module.expected_channel(""))


if __name__ == "__main__":
    unittest.main()
