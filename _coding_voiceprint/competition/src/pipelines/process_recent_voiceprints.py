# -*- coding: utf-8 -*-
"""对已下载的近期双轨录音执行角色判断与客户侧CAM++ embedding。"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np


MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(MODULE_ROOT / "src" / "pipelines"))

from common import audio_io, embedding
from classify_roles_adaptive import (
    HIGH,
    ROLE_RULE_VERSION,
    _classify_stage,
    _worker_init as role_worker_init,
)


DEFAULT_INPUT = MODULE_ROOT / "data" / "recent_voiceprints_10k_20260819"


def _atomic_json(path: Path, payload: dict) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("status") == "success":
                rows.append(row)
    unique = {row["recording_id"]: row for row in rows}
    return [unique[key] for key in sorted(unique)]


def _classify_one_full(source_text: str, work_root_text: str) -> dict:
    """本批录音最长180秒，直接全长判角，避免30/120/全长重复解码。"""
    source = Path(source_text)
    recording_id = source.stem
    stages = []
    try:
        stage = _classify_stage(source, None, Path(work_root_text))
        stages.append(stage)
        final = stage["decision"]
        confidence = str(final.get("confidence", ""))
        return {
            "ok": final.get("customer_ch") in {"L", "R"},
            "recording_id": recording_id,
            "source": source.name,
            "customer_ch": final.get("customer_ch"),
            "agent_ch": final.get("agent_ch"),
            "confidence": confidence,
            "final_stage": "full",
            "stage_disagreement": False,
            "prior_conflict": False,
            "needs_review": confidence != HIGH or final.get("customer_ch") is None,
            "allow_full_asr": True,
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


def classify_roles(batch_dir: Path, workers: int, torch_threads: int | None,
                   checkpoint_every: int) -> tuple[dict, dict]:
    manifest = _read_jsonl(batch_dir / "download_manifest.jsonl")
    checkpoint_path = batch_dir / "adaptive_roles.json"
    signature = {
        "role_rule_version": ROLE_RULE_VERSION,
        "use_right_prior": False,
        "allow_full_asr": True,
        "role_mode": "single_full_asr_max_180s",
        "input_policy": "recent_6m_actual_20_180s_dual_track",
    }
    payload = {"meta": signature, "records": {}, "failures": {}}
    if checkpoint_path.exists():
        current = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if current.get("meta") == signature:
            payload = current
    records = payload.get("records", {})
    failures = payload.get("failures", {})
    pending = [row for row in manifest if row["recording_id"] not in records]
    work_root = MODULE_ROOT / "_temp" / "recent_voiceprints_10k_role_work"
    work_root.mkdir(parents=True, exist_ok=True)
    threads = torch_threads or max(1, (os.cpu_count() or workers) // workers)

    print(f"ROLE_START total={len(manifest)} cached={len(records)} pending={len(pending)}", flush=True)
    with ProcessPoolExecutor(
            max_workers=workers, initializer=role_worker_init,
            initargs=(threads,)) as executor:
        futures = {}
        for row in pending:
            source = batch_dir / row["file"]
            futures[executor.submit(
                _classify_one_full, str(source), str(work_root))] = row["recording_id"]
        completed = 0
        for future in as_completed(futures):
            recording_id = futures[future]
            completed += 1
            try:
                result = future.result()
            except Exception as exc:
                result = {"ok": False, "recording_id": recording_id,
                          "error": f"WorkerError: {type(exc).__name__}: {exc}"}
            if result.get("ok"):
                records[recording_id] = result
                failures.pop(recording_id, None)
            else:
                failures[recording_id] = result
            if completed % checkpoint_every == 0:
                _atomic_json(checkpoint_path, {
                    "meta": signature, "records": records, "failures": failures})
                print(f"ROLE_CHECKPOINT records={len(records)} failures={len(failures)}", flush=True)
    _atomic_json(checkpoint_path, {
        "meta": signature, "records": records, "failures": failures})
    return records, failures


def _embedding_worker_init(torch_threads: int) -> None:
    import torch
    torch.set_num_threads(torch_threads)
    torch.set_num_interop_threads(torch_threads)
    embedding.get_model()


def _embed_one(source_text: str, recording_id: str, customer_ch: str,
               temp_root_text: str) -> dict:
    source = Path(source_text)
    try:
        with tempfile.TemporaryDirectory(prefix="embed_", dir=temp_root_text) as temp_dir:
            wav = Path(temp_dir) / f"{recording_id}_{customer_ch}.wav"
            channel = 0 if customer_ch == "L" else 1
            audio_io.extract_channel(str(source), channel, str(wav), dur=None, sr=16000)
            vector = embedding.embed(str(wav), disable_pbar=True)
        return {"ok": True, "recording_id": recording_id,
                "embedding": vector.astype(np.float32)}
    except Exception as exc:
        return {"ok": False, "recording_id": recording_id,
                "error": f"{type(exc).__name__}: {exc}"}


def _aggregate_embeddings(batch_dir: Path, manifest: list[dict], roles: dict) -> int:
    shard_dir = batch_dir / "embedding_shards"
    rows = []
    vectors = []
    manifest_map = {row["recording_id"]: row for row in manifest}
    for path in sorted(shard_dir.glob("*.npy")):
        recording_id = path.stem
        role = roles.get(recording_id)
        source = manifest_map.get(recording_id)
        if not role or not source:
            continue
        vector = np.load(path, allow_pickle=False).astype(np.float32)
        if vector.shape != (192,) or not np.isfinite(vector).all():
            continue
        rows.append((recording_id, role, source))
        vectors.append(vector)
    target = batch_dir / "customer_embeddings.npz"
    temp = batch_dir / "customer_embeddings.npz.tmp"
    with temp.open("wb") as handle:
        np.savez_compressed(
            handle,
            recording_ids=np.asarray([row[0] for row in rows]),
            customer_channels=np.asarray([row[1]["customer_ch"] for row in rows]),
            confidences=np.asarray([row[1].get("confidence", "") for row in rows]),
            needs_review=np.asarray([row[1].get("confidence") != HIGH for row in rows]),
            actual_durations=np.asarray([row[2]["actual_duration"] for row in rows], dtype=np.float32),
            identity_sha256=np.asarray([row[2].get("identity_sha256") or "" for row in rows]),
            embeddings=np.stack(vectors) if vectors else np.empty((0, 192), np.float32),
        )
    os.replace(temp, target)
    return len(rows)


def extract_embeddings(batch_dir: Path, roles: dict, workers: int,
                       torch_threads: int | None, checkpoint_every: int) -> tuple[int, dict]:
    manifest = _read_jsonl(batch_dir / "download_manifest.jsonl")
    shard_dir = batch_dir / "embedding_shards"
    shard_dir.mkdir(exist_ok=True)
    failures_path = batch_dir / "embedding_failures.json"
    failures = json.loads(failures_path.read_text(encoding="utf-8")) if failures_path.exists() else {}
    eligible = [row for row in manifest
                if roles.get(row["recording_id"], {}).get("customer_ch") in {"L", "R"}]
    pending = [row for row in eligible
               if not (shard_dir / f"{row['recording_id']}.npy").exists()]
    temp_root = MODULE_ROOT / "_temp" / "recent_voiceprints_10k_embedding_work"
    temp_root.mkdir(parents=True, exist_ok=True)
    threads = torch_threads or max(1, (os.cpu_count() or workers) // workers)

    print(f"EMBED_START eligible={len(eligible)} cached={len(eligible)-len(pending)} pending={len(pending)}", flush=True)
    with ProcessPoolExecutor(
            max_workers=workers, initializer=_embedding_worker_init,
            initargs=(threads,)) as executor:
        futures = {}
        for row in pending:
            recording_id = row["recording_id"]
            role = roles[recording_id]
            source = batch_dir / row["file"]
            futures[executor.submit(
                _embed_one, str(source), recording_id,
                role["customer_ch"], str(temp_root))] = recording_id
        completed = 0
        for future in as_completed(futures):
            recording_id = futures[future]
            completed += 1
            try:
                result = future.result()
            except Exception as exc:
                result = {"ok": False, "recording_id": recording_id,
                          "error": f"WorkerError: {type(exc).__name__}: {exc}"}
            if result.get("ok"):
                target = shard_dir / f"{recording_id}.npy"
                temp = shard_dir / f"{recording_id}.npy.tmp"
                with temp.open("wb") as handle:
                    np.save(handle, result["embedding"], allow_pickle=False)
                os.replace(temp, target)
                failures.pop(recording_id, None)
            else:
                failures[recording_id] = result
            if completed % checkpoint_every == 0:
                _atomic_json(failures_path, failures)
                print(f"EMBED_CHECKPOINT completed={completed}/{len(pending)} failures={len(failures)}", flush=True)
    _atomic_json(failures_path, failures)
    count = _aggregate_embeddings(batch_dir, manifest, roles)
    return count, failures


def write_summary(batch_dir: Path, roles: dict, role_failures: dict,
                  embedding_count: int, embedding_failures: dict,
                  elapsed: float) -> dict:
    high = sum(item.get("confidence") == HIGH for item in roles.values())
    review = len(roles) - high
    summary = {
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "role_records": len(roles),
        "role_high_confidence": high,
        "role_needs_review": review,
        "role_failures": len(role_failures),
        "embedding_records": embedding_count,
        "embedding_failures": len(embedding_failures),
        "embedding_dimension": 192,
        "model": "CAM++",
        "elapsed_seconds_this_run": round(elapsed, 1),
        "privacy": "不保存ASR转写正文；embedding产物不包含原始URL、客户号或源记录ID。",
    }
    _atomic_json(batch_dir / "processing_summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--role-workers", type=int, default=4)
    parser.add_argument("--embedding-workers", type=int, default=2)
    parser.add_argument("--torch-threads", type=int, default=None)
    parser.add_argument("--checkpoint-every", type=int, default=50)
    args = parser.parse_args()
    started = time.time()
    roles, role_failures = classify_roles(
        args.batch_dir, args.role_workers, args.torch_threads, args.checkpoint_every)
    count, embedding_failures = extract_embeddings(
        args.batch_dir, roles, args.embedding_workers,
        args.torch_threads, args.checkpoint_every)
    summary = write_summary(
        args.batch_dir, roles, role_failures,
        count, embedding_failures, time.time() - started)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
