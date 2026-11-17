# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from common.gang_cluster import cluster_embeddings, evaluate_clusters


class GangClusterTest(unittest.TestCase):
    def test_separated_gangs_are_recovered(self):
        vectors = np.asarray([
            [1.0, 0.0, 0.0], [0.99, 0.05, 0.0], [0.98, -0.04, 0.0],
            [0.0, 1.0, 0.0], [0.04, 0.99, 0.0], [-0.03, 0.98, 0.0],
            [0.0, 0.0, 1.0],
        ], dtype=np.float32)
        result = cluster_embeddings(vectors, threshold=0.9, topk=3)
        metrics = evaluate_clusters(
            ["gang_a"] * 3 + ["gang_b"] * 3 + ["background_1"],
            result["clusters"])
        self.assertEqual(metrics["cluster_count"], 2)
        self.assertEqual(metrics["false_positive_pairs"], 0)
        self.assertEqual(metrics["gang_detection_recall"], 1.0)


if __name__ == "__main__":
    unittest.main()
