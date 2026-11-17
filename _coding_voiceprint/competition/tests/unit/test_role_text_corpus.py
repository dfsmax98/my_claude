# -*- coding: utf-8 -*-
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "src" / "pipelines" / "build_role_text_corpus.py"
spec = importlib.util.spec_from_file_location("build_role_text_corpus", SCRIPT)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class RoleTextCorpusTest(unittest.TestCase):
    def test_quality_requires_both_channels(self):
        valid = {
            "stages": [{
                "left": {"char_count": 20, "speech_duration": 5},
                "right": {"char_count": 21, "speech_duration": 6},
            }]
        }
        one_sided = {
            "stages": [{
                "left": {"char_count": 20, "speech_duration": 5},
                "right": {"char_count": 19, "speech_duration": 6},
            }]
        }
        empty = {
            "stages": [{
                "left": {"char_count": 0, "speech_duration": 0},
                "right": {"char_count": 0, "speech_duration": 0},
            }]
        }
        self.assertEqual(module.quality_class(valid), "valid_dialogue")
        self.assertEqual(module.quality_class(one_sided), "one_sided")
        self.assertEqual(module.quality_class(empty), "no_effective_dialogue")


if __name__ == "__main__":
    unittest.main()
