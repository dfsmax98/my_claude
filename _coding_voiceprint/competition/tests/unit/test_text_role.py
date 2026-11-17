# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from common.text_role import channel_valid


class TextRoleTest(unittest.TestCase):
    def test_channel_quality_requires_text_chars_and_speech(self):
        self.assertTrue(channel_valid({
            "text": "有效客服对话文本有效客服对话文本有效客服对话文本",
            "summary": {"char_count": 30, "speech_duration": 6},
        }))
        self.assertFalse(channel_valid({
            "text": "有效客服对话文本有效客服对话文本有效客服对话文本",
            "summary": {"char_count": 30, "speech_duration": 2},
        }))
        self.assertFalse(channel_valid({
            "text": "太短",
            "summary": {"char_count": 30, "speech_duration": 6},
        }))


if __name__ == "__main__":
    unittest.main()
