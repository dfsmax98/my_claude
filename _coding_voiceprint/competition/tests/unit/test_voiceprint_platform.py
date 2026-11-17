# -*- coding: utf-8 -*-
import io
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from voiceprint_platform.backend import VoiceprintBackend
from voiceprint_platform.clustering import run_customer_clustering
from voiceprint_platform.config import load_platform_config
from voiceprint_platform.service import VoiceprintPlatformService, hash_password
from voiceprint_platform.store import JsonStateStore, now_text


class FakePipeline:
    def process(self, _audio_path, channel_dir):
        channel_dir = Path(channel_dir)
        channel_dir.mkdir(parents=True, exist_ok=True)
        left = channel_dir / "left.wav"
        right = channel_dir / "right.wav"
        left.write_bytes(b"left")
        right.write_bytes(b"right")
        return {
            "audio_info": {
                "bytes": 4,
                "duration": 10.0,
                "channels": 2,
                "sample_rate": 8000,
                "format": "WAV",
            },
            "role": {
                "status": "identified",
                "customer_ch": "R",
                "agent_ch": "L",
                "confidence": "高",
                "margin": 0.9,
                "stage_count": 1,
                "left_summary": {"speech_duration": 8.0, "char_count": 30},
                "right_summary": {"speech_duration": 9.0, "char_count": 40},
            },
            "transcript": {"left": "客服文本", "right": "客户文本"},
            "embedding": np.r_[1.0, np.zeros(191)].astype(np.float32),
            "channels": {"L": str(left), "R": str(right)},
        }


class FakeBackend:
    def __init__(self, config):
        self.config = config

    def quality_score(self, _vector, _role):
        return {"score": 0.95, "threshold": 0.7, "status": "accepted"}

    def self_check(self, _query, templates, _quality):
        if not templates:
            return {"status": "no_template", "score": None, "template_index": None}
        return {"status": "verified", "score": 10.0, "template_index": 0}

    def black_search(self, _query, _templates):
        return {"status": "clear", "threshold": 0.9, "topk": []}

    def model_info(self):
        return {
            "role_model_version": "test-role",
            "embedding_model_version": "test-embedding",
            "backend_version": "test-backend",
            "plda_dimension": 2,
            "quality_threshold": 0.7,
            "self_check": self.config["self_check"],
            "black_search": self.config["black_search"],
        }


class GrayBackend(FakeBackend):
    def self_check(self, _query, templates, _quality):
        if not templates:
            return {"status": "no_template", "score": None, "template_index": None}
        return {
            "status": "review",
            "score": -20.0,
            "template_index": 0,
            "reject_below": -41.0,
            "accept_at_or_above": -14.0,
        }


def test_config(storage):
    return {
        "storage_path": str(storage),
        "black_bootstrap_path": str(Path(storage) / "missing.pkl"),
        "audio": {
            "allowed_extensions": [".wav"],
            "max_upload_bytes": 1024 * 1024,
            "transcript_retention_hours": 24,
        },
        "models": {
            "role_model_version": "test-role",
            "embedding_model_version": "test-embedding",
            "embedding_dimension": 192,
            "backend_version": "test-backend",
        },
        "quality": {"review_below": 0.7, "cohort_topk": 2},
        "self_check": {"reject_below": -2.0, "accept_at_or_above": 2.0},
        "black_search": {"threshold": 0.9, "topk": 5, "backend": "cosine"},
        "security": {
            "default_admin": {
                "username": "admin",
                "display_name": "测试管理员",
                "password_hash": hash_password("unit-test-admin"),
            }
        },
        "gang_cluster": {
            "threshold": 0.9,
            "topk": 2,
            "min_cluster_size": 3,
            "interval_hours": 24,
            "shadow_only": True,
        },
    }


