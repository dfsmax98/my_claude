# -*- coding: utf-8 -*-
"""渐进式 ASR 角色识别，并生成客户/客服分角色声纹 N×N 矩阵。"""
import argparse
import json
import os
import sys
import tempfile
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from common import asr_role, audio_io, text_role
from evaluate_nxn_channels import (
    _atomic_save_npz,
    evaluate_matrix,
    load_checkpoint,
    write_matrix_csv,
)


HIGH = "高"
LOW_PREFIX = "低"
ROLE_RULE_VERSION = "2026-08-20-text-v1"


def _atomic_write_json(path, value):
    path = Path(path)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_path, path)


def _worker_init(torch_threads):
    import torch

    torch.set_num_threads(torch_threads)
    torch.set_num_interop_threads(torch_threads)
    asr_role.get_model()
    text_role.load_model()


def _text_decision(left, right):
    result = text_role.classify_features(left, right)
    confidence = {
        "identified": HIGH,
        "needs_review": f"{LOW_PREFIX}(话术差值不足)",
        "one_sided": "缺一方",
        "no_effective_dialogue": "无有效对话",
    }.get(result["status"], f"{LOW_PREFIX}(需复核)")
    return {**result, "confidence": confidence}


def _classify_stage(source, duration, work_root):
    stage_label = "full" if duration is None else str(duration)
    with tempfile.TemporaryDirectory(prefix="role_", dir=work_root) as temp_dir:
        left_path = Path(temp_dir) / "left.wav"
        right_path = Path(temp_dir) / "right.wav"
        audio_io.extract_channel(str(source), 0, str(left_path), dur=duration)
        audio_io.extract_channel(str(source), 1, str(right_path), dur=duration)
        left_features = asr_role.transcribe_role_features(str(left_path))
        right_features = asr_role.transcribe_role_features(str(right_path))
    decision = _text_decision(left_features, right_features)
    return {
        "stage": stage_label,
        "decision": decision,
        "left": left_features["summary"],
        "right": right_features["summary"],
    }


def _needs_full(decision):
    confidence = str(decision.get("confidence", ""))
    return decision.get("customer_ch") is None or confidence != HIGH


def _classify_one(source_text, work_root_text, allow_full_asr):
    source = Path(source_text)
    recording_id = source.stem
    stages = []
    try:
        first = _classify_stage(source, 30, Path(work_root_text))
        stages.append(first)
        first_decision = first["decision"]
        accept_first = first_decision.get("confidence") == HIGH

        if accept_first:
            final = first_decision
        else:
            second = _classify_stage(source, 120, Path(work_root_text))
            stages.append(second)
            if _needs_full(second["decision"]) and allow_full_asr:
                last = _classify_stage(source, None, Path(work_root_text))
                stages.append(last)
                final = last["decision"]
            else:
                final = second["decision"]

        channels = [item["decision"].get("customer_ch") for item in stages]
        channels = [channel for channel in channels if channel is not None]
        confidence = str(final.get("confidence", ""))
        return {
            "ok": final.get("customer_ch") in {"L", "R"},
            "recording_id": recording_id,
            "source": source.name,
            "customer_ch": final.get("customer_ch"),
            "agent_ch": final.get("agent_ch"),
            "confidence": confidence,
            "final_stage": stages[-1]["stage"],
            "stage_disagreement": len(set(channels)) > 1,
            "prior_conflict": False,
            "needs_review": confidence != HIGH or final.get("customer_ch") is None,
            "allow_full_asr": allow_full_asr,
            "stages": stages,
        }
    except Exception as exc:
        return {
            "ok": False,
            "recording_id": recording_id,
            "source": source.name,
            "error": f"{type(exc).__name__}: {exc}",
            "stages": stages,
        }


