# -*- coding: utf-8 -*-
"""滚动构建全量客户声纹库。

默认筛选条件按 2026-08-20 用户确认口径：
  begin_time >= '2025-01-01'
  call_time_length >= 20
  cust_no IS NOT NULL

数据库侧只执行 SELECT。原始 URL、cust_no 和源 id 只在内存中使用，持久化产物仅保存
SHA-256、批次游标、角色摘要和 CAM++ 192 维向量。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

import numpy as np


MODULE_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = MODULE_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT / "src"))
SOURCE_TABLE = "smy_pc.uld_dwd.dwd_serv_ark_call_records"
DEFAULT_OUTPUT = MODULE_ROOT / "data" / "full_customer_voiceprint_library_20250101_v1"
DEFAULT_TEMP_ROOT = MODULE_ROOT / "_temp" / "full_voiceprint_build"
ASR_PYTHON = Path(r"D:\asrvenv\Scripts\python.exe")
MIN_FREE_BYTES = 15 * 1024**3
HTTP_TIMEOUT = 45
MAX_RETRIES = 3
CHUNK_SIZE = 1024 * 1024
ROLE_MODEL_VERSION = "role-text-v1-20260820"
ROLE_RULE_VERSION = "2026-08-20-text-v1"
EMBEDDING_MODEL = "CAM++"
EMBEDDING_MODEL_VERSION = "cam++-funasr-ms"
ASR_MODEL_VERSION = "funasr-paraformer-zh"
EMBEDDING_DIMENSION = 192
ROLE_THRESHOLD = 0.817575


@dataclass(frozen=True)
class KeysetCursor:
    begin_time: str
    id: object


@dataclass(frozen=True)
class BuildConfig:
    source_table: str = SOURCE_TABLE
    since: str = "2025-01-01 00:00:00"
    min_seconds: int = 20
    batch_size: int = 1000
    download_workers: int = 8
    require_identity: bool = True
    output_dir: Path = DEFAULT_OUTPUT
    temp_root: Path = DEFAULT_TEMP_ROOT


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_text(value: object) -> str | None:
    text = "" if value is None else str(value).strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None


def json_default(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    return str(value)


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=json_default),
        encoding="utf-8",
    )
    os.replace(temp, path)


def append_jsonl(path: Path, item: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(item, ensure_ascii=False, default=json_default) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def latest_batch_temp_dir(temp_root: Path) -> Path | None:
    if not temp_root.exists():
        return None
    batch_dirs = [
        path for path in temp_root.iterdir()
        if path.is_dir() and path.name.startswith("batch_")
    ]
    if not batch_dirs:
        return None
    return max(batch_dirs, key=lambda path: (path.stat().st_mtime, path.name))


def sql_literal(value: object) -> str:
    text = "" if value is None else str(value)
    return "'" + text.replace("'", "''") + "'"


def candidate_sql(config: BuildConfig, cursor: KeysetCursor | None = None) -> str:
    """生成稳定键集分页 SQL；不使用 OFFSET。"""
    identity_filter = "      AND cust_no IS NOT NULL\n" if config.require_identity else ""
    cursor_filter = ""
    if cursor is not None:
        cursor_filter = (
            "\n  AND (begin_time < {begin_time}"
            "\n       OR (begin_time = {begin_time} AND id < {id_value}))"
        ).format(
            begin_time=sql_literal(cursor.begin_time),
            id_value=sql_literal(cursor.id),
        )
    return f"""
