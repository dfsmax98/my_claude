# -*- coding: utf-8 -*-
"""构建客服/客户角色文本语料；只在_temp保存完整ASR文本。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from common import asr_role, audio_io  # noqa: E402


DEFAULT_BATCH = MODULE_ROOT / "data" / "recent_voiceprints_10k_20260819"
DEFAULT_OUTPUT = MODULE_ROOT / "_temp" / "role_text_corpus_20260820"
MIN_CHARS = 20
MIN_SPEECH_SECONDS = 5.0
DEFAULT_TARGET = 4000
SEED = "role-corpus-20260820"


def _atomic_json(path: Path, payload: dict) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def _manifest(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _summary_pair(item: dict) -> tuple[dict, dict]:
    stage = (item.get("stages") or [{}])[-1]
    return stage.get("left") or {}, stage.get("right") or {}


def channel_valid(summary: dict) -> bool:
    return (
        int(summary.get("char_count") or 0) >= MIN_CHARS
        and float(summary.get("speech_duration") or 0.0) >= MIN_SPEECH_SECONDS
    )


def quality_class(item: dict) -> str:
    left, right = _summary_pair(item)
    valid_left = channel_valid(left)
    valid_right = channel_valid(right)
    if valid_left and valid_right:
        return "valid_dialogue"
    if valid_left or valid_right:
        return "one_sided"
    return "no_effective_dialogue"


def select_corpus(batch_dir: Path, target: int) -> tuple[list[dict], dict]:
    from audit_recent_role_accuracy import load_directions

    role_payload = json.loads(
        (batch_dir / "adaptive_roles.json").read_text(encoding="utf-8"))
    all_roles = {**role_payload.get("records", {}), **role_payload.get("failures", {})}
    manifest = _manifest(batch_dir / "download_manifest.jsonl")
    manifest_map = {row["recording_id"]: row for row in manifest}
    directions, engine, sql = load_directions(manifest)

    quality_counts = {"valid_dialogue": 0, "one_sided": 0,
                      "no_effective_dialogue": 0}
    valid = []
    for recording_id, item in all_roles.items():
        quality = quality_class(item)
        quality_counts[quality] += 1
        direction = directions.get(recording_id)
        if quality != "valid_dialogue" or direction not in {"I", "O"}:
            continue
        source = manifest_map[recording_id]
        valid.append({
            "recording_id": recording_id,
            "direction": direction,
            "identity_sha256": source.get("identity_sha256") or "",
            "source_file": source["file"],
            "quality": quality,
        })

    outbound = sorted(
        (row for row in valid if row["direction"] == "O"),
        key=lambda row: row["recording_id"],
    )
    inbound = sorted(
        (row for row in valid if row["direction"] == "I"),
        key=lambda row: hashlib.sha256(
            f"{SEED}:{row['recording_id']}".encode("utf-8")).hexdigest(),
    )
    if len(outbound) >= target:
        selected = outbound[:target]
    else:
        selected = outbound + inbound[:target - len(outbound)]
    selected.sort(key=lambda row: row["recording_id"])
    summary = {
        "quality_rule": {
            "min_chars_per_channel": MIN_CHARS,
            "min_speech_seconds_per_channel": MIN_SPEECH_SECONDS,
        },
        "quality_counts": quality_counts,
        "valid_with_direction": len(valid),
        "target": target,
        "selected": len(selected),
        "selected_direction": {
            "I": sum(row["direction"] == "I" for row in selected),
            "O": sum(row["direction"] == "O" for row in selected),
        },
        "selection": "纳入全部有效呼出样本，再以固定随机种子补充呼入样本。",
        "label_rule": {
            "I": {"agent": "L", "customer": "R"},
            "O": {"agent": "R", "customer": "L"},
        },
        "leakage_control": "direction只用于构建代理标签，不写入模型输入特征。",
        "database": {"engine": engine, "executed_sql": sql},
    }
    return selected, summary


def prepare_selection(batch_dir: Path, output_dir: Path, target: int) -> dict:
    selected, summary = select_corpus(batch_dir, target)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {"summary": summary, "selected": selected}
    _atomic_json(output_dir / "corpus_selection.json", payload)
    return payload


def _worker_init(torch_threads: int) -> None:
    import torch
    torch.set_num_threads(torch_threads)
    torch.set_num_interop_threads(torch_threads)
    asr_role.get_model()


def _normalize_result(result) -> dict:
    record = result[0] if isinstance(result, list) and result else result
    record = record if isinstance(record, dict) else {}
    return {
        "text": str(record.get("text", "")).strip(),
        "summary": asr_role.summarize_result(result),
    }


def _extract_one(source_text: str, work_root_text: str) -> dict:
    source = Path(source_text)
    try:
        with tempfile.TemporaryDirectory(
                prefix="role_corpus_", dir=work_root_text) as temp_dir:
            outputs = {}
            for index, channel in ((0, "L"), (1, "R")):
                wav = Path(temp_dir) / f"{channel}.wav"
                audio_io.extract_channel(
                    str(source), index, str(wav), dur=None, sr=16000)
                result = asr_role.get_model().generate(
                    input=str(wav), batch_size_s=300,
                    disable_pbar=True, sentence_timestamp=True)
                outputs[channel] = _normalize_result(result)
        return {"ok": True, "channels": outputs}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def build_corpus(batch_dir: Path, output_dir: Path, target: int,
                 workers: int, torch_threads: int, checkpoint_every: int) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    selection_path = output_dir / "corpus_selection.json"
    if not selection_path.exists():
        raise FileNotFoundError(
            "缺少corpus_selection.json，请先用数据库环境执行--prepare-only")
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    selected = selection["selected"]
    summary = selection["summary"]
    if len(selected) != target:
        raise ValueError(
            f"已准备样本数{len(selected)}与本次target={target}不一致")
    records_dir = output_dir / "records"
    records_dir.mkdir(exist_ok=True)
    work_root = MODULE_ROOT / "_temp" / "role_text_corpus_work"
    work_root.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "corpus_summary.json"
    failures_path = output_dir / "failures.json"
    failures = json.loads(failures_path.read_text(encoding="utf-8")) if failures_path.exists() else {}
    pending = [
        row for row in selected
        if not (records_dir / f"{row['recording_id']}.json").is_file()
    ]
    print(
        f"CORPUS_START selected={len(selected)} "
        f"cached={len(selected)-len(pending)} pending={len(pending)}",
        flush=True,
    )
    with ProcessPoolExecutor(
            max_workers=workers, initializer=_worker_init,
            initargs=(torch_threads,)) as executor:
        futures = {}
        for row in pending:
            source = batch_dir / row["source_file"]
            futures[executor.submit(
                _extract_one, str(source), str(work_root))] = row
        completed = 0
        for future in as_completed(futures):
            row = futures[future]
            completed += 1
            try:
                result = future.result()
            except Exception as exc:
                result = {"ok": False, "error": f"WorkerError: {exc}"}
            recording_id = row["recording_id"]
            if result.get("ok"):
                agent_channel = "L" if row["direction"] == "I" else "R"
                payload = {
                    "recording_id": recording_id,
                    "identity_sha256": row["identity_sha256"],
                    "quality": row["quality"],
                    "label_source": "call_direction_proxy",
                    "agent_channel": agent_channel,
                    "customer_channel": "R" if agent_channel == "L" else "L",
                    "channels": result["channels"],
                }
                _atomic_json(records_dir / f"{recording_id}.json", payload)
                failures.pop(recording_id, None)
            else:
                failures[recording_id] = result
            if completed % checkpoint_every == 0:
                _atomic_json(failures_path, failures)
                print(
                    f"CORPUS_CHECKPOINT completed={completed}/{len(pending)} "
                    f"failures={len(failures)}",
                    flush=True,
                )
    _atomic_json(failures_path, failures)
    record_count = sum(1 for row in selected
                       if (records_dir / f"{row['recording_id']}.json").is_file())
    summary.update({
        "records_written": record_count,
        "failures": len(failures),
        "records_dir": str(records_dir),
        "privacy": "完整ASR文本仅保存于_temp语料目录，可能包含敏感业务内容。",
    })
    _atomic_json(summary_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-dir", type=Path, default=DEFAULT_BATCH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--target", type=int, default=DEFAULT_TARGET)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--torch-threads", type=int, default=8)
    parser.add_argument("--checkpoint-every", type=int, default=50)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if args.prepare_only:
        result = prepare_selection(args.batch_dir, args.output_dir, args.target)
        print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
        return
    build_corpus(
        args.batch_dir, args.output_dir, args.target,
        args.workers, args.torch_threads, args.checkpoint_every)


if __name__ == "__main__":
    main()
