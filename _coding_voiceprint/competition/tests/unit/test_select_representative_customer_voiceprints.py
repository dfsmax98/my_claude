# -*- coding: utf-8 -*-
import csv
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from pipelines.select_representative_customer_voiceprints import (  # noqa: E402
    identity_id,
    import_to_platform,
    load_matrix_rows,
    load_quality_rows,
    select_representatives,
)
from voiceprint_platform.store import JsonStateStore  # noqa: E402


def write_quality_csv(path: Path) -> None:
    rows = [
        {
            "recording_id": "cust_a_1",
            "identity": "cust_a",
            "quality_score": "0.70",
            "log_customer_speech_seconds": str(np.log1p(20.0)),
            "log_customer_asr_chars": str(np.log1p(40.0)),
            "role_margin": "0.90",
            "role_stage_count": "1",
        },
        {
            "recording_id": "cust_a_2",
            "identity": "cust_a",
            "quality_score": "0.76",
            "log_customer_speech_seconds": str(np.log1p(55.0)),
            "log_customer_asr_chars": str(np.log1p(90.0)),
            "role_margin": "0.88",
            "role_stage_count": "1",
        },
        {
            "recording_id": "cust_b_1",
            "identity": "cust_b",
            "quality_score": "0.99",
            "log_customer_speech_seconds": str(np.log1p(10.0)),
            "log_customer_asr_chars": str(np.log1p(20.0)),
            "role_margin": "0.95",
            "role_stage_count": "1",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


class RepresentativeCustomerVoiceprintTest(unittest.TestCase):
    def test_selects_best_of_two_and_import_preserves_customer_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            matrix_path = temp / "matrix.npz"
            quality_path = temp / "quality.csv"
            embeddings = np.zeros((3, 192), dtype=np.float32)
            embeddings[:, 0] = 1.0
            np.savez_compressed(
                matrix_path,
                recording_ids=np.asarray(["cust_a_1", "cust_a_2", "cust_b_1"]),
                identities=np.asarray(["cust_a", "cust_a", "cust_b"]),
                embeddings=embeddings,
                trusted_mask=np.asarray([True, True, True]),
            )
            write_quality_csv(quality_path)

            quality_rows = load_quality_rows(quality_path)
            rows = load_matrix_rows(matrix_path, quality_rows)
            selected, skipped = select_representatives(rows)

            self.assertEqual(len(selected), 1)
            self.assertEqual(selected[0]["cust_no"], "cust_a")
            self.assertEqual(selected[0]["recording_id"], "cust_a_2")
            self.assertEqual(skipped["not_two_recordings"], 1)

            config = {
                "storage_path": str(temp / "platform"),
                "models": {"embedding_model_version": "test-campp"},
            }
            result = import_to_platform(
                selected,
                config,
                template_status="active",
                dry_run=False,
            )
            store = JsonStateStore(config["storage_path"])
            customer_id = identity_id("cust_a", "cust")
            customer = store.get("customers", customer_id)
            template = store.list("customer_templates")[0]

            self.assertEqual(result["templates_upserted"], 1)
            self.assertEqual(customer["customer_key"], "cust_a")
            self.assertEqual(customer["cust_no"], "cust_a")
            self.assertEqual(customer["active_template_count"], 1)
            self.assertEqual(template["customer_key"], "cust_a")
            self.assertEqual(template["source_recording_id"], "cust_a_2")


if __name__ == "__main__":
    unittest.main()
