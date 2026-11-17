# -*- coding: utf-8 -*-
"""离线评估 AS-Norm、PLDA 及二者融合效果。

本脚本是测试版本，只读取现有评估 embedding、冻结 PLDA 和 external cohort。
不修改平台配置、不替换模型、不新增依赖。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np


MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from pipelines.evaluate_customer_plda_quality import (  # noqa: E402
    PldaModel,
    evaluate_score_matrix,
    external_asnorm,
    score_plda,
)
from pipelines.optimize_customer_voiceprint_backend import normalize_rows  # noqa: E402


DEFAULT_MATRIX = (
    MODULE_ROOT
    / "reports"
    / "kesu_customer_refresh_role_text_v1_20260820"
    / "customer_nxn_matrix.npz"
)
DEFAULT_BACKEND_DIR = MODULE_ROOT / "models" / "backend" / "customer_plda_v2_current_role"
DEFAULT_OUTPUT = MODULE_ROOT / "reports" / "asnorm_plda_ab_test_20260822"


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(content, encoding="utf-8")
    os.replace(temp, path)


def atomic_write_json(path: Path, payload: dict) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


def load_eval_matrix(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    with np.load(path, allow_pickle=False) as data:
        recording_ids = data["recording_ids"].astype(str)
        identities = data["identities"].astype(str)
        embeddings = normalize_rows(np.asarray(data["embeddings"], dtype=np.float64))
        trusted_mask = (
            data["trusted_mask"].astype(bool)
            if "trusted_mask" in data.files
            else np.ones(len(recording_ids), dtype=bool)
        )
    return recording_ids, identities, embeddings, trusted_mask


def load_plda_model(path: Path) -> PldaModel:
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


def load_cohort(path: Path) -> tuple[np.ndarray, dict]:
    with np.load(path, allow_pickle=False) as data:
        embeddings = normalize_rows(np.asarray(data["embeddings"], dtype=np.float64))
        identities = data["identities"].astype(str) if "identities" in data.files else np.asarray([])
    return embeddings, {
        "path": str(path),
        "record_count": int(len(embeddings)),
        "identity_count": int(len(set(identities.tolist()))) if len(identities) else None,
    }


def zscore_off_diagonal(matrix: np.ndarray) -> np.ndarray:
    values = matrix[np.triu_indices(len(matrix), k=1)]
    mean = float(values.mean())
    std = max(float(values.std(ddof=0)), 1e-6)
    return (matrix - mean) / std


def metric_row(backend: str, matrix: np.ndarray, identities: np.ndarray, mask: np.ndarray) -> dict:
    row = evaluate_score_matrix(matrix, identities, mask)
    row["backend"] = backend
    row["coverage"] = float(mask.mean())
    return row


def fused_matrix(left: np.ndarray, right: np.ndarray, left_weight: float) -> np.ndarray:
    weight = float(left_weight)
    return weight * zscore_off_diagonal(left) + (1.0 - weight) * zscore_off_diagonal(right)


def write_metrics_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        "backend",
        "coverage",
        "record_count",
        "identity_count",
        "genuine_pairs",
        "impostor_pairs",
        "eer",
        "eer_threshold",
        "top1_accuracy",
        "fusion_plda_weight",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})


def pct(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.2f}%"


def num(value: float | None, digits: int = 4) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def write_report(path: Path, summary: dict, rows: list[dict]) -> None:
    best = min(rows, key=lambda row: row["eer"])
    by_name = {row["backend"]: row for row in rows}
    lines = [
        "# AS-Norm 与 PLDA 测试版效果评估",
        "",
        "> 本报告为离线测试版本，只读取现有评估集、冻结 PLDA 和 external cohort；未修改平台依赖、模型和实时阈值。",
        "",
        "## 评估口径",
        "",
        f"- 生成时间: {summary['generated_at']}",
        f"- 评估录音数: {summary['evaluation']['record_count']}",
        f"- 评估客户数: {summary['evaluation']['identity_count']}",
        f"- 同人 pair: {summary['evaluation']['genuine_pairs']}",
        f"- 异人 pair: {summary['evaluation']['impostor_pairs']}",
        f"- external cohort: {summary['cohort']['record_count']} 条",
        f"- PLDA 维度: {summary['plda']['dimension']}",
        "",
        "## 结果对比",
        "",
        "| 后端 | EER | 阈值 | Top-1 | 说明 |",
        "|---|---:|---:|---:|---|",
    ]
    descriptions = {
        "raw_cosine": "裸 CAM++ 余弦基线",
        "external_asnorm": f"外部 cohort AS-Norm，k={summary['asnorm']['cohort_size']}",
        "plda": "当前冻结 PLDA 后端",
        "fusion_equal_plda_asnorm": "PLDA 与 AS-Norm 标准化后等权融合",
        "fusion_best_plda_asnorm": "测试集内网格搜索最优权重，仅作上限参考",
    }
    for row in rows:
        lines.append(
            "| {backend} | {eer} | {threshold} | {top1} | {desc} |".format(
                backend=row["backend"],
                eer=pct(row["eer"]),
                threshold=num(row["eer_threshold"]),
                top1=pct(row["top1_accuracy"]),
                desc=descriptions.get(row["backend"], ""),
            )
        )
    lines += [
        "",
        "## 结论",
        "",
        f"- 当前最佳测试项: `{best['backend']}`，EER {pct(best['eer'])}，Top-1 {pct(best['top1_accuracy'])}。",
    ]
    if "plda" in by_name and "external_asnorm" in by_name:
        delta = (by_name["plda"]["eer"] - by_name["external_asnorm"]["eer"]) * 100
        lines.append(
            f"- PLDA 相比 AS-Norm 的 EER 差异为 {delta:+.2f}pp；负数表示 PLDA 更低。"
        )
    if "fusion_equal_plda_asnorm" in by_name and "plda" in by_name:
        delta = (by_name["fusion_equal_plda_asnorm"]["eer"] - by_name["plda"]["eer"]) * 100
        lines.append(
            f"- 等权融合相比 PLDA 的 EER 差异为 {delta:+.2f}pp。"
        )
    lines += [
        "- `fusion_best_plda_asnorm` 使用当前评估集内选权重，会偏乐观，不能直接作为上线结论。",
        "- 若融合项优于单后端，下一步应使用身份隔离验证集或时间后验样本重新标定阈值。",
        "",
        "## 输出文件",
        "",
        "- `metrics.csv`: 指标明细。",
        "- `score_matrices.npz`: raw、AS-Norm、PLDA 和融合分数矩阵。",
        "- `summary.json`: 机器可读摘要。",
    ]
    atomic_write_text(path, "\n".join(lines) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--backend-dir", type=Path, default=DEFAULT_BACKEND_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cohort-size", type=int, default=50)
    parser.add_argument(
        "--fusion-weights",
        type=float,
        nargs="+",
        default=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        help="PLDA权重；1.0等于纯PLDA，0.0等于纯AS-Norm",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    recording_ids, identities, embeddings, trusted_mask = load_eval_matrix(args.matrix)
    raw_matrix = normalize_rows(embeddings) @ normalize_rows(embeddings).T
    cohort_embeddings, cohort_stats = load_cohort(args.backend_dir / "external_cohort_snapshot.npz")
    asnorm_matrix, cohort_means, cohort_stds = external_asnorm(
        raw_matrix,
        embeddings,
        cohort_embeddings,
        args.cohort_size,
    )
    plda_model = load_plda_model(args.backend_dir / "plda_model.npz")
    plda_matrix = score_plda(plda_model, embeddings)

    rows = [
        metric_row("raw_cosine", raw_matrix, identities, trusted_mask),
        metric_row("external_asnorm", asnorm_matrix, identities, trusted_mask),
        metric_row("plda", plda_matrix, identities, trusted_mask),
    ]
    equal_fusion = fused_matrix(plda_matrix, asnorm_matrix, 0.5)
    equal_row = metric_row("fusion_equal_plda_asnorm", equal_fusion, identities, trusted_mask)
    equal_row["fusion_plda_weight"] = 0.5
    rows.append(equal_row)

    best_weight = None
    best_matrix = None
    best_row = None
    for weight in args.fusion_weights:
        matrix = fused_matrix(plda_matrix, asnorm_matrix, weight)
        row = metric_row("fusion_best_plda_asnorm", matrix, identities, trusted_mask)
        row["fusion_plda_weight"] = float(weight)
        if best_row is None or row["eer"] < best_row["eer"]:
            best_weight = float(weight)
            best_matrix = matrix
            best_row = row
    rows.append(best_row)

    base_metrics = evaluate_score_matrix(raw_matrix, identities, trusted_mask)
    summary = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": "offline_test_only_no_platform_change",
        "inputs": {
            "matrix": str(args.matrix),
            "backend_dir": str(args.backend_dir),
        },
        "evaluation": {
            "record_count": base_metrics["record_count"],
            "identity_count": base_metrics["identity_count"],
            "genuine_pairs": base_metrics["genuine_pairs"],
            "impostor_pairs": base_metrics["impostor_pairs"],
        },
        "cohort": cohort_stats,
        "asnorm": {
            "cohort_size": int(min(args.cohort_size, len(cohort_embeddings))),
            "cohort_mean_mean": float(cohort_means.mean()),
            "cohort_std_mean": float(cohort_stds.mean()),
        },
        "plda": {
            "dimension": int(plda_model.dimension),
            "model_path": str(args.backend_dir / "plda_model.npz"),
        },
        "fusion": {
            "equal_weight_plda": 0.5,
            "best_in_sample_plda_weight": best_weight,
            "warning": "best_in_sample仅为测试集内上限参考，不能直接上线。",
        },
        "metrics": rows,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_metrics_csv(args.output_dir / "metrics.csv", rows)
    atomic_write_json(args.output_dir / "summary.json", summary)
    np.savez_compressed(
        args.output_dir / "score_matrices.npz",
        recording_ids=recording_ids,
        identities=identities,
        trusted_mask=trusted_mask,
        raw_cosine=raw_matrix.astype(np.float32),
        external_asnorm=asnorm_matrix.astype(np.float32),
        plda=plda_matrix.astype(np.float32),
        fusion_equal_plda_asnorm=equal_fusion.astype(np.float32),
        fusion_best_plda_asnorm=best_matrix.astype(np.float32),
        fusion_best_plda_weight=np.asarray([best_weight], dtype=np.float32),
    )
    write_report(args.output_dir / "AS-Norm与PLDA测试版评估报告.md", summary, rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
