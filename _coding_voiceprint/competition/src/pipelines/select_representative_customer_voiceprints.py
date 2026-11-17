# -*- coding: utf-8 -*-
"""从每个双录音客户中筛选代表性客户声纹并导入平台客户库。

筛选依据:
  - embedding 质量模型分数代表清晰度和可检索性；
  - 客户侧有效语音时长代表可用声音信息；
  - 客户侧 ASR 字数作为有效对话量的辅助指标。

该脚本只写本地平台 JSON 状态和向量文件，不执行数据库 DDL/DML。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np


MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from voiceprint_platform.config import load_platform_config  # noqa: E402
from voiceprint_platform.store import JsonStateStore, now_text  # noqa: E402


DEFAULT_MATRIX = (
    MODULE_ROOT
    / "reports"
    / "kesu_customer_refresh_role_text_v1_20260820"
    / "customer_nxn_matrix.npz"
)
DEFAULT_QUALITY = (
    MODULE_ROOT
    / "reports"
    / "plda_current_role_min3_20260822"
    / "embedding_quality_scores.csv"
)
DEFAULT_OUTPUT_DIR = (
    MODULE_ROOT
    / "data"
    / "processed"
    / "customer_voiceprint_selected_472_20260822"
)
EMBEDDING_DIMENSION = 192


def identity_id(value: str, prefix: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError("业务主键不能为空")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:24]}"


def load_quality_rows(path: Path) -> dict[str, dict]:
    rows = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "recording_id",
            "identity",
            "quality_score",
            "log_customer_speech_seconds",
            "log_customer_asr_chars",
            "role_margin",
            "role_stage_count",
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"质量评分CSV缺少字段: {sorted(missing)}")
        for row in reader:
            recording_id = str(row["recording_id"]).strip()
            if recording_id:
                rows[recording_id] = row
    return rows


def as_float(value: object, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def row_metrics(row: dict) -> dict:
    speech_seconds = math.expm1(as_float(row.get("log_customer_speech_seconds")))
    asr_chars = math.expm1(as_float(row.get("log_customer_asr_chars")))
    return {
        "quality_score": as_float(row.get("quality_score")),
        "customer_speech_seconds": max(0.0, speech_seconds),
        "customer_asr_chars": max(0.0, asr_chars),
        "role_margin": as_float(row.get("role_margin")),
        "role_stage_count": as_float(row.get("role_stage_count"), 1.0),
    }


def representative_score(metrics: dict) -> float:
    duration_score = min(metrics["customer_speech_seconds"] / 60.0, 1.0)
    char_score = min(metrics["customer_asr_chars"] / 120.0, 1.0)
    return (
        0.65 * metrics["quality_score"]
        + 0.25 * duration_score
        + 0.10 * char_score
    )


def load_matrix_rows(matrix_path: Path, quality_rows: dict[str, dict]) -> list[dict]:
    with np.load(matrix_path, allow_pickle=False) as data:
        recording_ids = data["recording_ids"].astype(str)
        identities = data["identities"].astype(str)
        embeddings = data["embeddings"].astype(np.float32)
        trusted_mask = (
            data["trusted_mask"].astype(bool)
            if "trusted_mask" in data.files
            else np.ones(len(recording_ids), dtype=bool)
        )
    if embeddings.shape[1] != EMBEDDING_DIMENSION:
        raise ValueError(f"embedding维度异常: {embeddings.shape}")

    rows = []
    for index, recording_id in enumerate(recording_ids):
        if not trusted_mask[index]:
            continue
        quality_row = quality_rows.get(str(recording_id))
        if quality_row is None:
            continue
        metrics = row_metrics(quality_row)
        rows.append(
            {
                "index": index,
                "recording_id": str(recording_id),
                "cust_no": str(identities[index]),
                "embedding": embeddings[index],
                **metrics,
                "representative_score": representative_score(metrics),
            }
        )
    return rows


def select_representatives(rows: list[dict]) -> tuple[list[dict], dict]:
    groups = defaultdict(list)
    for row in rows:
        groups[row["cust_no"]].append(row)

    selected = []
    skipped = {
        "not_two_recordings": 0,
        "not_two_recordings_identities": [],
    }
    for cust_no, items in sorted(groups.items()):
        if len(items) != 2:
            skipped["not_two_recordings"] += 1
            skipped["not_two_recordings_identities"].append(cust_no)
            continue
        ranked = sorted(
            items,
            key=lambda item: (
                item["representative_score"],
                item["quality_score"],
                item["customer_speech_seconds"],
                item["customer_asr_chars"],
                item["role_margin"],
                item["recording_id"],
            ),
            reverse=True,
        )
        winner, alternate = ranked[0], ranked[1]
        selected.append({**winner, "alternate": alternate})
    return selected, skipped


def stable_id(prefix: str, *parts: object, length: int = 24) -> str:
    text = "::".join(str(part) for part in parts)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:length]}"


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def write_selection_outputs(output_dir: Path, selected: list[dict], summary: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "selected_customer_voiceprints.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = [
            "cust_no",
            "selected_recording_id",
            "alternate_recording_id",
            "representative_score",
            "quality_score",
            "customer_speech_seconds",
            "customer_asr_chars",
            "role_margin",
            "alternate_representative_score",
            "alternate_quality_score",
            "alternate_customer_speech_seconds",
            "alternate_customer_asr_chars",
            "selection_reason",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in selected:
            alt = row["alternate"]
            writer.writerow(
                {
                    "cust_no": row["cust_no"],
                    "selected_recording_id": row["recording_id"],
                    "alternate_recording_id": alt["recording_id"],
                    "representative_score": round(row["representative_score"], 6),
                    "quality_score": round(row["quality_score"], 6),
                    "customer_speech_seconds": round(row["customer_speech_seconds"], 3),
                    "customer_asr_chars": round(row["customer_asr_chars"], 1),
                    "role_margin": round(row["role_margin"], 6),
                    "alternate_representative_score": round(alt["representative_score"], 6),
                    "alternate_quality_score": round(alt["quality_score"], 6),
                    "alternate_customer_speech_seconds": round(alt["customer_speech_seconds"], 3),
                    "alternate_customer_asr_chars": round(alt["customer_asr_chars"], 1),
                    "selection_reason": (
                        "按0.65*质量分+0.25*有效语音时长+0.10*ASR字数综合分选择"
                    ),
                }
            )

    np.savez_compressed(
        output_dir / "selected_customer_voiceprints.npz",
        cust_no=np.asarray([row["cust_no"] for row in selected]),
        recording_ids=np.asarray([row["recording_id"] for row in selected]),
        alternate_recording_ids=np.asarray([row["alternate"]["recording_id"] for row in selected]),
        representative_scores=np.asarray([row["representative_score"] for row in selected], dtype=np.float32),
        quality_scores=np.asarray([row["quality_score"] for row in selected], dtype=np.float32),
        customer_speech_seconds=np.asarray([row["customer_speech_seconds"] for row in selected], dtype=np.float32),
        customer_asr_chars=np.asarray([row["customer_asr_chars"] for row in selected], dtype=np.float32),
        embeddings=np.stack([row["embedding"] for row in selected]).astype(np.float32),
    )

    atomic_write_json(output_dir / "import_summary.json", summary)
    report = [
        "# 客户代表声纹筛选与导入报告",
        "",
        f"- 生成时间: {summary['generated_at']}",
        f"- 候选客户数: {summary['candidate_identities']}",
        f"- 双录音客户数: {summary['two_recording_identities']}",
        f"- 已选择模板数: {summary['selected_templates']}",
        f"- 平台导入模板数: {summary['imported_templates']}",
        f"- 保留客户主键: {'是' if summary['preserve_customer_key'] else '否'}",
        "",
        "## 筛选规则",
        "",
        "综合分 = 0.65 * embedding质量分 + 0.25 * min(客户有效语音秒数/60, 1) + 0.10 * min(客户ASR字数/120, 1)。",
        "每个客户仅在两条录音内部比较，综合分高者作为客户声纹库模板。",
        "",
        "## 输出文件",
        "",
        "- `selected_customer_voiceprints.csv`: 含客户主键、入选录音和落选录音指标。",
        "- `selected_customer_voiceprints.npz`: 含客户主键、入选录音ID、指标和192维embedding。",
        "- `import_summary.json`: 本次导入汇总。",
    ]
    (output_dir / "客户代表声纹筛选与导入报告.md").write_text(
        "\n".join(report) + "\n", encoding="utf-8"
    )


def import_to_platform(
    selected: list[dict],
    config: dict,
    *,
    template_status: str,
    dry_run: bool,
) -> dict:
    if template_status not in {"active", "pending"}:
        raise ValueError("template_status 必须为 active 或 pending")
    if dry_run:
        return {"customers_upserted": 0, "templates_upserted": 0, "dry_run": True}

    store = JsonStateStore(config["storage_path"])
    created = now_text()
    customers_upserted = 0
    templates_upserted = 0
    recordings_upserted = 0

    for row in selected:
        cust_no = row["cust_no"]
        customer_id = identity_id(cust_no, "cust")
        recording_id = stable_id("rec_import", cust_no, row["recording_id"])
        template_id = stable_id("cust_tpl_selected", cust_no, row["recording_id"], length=20)
        vector_path = store.save_vector("customer", template_id, row["embedding"])
        quality = {
            "score": row["quality_score"],
            "representative_score": row["representative_score"],
            "customer_speech_seconds": row["customer_speech_seconds"],
            "customer_asr_chars": row["customer_asr_chars"],
            "role_margin": row["role_margin"],
            "selection_rule": "0.65_quality_0.25_effective_speech_0.10_asr_chars",
        }

        def upsert(state: dict) -> None:
            nonlocal customers_upserted, templates_upserted, recordings_upserted
            current_customer = state["customers"].get(customer_id, {})
            state["customers"][customer_id] = {
                **current_customer,
                "id": customer_id,
                "customer_key": cust_no,
                "cust_no": cust_no,
                "status": "active" if template_status == "active" else "pending_enrollment",
                "source": "selected_two_recording_representative_import",
                "active_template_count": current_customer.get("active_template_count", 0),
                "pending_template_count": current_customer.get("pending_template_count", 0),
                "created_at": current_customer.get("created_at", created),
                "updated_at": now_text(),
            }
            state["recordings"][recording_id] = {
                **state["recordings"].get(recording_id, {}),
                "id": recording_id,
                "kind": "customer_library_import",
                "customer_id": customer_id,
                "customer_key": cust_no,
                "cust_no": cust_no,
                "source_recording_id": row["recording_id"],
                "alternate_recording_id": row["alternate"]["recording_id"],
                "status": "completed",
                "quality": quality,
                "vector_path": vector_path,
                "created_at": state["recordings"].get(recording_id, {}).get("created_at", created),
                "updated_at": now_text(),
            }
            state["customer_templates"][template_id] = {
                **state["customer_templates"].get(template_id, {}),
                "id": template_id,
                "customer_id": customer_id,
                "customer_key": cust_no,
                "cust_no": cust_no,
                "recording_id": recording_id,
                "source_recording_id": row["recording_id"],
                "alternate_recording_id": row["alternate"]["recording_id"],
                "vector_path": vector_path,
                "status": template_status,
                "quality": quality,
                "model_version": config["models"]["embedding_model_version"],
                "created_at": state["customer_templates"].get(template_id, {}).get("created_at", created),
                "updated_at": now_text(),
            }
            customer_templates = [
                item
                for item in state["customer_templates"].values()
                if item.get("customer_id") == customer_id
            ]
            active = sum(item.get("status") == "active" for item in customer_templates)
            pending = sum(item.get("status") == "pending" for item in customer_templates)
            state["customers"][customer_id]["active_template_count"] = active
            state["customers"][customer_id]["pending_template_count"] = pending
            state["customers"][customer_id]["status"] = (
                "active" if active else "pending_enrollment"
            )
            customers_upserted += 1
            recordings_upserted += 1
            templates_upserted += 1

        store.mutate(upsert)

    store.append_audit(
        "selected_customer_voiceprints_imported",
        "customer_library",
        {
            "template_count": templates_upserted,
            "preserve_customer_key": True,
            "template_status": template_status,
        },
    )
    return {
        "customers_upserted": customers_upserted,
        "recordings_upserted": recordings_upserted,
        "templates_upserted": templates_upserted,
        "dry_run": False,
    }


def build_summary(
    *,
    rows: list[dict],
    selected: list[dict],
    skipped: dict,
    matrix_path: Path,
    quality_path: Path,
    output_dir: Path,
    import_result: dict,
    template_status: str,
) -> dict:
    identities = {row["cust_no"] for row in rows}
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "matrix_path": str(matrix_path),
        "quality_scores_path": str(quality_path),
        "output_dir": str(output_dir),
        "candidate_records": len(rows),
        "candidate_identities": len(identities),
        "two_recording_identities": len(selected),
        "selected_templates": len(selected),
        "skipped": skipped,
        "template_status": template_status,
        "preserve_customer_key": True,
        "imported_customers": import_result["customers_upserted"],
        "imported_recordings": import_result.get("recordings_upserted", 0),
        "imported_templates": import_result["templates_upserted"],
        "dry_run": import_result["dry_run"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--quality-scores", type=Path, default=DEFAULT_QUALITY)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--template-status", choices=["active", "pending"], default="active")
    parser.add_argument("--expected-count", type=int, default=472)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    quality_rows = load_quality_rows(args.quality_scores)
    rows = load_matrix_rows(args.matrix, quality_rows)
    selected, skipped = select_representatives(rows)
    if args.expected_count and len(selected) != args.expected_count:
        raise RuntimeError(
            f"双录音客户数不符合预期: actual={len(selected)}, expected={args.expected_count}"
        )
    config = load_platform_config(args.config) if args.config else load_platform_config()
    import_result = import_to_platform(
        selected,
        config,
        template_status=args.template_status,
        dry_run=args.dry_run,
    )
    summary = build_summary(
        rows=rows,
        selected=selected,
        skipped=skipped,
        matrix_path=args.matrix,
        quality_path=args.quality_scores,
        output_dir=args.output_dir,
        import_result=import_result,
        template_status=args.template_status,
    )
    write_selection_outputs(args.output_dir, selected, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
