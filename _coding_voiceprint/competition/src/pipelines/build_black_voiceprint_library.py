# -*- coding: utf-8 -*-
"""对本地双声道黑产录音做角色识别、客户 embedding 提取并建立声纹库。

输入目录可递归包含音频。原始业务个体号仅用于内存分组，正式产物只保存
SHA-256 派生 actor_id、音频哈希、角色数值摘要和 CAM++ embedding，不保存 ASR 全文。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import pickle
import re
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np


MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(MODULE_ROOT / "src" / "pipelines"))

from common import audio_io, embedding, vpdb  # noqa: E402


ROLE_MODEL_VERSION = "role-text-v1-20260820"
ROLE_RULE_VERSION = "2026-08-20-text-v1"
ASR_MODEL_VERSION = "funasr-paraformer-zh"
EMBEDDING_MODEL = "CAM++"
EMBEDDING_MODEL_VERSION = "cam++-funasr-ms"
EMBEDDING_DIMENSION = 192
AUDIO_SUFFIXES = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".wma"}
ACTOR_PATTERN = re.compile(r"(?<!\d)(1[67]\d{10})(?!\d)")
DEFAULT_SOURCE = MODULE_ROOT / "data" / "raw" / "black_recordings"
DEFAULT_OUTPUT = (
    MODULE_ROOT / "data" / "processed" / "black_voiceprint_library_20260821"
)


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_text(value: object) -> str:
    return hashlib.sha256(str(value).strip().encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temp, path)


def atomic_write_pickle(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("wb") as handle:
        pickle.dump(payload, handle)
    os.replace(temp, path)


def atomic_save_npz(path: Path, **arrays: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.stem + ".tmp.npz")
    np.savez_compressed(temp, **arrays)
    os.replace(temp, path)


def discover_audio_files(source_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in source_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in AUDIO_SUFFIXES
    )


def source_actor_key(path: Path, source_dir: Path) -> str:
    """从顶层子目录或文件名提取 12 位业务个体号。"""
    relative = path.relative_to(source_dir)
    candidates = []
    if len(relative.parts) > 1:
        candidates.append(relative.parts[0])
    candidates.append(path.stem)
    for candidate in candidates:
        match = ACTOR_PATTERN.search(candidate)
        if match:
            return match.group(1)
    raise ValueError("路径中未找到12位业务个体号")


def actor_id_of(source_actor: str) -> str:
    return f"black_actor_{sha256_text(source_actor)[:24]}"


def probe_audio(path: Path) -> dict:
    import soundfile as sf

    info = sf.info(str(path))
    return {
        "duration": round(float(info.duration), 3),
        "channels": int(info.channels),
        "samplerate": int(info.samplerate),
        "format": str(info.format),
    }


def valid_embedding(vector: np.ndarray) -> bool:
    return (
        isinstance(vector, np.ndarray)
        and vector.shape == (EMBEDDING_DIMENSION,)
        and np.isfinite(vector).all()
        and 0.99 <= float(np.linalg.norm(vector)) <= 1.01
    )


def formally_eligible(role: dict, audio_info: dict) -> bool:
    return (
        int(audio_info.get("channels") or 0) >= 2
        and bool(role.get("ok"))
        and role.get("customer_ch") in {"L", "R"}
        and role.get("agent_ch") in {"L", "R"}
        and str(role.get("confidence")) == "高"
        and not bool(role.get("needs_review"))
        and not bool(role.get("stage_disagreement"))
    )


def sanitized_role_payload(
    role: dict,
    recording_id: str,
    actor_id: str,
    audio_sha256: str,
    source_relpath_sha256: str,
    audio_info: dict,
) -> dict:
    payload = dict(role)
    payload.pop("source", None)
    payload["recording_id"] = recording_id
    payload["actor_id"] = actor_id
    payload["audio_sha256"] = audio_sha256
    payload["source_relpath_sha256"] = source_relpath_sha256
    payload["audio_info"] = audio_info
    payload["role_model_version"] = ROLE_MODEL_VERSION
    payload["role_rule_version"] = ROLE_RULE_VERSION
    payload["asr_model_version"] = ASR_MODEL_VERSION
    payload["processed_at"] = now_text()
    return payload


def customer_summary(role: dict) -> dict:
    stages = role.get("stages") or []
    if not stages or role.get("customer_ch") not in {"L", "R"}:
        return {}
    final_stage = stages[-1]
    return final_stage["left" if role["customer_ch"] == "L" else "right"]


def role_margin(role: dict) -> float:
    stages = role.get("stages") or []
    if not stages:
        return 0.0
    return float(stages[-1].get("decision", {}).get("margin") or 0.0)


def extract_customer_vector(audio_path: Path, customer_ch: str, work_root: Path) -> np.ndarray:
    with tempfile.TemporaryDirectory(prefix="black_emb_", dir=work_root) as temp_dir:
        wav = Path(temp_dir) / "customer.wav"
        audio_io.extract_channel(
            str(audio_path), 0 if customer_ch == "L" else 1, str(wav), dur=None, sr=16000
        )
        vector = embedding.embed(str(wav), disable_pbar=True).astype(np.float32)
    if not valid_embedding(vector):
        raise ValueError("CAM++ embedding维度、数值或归一化异常")
    return vector


def classify_one(audio_path: Path, work_root: Path) -> dict:
    # 延迟导入，避免仅使用库结构工具时加载ASR运行依赖。
    from pipelines.classify_roles_adaptive import _classify_one

    return _classify_one(str(audio_path), str(work_root), True)


def build_database(records: list[dict], vectors: list[np.ndarray], reviewer: str) -> dict:
    database = {
        "model": "cam++",
        "embedding_model": EMBEDDING_MODEL,
        "embedding_model_version": EMBEDDING_MODEL_VERSION,
        "role_model_version": ROLE_MODEL_VERSION,
        "schema_version": 2,
        "library_type": "confirmed_black_voiceprint",
        "created_at": now_text(),
        "reviewer": reviewer,
        "identities": {},
        "records": [],
    }
    by_actor = defaultdict(list)
    for metadata, vector in zip(records, vectors):
        item = {
            "id": metadata["recording_id"],
            "actor_id": metadata["actor_id"],
            "emb": vector,
            "audio_sha256": metadata["audio_sha256"],
            "source_relpath_sha256": metadata["source_relpath_sha256"],
            "customer_ch": metadata["customer_ch"],
            "role_margin": metadata["role_margin"],
            "customer_speech_seconds": metadata["customer_speech_seconds"],
            "customer_asr_chars": metadata["customer_asr_chars"],
            "quality": "formal",
            "tag": "确认黑产",
            "reviewer": reviewer,
            "review_ts": metadata["processed_at"],
            "added": metadata["processed_at"],
        }
        database["records"].append(item)
        by_actor[item["actor_id"]].append(item["id"])

    for actor_id, rec_ids in sorted(by_actor.items()):
        database["identities"][actor_id] = {
            "rec_ids": rec_ids,
            "n_calls": len(rec_ids),
            "status": "confirmed_black",
            "tag": "确认黑产",
            "reviewer": reviewer,
        }
    return database


def score_diagnostics(database: dict, topk: int = 20) -> tuple[dict, list[dict]]:
    records = database["records"]
    if len(records) < 2:
        return {
            "same_actor_pairs": 0,
            "cross_actor_pairs": 0,
            "same_actor_mean": None,
            "cross_actor_mean": None,
            "cross_actor_p95": None,
            "cross_actor_max": None,
        }, []
    vectors = np.stack([item["emb"] for item in records])
    matrix = vectors @ vectors.T
    same_scores = []
    cross_rows = []
    for left in range(len(records)):
        for right in range(left + 1, len(records)):
            score = float(matrix[left, right])
            if records[left]["actor_id"] == records[right]["actor_id"]:
                same_scores.append(score)
            else:
                cross_rows.append(
                    {
                        "left_actor_id": records[left]["actor_id"],
                        "right_actor_id": records[right]["actor_id"],
                        "left_recording_id": records[left]["id"],
                        "right_recording_id": records[right]["id"],
                        "cosine_score": score,
                    }
                )
    cross_scores = [item["cosine_score"] for item in cross_rows]
    diagnostics = {
        "same_actor_pairs": len(same_scores),
        "cross_actor_pairs": len(cross_scores),
        "same_actor_mean": float(np.mean(same_scores)) if same_scores else None,
        "same_actor_min": float(np.min(same_scores)) if same_scores else None,
        "cross_actor_mean": float(np.mean(cross_scores)) if cross_scores else None,
        "cross_actor_p95": float(np.percentile(cross_scores, 95)) if cross_scores else None,
        "cross_actor_max": float(np.max(cross_scores)) if cross_scores else None,
    }
    return diagnostics, sorted(
        cross_rows, key=lambda item: item["cosine_score"], reverse=True
    )[:topk]


def write_similarity_review(path: Path, rows: list[dict]) -> None:
    fields = [
        "left_actor_id",
        "right_actor_id",
        "left_recording_id",
        "right_recording_id",
        "cosine_score",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_report(
    path: Path,
    source_count: int,
    source_actor_count: int,
    database: dict,
    failures: list[dict],
    channel_counts: Counter,
    diagnostics: dict,
) -> None:
    reason_counts = Counter(item["reason"] for item in failures)
    lines = [
        "# 黑产声纹库建库报告",
        "",
        "> 使用文本角色模型识别客户声道，仅高置信客户侧 CAM++ embedding 进入正式黑产声纹库；不保存ASR全文或原始业务个体号。",
        "",
        "## 建库结果",
        "",
        f"- 输入音频：{source_count} 通。",
        f"- 输入黑产个体：{source_actor_count} 个。",
        f"- 正式入库录音：{len(database['records'])} 通。",
        f"- 正式入库黑产个体：{len(database['identities'])} 个。",
        f"- 待复核/失败：{len(failures)} 通。",
        f"- 客户声道分布：`{dict(channel_counts)}`。",
        f"- 角色模型：`{ROLE_MODEL_VERSION}`。",
        f"- embedding模型：`{EMBEDDING_MODEL_VERSION}`，{EMBEDDING_DIMENSION}维L2归一化向量。",
        f"- 唯一同个体配对余弦：{diagnostics['same_actor_mean']:.3f}。" if diagnostics["same_actor_mean"] is not None else "- 当前没有可计算的同个体配对。",
        f"- 跨个体余弦最高值/P95：{diagnostics['cross_actor_max']:.3f}/{diagnostics['cross_actor_p95']:.3f}。" if diagnostics["cross_actor_max"] is not None else "- 当前没有可计算的跨个体配对。",
        "",
        "## 个体模板数",
        "",
        "| actor_id | 模板数 | 状态 |",
        "|---|---:|---|",
    ]
    for actor_id, identity in sorted(database["identities"].items()):
        lines.append(f"| `{actor_id}` | {identity['n_calls']} | `confirmed_black` |")
    lines += ["", "## 待复核与失败", ""]
    if failures:
        lines.append(f"- 原因统计：`{dict(reason_counts)}`。")
        lines.append("- 逐录音明细见 `review_queue.json`，其中仅保存脱敏标识和错误原因。")
    else:
        lines.append("- 无。")
    lines += [
        "",
        "## 产物",
        "",
        "- `black_db.pkl`：schema v2黑产声纹库，可供`vpdb.search_by_identity(..., id_key='actor_id')`检索。",
        "- `black_embeddings.npz`：正式入库embedding及脱敏元数据。",
        "- `role_results.json`：角色识别数值摘要，不含ASR全文。",
        "- `input_manifest.json`：脱敏输入清单和音频质量信息。",
        "- `review_queue.json`：未进入正式库的录音及原因。",
        "- `library_manifest.json`：模型版本、数量和文件校验信息。",
        "- `high_similarity_cross_actor_review.csv`：跨个体高相似Top配对，供人工复核，不自动合并身份。",
        "",
        "## 使用限制",
        "",
        "- 录音文件被用户归入黑产目录并要求建库，本次按`确认黑产`标签写入；生产接入仍应保留正式审批与撤库流程。",
        "- 黑产库1:N阈值必须使用独立非黑查询集按目标FAR重新标定，不能直接复用客户1:1余弦、AS-norm或PLDA阈值。",
        "- 单模板个体的跨时间、跨设备稳定性尚未验证；后续新增确认录音时应追加模板并执行回归评估。",
        "- 当前跨个体最高余弦高于唯一同个体配对，必须结合人工听音或独立标定集复核高分配对，不能据此自动合并actor。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> dict:
    source_dir = Path(args.source_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    role_dir = output_dir / "role_results"
    embedding_dir = output_dir / "embedding_shards"
    work_root = MODULE_ROOT / "_temp" / "black_voiceprint_build_work"
    role_dir.mkdir(parents=True, exist_ok=True)
    embedding_dir.mkdir(parents=True, exist_ok=True)
    work_root.mkdir(parents=True, exist_ok=True)

    audio_files = discover_audio_files(source_dir)
    if not audio_files:
        raise RuntimeError(f"未找到支持的音频文件: {source_dir}")

    input_manifest = []
    failures = []
    formal_records = []
    formal_vectors = []
    source_actors = set()
    seen_recordings = set()
    channel_counts = Counter()

    for index, audio_path in enumerate(audio_files, 1):
        relative = audio_path.relative_to(source_dir)
        relative_hash = sha256_text(relative.as_posix())
        try:
            source_actor = source_actor_key(audio_path, source_dir)
            actor_id = actor_id_of(source_actor)
            source_actors.add(actor_id)
            audio_hash = sha256_file(audio_path)
            recording_id = f"black_rec_{audio_hash[:24]}"
            audio_info = probe_audio(audio_path)
            manifest_item = {
                "recording_id": recording_id,
                "actor_id": actor_id,
                "audio_sha256": audio_hash,
                "source_relpath_sha256": relative_hash,
                "bytes": audio_path.stat().st_size,
                **audio_info,
            }
            input_manifest.append(manifest_item)
            if recording_id in seen_recordings:
                failures.append({**manifest_item, "reason": "duplicate_audio"})
                print(f"[{index}/{len(audio_files)}] SKIP duplicate {recording_id}", flush=True)
                continue
            seen_recordings.add(recording_id)
            if audio_info["channels"] < 2:
                failures.append({**manifest_item, "reason": "not_dual_track"})
                print(f"[{index}/{len(audio_files)}] REVIEW mono {recording_id}", flush=True)
                continue

            role_path = role_dir / f"{recording_id}.json"
            if role_path.exists():
                role = json.loads(role_path.read_text(encoding="utf-8"))
            else:
                raw_role = classify_one(audio_path, work_root)
                role = sanitized_role_payload(
                    raw_role,
                    recording_id,
                    actor_id,
                    audio_hash,
                    relative_hash,
                    audio_info,
                )
                atomic_write_json(role_path, role)

            if not formally_eligible(role, audio_info):
                reason = str(role.get("error") or role.get("confidence") or "role_needs_review")
                failures.append({**manifest_item, "reason": reason})
                print(f"[{index}/{len(audio_files)}] REVIEW role {recording_id}: {reason}", flush=True)
                continue

            shard_path = embedding_dir / f"{recording_id}__{role['customer_ch']}.npy"
            if shard_path.exists():
                vector = np.load(shard_path, allow_pickle=False)
            else:
                vector = extract_customer_vector(audio_path, role["customer_ch"], work_root)
                temp_shard = shard_path.with_suffix(".tmp.npy")
                np.save(temp_shard, vector)
                os.replace(temp_shard, shard_path)
            if not valid_embedding(vector):
                raise ValueError("缓存embedding校验失败")

            summary = customer_summary(role)
            record = {
                **manifest_item,
                "customer_ch": role["customer_ch"],
                "agent_ch": role["agent_ch"],
                "role_margin": role_margin(role),
                "customer_speech_seconds": float(summary.get("speech_duration") or 0.0),
                "customer_asr_chars": int(summary.get("char_count") or 0),
                "processed_at": role.get("processed_at") or now_text(),
            }
            formal_records.append(record)
            formal_vectors.append(np.asarray(vector, dtype=np.float32))
            channel_counts[role["customer_ch"]] += 1
            print(
                f"[{index}/{len(audio_files)}] OK {recording_id} actor={actor_id} "
                f"customer={role['customer_ch']} margin={record['role_margin']:.4f}",
                flush=True,
            )
        except Exception as exc:
            failure = {
                "source_relpath_sha256": relative_hash,
                "reason": f"{type(exc).__name__}: {exc}",
            }
            failures.append(failure)
            print(f"[{index}/{len(audio_files)}] FAIL {failure['reason']}", flush=True)

        atomic_write_json(output_dir / "input_manifest.json", input_manifest)
        atomic_write_json(output_dir / "review_queue.json", failures)

    if not formal_records:
        raise RuntimeError("没有高置信客户侧embedding可进入正式黑产库")

    database = build_database(formal_records, formal_vectors, args.reviewer)
    diagnostics, similarity_review = score_diagnostics(database)
    atomic_write_pickle(output_dir / "black_db.pkl", database)
    write_similarity_review(
        output_dir / "high_similarity_cross_actor_review.csv", similarity_review
    )
    atomic_save_npz(
        output_dir / "black_embeddings.npz",
        recording_ids=np.asarray([item["recording_id"] for item in formal_records]),
        actor_ids=np.asarray([item["actor_id"] for item in formal_records]),
        customer_channels=np.asarray([item["customer_ch"] for item in formal_records]),
        role_margins=np.asarray([item["role_margin"] for item in formal_records], dtype=np.float32),
        customer_speech_seconds=np.asarray(
            [item["customer_speech_seconds"] for item in formal_records], dtype=np.float32
        ),
        customer_asr_chars=np.asarray(
            [item["customer_asr_chars"] for item in formal_records], dtype=np.int32
        ),
        embeddings=np.stack(formal_vectors).astype(np.float32),
    )
    roles = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(role_dir.glob("*.json"))
    }
    atomic_write_json(
        output_dir / "role_results.json",
        {
            "meta": {
                "role_model_version": ROLE_MODEL_VERSION,
                "role_rule_version": ROLE_RULE_VERSION,
                "asr_model_version": ASR_MODEL_VERSION,
                "model_input": "asr_text_only",
            },
            "records": roles,
        },
    )
    db_hash = sha256_file(output_dir / "black_db.pkl")
    embedding_hash = sha256_file(output_dir / "black_embeddings.npz")
    manifest = {
        "library_type": "confirmed_black_voiceprint",
        "schema_version": 2,
        "created_at": now_text(),
        "source_audio_count": len(audio_files),
        "source_actor_count": len(source_actors),
        "formal_record_count": len(database["records"]),
        "formal_actor_count": len(database["identities"]),
        "review_count": len(failures),
        "role_model_version": ROLE_MODEL_VERSION,
        "role_rule_version": ROLE_RULE_VERSION,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_model_version": EMBEDDING_MODEL_VERSION,
        "embedding_dimension": EMBEDDING_DIMENSION,
        "reviewer": args.reviewer,
        "customer_channel_distribution": dict(channel_counts),
        "score_diagnostics": diagnostics,
        "black_db_sha256": db_hash,
        "black_embeddings_sha256": embedding_hash,
    }
    atomic_write_json(output_dir / "library_manifest.json", manifest)
    write_report(
        output_dir / "黑产声纹库建库报告.md",
        len(audio_files),
        len(source_actors),
        database,
        failures,
        channel_counts,
        diagnostics,
    )
    return manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="本地黑产录音角色识别与声纹建库")
    parser.add_argument("source_dir", nargs="?", default=str(DEFAULT_SOURCE))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--reviewer",
        default="user_requested_20260821",
        help="本批黑产标签确认来源或审核人标识",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    manifest = run(parse_args(argv))
    print(
        "DONE "
        f"INPUT={manifest['source_audio_count']} "
        f"FORMAL={manifest['formal_record_count']} "
        f"ACTORS={manifest['formal_actor_count']} "
        f"REVIEW={manifest['review_count']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
