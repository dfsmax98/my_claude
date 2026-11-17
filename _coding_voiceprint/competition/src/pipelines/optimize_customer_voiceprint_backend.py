# -*- coding: utf-8 -*-
"""客户声纹后端优化评估。

基于已生成的客户侧 embedding/matrix 和角色识别元数据，评估：
- 质量门槛：客户侧有效语音时长、角色模型 margin、阶段一致性。
- AS-norm：使用同批异客户 cohort 做自适应分数归一化。

本脚本不重新提取 embedding，不覆盖原始报告。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np


MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))


DEFAULT_REPORT_DIR = (
    MODULE_ROOT / "reports" / "kesu_customer_refresh_role_text_v1_20260820"
)
DEFAULT_MATRIX = DEFAULT_REPORT_DIR / "customer_nxn_matrix.npz"
DEFAULT_ROLES = DEFAULT_REPORT_DIR / "adaptive_roles.json"
DEFAULT_OUTPUT = DEFAULT_REPORT_DIR / "backend_optimization"
FIXED_THRESHOLD = 0.751


@dataclass(frozen=True)
class RoleMeta:
    recording_id: str
    margin: float
    customer_speech_seconds: float
    customer_chars: int
    final_stage: str
    stage_disagreement: bool


@dataclass(frozen=True)
class QualityConfig:
    name: str
    min_speech_seconds: float | None = None
    min_margin: float | None = None
    require_stage_stable: bool = False

    def mask(self, metas: list[RoleMeta]) -> np.ndarray:
        selected = []
        for meta in metas:
            ok = True
            if self.min_speech_seconds is not None:
                ok = ok and meta.customer_speech_seconds >= self.min_speech_seconds
            if self.min_margin is not None:
                ok = ok and meta.margin >= self.min_margin
            if self.require_stage_stable:
                ok = ok and not meta.stage_disagreement
            selected.append(ok)
        return np.asarray(selected, dtype=bool)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def atomic_write_json(path: Path, payload: dict) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


def atomic_save_npz(path: Path, **arrays) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.stem + ".tmp.npz")
    np.savez_compressed(temp, **arrays)
    os.replace(temp, path)


def normalize_rows(vectors: np.ndarray) -> np.ndarray:
    vectors = np.asarray(vectors, dtype=np.float64)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.maximum(norms, 1e-12)


def compute_eer(scores: np.ndarray, genuine: np.ndarray) -> tuple[float | None, float | None]:
    scores = np.asarray(scores, dtype=np.float64)
    genuine = np.asarray(genuine, dtype=bool)
    positives = int(genuine.sum())
    negatives = int((~genuine).sum())
    if positives == 0 or negatives == 0:
        return None, None

    order = np.argsort(scores)[::-1]
    sorted_scores = scores[order]
    sorted_genuine = genuine[order]
    true_positive = np.cumsum(sorted_genuine)
    false_positive = np.cumsum(~sorted_genuine)
    boundaries = np.r_[
        np.flatnonzero(sorted_scores[:-1] != sorted_scores[1:]),
        len(scores) - 1,
    ]
    far = false_positive[boundaries] / negatives
    frr = (positives - true_positive[boundaries]) / positives
    best = int(np.argmin(np.abs(far - frr)))
    return float((far[best] + frr[best]) / 2), float(sorted_scores[boundaries[best]])


def evaluate_matrix(
    matrix: np.ndarray,
    identities: np.ndarray,
    mask: np.ndarray,
    fixed_threshold: float = FIXED_THRESHOLD,
) -> dict:
    idx = np.flatnonzero(mask)
    sub_ids = identities[idx]
    sub = matrix[np.ix_(idx, idx)]
    row, col = np.triu_indices(len(idx), k=1)
    scores = sub[row, col]
    genuine = sub_ids[row] == sub_ids[col]
    genuine_scores = scores[genuine]
    impostor_scores = scores[~genuine]
    eer, eer_threshold = compute_eer(scores, genuine)

    counts = Counter(sub_ids.tolist())
    work = sub.copy()
    np.fill_diagonal(work, -np.inf)
    nearest = np.argmax(work, axis=1) if len(idx) else np.asarray([], dtype=int)
    eligible = np.asarray([counts[item] > 1 for item in sub_ids])
    top1 = (
        float((sub_ids[nearest][eligible] == sub_ids[eligible]).mean())
        if eligible.any()
        else None
    )
    return {
        "record_count": int(len(idx)),
        "identity_count": int(len(counts)),
        "genuine_pairs": int(len(genuine_scores)),
        "impostor_pairs": int(len(impostor_scores)),
        "genuine_mean": float(genuine_scores.mean()) if len(genuine_scores) else None,
        "genuine_p05": (
            float(np.percentile(genuine_scores, 5)) if len(genuine_scores) else None
        ),
        "impostor_mean": float(impostor_scores.mean()) if len(impostor_scores) else None,
        "impostor_p95": (
            float(np.percentile(impostor_scores, 95)) if len(impostor_scores) else None
        ),
        "eer": eer,
        "eer_threshold": eer_threshold,
        "tar_at_fixed": (
            float((genuine_scores >= fixed_threshold).mean())
            if len(genuine_scores)
            else None
        ),
        "far_at_fixed": (
            float((impostor_scores >= fixed_threshold).mean())
            if len(impostor_scores)
            else None
        ),
        "top1_accuracy": top1,
    }


def build_asnorm_matrix(
    raw_matrix: np.ndarray,
    identities: np.ndarray,
    cohort_size: int,
) -> np.ndarray:
    """构造对称 AS-norm 分数矩阵。

    每条录音使用异客户最高分 cohort 估计局部分布，避免同客户样本进入
    cohort。输出分数不再是余弦相似度，因此固定余弦阈值不适用。
    """
    matrix = np.asarray(raw_matrix, dtype=np.float64)
    n = len(identities)
    means = np.zeros(n, dtype=np.float64)
    stds = np.ones(n, dtype=np.float64)
    for idx in range(n):
        impostor = identities != identities[idx]
        values = np.sort(matrix[idx, impostor])
        if len(values) == 0:
            continue
        cohort = values[-min(cohort_size, len(values)) :]
        means[idx] = float(cohort.mean())
        std = float(cohort.std(ddof=0))
        stds[idx] = std if std > 1e-6 else 1.0
    return 0.5 * (
        (matrix - means[:, None]) / stds[:, None]
        + (matrix - means[None, :]) / stds[None, :]
    )


def load_role_metas(path: Path, recording_ids: np.ndarray) -> list[RoleMeta]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload["records"]
    metas = []
    for recording_id in recording_ids.astype(str):
        item = records[str(recording_id)]
        final_stage = item["stages"][-1]
        decision = final_stage["decision"]
        channel_key = {"L": "left", "R": "right"}[item["customer_ch"]]
        summary = final_stage[channel_key]
        metas.append(
            RoleMeta(
                recording_id=str(recording_id),
                margin=float(decision.get("margin") or 0.0),
                customer_speech_seconds=float(summary.get("speech_duration") or 0.0),
                customer_chars=int(summary.get("char_count") or 0),
                final_stage=str(item.get("final_stage") or ""),
                stage_disagreement=bool(item.get("stage_disagreement")),
            )
        )
    return metas


def quality_configs() -> list[QualityConfig]:
    return [
        QualityConfig("all"),
        QualityConfig("speech_ge_8", min_speech_seconds=8.0),
        QualityConfig("speech_ge_10", min_speech_seconds=10.0),
        QualityConfig("margin_ge_0_85", min_margin=0.85),
        QualityConfig("margin_ge_0_88", min_margin=0.88),
        QualityConfig("margin_ge_0_90", min_margin=0.90),
        QualityConfig("margin_ge_0_92", min_margin=0.92),
        QualityConfig(
            "speech_ge_8_margin_ge_0_85_stable",
            min_speech_seconds=8.0,
            min_margin=0.85,
            require_stage_stable=True,
        ),
        QualityConfig(
            "speech_ge_8_margin_ge_0_90_stable",
            min_speech_seconds=8.0,
            min_margin=0.90,
            require_stage_stable=True,
        ),
        QualityConfig(
            "speech_ge_10_margin_ge_0_85_stable",
            min_speech_seconds=10.0,
            min_margin=0.85,
            require_stage_stable=True,
        ),
        QualityConfig(
            "speech_ge_10_margin_ge_0_90_stable",
            min_speech_seconds=10.0,
            min_margin=0.90,
            require_stage_stable=True,
        ),
        QualityConfig(
            "speech_ge_12_margin_ge_0_90_stable",
            min_speech_seconds=12.0,
            min_margin=0.90,
            require_stage_stable=True,
        ),
    ]


def metric_row(
    score_name: str,
    quality: QualityConfig,
    metrics: dict,
    total_records: int,
) -> dict:
    coverage = metrics["record_count"] / total_records if total_records else 0.0
    return {
        "score_name": score_name,
        "quality_config": quality.name,
        "coverage": coverage,
        **metrics,
    }


def pct(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.2f}%"


def num(value: float | None, digits: int = 3) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        "score_name",
        "quality_config",
        "coverage",
        "record_count",
        "identity_count",
        "genuine_pairs",
        "impostor_pairs",
        "eer",
        "eer_threshold",
        "top1_accuracy",
        "genuine_mean",
        "genuine_p05",
        "impostor_mean",
        "impostor_p95",
        "tar_at_fixed",
        "far_at_fixed",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})


def choose_best(
    rows: list[dict],
    score_prefix: str,
    quality_name: str | None = None,
    min_coverage: float = 0.0,
    min_genuine_pairs: int = 1,
) -> dict | None:
    candidates = []
    for row in rows:
        if row["eer"] is None:
            continue
        if not str(row["score_name"]).startswith(score_prefix):
            continue
        if quality_name is not None and row["quality_config"] != quality_name:
            continue
        if row["coverage"] < min_coverage:
            continue
        if row["genuine_pairs"] < min_genuine_pairs:
            continue
        candidates.append(row)
    if not candidates:
        return None
    return min(candidates, key=lambda row: (row["eer"], -row["coverage"]))


def write_report(
    path: Path,
    rows: list[dict],
    baseline: dict,
    best_full: dict,
    best_operating: dict,
    identity_count_distribution: dict[str, int],
) -> None:
    delta_full = (
        None
        if baseline["eer"] is None or best_full["eer"] is None
        else best_full["eer"] - baseline["eer"]
    )
    delta_operating = (
        None
        if baseline["eer"] is None or best_operating["eer"] is None
        else best_operating["eer"] - baseline["eer"]
    )
    sorted_rows = sorted(
        [row for row in rows if row["eer"] is not None],
        key=lambda row: (row["eer"], -row["coverage"]),
    )[:12]

    lines = [
        "# 客户声纹后端优化评估报告",
        "",
        "> 本报告基于既有客户侧 CAM++ embedding，不重新提取音频；优化项为质量门槛和 AS-norm 后端分数归一化。",
        "",
        "## 结论",
        "",
        f"- 基线：EER {pct(baseline['eer'])}，阈值 {num(baseline['eer_threshold'])}，Top-1 {pct(baseline['top1_accuracy'])}。",
        (
            f"- 全量推荐后端：`{best_full['score_name']}`，覆盖 {pct(best_full['coverage'])}，"
            f"EER {pct(best_full['eer'])}，较基线 {delta_full * 100:+.2f}pp，"
            f"Top-1 {pct(best_full['top1_accuracy'])}。"
        ),
        (
            f"- 高置信运行子集：`{best_operating['quality_config']}` + `{best_operating['score_name']}`，"
            f"覆盖 {pct(best_operating['coverage'])}，EER {pct(best_operating['eer'])}，"
            f"较基线 {delta_operating * 100:+.2f}pp，Top-1 {pct(best_operating['top1_accuracy'])}。"
        ),
        "- AS-norm 输出不是余弦相似度，不能继续沿用 `0.751/0.8` 这类余弦阈值，必须按新分数重新标定业务阈值。",
        "- 高置信子集会牺牲覆盖率，适合自动命中或强提醒；未进入子集的样本仍可走全量 AS-norm + 人工复核。",
        (
            "- 本样本多数客户只有两通录音，身份条数分布为 "
            f"`{identity_count_distribution}`；因此多模板建库收益本轮不能充分验证。"
        ),
        "",
        "## Top 结果",
        "",
        "| 排名 | 分数后端 | 质量口径 | 覆盖率 | 样本数 | 同人对 | EER | 阈值 | Top-1 |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for rank, row in enumerate(sorted_rows, 1):
        lines.append(
            f"| {rank} | `{row['score_name']}` | `{row['quality_config']}` | "
            f"{pct(row['coverage'])} | {row['record_count']} | {row['genuine_pairs']} | "
            f"{pct(row['eer'])} | {num(row['eer_threshold'])} | {pct(row['top1_accuracy'])} |"
        )
    lines += [
        "",
        "## 使用建议",
        "",
        "- P0：上线前先采用全量 AS-norm 后端，保持全部客户侧样本可检索，同时降低裸余弦的分布漂移影响。",
        "- P1：自动命中层使用高置信子集口径；子集外只做候选召回或人工复核，避免为了覆盖率硬吃低质量样本。",
        "- P2：后续如果保留原始音频或可重拉音频，再做分段 VAD embedding、多段质量加权聚合和客户多模板建库；这是继续压低 EER 的主要空间。",
        "",
        "## 产物",
        "",
        "- `optimization_metrics.csv`：全部实验明细。",
        "- `optimization_summary.json`：基线、全量推荐和高置信推荐摘要。",
        "- `optimized_customer_scores_*.npz`：全量推荐 AS-norm 分数矩阵。",
        "",
        "## 口径说明",
        "",
        "- 质量门槛来自角色识别输出中的客户侧有效语音时长、角色模型 margin 和阶段一致性。",
        "- AS-norm 的 cohort 仅使用异客户样本，避免同客户样本参与每条录音的局部分布估计。",
        "- 本报告为同一冻结样本上的探索性离线结果；生产冻结参数仍应使用独立验证集确认。",
    ]
    atomic_write_text(path, "\n".join(lines) + "\n")


def run(args: argparse.Namespace) -> dict:
    matrix_path = Path(args.matrix)
    roles_path = Path(args.roles)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    data = np.load(matrix_path, allow_pickle=False)
    recording_ids = data["recording_ids"].astype(str)
    identities = data["identities"].astype(str)
    vectors = normalize_rows(data["embeddings"])
    raw_matrix = vectors @ vectors.T
    metas = load_role_metas(roles_path, recording_ids)
    total_records = len(recording_ids)
    identity_count_distribution = {
        str(count): int(freq)
        for count, freq in sorted(Counter(Counter(identities.tolist()).values()).items())
    }

    matrices = {"raw_cosine": raw_matrix}
    for cohort_size in args.cohort_sizes:
        matrices[f"asnorm_k{cohort_size}"] = build_asnorm_matrix(
            raw_matrix,
            identities,
            int(cohort_size),
        )

    rows = []
    configs = quality_configs()
    for score_name, matrix in matrices.items():
        for quality in configs:
            mask = quality.mask(metas)
            if int(mask.sum()) < args.min_records:
                continue
            metrics = evaluate_matrix(matrix, identities, mask, args.fixed_threshold)
            if metrics["genuine_pairs"] < args.min_genuine_pairs:
                continue
            rows.append(metric_row(score_name, quality, metrics, total_records))

    baseline = next(
        row
        for row in rows
        if row["score_name"] == "raw_cosine" and row["quality_config"] == "all"
    )
    best_full = choose_best(rows, "asnorm_", quality_name="all")
    best_operating = choose_best(
        rows,
        "asnorm_",
        min_coverage=args.operating_min_coverage,
        min_genuine_pairs=args.operating_min_genuine_pairs,
    )
    if best_full is None or best_operating is None:
        raise RuntimeError("没有找到满足约束的 AS-norm 优化结果")

    write_csv(output_dir / "optimization_metrics.csv", rows)
    summary = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "matrix_path": str(matrix_path),
        "roles_path": str(roles_path),
        "fixed_threshold": args.fixed_threshold,
        "cohort_sizes": [int(item) for item in args.cohort_sizes],
        "identity_count_distribution": identity_count_distribution,
        "baseline": baseline,
        "best_full_backend": best_full,
        "best_operating_backend": best_operating,
        "note": "AS-norm分数不是余弦相似度，需重新标定业务阈值。",
    }
    atomic_write_json(output_dir / "optimization_summary.json", summary)
    write_report(
        output_dir / "客户声纹后端优化评估报告.md",
        rows,
        baseline,
        best_full,
        best_operating,
        identity_count_distribution,
    )
    best_matrix = matrices[best_full["score_name"]]
    atomic_save_npz(
        output_dir / f"optimized_customer_scores_{best_full['score_name']}.npz",
        recording_ids=recording_ids,
        identities=identities,
        score_matrix=best_matrix.astype(np.float32),
        raw_cosine_matrix=raw_matrix.astype(np.float32),
    )
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="客户声纹后端优化评估")
    parser.add_argument("--matrix", default=str(DEFAULT_MATRIX))
    parser.add_argument("--roles", default=str(DEFAULT_ROLES))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--fixed-threshold", type=float, default=FIXED_THRESHOLD)
    parser.add_argument("--cohort-sizes", type=int, nargs="+", default=[50, 100, 200, 400])
    parser.add_argument("--min-records", type=int, default=100)
    parser.add_argument("--min-genuine-pairs", type=int, default=10)
    parser.add_argument("--operating-min-coverage", type=float, default=0.50)
    parser.add_argument("--operating-min-genuine-pairs", type=int, default=100)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    summary = run(parse_args(argv))
    baseline = summary["baseline"]
    best_full = summary["best_full_backend"]
    best_operating = summary["best_operating_backend"]
    print(
        "DONE "
        f"BASE_EER={baseline['eer']:.4f} "
        f"BEST_FULL={best_full['score_name']} EER={best_full['eer']:.4f} "
        f"BEST_OPERATING={best_operating['quality_config']}+{best_operating['score_name']} "
        f"EER={best_operating['eer']:.4f}",
        flush=True,
    )


if __name__ == "__main__":
    main()
