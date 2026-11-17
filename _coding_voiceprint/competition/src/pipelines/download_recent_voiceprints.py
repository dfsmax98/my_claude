# -*- coding: utf-8 -*-
"""下载最近半年、20-180秒的双轨录音，支持断点续跑和实际音频复核。"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen


MODULE_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = MODULE_ROOT.parent
DEFAULT_OUTPUT = MODULE_ROOT / "data" / "recent_voiceprints_10k_20260819"
SOURCE_TABLE = "smy_pc.uld_dwd.dwd_serv_ark_call_records"
SINCE = "2026-02-19 00:00:00"
MIN_SECONDS = 20.0
MAX_SECONDS = 180.0
DEFAULT_TARGET = 10_000
DEFAULT_CANDIDATES = 12_000
MAX_BATCH_BYTES = 20 * 1024**3
MIN_FREE_BYTES = 15 * 1024**3
HTTP_TIMEOUT = 45
MAX_RETRIES = 3
CHUNK_SIZE = 1024 * 1024
ASR_PYTHON = Path(r"D:\asrvenv\Scripts\python.exe")


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def append_jsonl(path: Path, item: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
        handle.flush()


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


def candidate_sql(limit: int) -> str:
    """按URL去重后取最近的候选；不把URL写入本地清单。"""
    return f"""
