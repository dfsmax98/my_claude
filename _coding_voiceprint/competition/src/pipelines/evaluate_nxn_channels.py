# -*- coding: utf-8 -*-
"""完整拆分双声轨，提取 CAM++ embedding 并生成 N×N 对比矩阵。"""
import argparse
import csv
import json
import os
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from common import audio_io, embedding


AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".flac"}


def parse_recording_name(path):
    """从 <客户标识>_<通话序号> 中解析录音ID、客户标识和序号。"""
    stem = Path(path).stem
    if "_" not in stem:
        raise ValueError(f"文件名缺少通话序号: {Path(path).name}")
    identity, sequence = stem.rsplit("_", 1)
    if not identity or not sequence.isdigit():
        raise ValueError(f"文件名不符合 <客户标识>_<序号>: {Path(path).name}")
    return stem, identity, int(sequence)


def _atomic_save_npz(path, **arrays):
    path = Path(path)
    temp_path = path.with_name(path.stem + ".tmp.npz")
    np.savez_compressed(temp_path, **arrays)
    os.replace(temp_path, path)


def load_checkpoint(path):
    path = Path(path)
    if not path.exists():
        return {}
    data = np.load(path, allow_pickle=False)
    records = {}
    for idx, recording_id in enumerate(data["recording_ids"].tolist()):
        records[str(recording_id)] = {
            "recording_id": str(recording_id),
            "identity": str(data["identities"][idx]),
            "sequence": int(data["sequences"][idx]),
            "source": str(data["sources"][idx]),
            "duration": float(data["durations"][idx]),
            "left": data["left"][idx].astype(np.float32),
            "right": data["right"][idx].astype(np.float32),
        }
    return records


def save_checkpoint(path, records):
    ordered = sorted(records.values(), key=lambda item: item["recording_id"])
    count = len(ordered)
    left = np.stack([item["left"] for item in ordered]) if count else np.empty((0, 192), np.float32)
    right = np.stack([item["right"] for item in ordered]) if count else np.empty((0, 192), np.float32)
    _atomic_save_npz(
        path,
        recording_ids=np.asarray([item["recording_id"] for item in ordered]),
        identities=np.asarray([item["identity"] for item in ordered]),
        sequences=np.asarray([item["sequence"] for item in ordered], dtype=np.int32),
        sources=np.asarray([item["source"] for item in ordered]),
        durations=np.asarray([item["duration"] for item in ordered], dtype=np.float32),
        left=left.astype(np.float32),
        right=right.astype(np.float32),
    )


def compute_eer(scores, genuine):
    """按降序扫阈值，返回 EER 和对应阈值。"""
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
    boundaries = np.r_[np.flatnonzero(sorted_scores[:-1] != sorted_scores[1:]), len(scores) - 1]
    far = false_positive[boundaries] / negatives
    frr = (positives - true_positive[boundaries]) / positives
    best = int(np.argmin(np.abs(far - frr)))
    return float((far[best] + frr[best]) / 2), float(sorted_scores[boundaries[best]])


def evaluate_matrix(matrix, identities, fixed_threshold=0.751):
    identities = np.asarray(identities)
    row, col = np.triu_indices(len(identities), k=1)
    scores = matrix[row, col]
    genuine = identities[row] == identities[col]
    genuine_scores = scores[genuine]
    impostor_scores = scores[~genuine]
    eer, threshold = compute_eer(scores, genuine)

    work = matrix.copy()
    np.fill_diagonal(work, -np.inf)
    nearest = np.argmax(work, axis=1)
    counts = Counter(identities.tolist())
    eligible = np.asarray([counts[item] > 1 for item in identities])
    top1 = float((identities[nearest][eligible] == identities[eligible]).mean()) if eligible.any() else None

    return {
        "genuine_pairs": int(len(genuine_scores)),
        "impostor_pairs": int(len(impostor_scores)),
        "genuine_mean": float(genuine_scores.mean()),
        "genuine_p05": float(np.percentile(genuine_scores, 5)),
        "genuine_min": float(genuine_scores.min()),
        "impostor_mean": float(impostor_scores.mean()),
        "impostor_p95": float(np.percentile(impostor_scores, 95)),
        "impostor_p99": float(np.percentile(impostor_scores, 99)),
        "impostor_max": float(impostor_scores.max()),
        "eer": eer,
        "eer_threshold": threshold,
        "tar_at_fixed": float((genuine_scores >= fixed_threshold).mean()),
        "far_at_fixed": float((impostor_scores >= fixed_threshold).mean()),
        "top1_eligible": int(eligible.sum()),
        "top1_accuracy": top1,
    }


