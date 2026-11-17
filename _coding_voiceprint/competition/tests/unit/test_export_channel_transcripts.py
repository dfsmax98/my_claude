# -*- coding: utf-8 -*-
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "pipelines"))

from export_channel_transcripts import _write_markdown


class ExportChannelTranscriptsTest(unittest.TestCase):
    def test_markdown_groups_channels_without_losing_recording_suffix(self):
        records = {
            "cust_1_L": {
                "recording_id": "cust_1", "channel": "L", "text": "左声道文本"},
            "cust_1_R": {
                "recording_id": "cust_1", "channel": "R", "text": "右声道文本"},
            "cust_2_L": {
                "recording_id": "cust_2", "channel": "L", "text": "第二通文本"},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "result.md"
            _write_markdown(output, records, {}, 30)
            text = output.read_text(encoding="utf-8")
        self.assertIn("## 通话 cust_1", text)
        self.assertIn("## 通话 cust_2", text)
        self.assertIn("左声道文本", text)
        self.assertIn("右声道文本", text)


if __name__ == "__main__":
    unittest.main()