class VoiceprintPlatformTest(unittest.TestCase):
    def test_store_recovers_job_and_round_trips_vector(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonStateStore(temp_dir)
            job = store.create_job("test", {})
            claimed = store.claim_next_job()
            self.assertEqual(claimed["id"], job["id"])
            vector_path = store.save_vector("query", "vector_1", np.ones(192))

            recovered = JsonStateStore(temp_dir)

            self.assertEqual(recovered.get("jobs", job["id"])["status"], "queued")
            self.assertEqual(recovered.load_vector(vector_path).shape, (192,))

    def test_first_recording_auto_enrolls_then_verified_call_updates_template(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = test_config(temp_dir)
            service = VoiceprintPlatformService(
                config,
                start_worker=False,
                pipeline=FakePipeline(),
                backend=FakeBackend(config),
            )
            first = service.submit_recording(io.BytesIO(b"fake"), "call.wav", "customer-secret")
            service.run_next_job()
            first_job = service.get_job(first["id"])
            reviews = service.list_reviews()

            self.assertEqual(first_job["status"], "completed")
            self.assertEqual(reviews, [])
            self.assertIn("customer-secret", service.store.state_path.read_text(encoding="utf-8"))

            customer = service.list_customers()[0]
            self.assertEqual(customer["active_template_count"], 1)
            self.assertEqual(customer["customer_key"], "customer-secret")

            second = service.submit_recording(io.BytesIO(b"fake2"), "call.wav", "customer-secret")
            service.run_next_job()
            second_job = service.get_job(second["id"])
            verification = service.get_verification(second_job["result_id"])

            self.assertEqual(verification["self_check"]["status"], "verified")
            self.assertEqual(verification["labels"], [])
            self.assertEqual(service.list_customers()[0]["active_template_count"], 2)
            for template in service.get_customer(customer["id"])["templates"]:
                self.assertEqual(template["customer_key"], "customer-secret")
            service.close()

    def test_black_enrollment_quality_pass_auto_activates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = test_config(temp_dir)
            service = VoiceprintPlatformService(
                config,
                start_worker=False,
                pipeline=FakePipeline(),
                backend=FakeBackend(config),
            )
            job = service.submit_black_recording(
                io.BytesIO(b"fake"), "black.wav", "actor-secret", "tester"
            )
            service.run_next_job()
            result = service.get_job(job["id"])

            self.assertEqual(service.list_black_actors()[0]["status"], "active")
            self.assertEqual(result["status"], "completed")
            self.assertEqual(service.list_reviews(), [])
            service.close()

    def test_self_check_gray_zone_creates_external_review_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = test_config(temp_dir)
            service = VoiceprintPlatformService(
                config,
                start_worker=False,
                pipeline=FakePipeline(),
                backend=GrayBackend(config),
            )
            first = service.submit_recording(io.BytesIO(b"fake"), "call.wav", "customer-secret")
            service.run_next_job()
            first_job = service.get_job(first["id"])
            self.assertEqual(first_job["status"], "completed")
            self.assertEqual(service.list_customers()[0]["active_template_count"], 1)

            second = service.submit_recording(io.BytesIO(b"fake2"), "call.wav", "customer-secret")
            service.run_next_job()
            second_job = service.get_job(second["id"])
            reviews = service.list_reviews()

            self.assertEqual(service.get_recording(second_job["recording_id"])["status"], "external_review")
            self.assertEqual(reviews[0]["kind"], "self_check_gray_zone")
            service.decide_review(reviews[0]["id"], "approve", "tester")
            self.assertEqual(service.list_customers()[0]["active_template_count"], 1)
            service.close()

    def test_customer_active_template_limit_rolls_out_oldest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = test_config(temp_dir)
            service = VoiceprintPlatformService(
                config,
                start_worker=False,
                pipeline=FakePipeline(),
                backend=FakeBackend(config),
            )
            for index in range(4):
                job = service.submit_recording(
                    io.BytesIO(f"fake-{index}".encode("ascii")),
                    "call.wav",
                    "customer-secret",
                )
                service.run_next_job()
                self.assertEqual(service.get_job(job["id"])["status"], "completed")

            customer = service.list_customers()[0]
            templates = service.get_customer(customer["id"])["templates"]
            active = [row for row in templates if row["status"] == "active"]
            rolled = [row for row in templates if row["status"] == "rolled_out"]

            self.assertEqual(customer["active_template_count"], 3)
            self.assertEqual(len(active), 3)
            self.assertEqual(len(rolled), 1)
            self.assertNotIn("vector_path", rolled[0])
            service.close()

    def test_cluster_run_is_shadow_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonStateStore(temp_dir)
            vector = np.r_[1.0, np.zeros(191)].astype(np.float32)
            for index in range(3):
                customer_id = f"cust_{index}"
                template_id = f"template_{index}"
                store.put("customers", customer_id, {"id": customer_id, "created_at": now_text()})
                path = store.save_vector("customer", template_id, vector)
                store.put(
                    "customer_templates",
                    template_id,
                    {
                        "id": template_id,
                        "customer_id": customer_id,
                        "status": "active",
                        "vector_path": path,
                        "created_at": now_text(),
                    },
                )

            result = run_customer_clustering(store, test_config(temp_dir))

            self.assertTrue(result["shadow_only"])
            self.assertEqual(len(result["clusters"]), 1)
            self.assertEqual(result["clusters"][0]["member_count"], 3)

    def test_real_backend_loads_frozen_models(self):
        backend = VoiceprintBackend(load_platform_config())
        query = backend.cohort[0]
        role = {
            "customer_ch": "R",
            "left_summary": {"speech_duration": 8, "char_count": 30},
            "right_summary": {"speech_duration": 12, "char_count": 50},
            "margin": 0.9,
            "stage_count": 1,
        }

        quality = backend.quality_score(query, role)
        self_check = backend.self_check(query, [query], quality)
        black = backend.black_search(
            query,
            [({"id": "tpl", "actor_id": "actor", "status": "active"}, query)],
        )

        self.assertTrue(0.0 <= quality["score"] <= 1.0)
        self.assertTrue(np.isfinite(self_check["score"]))
        self.assertEqual(black["status"], "suspected")


if __name__ == "__main__":
    unittest.main()