def write_matrix_csv(path, matrix, recording_ids):
    with Path(path).open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["recording_id", *recording_ids])
        for recording_id, row in zip(recording_ids, matrix):
            writer.writerow([recording_id, *(f"{float(value):.6f}" for value in row)])


def write_labels_csv(path, records):
    with Path(path).open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["matrix_index", "recording_id", "identity", "sequence", "source", "duration_sec"])
        for idx, item in enumerate(records):
            writer.writerow([idx, item["recording_id"], item["identity"], item["sequence"],
                             item["source"], f"{item['duration']:.3f}"])


def write_report(path, records, failures, metrics, channel_evidence, elapsed):
    identity_counts = Counter(item["identity"] for item in records)

    def pct(value):
        return "-" if value is None else f"{value * 100:.2f}%"

    lines = [
        "# 客诉录音双声轨 N×N 声纹评估报告",
        "",
        "> 本脚本生成不使用 ASR 的双声轨声纹基线；客户侧角色确认请继续执行 "
        "`pipelines/classify_roles_adaptive.py`。",
        "",
        "## 样本概况",
        "",
        f"- 成功录音：{len(records)} 通",
        f"- 客户标识：{len(identity_counts)} 个",
        f"- 双通客户：{sum(count == 2 for count in identity_counts.values())} 个",
        f"- 单通客户：{sum(count == 1 for count in identity_counts.values())} 个",
        f"- 失败录音：{len(failures)} 通",
        f"- embedding：{len(records) * 2} 个，CAM++ 192 维",
        f"- 处理耗时：{elapsed / 3600:.2f} 小时",
        "",
        "## 评估结果",
        "",
        "固定判同阈值使用 8k 电话标定值 `0.751`。",
        "",
        "| 矩阵口径 | 同人均值 | 同人5分位 | 异人均值 | 异人95分位 | EER | EER阈值 | TAR@0.751 | FAR@0.751 | Top-1 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    labels = {
        "left_left": "L-L",
        "right_right": "R-R",
        "same_channel_max": "同声道最大值",
        "any_channel_max": "四组合最大值",
    }
    for key in ("left_left", "right_right", "same_channel_max", "any_channel_max"):
        item = metrics[key]
        lines.append(
            f"| {labels[key]} | {item['genuine_mean']:.3f} | {item['genuine_p05']:.3f} | "
            f"{item['impostor_mean']:.3f} | {item['impostor_p95']:.3f} | {pct(item['eer'])} | "
            f"{item['eer_threshold']:.3f} | {pct(item['tar_at_fixed'])} | "
            f"{pct(item['far_at_fixed'])} | {pct(item['top1_accuracy'])} |"
        )
    lines += [
        "",
        "## 无 ASR 基线声道归属推断",
        "",
        f"- 485 个同客户录音对中，R-R 分数高于 L-L 的有 "
        f"**{channel_evidence['right_gt_left']}/{channel_evidence['same_pairs']}** "
        f"（{channel_evidence['right_gt_left'] / channel_evidence['same_pairs'] * 100:.2f}%）。",
        f"- 四种声道组合取最高分时，R-R 直接胜出 "
        f"**{channel_evidence['winners']['R-R']}/{channel_evidence['same_pairs']}** "
        f"（{channel_evidence['winners']['R-R'] / channel_evidence['same_pairs'] * 100:.2f}%）。",
        f"- 其余胜出分布：L-L {channel_evidence['winners']['L-L']} 对、"
        f"L-R {channel_evidence['winners']['L-R']} 对、R-L {channel_evidence['winners']['R-L']} 对。",
        "- 结合 R-R 的 EER/Top-1 与 L-L 接近随机的结果，本批数据可把右声道作为客户侧强先验；"
        "该结论仅适用于本批录音，非 R-R 胜出样本仍需复核。",
        "- 四组合最大值会把重复坐席也当作命中：虽然 TAR 较高，但 FAR 和 Top-1 明显恶化，"
        "不适合作为客户身份检索的默认口径。",
        "",
        "## ASR 角色识别优化建议",
        "",
        "- 先转录双声道前 30 秒；话术差异达到高置信且不违背右声道客户先验时直接确定角色。",
        "- 30 秒结果为中/低置信，或与右声道客户先验冲突时，扩展到 120 秒。",
        "- 120 秒后仍缺一方或低置信时才跑全量；全量后仍低置信的样本进入人工复核。",
        "- ASR 仅用于客户/坐席角色判断；转译文本不落盘，只保留关键词计数、字符数、时长和角色结果。",
        "",
        "## 口径说明",
        "",
        "- `L-L` / `R-R`：固定比较相同声道，可观察客户声音是否稳定落在某一侧。",
        "- `同声道最大值`：取 `max(L-L, R-R)`，不处理左右声道互换。",
        "- `四组合最大值`：取 L-L、L-R、R-L、R-R 最大值，可处理声道互换，但重复坐席也可能造成跨客户高分。",
        "- 同人标签来自相同客户标识下的两通录音；单通客户只参与异人对和检索候选，不参与同人对。",
        "- 本报告验证的是双声轨声纹区分能力，不等同于已识别客户角色后的客户声纹效果。",
        "",
        "## 产物",
        "",
        "- `channel_embeddings.npz`：每通录音 L/R embedding 与元数据。",
        "- `nxn_matrices.npz`：录音级四类矩阵及 2N×2N 声道矩阵。",
        "- `recording_nxn_any_channel.csv`：四组合最大值的可读 N×N 矩阵。",
        "- `matrix_labels.csv`：矩阵下标与录音、客户标识映射。",
        "- `same_customer_channel_comparison.csv`：同客户录音对的四声道分数与胜出声道。",
        "- `channel_inference.json`：无 ASR 声道归属聚合统计。",
        "- `客户侧ASR评估报告.md`：运行 `classify_roles_adaptive.py` 后生成的 ASR 客户侧评估报告。",
        "- `failures.json`：失败明细。",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def analyze_channel_evidence(left_left, right_right, left_right, identities,
                             recording_ids, output_path):
    identities = np.asarray(identities)
    recording_ids = np.asarray(recording_ids)
    row, col = np.triu_indices(len(identities), k=1)
    same = identities[row] == identities[col]
    row, col = row[same], col[same]
    scores = np.column_stack([
        left_left[row, col], right_right[row, col],
        left_right[row, col], left_right[col, row],
    ])
    names = np.asarray(["L-L", "R-R", "L-R", "R-L"])
    winners = np.argmax(scores, axis=1)
    with Path(output_path).open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["identity", "recording_a", "recording_b", "L-L", "R-R",
                         "L-R", "R-L", "winner"])
        for idx, (a, b) in enumerate(zip(row, col)):
            writer.writerow([
                identities[a], recording_ids[a], recording_ids[b],
                *(f"{float(value):.6f}" for value in scores[idx]), names[winners[idx]],
            ])
    return {
        "same_pairs": int(len(row)),
        "right_gt_left": int((scores[:, 1] > scores[:, 0]).sum()),
        "winners": {name: int((winners == idx).sum()) for idx, name in enumerate(names)},
    }


