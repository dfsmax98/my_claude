# -*- coding: utf-8 -*-
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "src" / "pipelines" / "evaluate_recent_voiceprints_nxn_v2.py"
spec = importlib.util.spec_from_file_location("evaluate_recent_voiceprints_nxn_v2", SCRIPT)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class EvaluateRecentVoiceprintsNxNV2Test(unittest.TestCase):
    def test_same_person_pairs_excludes_self_pairs(self):
        vectors = np.asarray([
            [1.0, 0.0],
            [1.0, 0.0],
            [0.0, 1.0],
        ], dtype=np.float32)
        identities = np.asarray(["a", "a", "b"])
        recording_ids = np.asarray(["r1", "r2", "r3"])
        scores, rows = module.same_person_pairs(vectors, identities, recording_ids)
        self.assertEqual(scores.tolist(), [1.0])
        self.assertEqual(rows[0][1:3], ("r1", "r2"))

    def test_evaluate_vectors_reports_required_metrics(self):
        vectors = np.asarray([
            [1.0, 0.0],
            [0.98, 0.02],
            [0.0, 1.0],
            [0.02, 0.98],
        ], dtype=np.float32)
        vectors = module.normalize_rows(vectors)
        identities = np.asarray(["a", "a", "b", "b"])
        recording_ids = np.asarray(["a1", "a2", "b1", "b2"])
        metrics, same_scores, impostor_scores, _rows = module.evaluate_vectors(
            recording_ids, identities, vectors, max_impostor_pairs=10, seed=7)
        self.assertEqual(metrics["same_person"]["count"], 2)
        self.assertEqual(metrics["impostor_sampling"]["total_pairs"], 4)
        self.assertFalse(metrics["impostor_sampling"]["sampled"])
        self.assertGreater(metrics["same_p05_minus_impostor_p95"], 0)
        self.assertEqual(metrics["top1_identity_retrieval"]["eligible"], 4)
        self.assertEqual(len(same_scores), 2)
        self.assertEqual(len(impostor_scores), 4)

    def test_impostor_scores_enumerate_when_under_limit(self):
        vectors = np.asarray([
            [1.0, 0.0],
            [0.0, 1.0],
            [1.0, 0.0],
        ], dtype=np.float32)
        identities = np.asarray(["a", "b", "c"])
        scores, meta = module.sample_impostor_scores(
            vectors, identities, max_pairs=10, seed=1)
        self.assertFalse(meta["sampled"])
        self.assertEqual(meta["total_pairs"], 3)
        self.assertEqual(meta["sample_pairs"], 3)
        self.assertCountEqual(scores.tolist(), [0.0, 1.0, 0.0])

    def test_metric_delta_uses_new_minus_old(self):
        new = {
            "same_person": {"mean": 0.8, "p05": 0.7},
            "impostor": {"mean": 0.2, "p95": 0.4},
            "eer": 0.1,
            "tar_at_0_751": 0.9,
            "far_at_0_751": 0.05,
            "top1_identity_retrieval": {"accuracy": 0.6},
        }
        old = {
            "same_person": {"mean": 0.75, "p05": 0.6},
            "impostor": {"mean": 0.25, "p95": 0.5},
            "eer": 0.2,
            "tar_at_0_751": 0.8,
            "far_at_0_751": 0.1,
            "top1_identity_retrieval": {"accuracy": 0.5},
        }
        delta = module.metric_delta(new, old)
        self.assertAlmostEqual(delta["same_mean_delta"], 0.05)
        self.assertAlmostEqual(delta["eer_delta"], -0.1)
        self.assertAlmostEqual(delta["far_at_0_751_delta"], -0.05)

    def test_png_fallback_writes_png_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "distribution.png"
            ok = module.write_distribution_png_fallback(
                path,
                np.asarray([0.8, 0.9], dtype=np.float32),
                np.asarray([0.2, 0.3], dtype=np.float32),
            )
            self.assertTrue(ok)
            self.assertTrue(path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))


if __name__ == "__main__":
    unittest.main()
