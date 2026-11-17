# -*- coding: utf-8 -*-
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "src" / "pipelines" / "train_text_role_classifier.py"
spec = importlib.util.spec_from_file_location("train_text_role_classifier", SCRIPT)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class TrainTextRoleClassifierTest(unittest.TestCase):
    def test_stable_split_keeps_group_together(self):
        self.assertEqual(module.stable_split("same_identity"),
                         module.stable_split("same_identity"))

    def test_quality_band_rejects_one_sided_recording(self):
        record = {
            "channels": {
                "L": {"text": "客服有效文本足够长客服有效文本足够长",
                      "summary": {"char_count": 30, "speech_duration": 8}},
                "R": {"text": "", "summary": {"char_count": 0,
                                                  "speech_duration": 0}},
            }
        }
        self.assertEqual(module.quality_band(record), "invalid")

    def test_threshold_maximizes_coverage_at_target(self):
        rows = [
            {"margin": 0.9, "correct": True},
            {"margin": 0.8, "correct": True},
            {"margin": 0.7, "correct": True},
            {"margin": 0.1, "correct": False},
        ]
        selected = module.choose_abstain_threshold(rows, 0.95)
        self.assertEqual(selected["accepted"], 3)
        self.assertEqual(selected["accuracy"], 1.0)

    def test_missing_identity_is_excluded_from_model_split(self):
        record = {
            "recording_id": "vp_missing_identity",
            "identity_sha256": "",
            "agent_channel": "L",
            "channels": {
                "L": {"text": "客服有效文本足够长客服有效文本足够长",
                      "summary": {"char_count": 30, "speech_duration": 8}},
                "R": {"text": "客户有效文本足够长客户有效文本足够长",
                      "summary": {"char_count": 30, "speech_duration": 8}},
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "records").mkdir()
            (root / "records" / "sample.json").write_text(
                json.dumps(record, ensure_ascii=False), encoding="utf-8")
            (root / "corpus_summary.json").write_text(
                "{}", encoding="utf-8")
            records, _ = module.load_corpus(root)
        self.assertFalse(records[0]["model_eligible"])
        self.assertEqual(records[0]["split"], "excluded")


if __name__ == "__main__":
    unittest.main()
