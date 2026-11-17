# -*- coding: utf-8 -*-
"""按高置信角色拆出完整客户声道，重提 embedding 并生成客户 N×N 矩阵。"""
import argparse
import csv
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from common import audio_io, embedding
from evaluate_nxn_channels import (
    _atomic_save_npz,
    evaluate_matrix,
    load_checkpoint as load_channel_embeddings,
    write_matrix_csv,
)


def _atomic_write_json(path, value):
    path = Path(path)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_path, path)


def load_accepted_roles(path, overrides_path=None):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    records = payload.get("records", {})
    overrides = {}
    if overrides_path is not None:
        overrides = json.loads(Path(overrides_path).read_text(encoding="utf-8"))
        for recording_id, override in overrides.items():
            if recording_id not in records:
                raise ValueError(f"人工角色覆盖不存在于检查点: {recording_id}")
            original = records[recording_id]
            records[recording_id] = {
                **original,
                "customer_ch": override["customer_ch"],
                "agent_ch": override["agent_ch"],
                "confidence": "高(人工复核)",
                "prior_conflict": False,
                "needs_review": False,
                "manual_override": {
                    **override,
                    "original_customer_ch": original.get("customer_ch"),
                    "original_agent_ch": original.get("agent_ch"),
                    "original_confidence": original.get("confidence"),
                },
            }
    accepted = {
        recording_id: item
        for recording_id, item in records.items()
        if item.get("ok")
        and not item.get("needs_review", True)
        and item.get("customer_ch") in {"L", "R"}
    }
    return accepted, records, payload.get("failures", {}), overrides


def load_embedding_checkpoint(path):
    path = Path(path)
    if not path.exists():
        return {}
    data = np.load(path, allow_pickle=False)
    records = {}
    for idx, recording_id in enumerate(data["recording_ids"].tolist()):
        records[str(recording_id)] = {
            "recording_id": str(recording_id),
            "identity": str(data["identities"][idx]),
            "customer_ch": str(data["customer_channels"][idx]),
            "source": str(data["sources"][idx]),
            "audio": str(data["audio_paths"][idx]),
            "duration": float(data["durations"][idx]),
            "embedding": data["embeddings"][idx].astype(np.float32),
        }
    return records


def save_embedding_checkpoint(path, records):
    ordered = sorted(records.values(), key=lambda item: item["recording_id"])
    embeddings = (
        np.stack([item["embedding"] for item in ordered]).astype(np.float32)
        if ordered else np.empty((0, 192), dtype=np.float32)
    )
    _atomic_save_npz(
        path,
        recording_ids=np.asarray([item["recording_id"] for item in ordered]),
        identities=np.asarray([item["identity"] for item in ordered]),
        customer_channels=np.asarray([item["customer_ch"] for item in ordered]),
        sources=np.asarray([item["source"] for item in ordered]),
        audio_paths=np.asarray([item["audio"] for item in ordered]),
        durations=np.asarray([item["duration"] for item in ordered], dtype=np.float32),
        embeddings=embeddings,
    )


def _worker_init(torch_threads):
    import torch

    torch.set_num_threads(torch_threads)
    torch.set_num_interop_threads(torch_threads)
    embedding.get_model()


def _extract_embed_one(source_text, channel, audio_text, identity):
    import soundfile as sf

    source = Path(source_text)
    audio_path = Path(audio_text)
    recording_id = source.stem
    try:
        channel_index = 0 if channel == "L" else 1
        audio_io.extract_channel(
            str(source), channel_index, str(audio_path), dur=None, sr=16000)
        info = sf.info(audio_path)
        vector = embedding.embed(str(audio_path), disable_pbar=True)
        return {
            "ok": True,
            "record": {
                "recording_id": recording_id,
                "identity": identity,
                "customer_ch": channel,
                "source": source.name,
                "audio": str(audio_path.resolve()),
                "duration": float(info.duration),
                "embedding": vector,
            },
        }
    except Exception as exc:
        return {
            "ok": False,
            "failure": {
                "recording_id": recording_id,
                "source": source.name,
                "customer_ch": channel,
                "error": f"{type(exc).__name__}: {exc}",
            },
        }