def classify_all(source_dir, recording_ids, output_dir, workers=4,
                 torch_threads=None, checkpoint_every=10, use_right_prior=False,
                 allow_full_asr=True):
    if use_right_prior:
        raise ValueError("文本角色模型禁止启用右声道客户先验")
    checkpoint_path = output_dir / "adaptive_roles.json"
    signature = {
        "role_rule_version": ROLE_RULE_VERSION,
        "use_right_prior": False,
        "allow_full_asr": bool(allow_full_asr),
        "model_input": "asr_text_only",
    }
    checkpoint = {}
    if checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    if checkpoint.get("meta") != signature:
        checkpoint = {"meta": signature, "records": {}, "failures": {}}
    records = checkpoint.get("records", {})
    failures = checkpoint.get("failures", {})
    pending = [recording_id for recording_id in recording_ids if recording_id not in records]
    work_root = ROOT / "_temp" / "adaptive_role_work"
    work_root.mkdir(parents=True, exist_ok=True)
    threads = torch_threads or max(1, (os.cpu_count() or workers) // workers)
    started = time.time()

    print(f"START total={len(recording_ids)} cached={len(records)} pending={len(pending)} "
          f"workers={workers} threads={threads}", flush=True)
    with ProcessPoolExecutor(max_workers=workers, initializer=_worker_init,
                             initargs=(threads,)) as executor:
        futures = {
            executor.submit(
                _classify_one,
                str(source_dir / f"{recording_id}.mp3"),
                str(work_root),
                allow_full_asr,
            ): recording_id
            for recording_id in pending
        }
        completed = 0
        for future in as_completed(futures):
            recording_id = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {"ok": False, "recording_id": recording_id,
                          "error": f"WorkerError: {type(exc).__name__}: {exc}"}
            completed += 1
            if result.get("ok"):
                records[recording_id] = result
                failures.pop(recording_id, None)
                print(f"[{completed}/{len(pending)}] OK {recording_id} "
                      f"ch={result['customer_ch']} stage={result['final_stage']} "
                      f"conf={result['confidence']} review={result['needs_review']}", flush=True)
            else:
                failures[recording_id] = result
                print(f"[{completed}/{len(pending)}] FAIL {recording_id}: "
                      f"{result.get('error', '角色未判定')}", flush=True)

            if completed % checkpoint_every == 0:
                _atomic_write_json(checkpoint_path, {
                    "meta": signature, "records": records, "failures": failures})
                print(f"CHECKPOINT records={len(records)} failures={len(failures)}", flush=True)

    _atomic_write_json(checkpoint_path, {
        "meta": signature, "records": records, "failures": failures})
    return records, failures, time.time() - started


def _write_role_labels(path, ordered_roles):
    import csv

    with Path(path).open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["matrix_index", "recording_id", "customer_ch", "agent_ch",
                         "confidence", "final_stage", "stage_disagreement", "prior_conflict",
                         "needs_review", "included_in_matrix"])
        matrix_index = 0
        for item in ordered_roles:
            included = not item["needs_review"]
            writer.writerow([
                matrix_index if included else "",
                item["recording_id"], item["customer_ch"], item["agent_ch"],
                item["confidence"], item["final_stage"], item["stage_disagreement"],
                item.get("prior_conflict", False), item["needs_review"],
                included,
            ])
            if included:
                matrix_index += 1


def _select_role_embeddings(embeddings, roles):
    selected = []
    for recording_id in sorted(embeddings):
        role = roles.get(recording_id)
        if not role or role.get("customer_ch") not in {"L", "R"}:
            continue
        if role.get("agent_ch") not in {"L", "R"}:
            continue
        item = embeddings[recording_id]
        selected.append({
            **role,
            "identity": item["identity"],
            "customer_embedding": item["left"] if role["customer_ch"] == "L" else item["right"],
            "agent_embedding": item["left"] if role["agent_ch"] == "L" else item["right"],
        })
    return selected


