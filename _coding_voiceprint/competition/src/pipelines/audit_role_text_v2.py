# -*- coding: utf-8 -*-
"""审计新文本角色模型v2结果中的疑似角色误判。

使用呼叫方向声道规律作为代理校验：呼入 I 客户侧通常在 R，呼出 O 客户侧
通常在 L。该规则不是人工真值，只用于筛出需要复核的样本。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = MODULE_ROOT.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

from skill.lib.db_router import db_session  # noqa: E402


SOURCE_TABLE = "smy_pc.uld_dwd.dwd_serv_ark_call_records"
DEFAULT_BATCH = MODULE_ROOT / "data" / "recent_voiceprints_10k_20260819"
DEFAULT_V2 = MODULE_ROOT / "data" / "recent_voiceprints_10k_role_text_v2"
DEFAULT_OUTPUT = MODULE_ROOT / "reports" / "role_text_v2_audit"


def expected_channel(direction: str) -> str | None:
    return {"I": "R", "O": "L"}.get(str(direction or "").strip())


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def direction_sql() -> str:
    return f"""
SELECT id, direction
FROM (
    SELECT id, direction, record_file_url, begin_time,
           ROW_NUMBER() OVER (
               PARTITION BY record_file_url
               ORDER BY begin_time DESC, id DESC
           ) AS url_rank
    FROM {SOURCE_TABLE}
    WHERE record_file_url IS NOT NULL
      AND TRIM(record_file_url) <> ''
      AND begin_time >= '2026-02-19 00:00:00'
      AND CAST(NULLIF(TRIM(call_time_length), '') AS DOUBLE) BETWEEN 20 AND 180
      AND LOWER(TRIM(COALESCE(is_double_track, '')))
          IN ('1', 'y', 'yes', 'true')
) ranked
WHERE url_rank = 1
ORDER BY begin_time DESC, id DESC
LIMIT 12000
""".strip()


def load_directions(manifest: list[dict]) -> tuple[dict[str, str], str, str]:
    source_to_recording = {
        row.get("source_id_sha256"): row.get("recording_id")
        for row in manifest
        if row.get("source_id_sha256") and row.get("recording_id")
    }
    sql = direction_sql()
    with db_session(SOURCE_TABLE) as (_conn, cursor, engine):
        cursor.execute(sql)
        rows = cursor.fetchall()
    directions = {}
    for row in rows:
        source_hash = hashlib.sha256(
            str(row.get("id") or "").strip().encode("utf-8")
        ).hexdigest()
        recording_id = source_to_recording.get(source_hash)
        if recording_id:
            directions[recording_id] = str(row.get("direction") or "")
    return directions, engine, sql


def audit(batch_dir: Path, v2_dir: Path) -> tuple[dict, list[dict]]:
    manifest = read_jsonl(batch_dir / "download_manifest.jsonl")
    role_payload = json.loads((v2_dir / "role_results.json").read_text(encoding="utf-8"))
    roles = role_payload.get("records", {})
    failures = json.loads((v2_dir / "role_failures.json").read_text(encoding="utf-8")) if (v2_dir / "role_failures.json").exists() else {"failures": {}}
    directions, engine, sql = load_directions(manifest)

    counters = Counter()
    by_direction = {}
    review_rows = []
    for recording_id, role in sorted(roles.items()):
        direction = directions.get(recording_id, "")
        expected = expected_channel(direction)
        predicted = role.get("customer_ch")
        status = role.get("status")
        needs_review = bool(role.get("needs_review"))
        margin = role.get("margin")
        agree = expected is not None and predicted == expected
        tier = "formal" if role.get("formal_index_eligible") else "non_formal"
        counters["roles"] += 1
        counters[f"status_{status}"] += 1
        counters[f"direction_{direction or 'missing'}"] += 1
        counters[f"{tier}_total"] += 1
        if expected is None:
            counters[f"{tier}_direction_missing"] += 1
        elif agree:
            counters[f"{tier}_agree"] += 1
        else:
            counters[f"{tier}_conflict"] += 1
            review_rows.append({
                "priority": "P0" if role.get("formal_index_eligible") else "P1",
                "recording_id": recording_id,
                "direction": direction,
                "expected_customer_ch": expected,
                "predicted_customer_ch": predicted or "",
                "status": status or "",
                "needs_review": needs_review,
                "formal_index_eligible": bool(role.get("formal_index_eligible")),
                "margin": "" if margin is None else margin,
                "left_agent_probability": role.get("left_agent_probability", ""),
                "right_agent_probability": role.get("right_agent_probability", ""),
                "left_chars": (role.get("left_summary") or {}).get("char_count", ""),
                "right_chars": (role.get("right_summary") or {}).get("char_count", ""),
                "reason": "新角色结果与呼叫方向声道代理规则冲突",
            })
        direction_key = direction or "missing"
        by_direction.setdefault(direction_key, Counter())
        by_direction[direction_key][predicted or "None"] += 1
        by_direction[direction_key]["total"] += 1

    for recording_id, failure in sorted((failures.get("failures") or {}).items()):
        counters["failures"] += 1
        review_rows.append({
            "priority": "P1",
            "recording_id": recording_id,
            "direction": directions.get(recording_id, ""),
            "expected_customer_ch": expected_channel(directions.get(recording_id, "")) or "",
            "predicted_customer_ch": "",
            "status": "failure",
            "needs_review": True,
            "formal_index_eligible": False,
            "margin": "",
            "left_agent_probability": "",
            "right_agent_probability": "",
            "left_chars": "",
            "right_chars": "",
            "reason": failure.get("error", "角色处理失败"),
        })

    def rate(num: int, den: int) -> float | None:
        return round(num / den, 6) if den else None

    metrics = {
        "scope": {
            "v2_dir": str(v2_dir),
            "role_records": counters["roles"],
            "role_failures": counters["failures"],
            "direction_matched": sum(1 for rid in roles if rid in directions),
        },
        "status_counts": {
            key.replace("status_", ""): value
            for key, value in counters.items()
            if key.startswith("status_")
        },
        "direction_proxy": {
            "rule": {"I": "R", "O": "L"},
            "formal_total": counters["formal_total"],
            "formal_conflict": counters["formal_conflict"],
            "formal_direction_missing": counters["formal_direction_missing"],
            "formal_agreement_rate": rate(
                counters["formal_agree"],
                counters["formal_agree"] + counters["formal_conflict"],
            ),
            "non_formal_total": counters["non_formal_total"],
            "non_formal_conflict": counters["non_formal_conflict"],
            "non_formal_direction_missing": counters["non_formal_direction_missing"],
            "non_formal_agreement_rate": rate(
                counters["non_formal_agree"],
                counters["non_formal_agree"] + counters["non_formal_conflict"],
            ),
            "review_queue": len(review_rows),
            "by_direction": {key: dict(value) for key, value in sorted(by_direction.items())},
        },
        "sql": {
            "engine": engine,
            "executed": sql,
        },
        "limitations": [
            "呼叫方向声道规律是代理校验，不是逐通人工真值。",
            "方向冲突需要听音或脱敏ASR正文复核后才能判定为真实误判。",
        ],
    }
    review_rows.sort(key=lambda row: (row["priority"], row["direction"], row["recording_id"]))
    return metrics, review_rows


def write_outputs(output_dir: Path, metrics: dict, review_rows: list[dict]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "role_text_v2_audit_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = [
        "priority", "recording_id", "direction", "expected_customer_ch",
        "predicted_customer_ch", "status", "needs_review", "formal_index_eligible",
        "margin", "left_agent_probability", "right_agent_probability",
        "left_chars", "right_chars", "reason",
    ]
    with (output_dir / "role_text_v2_review_queue.csv").open(
        "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(review_rows)

    proxy = metrics["direction_proxy"]
    lines = [
        "# 新角色模型v2角色误判代理审计",
        "",
        "> 使用呼叫方向声道规律进行代理校验：呼入 `I` 期望客户在 `R`，呼出 `O` 期望客户在 `L`。该结果不是人工真值。",
        "",
        "## 结论",
        "",
        f"- 角色记录：{metrics['scope']['role_records']}",
        f"- 方向匹配：{metrics['scope']['direction_matched']}",
        f"- 正式入选样本：{proxy['formal_total']}，方向冲突：{proxy['formal_conflict']}，一致率：{proxy['formal_agreement_rate']}",
        f"- 非正式入选样本：{proxy['non_formal_total']}，方向冲突：{proxy['non_formal_conflict']}，一致率：{proxy['non_formal_agreement_rate']}",
        f"- 复核队列：{proxy['review_queue']} 条，详见 `role_text_v2_review_queue.csv`。",
        "",
        "## 边界",
        "",
        "- 方向冲突只能说明疑似角色误判或声轨异常，不能直接定性。",
        "- 最终是否误判需结合人工听音、脱敏ASR正文、转接/三方场景和业务元数据确认。",
    ]
    (output_dir / "新角色模型v2角色误判代理审计.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-dir", type=Path, default=DEFAULT_BATCH)
    parser.add_argument("--v2-dir", type=Path, default=DEFAULT_V2)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    metrics, review_rows = audit(args.batch_dir, args.v2_dir)
    write_outputs(args.output_dir, metrics, review_rows)
    print(json.dumps({
        "output_dir": str(args.output_dir),
        "scope": metrics["scope"],
        "direction_proxy": metrics["direction_proxy"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
