# -*- coding: utf-8 -*-
"""评估新角色模型客户声纹分布，并与旧客户向量同口径对比。"""
from __future__ import annotations

import argparse
import csv
import struct
import json
import math
import os
import sys
import zlib
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np


MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from pipelines.evaluate_nxn_channels import compute_eer


DEFAULT_NEW = MODULE_ROOT / "data" / "recent_voiceprints_10k_role_text_v2" / "customer_embeddings_v2.npz"
DEFAULT_OLD = MODULE_ROOT / "data" / "recent_voiceprints_10k_20260819" / "customer_embeddings.npz"
DEFAULT_ROLE_SUMMARY = MODULE_ROOT / "data" / "recent_voiceprints_10k_role_text_v2" / "processing_summary.json"
DEFAULT_OUTPUT = MODULE_ROOT / "reports" / "recent_voiceprints_nxn_v2"
FIXED_THRESHOLD = 0.751


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def load_customer_npz(path: Path) -> dict:
    data = np.load(path, allow_pickle=False)
    return {
        "recording_ids": np.asarray(data["recording_ids"]).astype(str),
        "identity_sha256": np.asarray(data["identity_sha256"]).astype(str),
        "customer_channels": np.asarray(data["customer_channels"]).astype(str),
        "embeddings": np.asarray(data["embeddings"], dtype=np.float32),
    }


