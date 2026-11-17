# -*- coding: utf-8 -*-
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from pipelines.build_black_voiceprint_library import (
    actor_id_of,
    build_database,
    formally_eligible,
    score_diagnostics,
    source_actor_key,
    valid_embedding,
)


class BuildBlackVoiceprintLibraryTest(unittest.TestCase):
    def test_actor_key_uses_file_or_top_level_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            direct = root / "20260622-170108019820.mp3"
            nested = root / "160053418285+2026-03-23" / "call.mp3"

            self.assertEqual(source_actor_key(direct, root), "170108019820")
            self.assertEqual(source_actor_key(nested, root), "160053418285")
            self.assertTrue(actor_id_of("170108019820").startswith("black_actor_"))

    def test_formal_gate_rejects_review_or_stage_disagreement(self):
        base = {
            "ok": True,
            "customer_ch": "R",
            "agent_ch": "L",
            "confidence": "高",
            "needs_review": False,
            "stage_disagreement": False,
        }
        audio = {"channels": 2}

        self.assertTrue(formally_eligible(base, audio))
        self.assertFalse(formally_eligible({**base, "needs_review": True}, audio))
        self.assertFalse(formally_eligible({**base, "stage_disagreement": True}, audio))
        self.assertFalse(formally_eligible(base, {"channels": 1}))

    def test_database_groups_multiple_templates_by_actor(self):
        records = [
            {
                "recording_id": "r1",
                "actor_id": "actor_a",
                "audio_sha256": "a" * 64,
                "source_relpath_sha256": "b" * 64,
                "customer_ch": "R",
                "role_margin": 0.9,
                "customer_speech_seconds": 12.0,
                "customer_asr_chars": 40,
                "processed_at": "2026-08-21T00:00:00+08:00",
            },
            {
                "recording_id": "r2",
                "actor_id": "actor_a",
                "audio_sha256": "c" * 64,
                "source_relpath_sha256": "d" * 64,
                "customer_ch": "L",
                "role_margin": 0.95,
                "customer_speech_seconds": 18.0,
                "customer_asr_chars": 50,
                "processed_at": "2026-08-21T00:00:01+08:00",
            },
        ]
        vectors = [
            np.r_[1.0, np.zeros(191)].astype(np.float32),
            np.r_[0.0, 1.0, np.zeros(190)].astype(np.float32),
        ]

        database = build_database(records, vectors, "reviewer")

        self.assertEqual(database["schema_version"], 2)
        self.assertEqual(len(database["records"]), 2)
        self.assertEqual(database["identities"]["actor_a"]["n_calls"], 2)
        self.assertTrue(valid_embedding(vectors[0]))
        diagnostics, review = score_diagnostics(database)
        self.assertEqual(diagnostics["same_actor_pairs"], 1)
        self.assertEqual(diagnostics["cross_actor_pairs"], 0)
        self.assertEqual(review, [])


if __name__ == "__main__":
    unittest.main()