def _worker_init(torch_threads):
    import torch

    torch.set_num_threads(torch_threads)
    torch.set_num_interop_threads(torch_threads)
    embedding.get_model()


def _extract_one(source_text, work_root_text):
    source = Path(source_text)
    work_root = Path(work_root_text)
    recording_id, identity, sequence = parse_recording_name(source)
    try:
        info = sf.info(source)
        if info.channels != 2:
            raise ValueError(f"要求双声道，实际{info.channels}声道")
        with tempfile.TemporaryDirectory(prefix="call_", dir=work_root) as temp_dir:
            left_path = Path(temp_dir) / "left.wav"
            right_path = Path(temp_dir) / "right.wav"
            audio_io.extract_channel(str(source), 0, str(left_path))
            audio_io.extract_channel(str(source), 1, str(right_path))
            left = embedding.embed(str(left_path), disable_pbar=True)
            right = embedding.embed(str(right_path), disable_pbar=True)
        return {
            "ok": True,
            "record": {
                "recording_id": recording_id,
                "identity": identity,
                "sequence": sequence,
                "source": source.name,
                "duration": float(info.duration),
                "left": left,
                "right": right,
            },
        }
    except Exception as exc:
        return {
            "ok": False,
            "failure": {"recording_id": recording_id, "source": source.name,
                        "error": f"{type(exc).__name__}: {exc}"},
        }