def normalize_rows(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.maximum(norms, 1e-12)


def percentile_dict(scores: np.ndarray) -> dict:
    if len(scores) == 0:
        return {
            "count": 0,
            "mean": None,
            "std": None,
            "min": None,
            "max": None,
            "p01": None,
            "p05": None,
            "p25": None,
            "p50": None,
            "p75": None,
            "p95": None,
            "p99": None,
        }
    scores = np.asarray(scores, dtype=np.float64)
    return {
        "count": int(len(scores)),
        "mean": float(scores.mean()),
        "std": float(scores.std(ddof=0)),
        "min": float(scores.min()),
        "max": float(scores.max()),
        "p01": float(np.percentile(scores, 1)),
        "p05": float(np.percentile(scores, 5)),
        "p25": float(np.percentile(scores, 25)),
        "p50": float(np.percentile(scores, 50)),
        "p75": float(np.percentile(scores, 75)),
        "p95": float(np.percentile(scores, 95)),
        "p99": float(np.percentile(scores, 99)),
    }


def same_person_pairs(vectors: np.ndarray, identities: np.ndarray,
                      recording_ids: np.ndarray) -> tuple[np.ndarray, list[tuple[str, str, str, float]]]:
    by_identity = defaultdict(list)
    for idx, identity in enumerate(identities):
        if identity:
            by_identity[str(identity)].append(idx)
    scores = []
    rows = []
    for identity, indices in sorted(by_identity.items()):
        if len(indices) < 2:
            continue
        sub = vectors[indices]
        matrix = sub @ sub.T
        r, c = np.triu_indices(len(indices), k=1)
        for local_a, local_b, score in zip(r, c, matrix[r, c]):
            idx_a = indices[int(local_a)]
            idx_b = indices[int(local_b)]
            value = float(score)
            scores.append(value)
            rows.append((identity, str(recording_ids[idx_a]), str(recording_ids[idx_b]), value))
    return np.asarray(scores, dtype=np.float32), rows


def total_impostor_pairs(identities: np.ndarray) -> int:
    n = len(identities)
    total = n * (n - 1) // 2
    counts = Counter(identities.tolist())
    same = sum(count * (count - 1) // 2 for identity, count in counts.items() if identity)
    return int(total - same)


def sample_impostor_scores(vectors: np.ndarray, identities: np.ndarray,
                           max_pairs: int, seed: int) -> tuple[np.ndarray, dict]:
    total = total_impostor_pairs(identities)
    rng = np.random.default_rng(seed)
    if total == 0:
        return np.empty(0, dtype=np.float32), {
            "sampled": False,
            "total_pairs": 0,
            "sample_pairs": 0,
            "seed": seed,
        }
    if total <= max_pairs:
        scores = []
        n = len(identities)
        for start in range(n):
            if start + 1 >= n:
                continue
            mask = identities[start + 1:] != identities[start]
            if mask.any():
                values = vectors[start + 1:][mask] @ vectors[start]
                scores.extend(float(value) for value in values)
        return np.asarray(scores, dtype=np.float32), {
            "sampled": False,
            "total_pairs": int(total),
            "sample_pairs": int(len(scores)),
            "seed": seed,
        }
    target = min(max_pairs, total)
    scores = np.empty(target, dtype=np.float32)
    n = len(identities)
    filled = 0
    batch = max(10000, min(200000, target))
    while filled < target:
        size = min(batch, target - filled)
        a = rng.integers(0, n, size=size * 2)
        b = rng.integers(0, n, size=size * 2)
        mask = (a != b) & (identities[a] != identities[b])
        a = a[mask][:size]
        b = b[mask][:size]
        if len(a) == 0:
            continue
        values = np.einsum("ij,ij->i", vectors[a], vectors[b]).astype(np.float32)
        end = min(target, filled + len(values))
        scores[filled:end] = values[:end - filled]
        filled = end
    return scores, {
        "sampled": target < total,
        "total_pairs": int(total),
        "sample_pairs": int(target),
        "seed": seed,
    }


def top1_accuracy(vectors: np.ndarray, identities: np.ndarray, block_size: int = 512) -> dict:
    counts = Counter(identities.tolist())
    eligible = np.asarray([counts[item] > 1 for item in identities])
    if not eligible.any():
        return {"eligible": 0, "accuracy": None}
    correct = 0
    eligible_count = 0
    n = len(vectors)
    for start in range(0, n, block_size):
        stop = min(n, start + block_size)
        scores = vectors[start:stop] @ vectors.T
        row = np.arange(stop - start)
        scores[row, np.arange(start, stop)] = -np.inf
        nearest = np.argmax(scores, axis=1)
        mask = eligible[start:stop]
        if mask.any():
            correct += int((identities[nearest][mask] == identities[start:stop][mask]).sum())
            eligible_count += int(mask.sum())
    return {
        "eligible": int(eligible_count),
        "accuracy": float(correct / eligible_count) if eligible_count else None,
    }


def evaluate_vectors(recording_ids: np.ndarray, identities: np.ndarray,
                     vectors: np.ndarray, max_impostor_pairs: int,
                     seed: int) -> tuple[dict, np.ndarray, np.ndarray, list[tuple[str, str, str, float]]]:
    vectors = normalize_rows(vectors)
    same_scores, same_rows = same_person_pairs(vectors, identities, recording_ids)
    impostor_scores, impostor_meta = sample_impostor_scores(
        vectors, identities, max_impostor_pairs, seed)
    all_scores = np.concatenate([same_scores, impostor_scores])
    labels = np.concatenate([
        np.ones(len(same_scores), dtype=bool),
        np.zeros(len(impostor_scores), dtype=bool),
    ])
    eer, threshold = compute_eer(all_scores, labels) if len(same_scores) and len(impostor_scores) else (None, None)
    top1 = top1_accuracy(vectors, identities)
    same_stats = percentile_dict(same_scores)
    impostor_stats = percentile_dict(impostor_scores)
    overlap_low = None
    overlap_high = None
    if len(same_scores) and len(impostor_scores):
        overlap_low = max(same_stats["min"], impostor_stats["min"])
        overlap_high = min(same_stats["max"], impostor_stats["max"])
        if overlap_low > overlap_high:
            overlap_low, overlap_high = None, None
    metrics = {
        "record_count": int(len(recording_ids)),
        "identity_count": int(len(set(identities.tolist()))),
        "same_person": same_stats,
        "impostor": impostor_stats,
        "impostor_sampling": impostor_meta,
        "eer": eer,
        "eer_threshold": threshold,
        "tar_at_0_751": (
            float((same_scores >= FIXED_THRESHOLD).mean()) if len(same_scores) else None
        ),
        "far_at_0_751": (
            float((impostor_scores >= FIXED_THRESHOLD).mean()) if len(impostor_scores) else None
        ),
        "top1_identity_retrieval": top1,
        "same_p05_minus_impostor_p95": (
            float(same_stats["p05"] - impostor_stats["p95"])
            if same_stats["p05"] is not None and impostor_stats["p95"] is not None
            else None
        ),
        "overlap_interval": {
            "low": overlap_low,
            "high": overlap_high,
        },
    }
    return metrics, same_scores, impostor_scores, same_rows


def subset_by_recording_ids(data: dict, ids: set[str]) -> dict:
    mask = np.asarray([item in ids for item in data["recording_ids"]])
    return {key: value[mask] if hasattr(value, "__len__") and len(value) == len(mask) else value
            for key, value in data.items()}


def metric_delta(new_metrics: dict, old_metrics: dict) -> dict:
    def delta(path: tuple[str, ...]):
        left = new_metrics
        right = old_metrics
        for key in path:
            left = left[key]
            right = right[key]
        if left is None or right is None:
            return None
        return float(left - right)

    return {
        "same_mean_delta": delta(("same_person", "mean")),
        "same_p05_delta": delta(("same_person", "p05")),
        "impostor_mean_delta": delta(("impostor", "mean")),
        "impostor_p95_delta": delta(("impostor", "p95")),
        "eer_delta": delta(("eer",)),
        "tar_at_0_751_delta": delta(("tar_at_0_751",)),
        "far_at_0_751_delta": delta(("far_at_0_751",)),
        "top1_delta": delta(("top1_identity_retrieval", "accuracy")),
    }


def write_score_csv(path: Path, same_scores: np.ndarray,
                    impostor_scores: np.ndarray) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["pair_type", "score"])
        for score in same_scores:
            writer.writerow(["same_person", f"{float(score):.6f}"])
        for score in impostor_scores:
            writer.writerow(["impostor", f"{float(score):.6f}"])


def write_same_person_csv(path: Path, rows: list[tuple[str, str, str, float]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["identity_sha256", "recording_id_a", "recording_id_b", "score"])
        for identity, a, b, score in rows:
            writer.writerow([identity, a, b, f"{score:.6f}"])


def write_distribution_png(path: Path, same_scores: np.ndarray,
                           impostor_scores: np.ndarray) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False
    plt.figure(figsize=(10, 5))
    bins = np.linspace(-0.1, 1.0, 80)
    plt.hist(impostor_scores, bins=bins, alpha=0.55, density=True, label="impostor")
    plt.hist(same_scores, bins=bins, alpha=0.55, density=True, label="same person")
    plt.axvline(FIXED_THRESHOLD, color="black", linestyle="--", linewidth=1, label="0.751")
    plt.xlabel("cosine similarity")
    plt.ylabel("density")
    plt.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()
    return True


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def _write_rgb_png(path: Path, width: int, height: int, pixels: bytearray) -> None:
    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)
        raw.extend(pixels[y * stride:(y + 1) * stride])
    payload = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(payload)


def _set_pixel(pixels: bytearray, width: int, height: int, x: int, y: int,
               color: tuple[int, int, int]) -> None:
    if 0 <= x < width and 0 <= y < height:
        offset = (y * width + x) * 3
        pixels[offset:offset + 3] = bytes(color)


def _draw_rect(pixels: bytearray, width: int, height: int, x0: int, y0: int,
               x1: int, y1: int, color: tuple[int, int, int]) -> None:
    left, right = sorted((max(0, x0), min(width - 1, x1)))
    top, bottom = sorted((max(0, y0), min(height - 1, y1)))
    for y in range(top, bottom + 1):
        start = (y * width + left) * 3
        end = (y * width + right + 1) * 3
        row = bytearray()
        for _ in range(right - left + 1):
            row.extend(color)
        pixels[start:end] = row


def write_distribution_png_fallback(path: Path, same_scores: np.ndarray,
                                    impostor_scores: np.ndarray) -> bool:
    """无第三方绘图库时输出一个可读的简易直方图 PNG。"""
    width, height = 900, 480
    margin_left, margin_right, margin_top, margin_bottom = 60, 30, 30, 55
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    pixels = bytearray([255] * width * height * 3)
    axis = (60, 60, 60)
    impostor_color = (87, 126, 186)
    same_color = (209, 94, 74)
    threshold_color = (20, 20, 20)

    x_min, x_max = -0.1, 1.0
    bins = np.linspace(x_min, x_max, 80)
    imp_hist, _ = np.histogram(impostor_scores, bins=bins)
    same_hist, _ = np.histogram(same_scores, bins=bins)
    max_count = max(int(imp_hist.max()) if len(imp_hist) else 0,
                    int(same_hist.max()) if len(same_hist) else 0, 1)

    base_y = margin_top + plot_h
    _draw_rect(pixels, width, height, margin_left, margin_top, margin_left, base_y, axis)
    _draw_rect(pixels, width, height, margin_left, base_y, width - margin_right, base_y, axis)
    bar_w = max(1, int(plot_w / max(1, len(bins) - 1)))
    for idx, count in enumerate(imp_hist):
        x = margin_left + int(idx * plot_w / len(imp_hist))
        bar_h = int(plot_h * count / max_count)
        _draw_rect(pixels, width, height, x, base_y - bar_h, x + bar_w - 1, base_y - 1, impostor_color)
    for idx, count in enumerate(same_hist):
        x = margin_left + int(idx * plot_w / len(same_hist)) + max(1, bar_w // 3)
        bar_h = int(plot_h * count / max_count)
        _draw_rect(pixels, width, height, x, base_y - bar_h, x + max(1, bar_w // 2), base_y - 1, same_color)

    threshold_x = margin_left + int((FIXED_THRESHOLD - x_min) / (x_max - x_min) * plot_w)
    _draw_rect(pixels, width, height, threshold_x, margin_top, threshold_x + 1, base_y, threshold_color)
    _draw_rect(pixels, width, height, margin_left + 20, margin_top + 16, margin_left + 50, margin_top + 30, impostor_color)
    _draw_rect(pixels, width, height, margin_left + 20, margin_top + 42, margin_left + 50, margin_top + 56, same_color)
    _write_rgb_png(path, width, height, pixels)
    return True


def fmt(value, pct=False) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.2f}%" if pct else f"{value:.6f}"


def write_report(path: Path, metrics: dict, role_summary: dict | None,
                 old_comparison: dict | None, png_written: bool) -> None:
    new = metrics["new"]
    lines = [
        "# 新角色模型客户声纹分布报告",
        "",
        "> 主结果仅使用新文本角色模型高置信且正式入选的客户侧 CAM++ 向量；空录音、单边录音、拒识和失败样本不进入主评估分母。",
        "",
        "## 主结果",
        "",
        f"- 录音数：{new['record_count']}",
        f"- 客户身份数：{new['identity_count']}",
        f"- 同人对：{new['same_person']['count']}",
        f"- 异人对：{new['impostor_sampling']['total_pairs']}；本次统计使用 {new['impostor_sampling']['sample_pairs']} 对",
        f"- 异人抽样：{new['impostor_sampling']['sampled']}，固定随机种子 {new['impostor_sampling']['seed']}",
        f"- EER：{fmt(new['eer'], pct=True)}，阈值：{fmt(new['eer_threshold'])}",
        f"- TAR@0.751：{fmt(new['tar_at_0_751'], pct=True)}",
        f"- FAR@0.751：{fmt(new['far_at_0_751'], pct=True)}",
        f"- Top-1身份检索：{fmt(new['top1_identity_retrieval']['accuracy'], pct=True)}，可评估录音 {new['top1_identity_retrieval']['eligible']}",
        f"- 同人P05 - 异人P95：{fmt(new['same_p05_minus_impostor_p95'])}",
        f"- 分布重叠区间：{fmt(new['overlap_interval']['low'])} 至 {fmt(new['overlap_interval']['high'])}",
        "",
        "## 分布统计",
        "",
        "| 类型 | 数量 | 均值 | 标准差 | 最小 | P01 | P05 | P25 | P50 | P75 | P95 | P99 | 最大 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, item in (("同人对", new["same_person"]), ("异人对", new["impostor"])):
        lines.append(
            f"| {label} | {item['count']} | {fmt(item['mean'])} | {fmt(item['std'])} | "
            f"{fmt(item['min'])} | {fmt(item['p01'])} | {fmt(item['p05'])} | "
            f"{fmt(item['p25'])} | {fmt(item['p50'])} | {fmt(item['p75'])} | "
            f"{fmt(item['p95'])} | {fmt(item['p99'])} | {fmt(item['max'])} |"
        )
    if role_summary:
        lines += [
            "",
            "## 角色与质量分流",
            "",
            f"- 角色记录：{role_summary.get('role_records')}",
            f"- 正式入选：{role_summary.get('formal_eligible_records')}",
            f"- 角色失败：{role_summary.get('role_failures')}",
            f"- embedding成功：{role_summary.get('embedding_records')}",
            f"- embedding失败：{role_summary.get('embedding_failures')}",
            f"- 状态分布：`{json.dumps(role_summary.get('status_counts', {}), ensure_ascii=False)}`",
            f"- 质量分布：`{json.dumps(role_summary.get('quality_counts', {}), ensure_ascii=False)}`",
        ]
    if old_comparison:
        delta = old_comparison["delta"]
        lines += [
            "",
            "## 旧库同口径对照",
            "",
            f"- 交集录音数：{old_comparison['intersection_count']}",
            f"- 客户声道变化：{old_comparison['customer_channel_changed']}",
            f"- 同人均值变化：{fmt(delta['same_mean_delta'])}",
            f"- 同人P05变化：{fmt(delta['same_p05_delta'])}",
            f"- 异人均值变化：{fmt(delta['impostor_mean_delta'])}",
            f"- 异人P95变化：{fmt(delta['impostor_p95_delta'])}",
            f"- EER变化：{fmt(delta['eer_delta'], pct=True)}",
            f"- TAR@0.751变化：{fmt(delta['tar_at_0_751_delta'], pct=True)}",
            f"- FAR@0.751变化：{fmt(delta['far_at_0_751_delta'], pct=True)}",
            f"- Top-1变化：{fmt(delta['top1_delta'], pct=True)}",
        ]
    lines += [
        "",
        "## 产物",
        "",
        "- `distribution_metrics.json`：完整指标与旧库对照。",
        "- `score_distribution.csv`：同人全量分数和异人统计样本分数。",
        "- `same_person_scores.csv`：同人对明细。",
        "- `distribution.png`：分布图。" if png_written else "- `distribution.png`：当前环境缺少绘图库，未生成。",
        "",
        "## 边界",
        "",
        "- 异人对如发生抽样，FAR、EER和异人分位数均为固定种子的抽样估计。",
        "- `identity_sha256`是客户身份代理标签，不能替代人工声纹真值。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def evaluate_dataset(data: dict, max_impostor_pairs: int, seed: int) -> tuple[dict, np.ndarray, np.ndarray, list]:
    return evaluate_vectors(
        data["recording_ids"],
        data["identity_sha256"],
        data["embeddings"],
        max_impostor_pairs,
        seed,
    )


def run_evaluation(new_path: Path, old_path: Path | None, role_summary_path: Path | None,
                   output_dir: Path, max_impostor_pairs: int, seed: int) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    new_data = load_customer_npz(new_path)
    new_metrics, same_scores, impostor_scores, same_rows = evaluate_dataset(
        new_data, max_impostor_pairs, seed)
    metrics = {"new": new_metrics}
    old_comparison = None
    if old_path and old_path.exists():
        old_data = load_customer_npz(old_path)
        intersection = set(new_data["recording_ids"].tolist()) & set(old_data["recording_ids"].tolist())
        if intersection:
            new_intersection = subset_by_recording_ids(new_data, intersection)
            old_intersection = subset_by_recording_ids(old_data, intersection)
            old_metrics, *_ = evaluate_dataset(old_intersection, max_impostor_pairs, seed)
            new_intersection_metrics, *_ = evaluate_dataset(new_intersection, max_impostor_pairs, seed)
            old_channel = {
                rid: ch for rid, ch in zip(
                    old_intersection["recording_ids"].tolist(),
                    old_intersection["customer_channels"].tolist(),
                )
            }
            changed = sum(
                old_channel.get(rid) != ch
                for rid, ch in zip(
                    new_intersection["recording_ids"].tolist(),
                    new_intersection["customer_channels"].tolist(),
                )
            )
            old_comparison = {
                "intersection_count": int(len(intersection)),
                "customer_channel_changed": int(changed),
                "old_intersection": old_metrics,
                "new_intersection": new_intersection_metrics,
                "delta": metric_delta(new_intersection_metrics, old_metrics),
            }
            metrics["old_comparison"] = old_comparison
    role_summary = None
    if role_summary_path and role_summary_path.exists():
        role_summary = json.loads(role_summary_path.read_text(encoding="utf-8"))
        metrics["role_summary"] = role_summary

    write_score_csv(output_dir / "score_distribution.csv", same_scores, impostor_scores)
    write_same_person_csv(output_dir / "same_person_scores.csv", same_rows)
    png_path = output_dir / "distribution.png"
    png_written = (
        write_distribution_png(png_path, same_scores, impostor_scores)
        or write_distribution_png_fallback(png_path, same_scores, impostor_scores)
    )
    atomic_write_json(output_dir / "distribution_metrics.json", metrics)
    write_report(
        output_dir / "新角色模型客户声纹分布报告.md",
        metrics,
        role_summary,
        old_comparison,
        png_written,
    )
    return metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--new-embeddings", type=Path, default=DEFAULT_NEW)
    parser.add_argument("--old-embeddings", type=Path, default=DEFAULT_OLD)
    parser.add_argument("--role-summary", type=Path, default=DEFAULT_ROLE_SUMMARY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-impostor-pairs", type=int, default=2_000_000)
    parser.add_argument("--seed", type=int, default=20260820)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    metrics = run_evaluation(
        args.new_embeddings,
        args.old_embeddings,
        args.role_summary,
        args.output_dir,
        args.max_impostor_pairs,
        args.seed,
    )
    print(json.dumps(metrics["new"], ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
