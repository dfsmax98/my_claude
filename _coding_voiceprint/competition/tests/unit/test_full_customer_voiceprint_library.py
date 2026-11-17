# -*- coding: utf-8 -*-
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "src" / "pipelines" / "build_full_customer_voiceprint_library.py"
spec = importlib.util.spec_from_file_location("build_full_customer_voiceprint_library", SCRIPT)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class FullCustomerVoiceprintLibraryTest(unittest.TestCase):
    def test_build_config_defaults_to_1000_batch_and_more_download_workers(self):
        config = module.BuildConfig()
        self.assertEqual(config.batch_size, 1000)
        self.assertEqual(config.download_workers, 8)

    def test_latest_batch_temp_dir_prefers_newest_batch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old_batch = root / "batch_20260820_000001"
            new_batch = root / "batch_20260820_000002"
            other = root / "full_run"
            old_batch.mkdir()
            new_batch.mkdir()
            other.mkdir()
            os.utime(old_batch, (1, 1))
            os.utime(new_batch, (2, 2))
            os.utime(other, (3, 3))
            self.assertEqual(module.latest_batch_temp_dir(root), new_batch)

    def test_candidate_sql_uses_confirmed_full_scope(self):
        config = module.BuildConfig(batch_size=1000)
        sql = module.candidate_sql(config)
        self.assertIn("begin_time >= '2025-01-01 00:00:00'", sql)
        self.assertIn("CAST(NULLIF(TRIM(call_time_length), '') AS DOUBLE) >= 20", sql)
        self.assertIn("cust_no IS NOT NULL", sql)
        self.assertIn("PARTITION BY record_file_url", sql)
        self.assertIn("ORDER BY begin_time DESC, id DESC", sql)
        self.assertTrue(sql.endswith("LIMIT 1000"))
        self.assertNotIn("BETWEEN 20 AND 180", sql)

    def test_candidate_sql_uses_keyset_cursor_without_offset(self):
        config = module.BuildConfig(batch_size=100)
        cursor = module.KeysetCursor("2026-08-01 12:00:00", 12345)
        sql = module.candidate_sql(config, cursor)
        self.assertIn("begin_time < '2026-08-01 12:00:00'", sql)
        self.assertIn("begin_time = '2026-08-01 12:00:00' AND id < '12345'", sql)
        self.assertNotIn("OFFSET", sql.upper())

    def test_embedding_cache_key_contains_channel_and_model_version(self):
        key = module.embedding_cache_key("vp_abc", "L", "model_v1")
        self.assertEqual(key, "vp_abc__L__model_v1")
        with self.assertRaisesRegex(ValueError, "channel"):
            module.embedding_cache_key("vp_abc", "X", "model_v1")

    def test_formal_index_requires_identified_customer_side(self):
        role = {
            "quality_status": "valid_dialogue",
            "status": "identified",
            "customer_ch": "R",
            "agent_ch": "L",
            "margin": 0.9,
            "threshold": 0.817575,
            "needs_review": False,
        }
        self.assertTrue(module.formal_index_eligible(role, "hash"))
        self.assertFalse(module.formal_index_eligible({**role, "needs_review": True}, "hash"))
        self.assertFalse(module.formal_index_eligible({**role, "status": "needs_review"}, "hash"))
        self.assertFalse(module.formal_index_eligible(role, ""))

    def test_process_record_only_emits_customer_embedding(self):
        original_transcribe = module.transcribe_and_classify
        original_extract_paths = module.extract_channel_paths
        original_extract_embedding = module.extract_customer_embedding
        seen_embedding_channels = []
        try:
            module.transcribe_and_classify = lambda audio_path, work_dir: (
                {
                    "status": "identified",
                    "customer_ch": "R",
                    "agent_ch": "L",
                    "quality_status": "valid_dialogue",
                    "margin": 0.9,
                    "threshold": 0.817575,
                    "needs_review": False,
                },
                {"L": Path("left.wav"), "R": Path("right.wav")},
            )
            module.extract_channel_paths = lambda audio_path, work_dir: self.fail("不应重复拆分双声道")

            def fake_extract_customer_embedding(channel_paths, customer_ch):
                seen_embedding_channels.append(customer_ch)
                self.assertEqual(channel_paths[customer_ch], Path("right.wav"))
                return np.ones(192, dtype=np.float32)

            module.extract_customer_embedding = fake_extract_customer_embedding
            with tempfile.TemporaryDirectory() as temp_dir:
                role_dir = Path(temp_dir) / "role"
                role, rows, vectors = module.process_record(
                    {
                        "file": str(Path(temp_dir) / "sample.mp3"),
                        "recording_id": "vp_test",
                        "identity_sha256": "hash",
                        "audio_sha256": "audiohash",
                        "begin_time": "2026-08-21 10:00:00",
                    },
                    "batch_test",
                    role_dir,
                    Path(temp_dir),
                )
        finally:
            module.transcribe_and_classify = original_transcribe
            module.extract_channel_paths = original_extract_paths
            module.extract_customer_embedding = original_extract_embedding
        self.assertEqual(role["customer_ch"], "R")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["channel"], "R")
        self.assertEqual(len(vectors), 1)
        self.assertEqual(vectors[0].shape, (192,))
        self.assertEqual(seen_embedding_channels, ["R"])

    def test_process_record_skips_embedding_when_customer_channel_unknown(self):
        original_transcribe = module.transcribe_and_classify
        original_extract_embedding = module.extract_customer_embedding
        try:
            module.transcribe_and_classify = lambda audio_path, work_dir: (
                {
                    "status": "needs_review",
                    "customer_ch": None,
                    "agent_ch": None,
                    "quality_status": "valid_dialogue",
                    "margin": 0.1,
                    "threshold": 0.817575,
                    "needs_review": True,
                },
                {"L": Path("left.wav"), "R": Path("right.wav")},
            )
            module.extract_customer_embedding = lambda channel_paths, customer_ch: self.fail("未识别客户声道时不应提embedding")
            with tempfile.TemporaryDirectory() as temp_dir:
                role_dir = Path(temp_dir) / "role"
                role, rows, vectors = module.process_record(
                    {
                        "file": str(Path(temp_dir) / "sample.mp3"),
                        "recording_id": "vp_review",
                        "identity_sha256": "hash",
                        "audio_sha256": "audiohash",
                        "begin_time": "2026-08-21 10:00:00",
                    },
                    "batch_test",
                    role_dir,
                    Path(temp_dir),
                )
        finally:
            module.transcribe_and_classify = original_transcribe
            module.extract_customer_embedding = original_extract_embedding
        self.assertEqual(role["status"], "needs_review")
        self.assertEqual(rows, [])
        self.assertEqual(vectors, [])

    def test_cleanup_rejects_path_outside_temp_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "root"
            root.mkdir()
            outside = Path(temp_dir) / "outside"
            outside.mkdir()
            with self.assertRaisesRegex(ValueError, "越界"):
                module.cleanup_batch_temp(outside, root)

    def test_run_build_continues_batch_number_from_index(self):
        seen = []
        original = module.run_one_batch

        def fake_run_one_batch(config, batch_no, delete_audio_after_commit):
            seen.append(batch_no)
            return {"status": "committed", "batch_id": f"batch_{batch_no:06d}"}

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                output_dir = Path(temp_dir) / "library"
                output_dir.mkdir()
                (output_dir / "batch_index.jsonl").write_text(
                    '{"status":"committed","batch_id":"batch_000001"}\n',
                    encoding="utf-8",
                )
                config = module.BuildConfig(output_dir=output_dir)
                module.run_one_batch = fake_run_one_batch
                module.run_build(config, max_batches=1, delete_audio_after_commit=False)
        finally:
            module.run_one_batch = original
        self.assertEqual(seen, [2])


if __name__ == "__main__":
    unittest.main()
