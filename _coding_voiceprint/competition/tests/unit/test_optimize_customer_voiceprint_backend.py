# -*- coding: utf-8 -*-
import unittest
import sys
from pathlib import Path

import numpy as np

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from pipelines.optimize_customer_voiceprint_backend import (
    QualityConfig,
    RoleMeta,
    build_asnorm_matrix,
    compute_eer,
    evaluate_matrix,
)


class OptimizeCustomerVoiceprintBackendTest(unittest.TestCase):
    def test_compute_eer_separates_clean_scores(self):
        scores = np.asarray([0.95, 0.9, 0.2, 0.1], dtype=np.float64)
        genuine = np.asarray([True, True, False, False])

        eer, threshold = compute_eer(scores, genuine)

        self.assertEqual(eer, 0.0)
        self.assertGreaterEqual(threshold, 0.9)

    def test_quality_config_mask(self):
        metas = [
            RoleMeta("a", margin=0.91, customer_speech_seconds=12.0,
                     customer_chars=30, final_stage="30", stage_disagreement=False),
            RoleMeta("b", margin=0.80, customer_speech_seconds=12.0,
                     customer_chars=30, final_stage="120", stage_disagreement=False),
            RoleMeta("c", margin=0.95, customer_speech_seconds=6.0,
                     customer_chars=30, final_stage="30", stage_disagreement=False),
        ]
        config = QualityConfig("test", min_speech_seconds=10.0, min_margin=0.90)

        self.assertEqual(config.mask(metas).tolist(), [True, False, False])

    def test_asnorm_keeps_matrix_shape_and_evaluates(self):
        matrix = np.asarray([
            [1.0, 0.9, 0.2, 0.3],
            [0.9, 1.0, 0.25, 0.35],
            [0.2, 0.25, 1.0, 0.88],
            [0.3, 0.35, 0.88, 1.0],
        ], dtype=np.float64)
        identities = np.asarray(["x", "x", "y", "y"])

        normalized = build_asnorm_matrix(matrix, identities, cohort_size=1)
        metrics = evaluate_matrix(
            normalized,
            identities,
            np.asarray([True, True, True, True]),
        )

        self.assertEqual(normalized.shape, matrix.shape)
        self.assertEqual(metrics["genuine_pairs"], 2)
        self.assertEqual(metrics["top1_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
