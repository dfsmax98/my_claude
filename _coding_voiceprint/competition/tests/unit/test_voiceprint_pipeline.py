# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "pipelines"))

from common import vpdb
from test_voiceprint_functions import select_far_threshold


class VoiceprintFunctionTest(unittest.TestCase):
    def test_search_by_identity_uses_best_template_per_actor(self):
        database = {
            "records": [
                {"id": "a1", "actor_id": "actor_a",
                 "emb": np.asarray([1.0, 0.0], dtype=np.float32)},
                {"id": "a2", "actor_id": "actor_a",
                 "emb": np.asarray([0.8, 0.2], dtype=np.float32)},
                {"id": "b1", "actor_id": "actor_b",
                 "emb": np.asarray([0.0, 1.0], dtype=np.float32)},
            ]
        }
        query = np.asarray([1.0, 0.0], dtype=np.float32)
        hits = vpdb.search_by_identity(
            query, database, id_key="actor_id", topk=2)
        self.assertEqual(hits[0], ("actor_a", 1.0, "a1"))
        self.assertEqual(len(hits), 2)

    def test_far_threshold_counts_unsearched_queries_in_denominator(self):
        cases = [
            {"case_type": "black", "black_top1_score": 0.90,
             "black_top1_actor": "b1", "query_identity": "b1",
             "black_search_invoked": True},
            {"case_type": "ordinary", "black_top1_score": 0.80,
             "black_top1_actor": "b2", "query_identity": "c1",
             "black_search_invoked": True},
        ] + [
            {"case_type": "genuine", "black_top1_score": None,
             "black_top1_actor": None, "query_identity": f"g{i}"}
            for i in range(99)
        ]
        threshold = select_far_threshold(cases, target_far=0.01)
        self.assertLessEqual(threshold, 0.80)
        self.assertGreater(threshold, 0.79)

    def test_far_threshold_excludes_score_when_target_is_zero(self):
        cases = [
            {"case_type": "black", "black_top1_score": 0.90,
             "black_top1_actor": "b1", "query_identity": "b1",
             "black_search_invoked": True},
            {"case_type": "ordinary", "black_top1_score": 0.80,
             "black_top1_actor": "b2", "query_identity": "c1",
             "black_search_invoked": True},
        ]
        threshold = select_far_threshold(cases, target_far=0.0)
        self.assertGreater(threshold, 0.80)
        self.assertLess(threshold, 0.90)


if __name__ == "__main__":
    unittest.main()
