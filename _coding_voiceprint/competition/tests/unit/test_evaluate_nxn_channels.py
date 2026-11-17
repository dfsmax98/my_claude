# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "pipelines"))

from evaluate_nxn_channels import compute_eer, evaluate_matrix, parse_recording_name


class EvaluateNxnChannelsTest(unittest.TestCase):
    def test_parse_recording_name_uses_last_suffix(self):
        recording_id, identity, sequence = parse_recording_name("customer_group_12.mp3")
        self.assertEqual(recording_id, "customer_group_12")
        self.assertEqual(identity, "customer_group")
        self.assertEqual(sequence, 12)

    def test_compute_eer_separated_scores(self):
        scores = np.asarray([0.9, 0.8, 0.2, 0.1])
        genuine = np.asarray([True, True, False, False])
        eer, threshold = compute_eer(scores, genuine)
        self.assertEqual(eer, 0.0)
        self.assertEqual(threshold, 0.8)

    def test_evaluate_matrix_top1(self):
        matrix = np.asarray([
            [1.0, 0.9, 0.1, 0.2],
            [0.9, 1.0, 0.2, 0.1],
            [0.1, 0.2, 1.0, 0.8],
            [0.2, 0.1, 0.8, 1.0],
        ], dtype=np.float32)
        result = evaluate_matrix(matrix, np.asarray(["a", "a", "b", "b"]))
        self.assertEqual(result["genuine_pairs"], 2)
        self.assertEqual(result["impostor_pairs"], 4)
        self.assertEqual(result["top1_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
