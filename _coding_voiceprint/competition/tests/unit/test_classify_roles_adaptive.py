# -*- coding: utf-8 -*-
import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "pipelines"))

from classify_roles_adaptive import (
    _needs_full,
    _text_decision,
    _write_role_labels,
    classify_all,
)


class ClassifyRolesAdaptiveTest(unittest.TestCase):
    def test_non_high_confidence_needs_next_stage(self):
        self.assertFalse(_needs_full({"customer_ch": "R", "confidence": "高"}))
        self.assertTrue(_needs_full({"customer_ch": "R", "confidence": "中"}))
        self.assertTrue(_needs_full({"customer_ch": "R", "confidence": "低(需复核)"}))

    def test_empty_and_one_sided_dialogue_are_rejected(self):
        empty = {"text": "", "summary": {"char_count": 0, "speech_duration": 0}}
        valid = {
            "text": "有效对话文本有效对话文本有效对话文本有效对话文本",
            "summary": {"char_count": 30, "speech_duration": 8},
        }
        self.assertEqual(_text_decision(empty, empty)["status"],
                         "no_effective_dialogue")
        self.assertEqual(_text_decision(valid, empty)["status"], "one_sided")

    def test_right_channel_prior_is_forbidden(self):
        with self.assertRaisesRegex(ValueError, "禁止启用"):
            classify_all(Path("."), [], Path("."), use_right_prior=True)

    def test_review_record_has_no_matrix_index(self):
        rows = [
            {
                "recording_id": "a_1", "customer_ch": "R", "agent_ch": "L",
                "confidence": "高", "final_stage": "30", "stage_disagreement": False,
                "prior_conflict": False, "needs_review": False,
            },
            {
                "recording_id": "b_1", "customer_ch": "L", "agent_ch": "R",
                "confidence": "中", "final_stage": "120", "stage_disagreement": True,
                "prior_conflict": True, "needs_review": True,
            },
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "labels.csv"
            _write_role_labels(output, rows)
            with output.open(encoding="utf-8-sig", newline="") as handle:
                written = list(csv.DictReader(handle))
        self.assertEqual(written[0]["matrix_index"], "0")
        self.assertEqual(written[1]["matrix_index"], "")
        self.assertEqual(written[1]["included_in_matrix"], "False")


if __name__ == "__main__":
    unittest.main()
