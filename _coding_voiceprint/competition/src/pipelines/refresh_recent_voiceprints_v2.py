# -*- coding: utf-8 -*-
"""使用新文本角色模型重刷近期录音客户侧 CAM++ embedding。

本脚本只写入独立 v2 输出目录，不覆盖旧 `adaptive_roles.json` 或
`customer_embeddings.npz`。角色结果不保存完整 ASR 文本。
"""
from __future__ import annotations

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


MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from common import asr_role, audio_io, embedding, text_role


DEFAULT_INPUT = MODULE_ROOT / "data" / "recent_voiceprints_10k_20260819"
DEFAULT_OUTPUT = MODULE_ROOT / "data" / "recent_voiceprints_10k_role_text_v2"
ROLE_MODEL_VERSION = "role-text-v1-20260820"
ROLE_RULE_VERSION = "2026-08-20-text-v1"
EMBEDDING_MODEL = "CAM++"
EMBEDDING_MODEL_VERSION = "campp_funasr_ms"
EMBEDDING_DIMENSION = 192
ROLE_THRESHOLD = 0.817575
HIGH = "高"


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def read_manifest(batch_dir: Path) -> list[dict]:
    rows = []
    path = batch_dir / "download_manifest.jsonl"
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


def select_manifest_rows(rows: list[dict], recording_ids: set[str] | None,
                         limit: int | None) -> list[dict]:
    selected = [row for row in rows if recording_ids is None or row["recording_id"] in recording_ids]
    return selected[:limit] if limit is not None else selected


def role_confidence(status: str) -> str:
    return {
        "identified": HIGH,
        "needs_review": "低(话术差值不足)",
        "one_sided": "缺一方",
        "no_effective_dialogue": "无有效对话",
    }.get(status, "低(需复核)")


def quality_status(status: str) -> str:
    return {
        "identified": "valid_dialogue",
        "needs_review": "valid_dialogue",
        "one_sided": "one_sided",
        "no_effective_dialogue": "no_effective_dialogue",
    }.get(status, "unknown")


def embedding_cache_key(recording_id: str, customer_channel: str,
                        model_version: str = EMBEDDING_MODEL_VERSION) -> str:
    if customer_channel not in {"L", "R"}:
        raise ValueError("customer_channel must be L or R")
    return f"{recording_id}__{customer_channel}__{model_version}"


def validate_embedding(vector: np.ndarray) -> bool:
    if not isinstance(vector, np.ndarray):
        return False
    if vector.shape != (EMBEDDING_DIMENSION,):
        return False
    if not np.isfinite(vector).all():
        return False
    norm = float(np.linalg.norm(vector))
    return 0.98 <= norm <= 1.02


def formal_index_eligible(role: dict, identity_sha256: str | None) -> bool:
    return (
        bool(identity_sha256)
        and role.get("quality_status") == "valid_dialogue"
        and role.get("status") == "identified"
        and role.get("customer_ch") in {"L", "R"}
        and role.get("agent_ch") in {"L", "R"}
        and float(role.get("margin") or 0.0) >= float(role.get("threshold") or ROLE_THRESHOLD)
        and not bool(role.get("needs_review"))
    )


def _worker_init(torch_threads: int, load_embedding: bool) -> None:
    import torch

    torch.set_num_threads(torch_threads)
    torch.set_num_interop_threads(torch_threads)
    asr_role.get_model()
    text_role.load_model()
    if load_embedding:
        embedding.get_model()