SELECT id, cust_no, begin_time, call_time_length, record_file_url
FROM (
    SELECT id, cust_no, begin_time, call_time_length, record_file_url,
           ROW_NUMBER() OVER (
               PARTITION BY record_file_url
               ORDER BY begin_time DESC, id DESC
           ) AS url_rank
    FROM {SOURCE_TABLE}
    WHERE record_file_url IS NOT NULL
      AND TRIM(record_file_url) <> ''
      AND begin_time >= '{SINCE}'
      AND CAST(NULLIF(TRIM(call_time_length), '') AS DOUBLE)
          BETWEEN {int(MIN_SECONDS)} AND {int(MAX_SECONDS)}
      AND LOWER(TRIM(COALESCE(is_double_track, '')))
          IN ('1', 'y', 'yes', 'true')
) ranked
WHERE url_rank = 1
ORDER BY begin_time DESC, id DESC
LIMIT {int(limit)}
""".strip()


def fetch_candidates(limit: int) -> tuple[list[dict], str]:
    sys.path.insert(0, str(WORKSPACE_ROOT))
    from skill.lib.db_router import db_session

    sql = candidate_sql(limit)
    with db_session(SOURCE_TABLE) as (_conn, cursor, engine):
        cursor.execute(sql)
        rows = cursor.fetchall()
    return list(rows), engine


def _hash_text(value: object) -> str | None:
    text = "" if value is None else str(value).strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None


def _suffix(url: str, content_type: str | None) -> str:
    suffix = Path(unquote(urlparse(url).path)).suffix.lower()
    if re.fullmatch(r"\.[a-z0-9]{1,8}", suffix or ""):
        return suffix
    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";", 1)[0].strip())
        if guessed:
            return guessed
    return ".mp3"


def probe_audio(path: Path) -> dict:
    """使用声纹环境的libsndfile读取实际时长和声道数。"""
    code = (
        "import json,soundfile as sf,sys;"
        "i=sf.info(sys.argv[1]);"
        "print(json.dumps({'duration':i.duration,'channels':i.channels,"
        "'samplerate':i.samplerate,'format':i.format}))"
    )
    result = subprocess.run(
        [str(ASR_PYTHON), "-c", code, str(path)],
        check=True, capture_output=True, text=True, encoding="utf-8", timeout=30)
    return json.loads(result.stdout)


def _download_candidate(candidate: dict, audio_dir: Path, existing_bytes: int) -> dict:
    url = str(candidate.get("record_file_url") or "").strip()
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
    recording_id = f"vp_{url_hash[:24]}"
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return {"status": "rejected", "recording_id": recording_id,
                "url_sha256": url_hash, "reason": "unsupported_url_scheme"}

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        part_path = None
        final_path = None
        try:
            request = Request(url, headers={"User-Agent": "VoiceprintBatch/1.0"})
            with urlopen(request, timeout=HTTP_TIMEOUT) as response:
                content_type = response.headers.get("Content-Type")
                length_text = response.headers.get("Content-Length")
                content_length = int(length_text) if length_text and length_text.isdigit() else None
                free = shutil.disk_usage(audio_dir).free
                if free <= MIN_FREE_BYTES:
                    return {"status": "stop", "reason": "disk_free_reserve_reached"}
                if content_length and (
                        existing_bytes + content_length > MAX_BATCH_BYTES
                        or free - content_length < MIN_FREE_BYTES):
                    return {"status": "stop", "reason": "disk_or_batch_cap_reached"}

                final_path = audio_dir / f"{recording_id}{_suffix(url, content_type)}"
                part_path = Path(str(final_path) + ".part")
                downloaded = 0
                file_hash = hashlib.sha256()
                with part_path.open("wb") as handle:
                    while True:
                        chunk = response.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        downloaded += len(chunk)
                        if existing_bytes + downloaded > MAX_BATCH_BYTES:
                            raise OverflowError("batch_cap_reached")
                        handle.write(chunk)
                        file_hash.update(chunk)
                part_path.replace(final_path)

            info = probe_audio(final_path)
            duration = float(info["duration"])
            channels = int(info["channels"])
            if not (MIN_SECONDS <= duration <= MAX_SECONDS) or channels < 2:
                final_path.unlink(missing_ok=True)
                return {
                    "status": "rejected", "recording_id": recording_id,
                    "url_sha256": url_hash, "reason": "actual_audio_out_of_scope",
                    "actual_duration": round(duration, 3), "channels": channels,
                }
            return {
                "status": "success",
                "recording_id": recording_id,
                "url_sha256": url_hash,
                "source_id_sha256": _hash_text(candidate.get("id")),
                "identity_sha256": _hash_text(candidate.get("cust_no")),
                "begin_time": str(candidate.get("begin_time") or ""),
                "declared_duration": float(candidate.get("call_time_length") or 0),
                "actual_duration": round(duration, 3),
                "channels": channels,
                "samplerate": int(info["samplerate"]),
                "format": str(info["format"]),
                "file": str(final_path.relative_to(audio_dir.parent)),
                "bytes": downloaded,
                "file_sha256": file_hash.hexdigest(),
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
    return {"status": "failed", "recording_id": recording_id,
            "url_sha256": url_hash, "error": last_error, "failed_at": now_text()}


def _successful_records(manifest_path: Path, output_dir: Path) -> dict[str, dict]:
    records = {}
    for item in read_jsonl(manifest_path):
        if item.get("status") != "success" or not item.get("url_sha256"):
            continue
        path = output_dir / str(item.get("file") or "")
        if path.is_file() and path.stat().st_size == int(item.get("bytes") or -1):
            records[item["url_sha256"]] = item
    return records


def run_download(output_dir: Path, target: int, candidate_limit: int,
                 workers: int) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_dir = output_dir / "audio"
    audio_dir.mkdir(exist_ok=True)
    manifest_path = output_dir / "download_manifest.jsonl"
    failures_path = output_dir / "download_failures.jsonl"
    summary_path = output_dir / "download_summary.json"

    completed = _successful_records(manifest_path, output_dir)
    candidates, engine = fetch_candidates(candidate_limit)
    candidates_by_hash = []
    for candidate in candidates:
        url = str(candidate.get("record_file_url") or "").strip()
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
        if url_hash not in completed:
            candidates_by_hash.append(candidate)
    if len(completed) >= target:
        candidates_by_hash = []

    existing_bytes = sum(int(item.get("bytes") or 0) for item in completed.values())
    rejected = failed = 0
    stop_reason = "target_reached" if len(completed) >= target else "candidates_exhausted"
    candidate_iter = iter(candidates_by_hash)
    pending = {}
    started_at = now_text()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        while len(pending) < workers and len(completed) + len(pending) < target:
            try:
                candidate = next(candidate_iter)
            except StopIteration:
                break
            future = executor.submit(_download_candidate, candidate, audio_dir, existing_bytes)
            pending[future] = candidate

        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                pending.pop(future, None)
                result = future.result()
                status = result.get("status")
                if status == "success":
                    completed[result["url_sha256"]] = result
                    existing_bytes += int(result["bytes"])
                    append_jsonl(manifest_path, result)
                elif status == "stop":
                    stop_reason = result.get("reason", "stopped")
                else:
                    append_jsonl(failures_path, result)
                    rejected += status == "rejected"
                    failed += status == "failed"

                processed = len(completed) + rejected + failed
                if processed % 50 == 0:
                    print(json.dumps({
                        "event": "progress", "completed": len(completed),
                        "rejected": rejected, "failed": failed,
                        "gib": round(existing_bytes / 1024**3, 3),
                    }, ensure_ascii=False), flush=True)

                if stop_reason not in {"target_reached", "candidates_exhausted"}:
                    continue
                while len(pending) < workers and len(completed) + len(pending) < target:
                    try:
                        candidate = next(candidate_iter)
                    except StopIteration:
                        break
                    future = executor.submit(
                        _download_candidate, candidate, audio_dir, existing_bytes)
                    pending[future] = candidate

    if len(completed) >= target:
        stop_reason = "target_reached"
    summary = {
        "table": SOURCE_TABLE,
        "engine": engine,
        "since": SINCE,
        "duration_seconds": [MIN_SECONDS, MAX_SECONDS],
        "double_track_required": True,
        "target": target,
        "candidate_limit": candidate_limit,
        "completed": len(completed),
        "rejected_this_run": rejected,
        "failed_this_run": failed,
        "bytes": existing_bytes,
        "gib": round(existing_bytes / 1024**3, 6),
        "started_at": started_at,
        "finished_at": now_text(),
        "stop_reason": stop_reason,
        "executed_sql": [candidate_sql(candidate_limit)],
        "privacy": "本地清单不保存原始URL、客户号或源记录ID，仅保存SHA-256。",
    }
    temp = summary_path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, summary_path)
    print(json.dumps({"event": "complete", **summary}, ensure_ascii=False, indent=2), flush=True)
    if len(completed) < target:
        raise SystemExit(f"仅完成 {len(completed)}/{target} 条，原因: {stop_reason}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--target", type=int, default=DEFAULT_TARGET)
    parser.add_argument("--candidate-limit", type=int, default=DEFAULT_CANDIDATES)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if args.candidate_limit < args.target:
        parser.error("candidate-limit不能小于target")
    run_download(args.output_dir, args.target, args.candidate_limit, args.workers)


if __name__ == "__main__":
    main()
