"""PLDA、embedding质量评分和黑产余弦检索运行时。"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import numpy as np

from pipelines.evaluate_customer_plda_quality import (
    LogisticModel,
    PldaModel,
    predict_logistic,
    score_plda,
)


EXPECTED_QUALITY_FEATURES = [
    "log_customer_speech_seconds",
    "log_customer_asr_chars",
    "role_margin",
    "role_stage_count",
    "external_cohort_topk_mean",
    "external_cohort_topk_std",
]


def normalize(vector: np.ndarray) -> np.ndarray:
    value = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(value))
    if not np.isfinite(value).all() or norm <= 0:
        raise ValueError("embedding包含非法数值或零向量")
    return value / norm


class VoiceprintBackend:
    def __init__(self, config: dict):
        self.config = config
        backend_dir = Path(config["backend_path"])
        self.plda = self._load_plda(backend_dir / "plda_model.npz")
        self.quality = self._load_quality(
            backend_dir / "embedding_quality_model.npz"
        )
        with np.load(
            backend_dir / "external_cohort_snapshot.npz", allow_pickle=False
        ) as data:
            self.cohort = np.asarray(data["embeddings"], dtype=np.float32).copy()
        self.cohort = np.asarray([normalize(row) for row in self.cohort])

    @staticmethod
    def _load_plda(path: Path) -> PldaModel:
        with np.load(path, allow_pickle=False) as data:
            return PldaModel(
                input_mean=data["input_mean"].copy(),
                projection=data["projection"].copy(),
                projected_mean=data["projected_mean"].copy(),
                plus_precision=data["plus_precision"].copy(),
                within_precision=data["within_precision"].copy(),
                total_precision=data["total_precision"].copy(),
                dimension=int(data["dimension"][0]),
            )

    @staticmethod
    def _load_quality(path: Path) -> LogisticModel:
        with np.load(path, allow_pickle=False) as data:
            names = data["feature_names"].astype(str).tolist()
            if names != EXPECTED_QUALITY_FEATURES:
                raise ValueError(f"质量模型特征不兼容: {names}")
            return LogisticModel(
                feature_mean=data["feature_mean"].copy(),
                feature_scale=data["feature_scale"].copy(),
                coefficients=data["coefficients"].copy(),
                regularization=float(data["regularization"][0]),
            )

    def quality_score(self, vector: np.ndarray, role: dict) -> dict:
        query = normalize(vector)
        cohort_scores = self.cohort @ query
        topk = min(int(self.config["quality"]["cohort_topk"]), len(cohort_scores))
        selected = np.partition(cohort_scores, len(cohort_scores) - topk)[-topk:]
        side = role["left_summary" if role["customer_ch"] == "L" else "right_summary"]
        features = np.asarray(
            [[
                np.log1p(float(side.get("speech_duration") or 0.0)),
                np.log1p(float(side.get("char_count") or 0.0)),
                float(role.get("margin") or 0.0),
                float(role.get("stage_count") or 1.0),
                float(selected.mean()),
                float(max(selected.std(), 1e-6)),
            ]],
            dtype=np.float64,
        )
        score = float(predict_logistic(self.quality, features)[0])
        threshold = float(self.config["quality"]["review_below"])
        return {
            "score": score,
            "threshold": threshold,
            "status": "accepted" if score >= threshold else "review",
            "cohort_topk": topk,
            "cohort_mean": float(selected.mean()),
            "cohort_std": float(max(selected.std(), 1e-6)),
        }

    def self_check(
        self,
        query: np.ndarray,
        template_vectors: list[np.ndarray],
        quality: dict,
    ) -> dict:
        if not template_vectors:
            return {"status": "no_template", "score": None, "template_index": None}
        templates = np.asarray([normalize(row) for row in template_vectors])
        scores = score_plda(self.plda, normalize(query)[None, :], templates)[0]
        best_index = int(np.argmax(scores))
        best_score = float(scores[best_index])
        thresholds = self.config["self_check"]
        if quality["status"] != "accepted":
            status = "quality_rejected"
        elif best_score >= float(thresholds["accept_at_or_above"]):
            status = "verified"
        elif best_score < float(thresholds["reject_below"]):
            status = "not_self"
        else:
            status = "review"
        return {
            "status": status,
            "score": best_score,
            "template_index": best_index,
            "reject_below": float(thresholds["reject_below"]),
            "accept_at_or_above": float(thresholds["accept_at_or_above"]),
        }

    def black_search(
        self,
        query: np.ndarray,
        templates: list[tuple[dict, np.ndarray]],
    ) -> dict:
        by_actor: dict[str, list[tuple[dict, np.ndarray]]] = defaultdict(list)
        for metadata, vector in templates:
            if metadata.get("status") == "active":
                by_actor[metadata["actor_id"]].append((metadata, normalize(vector)))
        ranked = []
        query = normalize(query)
        for actor_id, rows in by_actor.items():
            scores = [float(vector @ query) for _, vector in rows]
            best_index = int(np.argmax(scores))
            ranked.append(
                {
                    "actor_id": actor_id,
                    "template_id": rows[best_index][0]["id"],
                    "score": scores[best_index],
                }
            )
        ranked.sort(key=lambda row: row["score"], reverse=True)
        topk = ranked[: int(self.config["black_search"]["topk"])]
        threshold = float(self.config["black_search"]["threshold"])
        review_below = self.config["black_search"].get("review_below")
        review_below = float(review_below) if review_below is not None else threshold
        top_score = topk[0]["score"] if topk else None
        if top_score is not None and top_score >= threshold:
            status = "suspected"
        elif top_score is not None and top_score >= review_below:
            status = "review"
        else:
            status = "clear"
        return {
            "status": status,
            "threshold": threshold,
            "review_below": review_below,
            "topk": topk,
        }

    def model_info(self) -> dict:
        black_search = {
            key: value
            for key, value in self.config["black_search"].items()
            if key != "bootstrap_db"
        }
        return {
            "role_model_version": self.config["models"]["role_model_version"],
            "embedding_model_version": self.config["models"]["embedding_model_version"],
            "backend_version": self.config["models"]["backend_version"],
            "plda_dimension": self.plda.dimension,
            "quality_threshold": self.config["quality"]["review_below"],
            "self_check": self.config["self_check"],
            "black_search": black_search,
        }