SELECT id, cust_no, begin_time, call_time_length, record_file_url
FROM (
    SELECT id, cust_no, begin_time, call_time_length, record_file_url,
           ROW_NUMBER() OVER (
               PARTITION BY record_file_url
               ORDER BY begin_time DESC, id DESC
           ) AS url_rank
    FROM {config.source_table}
    WHERE record_file_url IS NOT NULL
      AND TRIM(record_file_url) <> ''
      AND begin_time >= {sql_literal(config.since)}
      AND CAST(NULLIF(TRIM(call_time_length), '') AS DOUBLE) >= {int(config.min_seconds)}
{identity_filter}) ranked
WHERE url_rank = 1{cursor_filter}
ORDER BY begin_time DESC, id DESC
LIMIT {int(config.batch_size)}
""".strip()


def fetch_candidates(config: BuildConfig, cursor: KeysetCursor | None) -> tuple[list[dict], str, str]:
    sys.path.insert(0, str(WORKSPACE_ROOT))
    from skill.lib.db_router import db_session

    sql = candidate_sql(config, cursor)
    with db_session(config.source_table) as (_conn, db_cursor, engine):
        db_cursor.execute(sql)
        rows = db_cursor.fetchall()
    return list(rows), engine, sql


def load_state(output_dir: Path) -> dict:
    path = output_dir / "build_state.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def state_cursor(state: dict) -> KeysetCursor | None:
    cursor = state.get("cursor")
    if not cursor:
        return None
    return KeysetCursor(begin_time=str(cursor["begin_time"]), id=cursor["id"])


def recording_id_from_url(url: str) -> tuple[str, str]:
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return f"vp_{url_hash[:24]}", url_hash


def suffix_from_response(url: str, content_type: str | None) -> str:
    suffix = Path(unquote(urlparse(url).path)).suffix.lower()
    if suffix and len(suffix) <= 8 and suffix[1:].isalnum():
        return suffix
    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";", 1)[0].strip())
        if guessed:
            return guessed
    return ".mp3"


def probe_audio(path: Path) -> dict:
    code = (
        "import json,soundfile as sf,sys;"
        "i=sf.info(sys.argv[1]);"
        "print(json.dumps({'duration':i.duration,'channels':i.channels,"
        "'samplerate':i.samplerate,'format':i.format}))"
    )
    result = subprocess.run(
        [str(ASR_PYTHON), "-c", code, str(path)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    return json.loads(result.stdout)


def download_candidate(candidate: dict, audio_dir: Path, config: BuildConfig) -> dict:
    url = str(candidate.get("record_file_url") or "").strip()
    recording_id, url_hash = recording_id_from_url(url)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return {
            "status": "rejected",
            "recording_id": recording_id,
            "url_sha256": url_hash,
            "reason": "unsupported_url_scheme",
        }

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        part_path = None
        final_path = None
        try:
            if shutil.disk_usage(audio_dir).free <= MIN_FREE_BYTES:
                return {"status": "stop", "reason": "disk_free_reserve_reached"}
            request = Request(url, headers={"User-Agent": "VoiceprintFullBuild/1.0"})
            with urlopen(request, timeout=HTTP_TIMEOUT) as response:
                content_type = response.headers.get("Content-Type")
                content_length = response.headers.get("Content-Length")
                expected_bytes = (
                    int(content_length)
                    if content_length and content_length.isdigit()
                    else 0
                )
                if expected_bytes and shutil.disk_usage(audio_dir).free - expected_bytes < MIN_FREE_BYTES:
                    return {"status": "stop", "reason": "disk_free_reserve_reached"}
                final_path = audio_dir / f"{recording_id}{suffix_from_response(url, content_type)}"
                part_path = Path(str(final_path) + ".part")
                file_hash = hashlib.sha256()
                downloaded = 0
                with part_path.open("wb") as handle:
                    while True:
                        chunk = response.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        downloaded += len(chunk)
                        handle.write(chunk)
                        file_hash.update(chunk)
                part_path.replace(final_path)

            info = probe_audio(final_path)
            duration = float(info["duration"])
            channels = int(info["channels"])
            if duration < config.min_seconds or channels < 2:
                final_path.unlink(missing_ok=True)
                return {
                    "status": "rejected",
                    "recording_id": recording_id,
                    "url_sha256": url_hash,
                    "reason": "actual_audio_out_of_scope",
                    "actual_duration": round(duration, 3),
                    "channels": channels,
                }
            return {
                "status": "success",
                "recording_id": recording_id,
                "source_id_sha256": sha256_text(candidate.get("id")),
                "url_sha256": url_hash,
                "identity_sha256": sha256_text(candidate.get("cust_no")),
                "begin_time": str(candidate.get("begin_time") or ""),
                "declared_duration": float(candidate.get("call_time_length") or 0),
                "actual_duration": round(duration, 3),
                "channels": channels,
                "samplerate": int(info["samplerate"]),
                "format": str(info["format"]),
                "file": str(final_path),
                "bytes": downloaded,
                "audio_sha256": file_hash.hexdigest(),
                "completed_at": now_text(),
            }
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if part_path:
                part_path.unlink(missing_ok=True)
            if final_path:
                final_path.unlink(missing_ok=True)
            if attempt < MAX_RETRIES:
                time.sleep(attempt * 2)
    return {
        "status": "failed",
        "recording_id": recording_id,
        "url_sha256": url_hash,
        "error": last_error,
        "failed_at": now_text(),
    }


def extract_channel_paths(audio_path: Path, work_dir: Path) -> dict[str, Path]:
    from common import audio_io

    channel_paths = {}
    for index, channel in ((0, "L"), (1, "R")):
        wav = work_dir / f"{audio_path.stem}_{channel}.wav"
        audio_io.extract_channel(str(audio_path), index, str(wav), dur=None, sr=16000)
        channel_paths[channel] = wav
    return channel_paths


def extract_channel_path(audio_path: Path, work_dir: Path, channel: str) -> Path:
    from common import audio_io

    if channel not in {"L", "R"}:
        raise ValueError("channel must be L or R")
    wav = work_dir / f"{audio_path.stem}_{channel}.wav"
    if not wav.exists():
        audio_io.extract_channel(
            str(audio_path),
            0 if channel == "L" else 1,
            str(wav),
            dur=None,
            sr=16000,
        )
    return wav


def embedding_cache_key(recording_id: str, channel: str, model_version: str = EMBEDDING_MODEL_VERSION) -> str:
    if channel not in {"L", "R"}:
        raise ValueError("channel must be L or R")
    return f"{recording_id}__{channel}__{model_version}"


def validate_embedding(vector: np.ndarray) -> bool:
    return (
        isinstance(vector, np.ndarray)
        and vector.shape == (EMBEDDING_DIMENSION,)
        and np.isfinite(vector).all()
    )


def formal_index_eligible(role_result: dict, identity_sha256: str | None) -> bool:
    return (
        bool(identity_sha256)
        and role_result.get("quality_status") == "valid_dialogue"
        and role_result.get("status") == "identified"
        and role_result.get("customer_ch") in {"L", "R"}
        and role_result.get("agent_ch") in {"L", "R"}
        and float(role_result.get("margin") or 0.0) >= float(role_result.get("threshold") or ROLE_THRESHOLD)
        and not bool(role_result.get("needs_review"))
    )


def transcribe_and_classify(audio_path: Path, work_dir: Path) -> tuple[dict, dict[str, Path]]:
    from common import asr_role, text_role

    channel_paths = extract_channel_paths(audio_path, work_dir)
    features = {}
    for channel, wav in channel_paths.items():
        features[channel] = asr_role.transcribe_role_features(str(wav))
    decision = text_role.classify_features(features["L"], features["R"])
    summaries = {
        "left_summary": features["L"].get("summary", {}),
        "right_summary": features["R"].get("summary", {}),
    }
    quality_status = {
        "identified": "valid_dialogue",
        "needs_review": "valid_dialogue",
        "one_sided": "one_sided",
        "no_effective_dialogue": "no_effective_dialogue",
    }.get(decision.get("status"), "unknown")
    role_result = {
        **decision,
        **summaries,
        "quality_status": quality_status,
        "threshold": decision.get("threshold", ROLE_THRESHOLD),
        "role_model_version": ROLE_MODEL_VERSION,
        "asr_model_version": ASR_MODEL_VERSION,
    }
    return role_result, channel_paths


def extract_customer_embedding(channel_paths: dict[str, Path], customer_ch: str) -> np.ndarray:
    from common import embedding

    if customer_ch not in channel_paths:
        raise ValueError(f"customer_ch无效: {customer_ch}")
    vector = embedding.embed(str(channel_paths[customer_ch]), disable_pbar=True).astype(np.float32)
    if not validate_embedding(vector):
        raise ValueError(f"{customer_ch} embedding维度或数值非法")
    return vector


def process_record(download_row: dict, batch_id: str, role_dir: Path,
                   work_dir: Path, reuse_existing_role: bool = False) -> tuple[dict, list[dict], list[np.ndarray]]:
    audio_path = Path(download_row["file"])
    role_path = role_dir / f"{download_row['recording_id']}.json"
    role_payload = None
    channel_paths = None
    if reuse_existing_role and role_path.exists():
        role_payload = json.loads(role_path.read_text(encoding="utf-8"))

    if role_payload is None:
        try:
            role_result, channel_paths = transcribe_and_classify(audio_path, work_dir)
        except Exception as exc:
            raise RuntimeError(f"transcribe_and_classify failed: {type(exc).__name__}: {exc}") from exc
        role_payload = {
            "recording_id": download_row["recording_id"],
            "source_id_sha256": download_row.get("source_id_sha256"),
            "url_sha256": download_row.get("url_sha256"),
            "identity_sha256": download_row.get("identity_sha256"),
            "begin_time": download_row.get("begin_time"),
            "audio_sha256": download_row.get("audio_sha256"),
            "processed_at": now_text(),
            **role_result,
        }
        role_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(role_path, role_payload)

    customer_ch = str(role_payload.get("customer_ch") or "")
    if customer_ch not in {"L", "R"}:
        return role_payload, [], []
    if channel_paths is None:
        channel_paths = {customer_ch: extract_channel_path(audio_path, work_dir, customer_ch)}
    try:
        customer_vector = extract_customer_embedding(channel_paths, customer_ch)
    except Exception as exc:
        raise RuntimeError(f"extract_customer_embedding failed: {type(exc).__name__}: {exc}") from exc
    now = now_text()

    rows = [{
        "recording_id": download_row["recording_id"],
        "identity_sha256": download_row.get("identity_sha256"),
        "channel": customer_ch,
        "dimension": EMBEDDING_DIMENSION,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_model_version": EMBEDDING_MODEL_VERSION,
        "role_model_version": ROLE_MODEL_VERSION,
        "audio_sha256": download_row.get("audio_sha256"),
        "batch_id": batch_id,
        "cache_key": embedding_cache_key(download_row["recording_id"], customer_ch),
        "created_at": now,
        "formal_index_eligible": formal_index_eligible(role_payload, download_row.get("identity_sha256")),
    }]
    vector_list = [customer_vector]
    return role_payload, rows, vector_list


def resume_latest_temp_batch(config: BuildConfig, delete_audio_after_commit: bool) -> dict:
    state = load_state(config.output_dir)
    cursor = state_cursor(state)
    candidates, engine, sql = fetch_candidates(config, cursor)
    batch_temp = latest_batch_temp_dir(config.temp_root)
    if batch_temp is None:
        return {
            "status": "failed",
            "reason": "no_temp_batch_found",
            "engine": engine,
            "executed_sql": sql,
        }

    download_manifest = batch_temp / "download_manifest.jsonl"
    manifest_rows = read_jsonl(download_manifest)
    if not manifest_rows:
        return {
            "status": "failed",
            "reason": "missing_download_manifest",
            "batch_id": batch_temp.name,
            "engine": engine,
            "executed_sql": sql,
        }
    if len(manifest_rows) != len(candidates):
        return {
            "status": "failed_not_committed",
            "reason": "incomplete_download_manifest",
            "batch_id": batch_temp.name,
            "engine": engine,
            "candidate_count": len(candidates),
            "manifest_count": len(manifest_rows),
            "cursor": state.get("cursor"),
            "executed_sql": sql,
            "failed_at": now_text(),
        }

    batch_id = batch_temp.name
    audio_dir = batch_temp / "audio"
    work_dir = batch_temp / "work"
    role_dir = config.output_dir / "role_results" / batch_id
    embedding_path = config.output_dir / "embedding_batches" / f"{batch_id}.npz"
    download_by_id = {
        str(row.get("recording_id")): row
        for row in manifest_rows
        if row.get("status") == "success"
    }

    download_results = []
    for candidate in candidates:
        recording_id, _ = recording_id_from_url(str(candidate.get("record_file_url") or ""))
        row = download_by_id.get(recording_id)
        if row is None:
            download_results.append({
                "status": "failed",
                "recording_id": recording_id,
                "error": "missing_download_from_manifest",
                "batch_id": batch_id,
            })
            continue
        if not Path(str(row.get("file") or "")).exists():
            download_results.append({
                "status": "failed",
                "recording_id": recording_id,
                "error": "download_file_missing",
                "batch_id": batch_id,
            })
            continue
        download_results.append(row)

    role_records = []
    embedding_rows = []
    vectors = []
    failures = []
    reviews = []
    for row in download_results:
        if row.get("status") != "success":
            failures.append(row)
            continue
        try:
            role_payload, rows, vector_list = process_record(
                row,
                batch_id,
                role_dir,
                work_dir,
                reuse_existing_role=True,
            )
            role_records.append(role_payload)
            embedding_rows.extend(rows)
            vectors.extend(vector_list)
            if role_payload.get("needs_review"):
                reviews.append({
                    "recording_id": role_payload["recording_id"],
                    "identity_sha256": role_payload.get("identity_sha256"),
                    "quality_status": role_payload.get("quality_status"),
                    "status": role_payload.get("status"),
                    "margin": role_payload.get("margin"),
                    "threshold": role_payload.get("threshold"),
                    "batch_id": batch_id,
                })
        except Exception as exc:
            failures.append({
                "status": "failed",
                "recording_id": row.get("recording_id"),
                "error": f"{type(exc).__name__}: {exc}",
                "traceback_tail": traceback.format_exc(limit=4),
                "batch_id": batch_id,
            })

    if not role_records and not embedding_rows:
        batch_summary = {
            "status": "failed_not_committed",
            "batch_id": batch_id,
            "engine": engine,
            "candidate_count": len(candidates),
            "download_success": sum(row.get("status") == "success" for row in download_results),
            "role_records": len(role_records),
            "embedding_records": len(embedding_rows),
            "review_records": len(reviews),
            "failure_records": len(failures),
            "cursor": state.get("cursor"),
            "executed_sql": sql,
            "failed_at": now_text(),
            "reason": "no_role_records",
        }
        append_jsonl(config.output_dir / "batch_index.jsonl", batch_summary)
        for item in failures:
            append_jsonl(config.output_dir / "failure_queue.jsonl", item)
        return batch_summary

    atomic_write_embeddings(embedding_path, embedding_rows, vectors)
    for item in reviews:
        append_jsonl(config.output_dir / "review_queue.jsonl", item)
    for item in failures:
        append_jsonl(config.output_dir / "failure_queue.jsonl", item)

    formal_rows = [
        row for row in embedding_rows
        if row.get("formal_index_eligible")
    ]
    for row in formal_rows:
        append_jsonl(config.output_dir / "search_index" / "formal_customer_vectors.jsonl", row)

    last = candidates[-1]
    new_cursor = {"begin_time": str(last.get("begin_time") or ""), "id": last.get("id")}
    cleanup = None
    if delete_audio_after_commit:
        cleanup = cleanup_batch_temp(batch_temp, config.temp_root)
    state_payload = {
        "cursor": new_cursor,
        "last_batch_id": batch_id,
        "updated_at": now_text(),
    }
    atomic_write_json(config.output_dir / "build_state.json", state_payload)
    batch_summary = {
        "status": "committed",
        "batch_id": batch_id,
        "engine": engine,
        "candidate_count": len(candidates),
        "download_success": sum(row.get("status") == "success" for row in download_results),
        "role_records": len(role_records),
        "embedding_records": len(embedding_rows),
        "formal_index_records": len(formal_rows),
        "review_records": len(reviews),
        "failure_records": len(failures),
        "cursor": new_cursor,
        "cleanup": cleanup,
        "executed_sql": sql,
        "committed_at": now_text(),
        "resumed_from_temp_batch": True,
    }
    append_jsonl(config.output_dir / "batch_index.jsonl", batch_summary)
    return batch_summary


def atomic_write_embeddings(path: Path, rows: list[dict], vectors: list[np.ndarray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("wb") as handle:
        np.savez_compressed(
            handle,
            metadata=np.asarray([json.dumps(row, ensure_ascii=False) for row in rows]),
            embeddings=np.stack(vectors).astype(np.float32) if vectors else np.empty((0, EMBEDDING_DIMENSION), np.float32),
        )
    os.replace(temp, path)


def is_safe_child(base: Path, target: Path) -> bool:
    base_resolved = base.resolve()
    target_resolved = target.resolve()
    try:
        target_resolved.relative_to(base_resolved)
        return True
    except ValueError:
        return False


def cleanup_batch_temp(batch_temp_dir: Path, temp_root: Path) -> dict:
    if not is_safe_child(temp_root, batch_temp_dir):
        raise ValueError(f"拒绝清理越界目录: {batch_temp_dir}")
    before = shutil.disk_usage(temp_root).free if temp_root.exists() else 0
    if batch_temp_dir.exists():
        shutil.rmtree(batch_temp_dir)
    after = shutil.disk_usage(temp_root).free if temp_root.exists() else before
    return {"deleted_path": str(batch_temp_dir), "released_bytes": max(0, after - before)}


def write_manifest(config: BuildConfig) -> None:
    manifest_path = config.output_dir / "library_manifest.json"
    if manifest_path.exists():
        return
    atomic_write_json(manifest_path, {
        "library_version": config.output_dir.name,
        "source_table": config.source_table,
        "filter": {
            "begin_time": f">= {config.since}",
            "call_time_length": f">= {config.min_seconds}",
            "cust_no": "IS NOT NULL" if config.require_identity else "not required",
            "record_file_url": "IS NOT NULL AND TRIM(record_file_url) <> ''",
        },
        "role_model_version": ROLE_MODEL_VERSION,
        "role_rule_version": ROLE_RULE_VERSION,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_model_version": EMBEDDING_MODEL_VERSION,
        "embedding_dimension": EMBEDDING_DIMENSION,
        "created_at": now_text(),
        "privacy": "不保存原始URL、cust_no或源id；正式产物仅保存SHA-256和数值摘要。",
    })


def run_one_batch(config: BuildConfig, batch_no: int, delete_audio_after_commit: bool) -> dict:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    write_manifest(config)
    state = load_state(config.output_dir)
    cursor = state_cursor(state)
    candidates, engine, sql = fetch_candidates(config, cursor)
    batch_id = f"batch_{datetime.now().strftime('%Y%m%d')}_{batch_no:06d}"
    if not candidates:
        return {
            "status": "exhausted",
            "batch_id": batch_id,
            "engine": engine,
            "executed_sql": sql,
        }

    batch_temp = config.temp_root / batch_id
    audio_dir = batch_temp / "audio"
    work_dir = batch_temp / "work"
    audio_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    role_dir = config.output_dir / "role_results" / batch_id
    embedding_path = config.output_dir / "embedding_batches" / f"{batch_id}.npz"
    download_manifest = batch_temp / "download_manifest.jsonl"

    download_results = []
    max_workers = max(1, int(config.download_workers))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for result in executor.map(lambda candidate: download_candidate(candidate, audio_dir, config), candidates):
            download_results.append(result)
            append_jsonl(download_manifest, result)
            if result.get("status") == "stop":
                break

    role_records = []
    embedding_rows = []
    vectors = []
    failures = []
    reviews = []
    for row in download_results:
        if row.get("status") != "success":
            failures.append(row)
            continue
        try:
            role_payload, rows, vector_list = process_record(row, batch_id, role_dir, work_dir)
            role_records.append(role_payload)
            embedding_rows.extend(rows)
            vectors.extend(vector_list)
            if role_payload.get("needs_review"):
                reviews.append({
                    "recording_id": role_payload["recording_id"],
                    "identity_sha256": role_payload.get("identity_sha256"),
                    "quality_status": role_payload.get("quality_status"),
                    "status": role_payload.get("status"),
                    "margin": role_payload.get("margin"),
                    "threshold": role_payload.get("threshold"),
                    "batch_id": batch_id,
                })
        except Exception as exc:
            failures.append({
                "status": "failed",
                "recording_id": row.get("recording_id"),
                "error": f"{type(exc).__name__}: {exc}",
                "traceback_tail": traceback.format_exc(limit=4),
                "batch_id": batch_id,
            })

    if not role_records and not embedding_rows:
        batch_summary = {
            "status": "failed_not_committed",
            "batch_id": batch_id,
            "engine": engine,
            "candidate_count": len(candidates),
            "download_success": sum(row.get("status") == "success" for row in download_results),
            "role_records": len(role_records),
            "embedding_records": len(embedding_rows),
            "review_records": len(reviews),
            "failure_records": len(failures),
            "cursor": state.get("cursor"),
            "executed_sql": sql,
            "failed_at": now_text(),
            "reason": "no_role_records",
        }
        append_jsonl(config.output_dir / "batch_index.jsonl", batch_summary)
        for item in failures:
            append_jsonl(config.output_dir / "failure_queue.jsonl", item)
        return batch_summary

    atomic_write_embeddings(embedding_path, embedding_rows, vectors)
    for item in reviews:
        append_jsonl(config.output_dir / "review_queue.jsonl", item)
    for item in failures:
        append_jsonl(config.output_dir / "failure_queue.jsonl", item)

    formal_rows = [
        row for row in embedding_rows
        if row.get("formal_index_eligible")
    ]
    for row in formal_rows:
        append_jsonl(config.output_dir / "search_index" / "formal_customer_vectors.jsonl", row)

    last = candidates[-1]
    new_cursor = {"begin_time": str(last.get("begin_time") or ""), "id": last.get("id")}
    cleanup = None
    if delete_audio_after_commit:
        cleanup = cleanup_batch_temp(batch_temp, config.temp_root)
    state_payload = {
        "cursor": new_cursor,
        "last_batch_id": batch_id,
        "updated_at": now_text(),
    }
    atomic_write_json(config.output_dir / "build_state.json", state_payload)
    batch_summary = {
        "status": "committed",
        "batch_id": batch_id,
        "engine": engine,
        "candidate_count": len(candidates),
        "download_success": sum(row.get("status") == "success" for row in download_results),
        "role_records": len(role_records),
        "embedding_records": len(embedding_rows),
        "formal_index_records": len(formal_rows),
        "review_records": len(reviews),
        "failure_records": len(failures),
        "cursor": new_cursor,
        "cleanup": cleanup,
        "executed_sql": sql,
        "committed_at": now_text(),
    }
    append_jsonl(config.output_dir / "batch_index.jsonl", batch_summary)
    return batch_summary


def run_build(config: BuildConfig, max_batches: int, delete_audio_after_commit: bool) -> list[dict]:
    summaries = []
    existing_batches = read_jsonl(config.output_dir / "batch_index.jsonl")
    start_batch_no = len(existing_batches) + 1
    for batch_no in range(start_batch_no, start_batch_no + max_batches):
        summary = run_one_batch(config, batch_no, delete_audio_after_commit)
        summaries.append(summary)
        if summary.get("status") != "committed":
            break
    return summaries


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--temp-root", type=Path, default=DEFAULT_TEMP_ROOT)
    parser.add_argument("--since", default="2025-01-01 00:00:00")
    parser.add_argument("--min-seconds", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--download-workers", type=int, default=8,
                        help="下载阶段并发线程数")
    parser.add_argument("--max-batches", type=int, default=1)
    parser.add_argument("--resume-last-temp-batch", action="store_true",
                        help="不再下载新候选，直接恢复最近的临时批次继续角色识别和提交")
    parser.add_argument("--dry-run-sql", action="store_true",
                        help="只打印下一批SELECT，不下载、不处理")
    parser.add_argument("--keep-audio", action="store_true",
                        help="提交批次后保留本批原始录音和临时WAV")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = BuildConfig(
        since=args.since,
        min_seconds=args.min_seconds,
        batch_size=args.batch_size,
        download_workers=args.download_workers,
        output_dir=args.output_dir,
        temp_root=args.temp_root,
    )
    if args.dry_run_sql:
        state = load_state(config.output_dir)
        print(candidate_sql(config, state_cursor(state)))
        return
    if args.resume_last_temp_batch:
        summaries = [resume_latest_temp_batch(config, delete_audio_after_commit=not args.keep_audio)]
    else:
        summaries = run_build(
            config,
            max_batches=args.max_batches,
            delete_audio_after_commit=not args.keep_audio,
        )
    print(json.dumps(summaries, ensure_ascii=False, indent=2, default=json_default))


if __name__ == "__main__":
    main()