def rebuild_embeddings(source_dir, audio_dir, output_dir, roles, identity_lookup,
                       workers=2, torch_threads=None, checkpoint_every=10):
    source_dir = Path(source_dir)
    audio_dir = Path(audio_dir)
    output_dir = Path(output_dir)
    audio_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / "customer_embeddings.npz"
    failures_path = output_dir / "customer_embedding_failures.json"
    records = load_embedding_checkpoint(checkpoint_path)
    failures = (
        json.loads(failures_path.read_text(encoding="utf-8"))
        if failures_path.exists() else {}
    )
    pending = [
        recording_id for recording_id in sorted(roles)
        if recording_id not in records
        or records[recording_id].get("customer_ch") != roles[recording_id]["customer_ch"]
    ]
    threads = torch_threads or max(1, (os.cpu_count() or workers) // workers)
    started = time.time()
    print(
        f"START accepted={len(roles)} cached={len(records)} pending={len(pending)} "
        f"workers={workers} threads={threads}", flush=True)

    with ProcessPoolExecutor(
            max_workers=workers, initializer=_worker_init,
            initargs=(threads,)) as executor:
        futures = {}
        for recording_id in pending:
            role = roles[recording_id]
            channel = role["customer_ch"]
            source = source_dir / f"{recording_id}.mp3"
            audio_path = audio_dir / f"{recording_id}_customer_{channel}.flac"
            futures[executor.submit(
                _extract_embed_one, str(source), channel, str(audio_path),
                identity_lookup[recording_id])
            ] = recording_id

        completed = 0
        for future in as_completed(futures):
            recording_id = futures[future]
            completed += 1
            try:
                result = future.result()
            except Exception as exc:
                result = {"ok": False, "failure": {
                    "recording_id": recording_id,
                    "error": f"WorkerError: {type(exc).__name__}: {exc}"}}
            if result["ok"]:
                item = result["record"]
                previous = records.get(recording_id)
                records[recording_id] = item
                failures.pop(recording_id, None)
                if previous and previous.get("audio") != item["audio"]:
                    previous_audio = Path(previous["audio"])
                    if previous_audio.is_file() and previous_audio.parent.resolve() == audio_dir.resolve():
                        previous_audio.unlink()
                print(
                    f"[{completed}/{len(pending)}] OK {recording_id} "
                    f"ch={item['customer_ch']} dur={item['duration']:.1f}s",
                    flush=True)
            else:
                failures[recording_id] = result["failure"]
                print(
                    f"[{completed}/{len(pending)}] FAIL {recording_id}: "
                    f"{result['failure'].get('error')}", flush=True)
            if completed % checkpoint_every == 0:
                save_embedding_checkpoint(checkpoint_path, records)
                _atomic_write_json(failures_path, failures)
                print(
                    f"CHECKPOINT records={len(records)} failures={len(failures)}",
                    flush=True)

    save_embedding_checkpoint(checkpoint_path, records)
    _atomic_write_json(failures_path, failures)
    return records, failures, time.time() - started


def _write_labels(path, ordered, roles):
    with Path(path).open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "matrix_index", "recording_id", "identity", "customer_ch",
            "confidence", "final_stage", "audio", "duration_sec",
        ])
        for index, item in enumerate(ordered):
            role = roles[item["recording_id"]]
            writer.writerow([
                index, item["recording_id"], item["identity"], item["customer_ch"],
                role["confidence"], role["final_stage"], item["audio"],
                f"{item['duration']:.3f}",
            ])


