# -*- coding: utf-8 -*-
"""客户声纹 PLDA、外部 AS-norm 与 embedding 质量评分评估。

评估集使用当日角色模型生成的客户侧 embedding。PLDA 训练身份与评估身份
严格隔离；质量模型使用客户身份互斥的 OOF 预测，避免直接在训练样本上报告效果。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np


MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from pipelines.optimize_customer_voiceprint_backend import (  # noqa: E402
    compute_eer,
    normalize_rows,
)


DEFAULT_REPORT_DIR = (
    MODULE_ROOT / "reports" / "kesu_customer_refresh_role_text_v1_20260820"
)
DEFAULT_MATRIX = DEFAULT_REPORT_DIR / "customer_nxn_matrix.npz"
DEFAULT_ROLES = DEFAULT_REPORT_DIR / "adaptive_roles.json"
DEFAULT_PLDA_TRAIN = (
    MODULE_ROOT / "data" / "recent_voiceprints_10k_20260819"
    / "customer_embeddings.npz"
)
DEFAULT_COHORT_DIR = (
    MODULE_ROOT / "data" / "full_customer_voiceprint_library_20250101_v1"
    / "embedding_batches"
)
DEFAULT_OUTPUT = DEFAULT_REPORT_DIR / "backend_optimization" / "plda_quality"


@dataclass(frozen=True)
class PldaModel:
    input_mean: np.ndarray
    projection: np.ndarray
    projected_mean: np.ndarray
    plus_precision: np.ndarray
    within_precision: np.ndarray
    total_precision: np.ndarray
    dimension: int


@dataclass(frozen=True)
class LogisticModel:
    feature_mean: np.ndarray
    feature_scale: np.ndarray
    coefficients: np.ndarray
    regularization: float


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(content, encoding="utf-8")
    os.replace(temp, path)


def atomic_write_json(path: Path, payload: dict) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


def atomic_save_npz(path: Path, **arrays: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.stem + ".tmp.npz")
    np.savez_compressed(temp, **arrays)
    os.replace(temp, path)


def identity_sha256(identity: str) -> str:
    return hashlib.sha256(str(identity).strip().encode("utf-8")).hexdigest()


def identity_hash(identity: str) -> str:
    value = str(identity).strip().lower()
    if re.fullmatch(r"[0-9a-f]{64}", value):
        return value
    return identity_sha256(value)


def stable_identity_folds(identities: np.ndarray, fold_count: int) -> np.ndarray:
    if fold_count < 2:
        raise ValueError("fold_count 必须大于等于 2")
    return np.asarray(
        [
            int(hashlib.sha256(str(item).encode("utf-8")).hexdigest()[:8], 16)
            % fold_count
            for item in identities
        ],
        dtype=np.int32,
    )


def _positive_definite(matrix: np.ndarray, relative_floor: float) -> np.ndarray:
    symmetric = 0.5 * (matrix + matrix.T)
    values, vectors = np.linalg.eigh(symmetric)
    scale = max(float(values.max()), 1e-6)
    values = np.maximum(values, scale * relative_floor)
    return (vectors * values) @ vectors.T


def fit_plda(
    embeddings: np.ndarray,
    identities: np.ndarray,
    dimension: int = 80,
) -> PldaModel:
    vectors = normalize_rows(embeddings)
    labels = np.asarray(identities).astype(str)
    unique_labels, counts = np.unique(labels, return_counts=True)
    if len(unique_labels) < 10 or int(counts.min()) < 2:
        raise ValueError("PLDA 训练至少需要 10 个身份，且每个身份至少 2 条样本")

    input_mean = vectors.mean(axis=0)
    centered = vectors - input_mean
    covariance = centered.T @ centered / len(centered)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    output_dimension = min(int(dimension), vectors.shape[1], len(vectors) - 1)
    order = np.argsort(eigenvalues)[::-1][:output_dimension]
    projection = eigenvectors[:, order]

    projected = normalize_rows(centered @ projection)
    projected_mean = projected.mean(axis=0)
    projected = projected - projected_mean

    within_scatter = np.zeros((output_dimension, output_dimension), dtype=np.float64)
    class_means = []
    within_dof = 0
    reciprocal_counts = []
    for label in unique_labels:
        group = projected[labels == label]
        group_mean = group.mean(axis=0)
        residual = group - group_mean
        within_scatter += residual.T @ residual
        within_dof += len(group) - 1
        class_means.append(group_mean)
        reciprocal_counts.append(1.0 / len(group))

    within = within_scatter / max(within_dof, 1)
    means = np.asarray(class_means)
    centered_means = means - means.mean(axis=0)
    mean_covariance = centered_means.T @ centered_means / max(len(means) - 1, 1)
    between = mean_covariance - within * float(np.mean(reciprocal_counts))

    within = _positive_definite(within, relative_floor=1e-3)
    between = _positive_definite(between, relative_floor=1e-5)
    total = within + between
    return PldaModel(
        input_mean=input_mean,
        projection=projection,
        projected_mean=projected_mean,
        plus_precision=np.linalg.inv(total + between),
        within_precision=np.linalg.inv(within),
        total_precision=np.linalg.inv(total),
        dimension=output_dimension,
    )


def transform_plda(model: PldaModel, embeddings: np.ndarray) -> np.ndarray:
    vectors = normalize_rows(embeddings)
    projected = normalize_rows((vectors - model.input_mean) @ model.projection)
    return projected - model.projected_mean


def score_plda(
    model: PldaModel,
    left_embeddings: np.ndarray,
    right_embeddings: np.ndarray | None = None,
) -> np.ndarray:
    left = transform_plda(model, left_embeddings)
    right = left if right_embeddings is None else transform_plda(model, right_embeddings)

    left_plus = left @ model.plus_precision
    right_plus = right @ model.plus_precision
    left_within = left @ model.within_precision
    right_within = right @ model.within_precision
    left_total = left @ model.total_precision
    right_total = right @ model.total_precision

    left_plus_diag = np.sum(left_plus * left, axis=1)
    right_plus_diag = np.sum(right_plus * right, axis=1)
    left_within_diag = np.sum(left_within * left, axis=1)
    right_within_diag = np.sum(right_within * right, axis=1)
    left_total_diag = np.sum(left_total * left, axis=1)
    right_total_diag = np.sum(right_total * right, axis=1)

    sum_term = 0.5 * (
        left_plus_diag[:, None]
        + right_plus_diag[None, :]
        + 2.0 * (left_plus @ right.T)
    )
    difference_term = 0.5 * (
        left_within_diag[:, None]
        + right_within_diag[None, :]
        - 2.0 * (left_within @ right.T)
    )
    different_speaker_term = left_total_diag[:, None] + right_total_diag[None, :]
    return -0.5 * (sum_term + difference_term - different_speaker_term)


def select_plda_dimension(
    embeddings: np.ndarray,
    identities: np.ndarray,
    candidates: list[int],
    fold_count: int = 5,
) -> tuple[int, list[dict]]:
    """仅在 PLDA 训练身份内部选择维度，不接触最终评估身份。"""
    folds = stable_identity_folds(identities, fold_count)
    results = []
    for dimension in sorted(set(int(item) for item in candidates)):
        fold_eers = []
        for fold in range(fold_count):
            train = folds != fold
            validation = folds == fold
            model = fit_plda(embeddings[train], identities[train], dimension)
            scores = score_plda(model, embeddings[validation])
            metrics = evaluate_score_matrix(
                scores,
                identities[validation],
                np.ones(int(validation.sum()), dtype=bool),
            )
            fold_eers.append(float(metrics["eer"]))
        results.append(
            {
                "dimension": dimension,
                "fold_eers": fold_eers,
                "mean_eer": float(np.mean(fold_eers)),
                "median_eer": float(np.median(fold_eers)),
            }
        )
    selected = min(results, key=lambda row: (row["mean_eer"], row["dimension"]))
    return int(selected["dimension"]), results


def evaluate_score_matrix(
    matrix: np.ndarray,
    identities: np.ndarray,
    mask: np.ndarray,
) -> dict:
    selected = np.flatnonzero(mask)
    labels = identities[selected]
    scores = matrix[np.ix_(selected, selected)]
    row, col = np.triu_indices(len(selected), k=1)
    pair_scores = scores[row, col]
    genuine = labels[row] == labels[col]
    eer, threshold = compute_eer(pair_scores, genuine)

    counts = Counter(labels.tolist())
    nearest_matrix = scores.copy()
    np.fill_diagonal(nearest_matrix, -np.inf)
    nearest = np.argmax(nearest_matrix, axis=1) if len(selected) else np.asarray([])
    eligible = np.asarray([counts[item] > 1 for item in labels], dtype=bool)
    top1 = (
        float((labels[nearest][eligible] == labels[eligible]).mean())
        if eligible.any()
        else None
    )
    return {
        "record_count": int(len(selected)),
        "identity_count": int(len(counts)),
        "genuine_pairs": int(genuine.sum()),
        "impostor_pairs": int((~genuine).sum()),
        "eer": eer,
        "eer_threshold": threshold,
        "top1_accuracy": top1,
    }


def external_asnorm(
    raw_matrix: np.ndarray,
    eval_embeddings: np.ndarray,
    cohort_embeddings: np.ndarray,
    cohort_size: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    cohort_scores = normalize_rows(eval_embeddings) @ normalize_rows(cohort_embeddings).T
    actual_size = min(int(cohort_size), cohort_scores.shape[1])
    if actual_size < 2:
        raise ValueError("外部 cohort 至少需要 2 条 embedding")
    start = cohort_scores.shape[1] - actual_size
    selected = np.partition(cohort_scores, start, axis=1)[:, start:]
    means = selected.mean(axis=1)
    stds = np.maximum(selected.std(axis=1), 1e-6)
    normalized = 0.5 * (
        (raw_matrix - means[:, None]) / stds[:, None]
        + (raw_matrix - means[None, :]) / stds[None, :]
    )
    return normalized, means, stds


def load_external_cohort(
    batch_dir: Path,
    excluded_identity_hashes: set[str],
) -> tuple[np.ndarray, np.ndarray, dict]:
    if batch_dir.is_file():
        data = np.load(batch_dir, allow_pickle=False)
        embeddings = normalize_rows(data["embeddings"])
        identities = data["identities"].astype(str)
        selected = np.asarray(
            [identity not in excluded_identity_hashes for identity in identities],
            dtype=bool,
        )
        role_versions = json.loads(str(data["role_model_versions_json"][0]))
        original_overlap = int(data["overlap_removed"][0])
        labels = identities[selected]
        return (
            embeddings[selected],
            labels,
            {
                "record_count": int(selected.sum()),
                "identity_count": int(len(set(labels.tolist()))),
                "overlap_removed": original_overlap + int((~selected).sum()),
                "role_model_versions": role_versions,
                "source": "frozen_snapshot",
                "snapshot_path": str(batch_dir),
            },
        )

    embeddings = []
    identities = []
    model_versions = Counter()
    overlap_removed = 0
    for path in sorted(batch_dir.glob("*.npz")):
        data = np.load(path, allow_pickle=False)
        for metadata_text, embedding in zip(data["metadata"].astype(str), data["embeddings"]):
            metadata = json.loads(metadata_text)
            if not metadata.get("formal_index_eligible"):
                continue
            identity = str(metadata["identity_sha256"])
            if identity in excluded_identity_hashes:
                overlap_removed += 1
                continue
            embeddings.append(embedding)
            identities.append(identity)
            model_versions[str(metadata.get("role_model_version") or "unknown")] += 1
    if not embeddings:
        raise RuntimeError(f"外部 cohort 目录没有可用正式客户向量: {batch_dir}")
    labels = np.asarray(identities)
    return (
        normalize_rows(np.asarray(embeddings)),
        labels,
        {
            "record_count": len(embeddings),
            "identity_count": len(set(identities)),
            "overlap_removed": overlap_removed,
            "role_model_versions": dict(model_versions),
            "source": "embedding_batches",
            "source_batch_count": len(list(batch_dir.glob("*.npz"))),
        },
    )


def load_plda_training(
    path: Path,
    excluded_identity_hashes: set[str],
    max_identity_records: int,
    min_identity_records: int = 2,
) -> tuple[np.ndarray, np.ndarray, dict]:
    data = np.load(path, allow_pickle=False)
    embeddings = np.asarray(data["embeddings"], dtype=np.float64)
    identities = data["identity_sha256"].astype(str)
    if "needs_review" in data.files:
        high_confidence = ~data["needs_review"].astype(bool)
        source_schema = "legacy_needs_review"
    elif {"statuses", "quality_statuses", "confidences"}.issubset(data.files):
        high_confidence = (
            (data["statuses"].astype(str) == "identified")
            & (data["quality_statuses"].astype(str) == "valid_dialogue")
            & (data["confidences"].astype(str) == "高")
        )
        source_schema = "role_text_v2_formal"
    else:
        raise ValueError(
            "PLDA训练文件缺少置信筛选字段：需要needs_review，或"
            "statuses/quality_statuses/confidences"
        )
    high_counts = Counter(identities[high_confidence].tolist())
    selected = np.asarray(
        [
            high_confidence[index]
            and min_identity_records <= high_counts[identity] <= max_identity_records
            and identity not in excluded_identity_hashes
            for index, identity in enumerate(identities)
        ],
        dtype=bool,
    )
    labels = identities[selected]
    stats = {
        "source_record_count": int(len(identities)),
        "selected_record_count": int(selected.sum()),
        "selected_identity_count": int(len(set(labels.tolist()))),
        "excluded_eval_overlap_records": int(
            sum(
                high_confidence[index] and identity in excluded_identity_hashes
                for index, identity in enumerate(identities)
            )
        ),
        "max_identity_records": int(max_identity_records),
        "min_identity_records": int(min_identity_records),
        "selection": (
            "正式角色准入且每身份 "
            f"{min_identity_records} 至 {max_identity_records} 条"
        ),
        "source_schema": source_schema,
    }
    return normalize_rows(embeddings[selected]), labels, stats


def sigmoid(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    output = np.empty_like(values)
    nonnegative = values >= 0
    output[nonnegative] = 1.0 / (1.0 + np.exp(-values[nonnegative]))
    exp_values = np.exp(values[~nonnegative])
    output[~nonnegative] = exp_values / (1.0 + exp_values)
    return output


def fit_logistic(
    features: np.ndarray,
    targets: np.ndarray,
    regularization: float = 1.0,
    max_iterations: int = 60,
) -> LogisticModel:
    x = np.asarray(features, dtype=np.float64)
    y = np.asarray(targets, dtype=np.float64)
    if len(np.unique(y)) != 2:
        raise ValueError("Logistic 训练目标必须同时包含正负样本")
    mean = x.mean(axis=0)
    scale = np.maximum(x.std(axis=0), 1e-6)
    design = np.column_stack([np.ones(len(x)), (x - mean) / scale])
    coefficients = np.zeros(design.shape[1], dtype=np.float64)
    penalty = np.eye(design.shape[1]) * (regularization / len(x))
    penalty[0, 0] = 0.0
    for _ in range(max_iterations):
        probabilities = sigmoid(design @ coefficients)
        weights = np.maximum(probabilities * (1.0 - probabilities), 1e-6)
        gradient = design.T @ (probabilities - y) / len(y) + penalty @ coefficients
        hessian = (design.T * weights) @ design / len(y) + penalty
        step = np.linalg.solve(hessian, gradient)
        coefficients -= step
        if float(np.max(np.abs(step))) < 1e-8:
            break
    return LogisticModel(mean, scale, coefficients, regularization)


def predict_logistic(model: LogisticModel, features: np.ndarray) -> np.ndarray:
    standardized = (np.asarray(features) - model.feature_mean) / model.feature_scale
    design = np.column_stack([np.ones(len(standardized)), standardized])
    return sigmoid(design @ model.coefficients)


def retrieval_targets(score_matrix: np.ndarray, identities: np.ndarray) -> np.ndarray:
    targets = np.full(len(identities), np.nan, dtype=np.float64)
    for index, identity in enumerate(identities):
        genuine = identities == identity
        genuine[index] = False
        impostor = identities != identity
        if genuine.any() and impostor.any():
            targets[index] = float(
                score_matrix[index, genuine].max() > score_matrix[index, impostor].max()
            )
    return targets


def load_quality_features(
    roles_path: Path,
    recording_ids: np.ndarray,
    cohort_means: np.ndarray,
    cohort_stds: np.ndarray,
) -> tuple[np.ndarray, list[str]]:
    payload = json.loads(roles_path.read_text(encoding="utf-8"))
    records = payload.get("records", payload) if isinstance(payload, dict) else payload
    rows = []
    for index, recording_id in enumerate(recording_ids.astype(str)):
        item = records[recording_id] if isinstance(records, dict) else next(
            row for row in records if row["recording_id"] == recording_id
        )
        customer_ch = item["customer_ch"]
        side_name = {"L": "left", "R": "right"}[customer_ch]
        if "stages" in item:
            stage = item["stages"][-1]
            side = stage[side_name]
            margin = float(stage["decision"].get("margin") or 0.0)
            stage_count = float(len(item["stages"]))
        else:
            side = item[f"{side_name}_summary"]
            margin = float(item.get("margin") or 0.0)
            stage_count = 1.0
        rows.append(
            [
                np.log1p(float(side.get("speech_duration") or 0.0)),
                np.log1p(float(side.get("char_count") or 0.0)),
                margin,
                stage_count,
                float(cohort_means[index]),
                float(cohort_stds[index]),
            ]
        )
    names = [
        "log_customer_speech_seconds",
        "log_customer_asr_chars",
        "role_margin",
        "role_stage_count",
        "external_cohort_topk_mean",
        "external_cohort_topk_std",
    ]
    return np.asarray(rows, dtype=np.float64), names


def oof_quality_scores(
    features: np.ndarray,
    targets: np.ndarray,
    identities: np.ndarray,
    fold_count: int,
    regularization: float,
) -> tuple[np.ndarray, list[dict], LogisticModel]:
    folds = stable_identity_folds(identities, fold_count)
    scores = np.zeros(len(identities), dtype=np.float64)
    fold_stats = []
    for fold in range(fold_count):
        train = (folds != fold) & np.isfinite(targets)
        test = folds == fold
        model = fit_logistic(features[train], targets[train], regularization)
        scores[test] = predict_logistic(model, features[test])
        fold_stats.append(
            {
                "fold": fold,
                "train_records": int(train.sum()),
                "test_records": int(test.sum()),
                "train_positive_rate": float(targets[train].mean()),
            }
        )
    final_train = np.isfinite(targets)
    final_model = fit_logistic(
        features[final_train], targets[final_train], regularization
    )
    return scores, fold_stats, final_model


def exact_coverage_mask(scores: np.ndarray, coverage: float) -> tuple[np.ndarray, float]:
    count = max(1, min(len(scores), int(round(len(scores) * coverage))))
    selected = np.argsort(scores, kind="stable")[::-1][:count]
    mask = np.zeros(len(scores), dtype=bool)
    mask[selected] = True
    return mask, float(scores[selected].min())


def pct(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.2f}%"


def num(value: float | None, digits: int = 3) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def write_metrics_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        "backend",
        "requested_coverage",
        "actual_coverage",
        "quality_threshold",
        "record_count",
        "identity_count",
        "genuine_pairs",
        "impostor_pairs",
        "eer",
        "eer_threshold",
        "top1_accuracy",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{field: row.get(field) for field in fields} for row in rows])


def write_quality_csv(
    path: Path,
    recording_ids: np.ndarray,
    identities: np.ndarray,
    scores: np.ndarray,
    targets: np.ndarray,
    features: np.ndarray,
    feature_names: list[str],
) -> None:
    fields = ["recording_id", "identity", "quality_score", "retrieval_target"] + feature_names
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, recording_id in enumerate(recording_ids.astype(str)):
            row = {
                "recording_id": recording_id,
                "identity": identities[index],
                "quality_score": float(scores[index]),
                "retrieval_target": (
                    "" if not np.isfinite(targets[index]) else int(targets[index])
                ),
            }
            row.update(
                {name: float(features[index, pos]) for pos, name in enumerate(feature_names)}
            )
            writer.writerow(row)


def write_report(path: Path, summary: dict, rows: list[dict]) -> None:
    baseline = summary["baseline"]
    external = summary["best_external_asnorm"]
    plda = summary["plda_full"]
    quality = summary["best_plda_quality_subset"]
    external_quality = summary.get("best_external_asnorm_quality_subset")
    overall_quality = summary.get("best_overall_quality_subset", quality)
    same_batch = summary.get("previous_same_batch_asnorm")
    plda_delta = (plda["eer"] - baseline["eer"]) * 100
    external_delta = (external["eer"] - baseline["eer"]) * 100
    quality_delta = (quality["eer"] - baseline["eer"]) * 100
    overall_quality_delta = (overall_quality["eer"] - baseline["eer"]) * 100

    lines = [
        "# 客户声纹 PLDA 与 embedding 质量优化报告",
        "",
        f"> 当前 {summary['evaluation']['record_count']} 条评估 embedding 均来自 {summary['evaluation']['role_model_version']} 角色模型结果；本报告验证外部 cohort、独立训练 PLDA 和身份互斥 OOF 质量评分。",
        "",
        "## 核心结论",
        "",
        f"- 裸余弦基线：EER {pct(baseline['eer'])}，Top-1 {pct(baseline['top1_accuracy'])}。",
        (
            f"- 外部 AS-norm：`{external['backend']}` 使用 {summary['external_cohort']['record_count']} 条独立客户向量，"
            f"EER {pct(external['eer'])}，较裸余弦 {external_delta:+.2f}pp，Top-1 {pct(external['top1_accuracy'])}。"
        ),
        (
            f"- PLDA：使用 {summary['plda_training']['selected_record_count']} 条、"
            f"{summary['plda_training']['selected_identity_count']} 个独立训练身份，EER {pct(plda['eer'])}，"
            f"较裸余弦 {plda_delta:+.2f}pp，Top-1 {pct(plda['top1_accuracy'])}。"
        ),
        (
            f"- PLDA + 质量分流：保留 {pct(quality['actual_coverage'])} 样本时，"
            f"EER {pct(quality['eer'])}，较裸余弦 {quality_delta:+.2f}pp，"
            f"Top-1 {pct(quality['top1_accuracy'])}。"
        ),
    ]
    if external_quality:
        external_quality_delta = (external_quality["eer"] - baseline["eer"]) * 100
        lines.append(
            f"- AS-norm + 质量分流：保留 {pct(external_quality['actual_coverage'])} 样本时，"
            f"EER {pct(external_quality['eer'])}，较裸余弦 {external_quality_delta:+.2f}pp。"
        )
    lines.append(
        f"- 本轮全局最佳质量分流后端为 `{overall_quality['backend']}`，保留 {pct(overall_quality['actual_coverage'])} 样本时 "
        f"EER {pct(overall_quality['eer'])}，较裸余弦 {overall_quality_delta:+.2f}pp；质量分流应作为人工复核/拒识策略，不应让低分样本静默消失。"
    )
    if same_batch:
        lines.append(
            f"- 对照：上一轮同批 cohort AS-norm EER 为 {pct(same_batch['eer'])}；"
            "本轮外部 cohort 样本量较小，主要价值是验证无测试集借用的真实部署口径。"
        )
    lines += [
        "",
        "## 覆盖率曲线",
        "",
        "| 后端 | 质量保留率 | 样本数 | 同人对 | EER | 后端阈值 | Top-1 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        if row["requested_coverage"] not in {
            1.0, 0.9, 0.8, 0.7, 0.6, 0.5
        }:
            continue
        lines.append(
            f"| `{row['backend']}` | {pct(row['actual_coverage'])} | {row['record_count']} | "
            f"{row['genuine_pairs']} | {pct(row['eer'])} | {num(row['eer_threshold'])} | "
            f"{pct(row['top1_accuracy'])} |"
        )
    lines += [
        "",
        "## 数据隔离与限制",
        "",
        f"- PLDA 训练集来自配置的身份隔离训练向量，源记录 {summary['plda_training']['source_record_count']} 条，"
        f"筛选后为 {summary['plda_training']['selected_record_count']} 条；"
        f"按身份哈希剔除了与评估集重叠的 {summary['plda_training']['excluded_eval_overlap_records']} 条训练记录。",
        f"- 当前 PLDA 训练身份只有 {summary['plda_training']['selected_identity_count']} 个，训练规模偏小；本次 PLDA 数值只能作为路线验证，不能作为生产定版结论。",
        (
            f"- PLDA 维度仅用训练身份做 {summary['plda_training']['dimension_selection_folds']} 折内部验证，"
            f"从 {summary['plda_training']['dimension_candidates']} 中选择 {summary['plda_training']['plda_dimension']} 维，"
            f"未使用当前 {summary['evaluation']['record_count']} 条评估集调参。"
        ),
        f"- 外部 cohort 共 {summary['external_cohort']['record_count']} 条、{summary['external_cohort']['identity_count']} 个身份，"
        f"角色版本为 `{summary['external_cohort']['role_model_versions']}`，并剔除 {summary['external_cohort']['overlap_removed']} 条重叠身份记录。",
        "- 质量分数预测 PLDA 的 Top-1 检索是否成功，使用客户身份互斥的 5 折 OOF 生成；最终质量模型虽已导出，仍需独立冻结集复核后才能固定生产门槛。",
        "- PLDA、AS-norm 和余弦的分数空间不同，报告阈值只对应各自后端，不能交叉复用 `0.751/0.8`。",
        "",
        "## 上线建议",
        "",
        "- P0：先以外部 AS-norm 替代裸余弦做候选打分，在独立冻结集重新标定阈值；保留裸余弦作为回滚与监控口径。",
        "- P1：质量分数低于冻结门槛的样本转人工复核或只参与宽松召回，不直接注册为高可信模板。",
        "- P1：扩充新角色模型重刷后的身份隔离重复客户向量用于 PLDA 重训，并冻结更大的 AS-norm cohort，重新评估二者融合。",
        "- P2：补充音频级 SNR、削波率、VAD 有效占比和分段 embedding 一致性；当前质量模型主要覆盖时长、文本量、角色置信度和 cohort 可分性。",
        "",
        "## 产物",
        "",
        "- `plda_quality_metrics.csv`：各后端和质量覆盖率的完整指标。",
        "- `embedding_quality_scores.csv`：逐录音 OOF 质量分及输入特征。",
        "- `plda_model.npz`、`embedding_quality_model.npz`：实验模型参数。",
        "- `external_cohort_snapshot.npz`：本次外部 cohort 冻结快照，用于复现实验。",
        "- `optimized_scores_plda_quality.npz`：余弦、外部 AS-norm、PLDA 分数矩阵和质量分。",
        "- `plda_quality_summary.json`：机器可读实验摘要。",
    ]
    atomic_write_text(path, "\n".join(lines) + "\n")


def run(args: argparse.Namespace) -> dict:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    eval_data = np.load(Path(args.matrix), allow_pickle=False)
    recording_ids = eval_data["recording_ids"].astype(str)
    identities = eval_data["identities"].astype(str)
    embeddings = normalize_rows(eval_data["embeddings"])
    raw_matrix = embeddings @ embeddings.T
    all_mask = np.ones(len(identities), dtype=bool)
    excluded_hashes = {identity_hash(item) for item in set(identities.tolist())}

    cohort_embeddings, cohort_identities, cohort_stats = load_external_cohort(
        Path(args.cohort_dir), excluded_hashes
    )
    asnorm_matrices = {}
    asnorm_stats = {}
    for cohort_size in args.cohort_sizes:
        matrix, means, stds = external_asnorm(
            raw_matrix, embeddings, cohort_embeddings, cohort_size
        )
        name = f"external_asnorm_k{min(cohort_size, len(cohort_embeddings))}"
        asnorm_matrices[name] = matrix
        asnorm_stats[name] = (means, stds)

    plda_embeddings, plda_identities, plda_stats = load_plda_training(
        Path(args.plda_train),
        excluded_hashes,
        args.max_identity_records,
        args.min_identity_records,
    )
    selected_dimension, dimension_results = select_plda_dimension(
        plda_embeddings,
        plda_identities,
        args.plda_dimensions,
        args.plda_selection_folds,
    )
    plda_model = fit_plda(plda_embeddings, plda_identities, selected_dimension)
    plda_matrix = score_plda(plda_model, embeddings)

    baseline = evaluate_score_matrix(raw_matrix, identities, all_mask)
    external_results = []
    for name, matrix in asnorm_matrices.items():
        external_results.append({"backend": name, **evaluate_score_matrix(matrix, identities, all_mask)})
    best_external = min(external_results, key=lambda row: row["eer"])
    quality_backend = best_external["backend"]
    cohort_means, cohort_stds = asnorm_stats[quality_backend]

    features, feature_names = load_quality_features(
        Path(args.roles), recording_ids, cohort_means, cohort_stds
    )
    targets = retrieval_targets(plda_matrix, identities)
    quality_scores, quality_fold_stats, quality_model = oof_quality_scores(
        features,
        targets,
        identities,
        args.quality_folds,
        args.quality_regularization,
    )

    matrices = {
        "raw_cosine": raw_matrix,
        quality_backend: asnorm_matrices[quality_backend],
        "plda": plda_matrix,
    }
    rows = []
    for requested_coverage in args.quality_coverages:
        mask, quality_threshold = exact_coverage_mask(quality_scores, requested_coverage)
        for backend, matrix in matrices.items():
            metrics = evaluate_score_matrix(matrix, identities, mask)
            rows.append(
                {
                    "backend": backend,
                    "requested_coverage": float(requested_coverage),
                    "actual_coverage": metrics["record_count"] / len(identities),
                    "quality_threshold": quality_threshold,
                    **metrics,
                }
            )

    plda_full = next(
        row for row in rows if row["backend"] == "plda" and row["requested_coverage"] == 1.0
    )
    quality_candidates = [
        row
        for row in rows
        if row["backend"] == "plda"
        and row["actual_coverage"] >= args.min_recommended_coverage
        and row["genuine_pairs"] >= args.min_recommended_genuine_pairs
    ]
    best_quality = min(quality_candidates, key=lambda row: (row["eer"], -row["actual_coverage"]))
    best_quality_by_backend = {}
    for backend in sorted(matrices):
        candidates = [
            row
            for row in rows
            if row["backend"] == backend
            and row["actual_coverage"] >= args.min_recommended_coverage
            and row["genuine_pairs"] >= args.min_recommended_genuine_pairs
        ]
        if candidates:
            best_quality_by_backend[backend] = min(
                candidates, key=lambda row: (row["eer"], -row["actual_coverage"])
            )
    best_overall_quality = min(
        best_quality_by_backend.values(), key=lambda row: (row["eer"], -row["actual_coverage"])
    )

    previous_same_batch = None
    previous_summary_path = DEFAULT_REPORT_DIR / "backend_optimization" / "optimization_summary.json"
    if previous_summary_path.exists():
        previous = json.loads(previous_summary_path.read_text(encoding="utf-8"))
        previous_same_batch = previous.get("best_full_backend")

    summary = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "evaluation": {
            "matrix_path": str(Path(args.matrix)),
            "roles_path": str(Path(args.roles)),
            "plda_train_path": str(Path(args.plda_train)),
            "cohort_path": str(Path(args.cohort_dir)),
            "record_count": len(identities),
            "identity_count": len(set(identities.tolist())),
            "role_model_version": "role-text-v1-20260820",
        },
        "external_cohort": cohort_stats,
        "plda_training": {
            **plda_stats,
            "plda_dimension": plda_model.dimension,
            "dimension_candidates": [int(item) for item in args.plda_dimensions],
            "dimension_selection_folds": args.plda_selection_folds,
            "dimension_selection_results": dimension_results,
        },
        "quality_model": {
            "feature_names": feature_names,
            "target_record_count": int(np.isfinite(targets).sum()),
            "target_positive_rate": float(np.nanmean(targets)),
            "fold_count": args.quality_folds,
            "folds": quality_fold_stats,
            "evaluation_mode": "identity-disjoint OOF",
        },
        "baseline": {"backend": "raw_cosine", **baseline},
        "external_asnorm_candidates": external_results,
        "best_external_asnorm": best_external,
        "plda_full": plda_full,
        "best_plda_quality_subset": best_quality,
        "best_quality_subset_by_backend": best_quality_by_backend,
        "best_external_asnorm_quality_subset": best_quality_by_backend.get(quality_backend),
        "best_overall_quality_subset": best_overall_quality,
        "previous_same_batch_asnorm": previous_same_batch,
        "warning": "当前外部 PLDA 训练身份较少；正式上线前须用更大规模、身份隔离的新角色客户向量重训并冻结验证。",
    }

    write_metrics_csv(output_dir / "plda_quality_metrics.csv", rows)
    write_quality_csv(
        output_dir / "embedding_quality_scores.csv",
        recording_ids,
        identities,
        quality_scores,
        targets,
        features,
        feature_names,
    )
    atomic_save_npz(
        output_dir / "external_cohort_snapshot.npz",
        embeddings=cohort_embeddings.astype(np.float32),
        identities=cohort_identities,
        role_model_versions_json=np.asarray(
            [json.dumps(cohort_stats["role_model_versions"], ensure_ascii=False)]
        ),
        overlap_removed=np.asarray([cohort_stats["overlap_removed"]], dtype=np.int32),
    )
    atomic_save_npz(
        output_dir / "plda_model.npz",
        input_mean=plda_model.input_mean,
        projection=plda_model.projection,
        projected_mean=plda_model.projected_mean,
        plus_precision=plda_model.plus_precision,
        within_precision=plda_model.within_precision,
        total_precision=plda_model.total_precision,
        dimension=np.asarray([plda_model.dimension], dtype=np.int32),
    )
    atomic_save_npz(
        output_dir / "embedding_quality_model.npz",
        feature_names=np.asarray(feature_names),
        feature_mean=quality_model.feature_mean,
        feature_scale=quality_model.feature_scale,
        coefficients=quality_model.coefficients,
        regularization=np.asarray([quality_model.regularization]),
    )
    atomic_save_npz(
        output_dir / "optimized_scores_plda_quality.npz",
        recording_ids=recording_ids,
        identities=identities,
        raw_cosine_matrix=raw_matrix.astype(np.float32),
        external_asnorm_matrix=asnorm_matrices[quality_backend].astype(np.float32),
        plda_score_matrix=plda_matrix.astype(np.float32),
        quality_scores=quality_scores.astype(np.float32),
        external_cohort_identities=cohort_identities,
    )
    atomic_write_json(output_dir / "plda_quality_summary.json", summary)
    write_report(output_dir / "客户声纹PLDA与质量优化报告.md", summary, rows)
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="客户声纹 PLDA 与 embedding 质量评估")
    parser.add_argument("--matrix", default=str(DEFAULT_MATRIX))
    parser.add_argument("--roles", default=str(DEFAULT_ROLES))
    parser.add_argument("--plda-train", default=str(DEFAULT_PLDA_TRAIN))
    parser.add_argument("--cohort-dir", default=str(DEFAULT_COHORT_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--plda-dimensions", type=int, nargs="+", default=[40, 60, 80, 100, 120]
    )
    parser.add_argument("--plda-selection-folds", type=int, default=5)
    parser.add_argument("--max-identity-records", type=int, default=20)
    parser.add_argument("--min-identity-records", type=int, default=2)
    parser.add_argument("--cohort-sizes", type=int, nargs="+", default=[25, 50, 100, 200])
    parser.add_argument("--quality-folds", type=int, default=5)
    parser.add_argument("--quality-regularization", type=float, default=1.0)
    parser.add_argument(
        "--quality-coverages", type=float, nargs="+", default=[1.0, 0.9, 0.8, 0.7, 0.6, 0.5]
    )
    parser.add_argument("--min-recommended-coverage", type=float, default=0.50)
    parser.add_argument("--min-recommended-genuine-pairs", type=int, default=100)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    summary = run(parse_args(argv))
    print(
        "DONE "
        f"BASE_EER={summary['baseline']['eer']:.4f} "
        f"EXTERNAL_ASNORM_EER={summary['best_external_asnorm']['eer']:.4f} "
        f"PLDA_EER={summary['plda_full']['eer']:.4f} "
        f"PLDA_QUALITY_EER={summary['best_plda_quality_subset']['eer']:.4f} "
        f"BEST_QUALITY_EER={summary['best_overall_quality_subset']['eer']:.4f}",
        flush=True,
    )


if __name__ == "__main__":
    main()
