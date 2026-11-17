# -*- coding: utf-8 -*-
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from pipelines.evaluate_customer_plda_quality import (
    exact_coverage_mask,
    external_asnorm,
    fit_logistic,
    fit_plda,
    identity_hash,
    load_plda_training,
    load_quality_features,
    predict_logistic,
    score_plda,
    stable_identity_folds,
)


class EvaluateCustomerPldaQualityTest(unittest.TestCase):
    def test_identity_folds_keep_same_identity_together(self):
        identities = np.asarray(["a", "a", "b", "c", "c"])
        folds = stable_identity_folds(identities, fold_count=3)

        self.assertEqual(folds[0], folds[1])
        self.assertEqual(folds[3], folds[4])

    def test_identity_hash_does_not_rehash_sha256(self):
        digest = "a" * 64

        self.assertEqual(identity_hash(digest.upper()), digest)
        self.assertNotEqual(identity_hash("raw_identity"), "raw_identity")

    def test_plda_scores_genuine_pairs_above_impostors(self):
        rng = np.random.default_rng(7)
        centers = rng.normal(size=(20, 12))
        vectors = []
        labels = []
        for identity, center in enumerate(centers):
            for _ in range(3):
                vectors.append(center + rng.normal(scale=0.08, size=12))
                labels.append(str(identity))
        vectors = np.asarray(vectors)
        labels = np.asarray(labels)

        model = fit_plda(vectors, labels, dimension=8)
        matrix = score_plda(model, vectors)
        row, col = np.triu_indices(len(labels), k=1)
        genuine = labels[row] == labels[col]

        self.assertGreater(matrix[row, col][genuine].mean(), matrix[row, col][~genuine].mean())

    def test_external_asnorm_and_exact_coverage(self):
        eval_vectors = np.asarray([[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]])
        cohort = np.asarray([[0.7, 0.7], [-1.0, 0.0], [0.0, -1.0]])
        raw = eval_vectors @ eval_vectors.T

        matrix, means, stds = external_asnorm(raw, eval_vectors, cohort, cohort_size=2)
        mask, threshold = exact_coverage_mask(np.asarray([0.2, 0.9, 0.5]), 2 / 3)

        self.assertEqual(matrix.shape, raw.shape)
        self.assertEqual(means.shape, (3,))
        self.assertTrue(np.all(stds > 0))
        self.assertEqual(mask.tolist(), [False, True, True])
        self.assertEqual(threshold, 0.5)

    def test_logistic_predictions_are_bounded_and_ordered(self):
        features = np.asarray([[-2.0], [-1.0], [1.0], [2.0]])
        targets = np.asarray([0.0, 0.0, 1.0, 1.0])

        model = fit_logistic(features, targets, regularization=0.1)
        predictions = predict_logistic(model, features)

        self.assertTrue(np.all((predictions > 0) & (predictions < 1)))
        self.assertGreater(predictions[-1], predictions[0])

    def test_load_plda_training_accepts_current_role_schema(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "current_role_embeddings.npz"
            np.savez_compressed(
                path,
                embeddings=np.asarray(
                    [[1.0, 0.0], [0.9, 0.1], [0.0, 1.0], [0.1, 0.9]],
                    dtype=np.float32,
                ),
                identity_sha256=np.asarray(["a", "a", "b", "b"]),
                statuses=np.asarray(["identified"] * 4),
                quality_statuses=np.asarray(["valid_dialogue"] * 4),
                confidences=np.asarray(["高"] * 4),
            )

            vectors, labels, stats = load_plda_training(path, {"b"}, 20)

        self.assertEqual(vectors.shape, (2, 2))
        self.assertEqual(labels.tolist(), ["a", "a"])
        self.assertEqual(stats["source_schema"], "role_text_v2_formal")
        self.assertEqual(stats["excluded_eval_overlap_records"], 2)

    def test_load_plda_training_applies_minimum_identity_records(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "minimum_records.npz"
            np.savez_compressed(
                path,
                embeddings=np.eye(5, dtype=np.float32),
                identity_sha256=np.asarray(["a", "a", "b", "b", "b"]),
                needs_review=np.zeros(5, dtype=bool),
            )

            vectors, labels, stats = load_plda_training(path, set(), 20, 3)

        self.assertEqual(vectors.shape, (3, 5))
        self.assertEqual(labels.tolist(), ["b", "b", "b"])
        self.assertEqual(stats["min_identity_records"], 3)

    def test_load_quality_features_accepts_v2_role_results(self):
        path = Path(__file__).resolve().parent / "fixtures_v2_roles.json"
        path.write_text(
            """{
  "records": {
    "rec1": {
      "recording_id": "rec1",
      "customer_ch": "R",
      "margin": 0.9,
      "left_summary": {"speech_duration": 8.0, "char_count": 30},
      "right_summary": {"speech_duration": 12.0, "char_count": 45}
    }
  }
}""",
            encoding="utf-8",
        )
        self.addCleanup(path.unlink)

        features, names = load_quality_features(
            path,
            np.asarray(["rec1"]),
            np.asarray([0.4]),
            np.asarray([0.1]),
        )

        self.assertEqual(features.shape, (1, 6))
        self.assertEqual(names[2], "role_margin")
        self.assertAlmostEqual(features[0, 2], 0.9)
        self.assertAlmostEqual(features[0, 3], 1.0)


if __name__ == "__main__":
    unittest.main()
