# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from common.asr_role import decide_from_summaries, summarize_result
from common.role_id import decide_role_from_scores, kw_score


class AsrRoleTest(unittest.TestCase):
    def test_summary_contains_no_transcript(self):
        result = [{
            "text": "不应保留的完整文本",
            "sentence_info": [
                {"start": 1000, "end": 3000,
                 "text": "很高兴为您服务，请问有什么可以帮您？"},
            ],
        }]
        summary = summarize_result(result)
        self.assertNotIn("text", summary)
        self.assertEqual(summary["first_speech"], 1.0)
        self.assertEqual(summary["speech_duration"], 2.0)
        self.assertGreater(summary["weighted_hits"], 0)

    def test_decide_from_compact_summaries(self):
        left = {"char_count": 100, "score": 50.0, "weighted_hits": 8.0,
                "first_speech": 0.0}
        right = {"char_count": 100, "score": 2.0, "weighted_hits": 0.0,
                 "first_speech": 1.0}
        result = decide_from_summaries(left, right)
        self.assertEqual(result["agent_ch"], "L")
        self.assertEqual(result["customer_ch"], "R")

    def test_summary_without_timestamps_does_not_invent_first_speech(self):
        summary = summarize_result([{"text": "只有转写文本，没有时间戳"}])
        self.assertIsNone(summary["first_speech"])
        self.assertEqual(summary["speech_duration"], 0.0)

    def test_zero_evidence_is_low_confidence(self):
        result = decide_role_from_scores(
            0.0, 0.0, None, None, evidence_a=0.0, evidence_b=0.0)
        self.assertTrue(result["confidence"].startswith("低"))
        self.assertFalse(result["first_speech_used"])

    def test_business_topic_words_are_not_agent_evidence(self):
        score, detail = kw_score("我在你们平台有欠款和费用，征信怎么处理？")
        self.assertEqual(score, 0.0)
        self.assertEqual(sum(detail.values()), 0)

    def test_agent_service_phrases_are_high_confidence(self):
        left = {
            "char_count": 100, "score": 130.0, "weighted_hits": 13.0,
            "first_speech": 0.2,
        }
        right = {
            "char_count": 100, "score": 0.0, "weighted_hits": 0.0,
            "first_speech": 0.5,
        }
        result = decide_from_summaries(left, right)
        self.assertEqual(result["confidence"], "高")
        self.assertEqual(result["agent_ch"], "L")


if __name__ == "__main__":
    unittest.main()