def _classify_one(source_text: str, manifest_row: dict, work_root_text: str) -> dict:
    source = Path(source_text)
    recording_id = manifest_row["recording_id"]
    try:
        with tempfile.TemporaryDirectory(prefix="role_text_v2_", dir=work_root_text) as temp_dir:
            temp_path = Path(temp_dir)
            features = {}
            summaries = {}
            for index, channel in ((0, "L"), (1, "R")):
                wav = temp_path / f"{recording_id}_{channel}.wav"
                audio_io.extract_channel(str(source), index, str(wav), dur=None, sr=16000)
                channel_features = asr_role.transcribe_role_features(str(wav))
                features[channel] = channel_features
                summaries[channel] = channel_features.get("summary", {})

        decision = text_role.classify_features(features["L"], features["R"])
        status = decision.get("status")
        role = {
            "ok": True,
            "recording_id": recording_id,
            "source": source.name,
            "identity_sha256": manifest_row.get("identity_sha256") or "",
            "actual_duration": manifest_row.get("actual_duration"),
            "audio_sha256": manifest_row.get("audio_sha256") or manifest_row.get("file_sha256"),
            "status": status,
            "quality_status": quality_status(str(status)),
            "confidence": role_confidence(str(status)),
            "agent_ch": decision.get("agent_ch"),
            "customer_ch": decision.get("customer_ch"),
            "candidate_agent_ch": decision.get("candidate_agent_ch"),
            "candidate_customer_ch": decision.get("candidate_customer_ch"),
            "needs_review": bool(decision.get("needs_review", True)),
            "left_agent_probability": decision.get("left_agent_probability"),
            "right_agent_probability": decision.get("right_agent_probability"),
            "margin": decision.get("margin"),
            "threshold": decision.get("threshold", ROLE_THRESHOLD),
            "left_summary": summaries["L"],
            "right_summary": summaries["R"],
            "role_model_version": ROLE_MODEL_VERSION,
            "role_rule_version": ROLE_RULE_VERSION,
            "model_input": "asr_text_only",
        }
        role["formal_index_eligible"] = formal_index_eligible(
            role, role.get("identity_sha256"))
        return role
    except Exception as exc:
        return {
            "ok": False,
            "recording_id": recording_id,
            "source": source.name,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _embedding_worker_init(torch_threads: int) -> None:
    import torch

    torch.set_num_threads(torch_threads)
    torch.set_num_interop_threads(torch_threads)
    embedding.get_model()


def _embed_one(source_text: str, recording_id: str, customer_ch: str,
               temp_root_text: str) -> dict:
    source = Path(source_text)
    try:
        with tempfile.TemporaryDirectory(prefix="embed_v2_", dir=temp_root_text) as temp_dir:
            wav = Path(temp_dir) / f"{recording_id}_{customer_ch}.wav"
            audio_io.extract_channel(
                str(source), 0 if customer_ch == "L" else 1, str(wav), dur=None, sr=16000)
            vector = embedding.embed(str(wav), disable_pbar=True).astype(np.float32)
        if not validate_embedding(vector):
            raise ValueError("embedding维度、有限值或归一化校验失败")
        return {
            "ok": True,
            "recording_id": recording_id,
            "customer_ch": customer_ch,
            "embedding": vector,
        }
    except Exception as exc:
        return {
            "ok": False,
            "recording_id": recording_id,
            "customer_ch": customer_ch,
            "error": f"{type(exc).__name__}: {exc}",
        }


def classify_roles(batch_dir: Path, output_dir: Path, rows: list[dict],
                   workers: int, torch_threads: int | None,
                   checkpoint_every: int, retry_failures: bool = False) -> tuple[dict, dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    role_path = output_dir / "role_results.json"
    failure_path = output_dir / "role_failures.json"
    payload = read_json(role_path, {
        "meta": {
            "role_model_version": ROLE_MODEL_VERSION,
            "role_rule_version": ROLE_RULE_VERSION,
            "threshold": ROLE_THRESHOLD,
            "model_input": "asr_text_only",
        },
        "records": {},
    })
    failures_payload = read_json(failure_path, {"failures": {}})
    records = payload.get("records", {})
    failures = failures_payload.get("failures", {})
    if retry_failures:
        failures = {}

    pending = [
        row for row in rows
        if row["recording_id"] not in records and row["recording_id"] not in failures
    ]
    if not pending:
        return records, failures

    work_root = MODULE_ROOT / "_temp" / "role_text_v2_work"
    work_root.mkdir(parents=True, exist_ok=True)
    threads = torch_threads or max(1, (os.cpu_count() or workers) // workers)
    print(
        f"ROLE_V2_START total={len(rows)} cached={len(records)} "
        f"failures={len(failures)} pending={len(pending)}",
        flush=True,
    )
    with ProcessPoolExecutor(
        max_workers=workers,
        initializer=_worker_init,
        initargs=(threads, False),
    ) as executor:
        futures = {}
        for row in pending:
            source = batch_dir / row["file"]
            futures[executor.submit(
                _classify_one, str(source), row, str(work_root))] = row["recording_id"]
        for completed, future in enumerate(as_completed(futures), 1):
            recording_id = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {
                    "ok": False,
                    "recording_id": recording_id,
                    "error": f"WorkerError: {type(exc).__name__}: {exc}",
                }
            if result.get("ok"):
                records[recording_id] = result
                failures.pop(recording_id, None)
            else:
                failures[recording_id] = result
            if completed % checkpoint_every == 0:
                payload["records"] = records
                atomic_write_json(role_path, payload)
                atomic_write_json(failure_path, {"failures": failures})
                print(
                    f"ROLE_V2_CHECKPOINT records={len(records)} failures={len(failures)}",
                    flush=True,
                )

    payload["records"] = records
    atomic_write_json(role_path, payload)
    atomic_write_json(failure_path, {"failures": failures})
    return records, failures


def extract_embeddings(batch_dir: Path, output_dir: Path, rows: list[dict],
                       roles: dict, workers: int, torch_threads: int | None,
                       checkpoint_every: int) -> dict:
    shard_dir = output_dir / "embedding_shards"
    shard_dir.mkdir(parents=True, exist_ok=True)
    failures_path = output_dir / "embedding_failures.json"
    failures = read_json(failures_path, {"failures": {}}).get("failures", {})
    row_map = {row["recording_id"]: row for row in rows}
    eligible = [
        role for role in roles.values()
        if role.get("formal_index_eligible") and role.get("customer_ch") in {"L", "R"}
    ]
    pending = []
    for role in eligible:
        cache_key = embedding_cache_key(role["recording_id"], role["customer_ch"])
        shard_path = shard_dir / f"{cache_key}.npy"
        if not shard_path.exists() and role["recording_id"] not in failures:
            pending.append(role)

    if pending:
        temp_root = MODULE_ROOT / "_temp" / "role_text_v2_embedding_work"
        temp_root.mkdir(parents=True, exist_ok=True)
        threads = torch_threads or max(1, (os.cpu_count() or workers) // workers)
        print(
            f"EMBED_V2_START eligible={len(eligible)} cached={len(eligible)-len(pending)} "
            f"failures={len(failures)} pending={len(pending)}",
            flush=True,
        )
        with ProcessPoolExecutor(
            max_workers=workers,
            initializer=_embedding_worker_init,
            initargs=(threads,),
        ) as executor:
            futures = {}
            for role in pending:
                row = row_map[role["recording_id"]]
                source = batch_dir / row["file"]
                futures[executor.submit(
                    _embed_one,
                    str(source),
                    role["recording_id"],
                    role["customer_ch"],
                    str(temp_root),
                )] = role["recording_id"]
            for completed, future in enumerate(as_completed(futures), 1):
                recording_id = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = {
                        "ok": False,
                        "recording_id": recording_id,
                        "error": f"WorkerError: {type(exc).__name__}: {exc}",
                    }
                if result.get("ok"):
                    cache_key = embedding_cache_key(recording_id, result["customer_ch"])
                    temp = shard_dir / f"{cache_key}.npy.tmp"
                    target = shard_dir / f"{cache_key}.npy"
                    with temp.open("wb") as handle:
                        np.save(handle, result["embedding"], allow_pickle=False)
                    os.replace(temp, target)
                    failures.pop(recording_id, None)
                else:
                    failures[recording_id] = result
                if completed % checkpoint_every == 0:
                    atomic_write_json(failures_path, {"failures": failures})
                    print(
                        f"EMBED_V2_CHECKPOINT completed={completed}/{len(pending)} "
                        f"failures={len(failures)}",
                        flush=True,
                    )

    atomic_write_json(failures_path, {"failures": failures})
    return failures


def aggregate_embeddings(output_dir: Path, rows: list[dict], roles: dict) -> int:
    shard_dir = output_dir / "embedding_shards"
    row_map = {row["recording_id"]: row for row in rows}
    records = []
    vectors = []
    for recording_id in sorted(roles):
        role = roles[recording_id]
        if not role.get("formal_index_eligible"):
            continue
        customer_ch = role.get("customer_ch")
        if customer_ch not in {"L", "R"}:
            continue
        cache_key = embedding_cache_key(recording_id, customer_ch)
        shard_path = shard_dir / f"{cache_key}.npy"
        if not shard_path.exists():
            continue
        vector = np.load(shard_path, allow_pickle=False).astype(np.float32)
        if not validate_embedding(vector):
            continue
        row = row_map.get(recording_id, {})
        records.append({
            "recording_id": recording_id,
            "identity_sha256": role.get("identity_sha256") or row.get("identity_sha256") or "",
            "customer_channel": customer_ch,
            "confidence": role.get("confidence", ""),
            "status": role.get("status", ""),
            "quality_status": role.get("quality_status", ""),
            "margin": float(role.get("margin") or 0.0),
            "threshold": float(role.get("threshold") or ROLE_THRESHOLD),
            "actual_duration": float(row.get("actual_duration") or role.get("actual_duration") or 0.0),
            "cache_key": cache_key,
        })
        vectors.append(vector)
    target = output_dir / "customer_embeddings_v2.npz"
    temp = output_dir / "customer_embeddings_v2.npz.tmp"
    with temp.open("wb") as handle:
        np.savez_compressed(
            handle,
            recording_ids=np.asarray([item["recording_id"] for item in records]),
            identity_sha256=np.asarray([item["identity_sha256"] for item in records]),
            customer_channels=np.asarray([item["customer_channel"] for item in records]),
            confidences=np.asarray([item["confidence"] for item in records]),
            statuses=np.asarray([item["status"] for item in records]),
            quality_statuses=np.asarray([item["quality_status"] for item in records]),
            margins=np.asarray([item["margin"] for item in records], dtype=np.float32),
            thresholds=np.asarray([item["threshold"] for item in records], dtype=np.float32),
            actual_durations=np.asarray([item["actual_duration"] for item in records], dtype=np.float32),
            cache_keys=np.asarray([item["cache_key"] for item in records]),
            embeddings=np.stack(vectors).astype(np.float32) if vectors else np.empty((0, EMBEDDING_DIMENSION), np.float32),
        )
    os.replace(temp, target)
    return len(records)


def write_summary(output_dir: Path, manifest_rows: list[dict], selected_rows: list[dict],
                  roles: dict, role_failures: dict, embedding_count: int,
                  embedding_failures: dict, elapsed: float) -> dict:
    status_counts = Counter(role.get("status", "unknown") for role in roles.values())
    quality_counts = Counter(role.get("quality_status", "unknown") for role in roles.values())
    channel_counts = Counter(role.get("customer_ch") for role in roles.values())
    formal_count = sum(1 for role in roles.values() if role.get("formal_index_eligible"))
    summary = {
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source_batch": str(DEFAULT_INPUT.name),
        "total_manifest_success": len(manifest_rows),
        "selected_records": len(selected_rows),
        "role_records": len(roles),
        "role_failures": len(role_failures),
        "status_counts": dict(status_counts),
        "quality_counts": dict(quality_counts),
        "customer_channel_counts": {str(k): v for k, v in channel_counts.items()},
        "formal_eligible_records": formal_count,
        "embedding_records": embedding_count,
        "embedding_failures": len(embedding_failures),
        "role_model_version": ROLE_MODEL_VERSION,
        "role_rule_version": ROLE_RULE_VERSION,
        "role_threshold": ROLE_THRESHOLD,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_model_version": EMBEDDING_MODEL_VERSION,
        "embedding_dimension": EMBEDDING_DIMENSION,
        "elapsed_seconds_this_run": round(elapsed, 1),
        "privacy": "不保存完整ASR正文、原始URL、客户号或源记录ID；仅保存SHA-256和数值摘要。",
    }
    atomic_write_json(output_dir / "processing_summary.json", summary)
    return summary


def parse_recording_ids(values: list[str]) -> set[str] | None:
    if not values:
        return None
    ids = set()
    for value in values:
        path = Path(value)
        if path.exists():
            ids.update(
                line.strip() for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
        else:
            ids.add(value.strip())
    return ids


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--recording-id", action="append", default=[],
                        help="只处理指定录音ID；可重复传入，也可传入包含ID的文本文件路径")
    parser.add_argument("--role-workers", type=int, default=2)
    parser.add_argument("--embedding-workers", type=int, default=1)
    parser.add_argument("--torch-threads", type=int, default=None)
    parser.add_argument("--checkpoint-every", type=int, default=50)
    parser.add_argument("--retry-failures", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    started = time.time()
    manifest_rows = read_manifest(args.batch_dir)
    selected_rows = select_manifest_rows(
        manifest_rows, parse_recording_ids(args.recording_id), args.limit)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    roles, role_failures = classify_roles(
        args.batch_dir,
        args.output_dir,
        selected_rows,
        args.role_workers,
        args.torch_threads,
        args.checkpoint_every,
        retry_failures=args.retry_failures,
    )
    embedding_failures = extract_embeddings(
        args.batch_dir,
        args.output_dir,
        selected_rows,
        roles,
        args.embedding_workers,
        args.torch_threads,
        args.checkpoint_every,
    )
    embedding_count = aggregate_embeddings(args.output_dir, selected_rows, roles)
    summary = write_summary(
        args.output_dir,
        manifest_rows,
        selected_rows,
        roles,
        role_failures,
        embedding_count,
        embedding_failures,
        time.time() - started,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