def _build_role_matrix(selected, output_dir, prefix, embedding_key):
    recording_ids = np.asarray([item["recording_id"] for item in selected])
    identities = np.asarray([item["identity"] for item in selected])
    vectors = np.stack([item[embedding_key] for item in selected]).astype(np.float32)
    matrix = vectors @ vectors.T
    metrics = evaluate_matrix(matrix, identities)
    trusted_idx = np.asarray([not item["needs_review"] for item in selected])
    trusted_matrix = matrix[np.ix_(trusted_idx, trusted_idx)]
    trusted_identities = identities[trusted_idx]
    trusted_metrics = (
        evaluate_matrix(trusted_matrix, trusted_identities)
        if len(trusted_identities) >= 2 and len(set(trusted_identities)) >= 2
        else None
    )

    _atomic_save_npz(
        output_dir / f"{prefix}_nxn_matrix.npz",
        recording_ids=recording_ids,
        identities=identities,
        embeddings=vectors,
        matrix=matrix.astype(np.float32),
        trusted_mask=trusted_idx,
    )
    write_matrix_csv(output_dir / f"{prefix}_nxn_matrix.csv", matrix, recording_ids)
    return {"all": metrics, "trusted": trusted_metrics}


def build_customer_outputs(embedding_path, roles, failures, output_dir, elapsed):
    embeddings = load_checkpoint(embedding_path)
    selected_all = _select_role_embeddings(embeddings, roles)
    selected = [item for item in selected_all if not item["needs_review"]]
    if not selected:
        raise RuntimeError("没有可用于矩阵计算的分角色embedding")

    customer_payload = _build_role_matrix(
        selected, output_dir, "customer", "customer_embedding")
    agent_payload = _build_role_matrix(
        selected, output_dir, "agent", "agent_embedding")
    _write_role_labels(output_dir / "adaptive_role_labels.csv", selected_all)
    payload = {"customer": customer_payload, "agent": agent_payload}
    (output_dir / "customer_metrics.json").write_text(
        json.dumps(customer_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "agent_metrics.json").write_text(
        json.dumps(agent_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "role_metrics.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    stage_counts = Counter(item["final_stage"] for item in selected_all)
    channel_counts = Counter(item["customer_ch"] for item in selected_all)
    confidence_counts = Counter(item["confidence"] for item in selected_all)
    review_count = sum(item["needs_review"] for item in selected_all)
    disagreement_count = sum(item["stage_disagreement"] for item in selected_all)

    full_asr_enabled = any(item.get("allow_full_asr") for item in selected_all)

    def pct(value):
        return "-" if value is None else f"{value * 100:.2f}%"

    def metric_lines(title, metrics, note):
        lines = [
            f"## {title}",
            "",
            note,
            "",
            f"- EER：{pct(metrics['eer'])}",
            f"- EER阈值：{metrics['eer_threshold']:.3f}",
            f"- 同客户配对均值/5分位：{metrics['genuine_mean']:.3f} / {metrics['genuine_p05']:.3f}",
            f"- 跨客户配对均值/95分位：{metrics['impostor_mean']:.3f} / {metrics['impostor_p95']:.3f}",
            f"- TAR@0.751：{pct(metrics['tar_at_fixed'])}",
            f"- FAR@0.751：{pct(metrics['far_at_fixed'])}",
            f"- Top-1：{pct(metrics['top1_accuracy'])}",
            "",
        ]
        return lines

    lines = [
        "# 客诉录音自适应ASR分角色声纹评估",
        "",
        "> ASR仅用于角色判断；每通录音按 `customer_ch` / `agent_ch` 分别提取客户侧、客服侧 embedding 后再做 N×N。",
        "",
        "## 执行概况",
        "",
        f"- 成功角色识别：{len(selected_all)} 通",
        f"- 纳入正式矩阵：{len(selected)} 通",
        f"- 失败：{len(failures)} 通",
        f"- 客户声道：L={channel_counts.get('L', 0)}，R={channel_counts.get('R', 0)}",
        f"- 30秒完成：{stage_counts.get('30', 0)} 通",
        f"- 120秒完成：{stage_counts.get('120', 0)} 通",
        (f"- 全量完成：{stage_counts.get('full', 0)} 通"
         if full_asr_enabled else "- 全量ASR：未启用，120秒后仍不确定则进入人工复核"),
        f"- 阶段判断不一致：{disagreement_count} 通",
        f"- 待复核：{review_count} 通",
        (f"- 本轮耗时：{elapsed / 3600:.2f} 小时"
         if elapsed else "- 本轮耗时：复用已有检查点生成矩阵，未重新计时"),
        "",
    ]
    lines += metric_lines(
        "客户对客户矩阵指标",
        customer_payload["all"],
        "同客户配对表示同一客户两通录音的客户侧声纹，跨客户配对表示不同客户的客户侧声纹。",
    )
    lines += metric_lines(
        "客服对客服矩阵指标",
        agent_payload["all"],
        "同客户配对表示同一客户两通录音对应的客服侧声纹；由于没有客服工号真值，这里不等同于客服本人识别指标。",
    )
    lines += [
        "## 说明",
        "",
        "- 先转录双声道前30秒；纯文本模型的话术差异达到冻结阈值时直接采用。",
        "- 30秒结果为低置信、空对话或单边对话时，扩展至120秒。",
        ("- 120秒仍为低置信或缺一方时才执行全量ASR；全量后仍低置信的样本进入人工复核。"
         if full_asr_enabled else "- 120秒仍为低置信或缺一方时，不再跑全量ASR，直接进入人工复核。"),
        "- 模型输入不包含呼叫方向、左右声道先验或客户标识。",
        "- `adaptive_roles.json` 只包含字符数、时长、模型概率和角色结果，不包含转译文本。",
        "- `customer_nxn_matrix.*` 为客户对客户矩阵，`agent_nxn_matrix.*` 为客服对客服矩阵。",
        "- 中低置信结果只保留在角色标签和人工复核清单中，不进入正式客户/客服矩阵。",
        "",
        "## 置信度分布",
        "",
    ]
    for confidence, count in sorted(confidence_counts.items()):
        lines.append(f"- {confidence}: {count} 通")
    report = "\n".join(lines) + "\n"
    (output_dir / "分角色ASR评估报告.md").write_text(report, encoding="utf-8")
    (output_dir / "客户侧ASR评估报告.md").write_text(report, encoding="utf-8")
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source_dir")
    parser.add_argument("--embedding-path", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--torch-threads", type=int, default=None)
    parser.add_argument("--checkpoint-every", type=int, default=10)
    parser.add_argument("--no-full-asr", action="store_true",
                        help="120秒后仍不确定时直接标人工复核，不继续跑全量ASR")
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    embeddings = load_checkpoint(args.embedding_path)
    recording_ids = sorted(embeddings)
    records, failures, elapsed = classify_all(
        source_dir, recording_ids, output_dir,
        workers=args.workers,
        torch_threads=args.torch_threads,
        checkpoint_every=args.checkpoint_every,
        use_right_prior=False,
        allow_full_asr=not args.no_full_asr,
    )
    metrics = build_customer_outputs(
        Path(args.embedding_path), records, failures, output_dir, elapsed)
    print(f"DONE records={len(records)} failures={len(failures)} elapsed={elapsed:.1f}s", flush=True)
    print(f"METRIC CUSTOMER_EER={metrics['customer']['all']['eer']:.4f} "
          f"CUSTOMER_THR={metrics['customer']['all']['eer_threshold']:.4f} "
          f"CUSTOMER_TOP1={metrics['customer']['all']['top1_accuracy']:.4f} "
          f"AGENT_EER={metrics['agent']['all']['eer']:.4f} "
          f"AGENT_THR={metrics['agent']['all']['eer_threshold']:.4f} "
          f"AGENT_TOP1={metrics['agent']['all']['top1_accuracy']:.4f}", flush=True)


if __name__ == "__main__":
    main()