def build_matrix(records, roles, role_total, role_failures, embedding_failures,
                 output_dir, elapsed, manual_override_count=0):
    output_dir = Path(output_dir)
    ordered = sorted(records.values(), key=lambda item: item["recording_id"])
    recording_ids = np.asarray([item["recording_id"] for item in ordered])
    identities = np.asarray([item["identity"] for item in ordered])
    vectors = np.stack([item["embedding"] for item in ordered]).astype(np.float32)
    matrix = vectors @ vectors.T
    metrics = evaluate_matrix(matrix, identities)
    _atomic_save_npz(
        output_dir / "customer_nxn_matrix_rebuilt.npz",
        recording_ids=recording_ids,
        identities=identities,
        embeddings=vectors,
        matrix=matrix.astype(np.float32),
    )
    write_matrix_csv(
        output_dir / "customer_nxn_matrix_rebuilt.csv", matrix, recording_ids)
    _write_labels(output_dir / "customer_matrix_labels.csv", ordered, roles)
    (output_dir / "customer_metrics_rebuilt.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    def pct(value):
        return "-" if value is None else f"{value * 100:.2f}%"

    channel_counts = {channel: sum(item["customer_ch"] == channel for item in ordered)
                      for channel in ("L", "R")}
    lines = [
        "# 客户声道全量重刷与声纹矩阵报告",
        "",
        "> 使用修复后的ASR角色规则重新判角；仅高置信客户声道进入矩阵，embedding从拆出的完整客户FLAC重新提取。",
        "",
        "## 执行概况",
        "",
        f"- 角色检查点记录：{len(role_total)} 通",
        f"- 角色识别失败：{len(role_failures)} 通",
        f"- 高置信纳入：{len(roles)} 通",
        f"- 人工复核后角色纠正：{manual_override_count} 通",
        f"- 人工复核/未纳入：{len(role_total) - len(roles)} 通",
        f"- 客户声道：L={channel_counts['L']}，R={channel_counts['R']}",
        f"- 客户声道文件：{len(ordered)} 个完整16kHz单声道FLAC",
        f"- embedding失败：{len(embedding_failures)} 通",
        f"- 拆分与embedding耗时：{elapsed / 3600:.2f} 小时",
        "",
        "## 客户对客户矩阵",
        "",
        f"- 样本：{len(ordered)} 通，客户标识：{len(set(identities))} 个",
        f"- 同客户配对：{metrics['genuine_pairs']} 对",
        f"- 跨客户配对：{metrics['impostor_pairs']} 对",
        f"- EER：{pct(metrics['eer'])}",
        f"- EER阈值：{metrics['eer_threshold']:.3f}",
        f"- 同客户均值/5分位：{metrics['genuine_mean']:.3f} / {metrics['genuine_p05']:.3f}",
        f"- 跨客户均值/95分位：{metrics['impostor_mean']:.3f} / {metrics['impostor_p95']:.3f}",
        f"- TAR@0.751：{pct(metrics['tar_at_fixed'])}",
        f"- FAR@0.751：{pct(metrics['far_at_fixed'])}",
        f"- Top-1：{pct(metrics['top1_accuracy'])}",
        "",
        "## 口径",
        "",
        "- 中低置信和角色缺失样本不进入正式矩阵，保留在角色标签中等待人工复核。",
        "- 客户声道FLAC为完整录音声道，不是30秒或120秒ASR截取片段。",
        "- `0.751`仅保留为历史参考阈值；本批最终阈值应以人工声纹真值复标。",
    ]
    (output_dir / "客户声纹重刷报告.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    return metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source_dir")
    parser.add_argument("--roles", required=True)
    parser.add_argument("--role-overrides", default=None)
    parser.add_argument("--channel-embedding-path", required=True,
                        help="仅用于读取recording_id到identity映射，不复用其中向量")
    parser.add_argument("--audio-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--torch-threads", type=int, default=None)
    parser.add_argument("--checkpoint-every", type=int, default=10)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    accepted, role_total, role_failures, overrides = load_accepted_roles(
        args.roles, args.role_overrides)
    _atomic_write_json(
        output_dir / "resolved_customer_roles.json",
        {"records": role_total, "failures": role_failures,
         "manual_overrides": overrides},
    )
    channel_records = load_channel_embeddings(args.channel_embedding_path)
    identity_lookup = {
        recording_id: item["identity"]
        for recording_id, item in channel_records.items()
    }
    missing = sorted(set(accepted) - set(identity_lookup))
    if missing:
        raise SystemExit(f"缺少客户标识映射: {missing[:5]}")
    records, embedding_failures, elapsed = rebuild_embeddings(
        args.source_dir, args.audio_dir, output_dir, accepted, identity_lookup,
        workers=args.workers, torch_threads=args.torch_threads,
        checkpoint_every=args.checkpoint_every)
    runtime_path = output_dir / "customer_rebuild_runtime.json"
    runtime = (
        json.loads(runtime_path.read_text(encoding="utf-8"))
        if runtime_path.exists() else {"total_elapsed_sec": 0.0, "runs": []}
    )
    runtime["total_elapsed_sec"] = float(runtime.get("total_elapsed_sec", 0.0)) + elapsed
    runtime.setdefault("runs", []).append({
        "elapsed_sec": round(elapsed, 1),
        "records": len(records),
        "failures": len(embedding_failures),
    })
    _atomic_write_json(runtime_path, runtime)
    metrics = build_matrix(
        records, accepted, role_total, role_failures, embedding_failures,
        output_dir, runtime["total_elapsed_sec"],
        manual_override_count=len(overrides))
    print(
        f"DONE records={len(records)} failures={len(embedding_failures)} "
        f"EER={metrics['eer']:.4f} TOP1={metrics['top1_accuracy']:.4f}",
        flush=True)


if __name__ == "__main__":
    main()
