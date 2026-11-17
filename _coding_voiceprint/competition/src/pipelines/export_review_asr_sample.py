# -*- coding: utf-8 -*-
"""分层抽取中低置信录音，分别保存左右声道的全长ASR JSON。"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np


MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from common import asr_role, audio_io  # noqa: E402


DEFAULT_BATCH = (
    MODULE_ROOT / "data" / "processed" / "recent_voiceprints_10k_20260819"
)
DEFAULT_QUEUE = (
    MODULE_ROOT / "reports" / "recent_voiceprints_role_audit_20260820"
    / "role_review_queue.csv"
)
DEFAULT_OUTPUT = MODULE_ROOT / "_temp" / "review_asr_sample_20260820"


def _atomic_json(path: Path, payload: dict) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    os.replace(temp, path)


def _json_default(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return str(value)


def load_direction_conflicts(queue_path: Path) -> dict[str, dict]:
    with queue_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {
            row["recording_id"]: row
            for row in csv.DictReader(handle)
            if row.get("confidence_tier") != "failure"
        }


def select_samples(role_path: Path, queue_path: Path,
                   middle_count: int, low_count: int) -> list[dict]:
    payload = json.loads(role_path.read_text(encoding="utf-8"))
    roles = payload.get("records", {})
    conflicts = load_direction_conflicts(queue_path)
    buckets = {"中置信": [], "低置信": []}
    for recording_id, role in roles.items():
        confidence = str(role.get("confidence", ""))
        if not role.get("needs_review") or recording_id not in conflicts:
            continue
        group = "中置信" if confidence.startswith("中") else (
            "低置信" if confidence.startswith("低") else None)
        if group is None:
            continue
        audit = conflicts[recording_id]
        buckets[group].append({
            "recording_id": recording_id,
            "sample_group": group,
            "confidence": confidence,
            "predicted_customer_ch": role.get("customer_ch"),
            "predicted_agent_ch": role.get("agent_ch"),
            "direction": audit.get("direction"),
            "direction_expected_customer_ch": audit.get(
                "direction_expected_channel"),
            "selection_reason": "中低置信且与呼叫方向声道规律冲突",
        })
    for rows in buckets.values():
        rows.sort(key=lambda row: row["recording_id"])
    if len(buckets["中置信"]) < middle_count:
        raise ValueError("中置信方向冲突样本不足")
    if len(buckets["低置信"]) < low_count:
        raise ValueError("低置信方向冲突样本不足")
    return buckets["中置信"][:middle_count] + buckets["低置信"][:low_count]


def _normalize_asr_result(result) -> dict:
    record = result[0] if isinstance(result, list) and result else result
    record = record if isinstance(record, dict) else {}
    allowed = {
        "text": str(record.get("text", "")).strip(),
        "sentence_info": record.get("sentence_info") or [],
        "timestamp": record.get("timestamp") or [],
    }
    return allowed


def export_sample(batch_dir: Path, queue_path: Path, output_dir: Path,
                  middle_count: int = 5, low_count: int = 5) -> dict:
    samples = select_samples(
        batch_dir / "adaptive_roles.json", queue_path,
        middle_count, low_count)
    json_dir = output_dir / "json"
    json_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / "sample_manifest.json"
    checkpoint = {
        "policy": {
            "middle_count": middle_count,
            "low_count": low_count,
            "full_audio": True,
            "channels": ["L", "R"],
            "selection": "优先抽取中低置信且与呼叫方向声道规律冲突的样本",
            "privacy": "不保存客户号、手机号、原始URL或源记录ID。ASR文本仅用于人工复核。",
        },
        "samples": samples,
        "records": {},
        "failures": {},
    }
    if checkpoint_path.exists():
        existing = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if existing.get("policy") == checkpoint["policy"]:
            checkpoint["records"] = existing.get("records", {})
            checkpoint["failures"] = existing.get("failures", {})

    model = asr_role.get_model()
    total = len(samples) * 2
    completed = 0
    with tempfile.TemporaryDirectory(
            prefix="review_asr_", dir=str(MODULE_ROOT / "_temp")) as work_dir:
        for sample in samples:
            recording_id = sample["recording_id"]
            source = batch_dir / "audio" / f"{recording_id}.mp3"
            if not source.is_file():
                raise FileNotFoundError(source)
            for channel_index, channel in ((0, "L"), (1, "R")):
                completed += 1
                key = f"{recording_id}_{channel}"
                target = json_dir / f"{key}.json"
                if key in checkpoint["records"] and target.is_file():
                    print(f"[{completed}/{total}] CACHE {key}", flush=True)
                    continue
                wav = Path(work_dir) / f"{key}.wav"
                try:
                    audio_io.extract_channel(
                        str(source), channel_index, str(wav), dur=None, sr=16000)
                    result = model.generate(
                        input=str(wav), batch_size_s=300,
                        disable_pbar=True, sentence_timestamp=True)
                    asr = _normalize_asr_result(result)
                    summary = asr_role.summarize_result(result)
                    output = {
                        "recording_id": recording_id,
                        "channel": channel,
                        "sample_group": sample["sample_group"],
                        "existing_role": {
                            "confidence": sample["confidence"],
                            "predicted_customer_ch": sample[
                                "predicted_customer_ch"],
                            "predicted_agent_ch": sample[
                                "predicted_agent_ch"],
                            "direction": sample["direction"],
                            "direction_expected_customer_ch": sample[
                                "direction_expected_customer_ch"],
                        },
                        "asr": asr,
                        "summary": summary,
                    }
                    _atomic_json(target, output)
                    checkpoint["records"][key] = {
                        "file": str(Path("json") / target.name),
                        "char_count": summary["char_count"],
                        "sentence_count": len(asr["sentence_info"]),
                    }
                    checkpoint["failures"].pop(key, None)
                    print(
                        f"[{completed}/{total}] OK {key} "
                        f"chars={summary['char_count']} "
                        f"sentences={len(asr['sentence_info'])}",
                        flush=True,
                    )
                except Exception as exc:
                    checkpoint["failures"][key] = {
                        "error": f"{type(exc).__name__}: {exc}"
                    }
                    print(f"[{completed}/{total}] FAIL {key}: {exc}", flush=True)
                finally:
                    wav.unlink(missing_ok=True)
                _atomic_json(checkpoint_path, checkpoint)
    _atomic_json(checkpoint_path, checkpoint)
    return checkpoint


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-dir", type=Path, default=DEFAULT_BATCH)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--middle-count", type=int, default=5)
    parser.add_argument("--low-count", type=int, default=5)
    args = parser.parse_args()
    result = export_sample(
        args.batch_dir, args.queue, args.output_dir,
        args.middle_count, args.low_count)
    print(json.dumps({
        "output_dir": str(args.output_dir),
        "samples": len(result["samples"]),
        "json_files": len(result["records"]),
        "failures": len(result["failures"]),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