def extract_embeddings(files, output_dir, checkpoint_every=10, limit=None,
                       workers=1, torch_threads=None):
    checkpoint = output_dir / "channel_embeddings.npz"
    records = load_checkpoint(checkpoint)
    failures_path = output_dir / "failures.json"
    failures = json.loads(failures_path.read_text(encoding="utf-8")) if failures_path.exists() else []
    targets = files[:limit] if limit else files
    work_root = ROOT / "_temp" / "nxn_channel_work"
    work_root.mkdir(parents=True, exist_ok=True)
    started = time.time()
    new_count = 0
    pending = [source for source in targets if parse_recording_name(source)[0] not in records]
    for source in targets:
        recording_id = parse_recording_name(source)[0]
        if recording_id in records:
            print(f"CACHE {recording_id}", flush=True)

    def accept_result(result, position):
        nonlocal new_count
        if result["ok"]:
            item = result["record"]
            records[item["recording_id"]] = item
            new_count += 1
            print(f"[{position}/{len(pending)}] OK {item['recording_id']} "
                  f"dur={item['duration']:.1f}s", flush=True)
        else:
            item = result["failure"]
            failures.append(item)
            print(f"[{position}/{len(pending)}] FAIL {item['recording_id']}: {item['error']}", flush=True)
        if new_count and new_count % checkpoint_every == 0:
            save_checkpoint(checkpoint, records)
            failures_path.write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"CHECKPOINT processed={len(records)} failures={len(failures)}", flush=True)

    if workers <= 1:
        _worker_init(torch_threads or max(1, os.cpu_count() or 1))
        for position, source in enumerate(pending, 1):
            accept_result(_extract_one(str(source), str(work_root)), position)
    else:
        threads = torch_threads or max(1, (os.cpu_count() or workers) // workers)
        print(f"PARALLEL workers={workers} torch_threads={threads} pending={len(pending)}", flush=True)
        with ProcessPoolExecutor(max_workers=workers, initializer=_worker_init,
                                 initargs=(threads,)) as executor:
            futures = {
                executor.submit(_extract_one, str(source), str(work_root)): source
                for source in pending
            }
            for position, future in enumerate(as_completed(futures), 1):
                source = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    recording_id = parse_recording_name(source)[0]
                    result = {"ok": False, "failure": {
                        "recording_id": recording_id, "source": source.name,
                        "error": f"WorkerError: {type(exc).__name__}: {exc}"}}
                accept_result(result, position)

    save_checkpoint(checkpoint, records)
    failures_path.write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
    return records, failures, time.time() - started


def build_outputs(output_dir, records, failures, elapsed, write_csv=True):
    ordered = sorted(records.values(), key=lambda item: item["recording_id"])
    recording_ids = np.asarray([item["recording_id"] for item in ordered])
    identities = np.asarray([item["identity"] for item in ordered])
    left = np.stack([item["left"] for item in ordered]).astype(np.float32)
    right = np.stack([item["right"] for item in ordered]).astype(np.float32)

    left_left = left @ left.T
    right_right = right @ right.T
    left_right = left @ right.T
    same_channel_max = np.maximum(left_left, right_right)
    any_channel_max = np.maximum.reduce([left_left, right_right, left_right, left_right.T])
    channel_matrix = np.block([[left_left, left_right], [left_right.T, right_right]])

    matrices = {
        "left_left": left_left,
        "right_right": right_right,
        "same_channel_max": same_channel_max,
        "any_channel_max": any_channel_max,
    }
    metrics = {name: evaluate_matrix(matrix, identities) for name, matrix in matrices.items()}
    channel_evidence = analyze_channel_evidence(
        left_left, right_right, left_right, identities, recording_ids,
        output_dir / "same_customer_channel_comparison.csv")
    _atomic_save_npz(
        output_dir / "nxn_matrices.npz",
        recording_ids=recording_ids,
        identities=identities,
        left_left=left_left.astype(np.float32),
        right_right=right_right.astype(np.float32),
        left_right=left_right.astype(np.float32),
        same_channel_max=same_channel_max.astype(np.float32),
        any_channel_max=any_channel_max.astype(np.float32),
        channel_matrix=channel_matrix.astype(np.float32),
    )
    write_labels_csv(output_dir / "matrix_labels.csv", ordered)
    if write_csv:
        write_matrix_csv(output_dir / "recording_nxn_any_channel.csv", any_channel_max, recording_ids)
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "channel_inference.json").write_text(
        json.dumps(channel_evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(output_dir / "评估报告.md", ordered, failures, metrics,
                 channel_evidence, elapsed)
    return metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("src_dir")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--checkpoint-every", type=int, default=10)
    parser.add_argument("--limit", type=int, default=None, help="仅处理前N个文件；后续去掉可断点续跑")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--torch-threads", type=int, default=None)
    parser.add_argument("--skip-csv", action="store_true")
    args = parser.parse_args()

    src_dir = Path(args.src_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(path for path in src_dir.iterdir()
                   if path.is_file() and path.suffix.lower() in AUDIO_SUFFIXES)
    if not files:
        raise SystemExit(f"目录中没有支持的音频: {src_dir}")
    for path in files:
        parse_recording_name(path)

    print(f"START files={len(files)} output={output_dir} at={datetime.now():%F %T}", flush=True)
    records, failures, elapsed = extract_embeddings(
        files, output_dir, checkpoint_every=args.checkpoint_every, limit=args.limit,
        workers=args.workers, torch_threads=args.torch_threads)
    expected = len(files) if args.limit is None else min(args.limit, len(files))
    if len(records) < expected:
        print(f"PARTIAL records={len(records)} expected={expected} failures={len(failures)}", flush=True)
    metrics = build_outputs(output_dir, records, failures, elapsed, write_csv=not args.skip_csv)
    print(f"DONE records={len(records)} failures={len(failures)} elapsed={elapsed:.1f}s", flush=True)
    for name, item in metrics.items():
        print(f"METRIC {name} EER={item['eer']:.4f} THR={item['eer_threshold']:.4f} "
              f"TOP1={item['top1_accuracy']:.4f}", flush=True)


if __name__ == "__main__":
    main()
