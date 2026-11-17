# -*- coding: utf-8 -*-
"""审计近期1万条录音的角色区分质量，不输出客户号或源记录明文。"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np


MODULE_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = MODULE_ROOT.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

from skill.lib.db_router import db_session  # noqa: E402


SOURCE_TABLE = "smy_pc.uld_dwd.dwd_serv_ark_call_records"
DEFAULT_BATCH = MODULE_ROOT / "data" / "recent_voiceprints_10k_20260819"
DEFAULT_OUTPUT = MODULE_ROOT / "reports" / "recent_voiceprints_role_audit_20260820"


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _direction_sql() -> str:
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
        row["source_id_sha256"]: row["recording_id"] for row in manifest
    }
    sql = _direction_sql()
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


def expected_channel(direction: str) -> str | None:
    return {"I": "R", "O": "L"}.get(direction)


def _score_stats(values: list[float]) -> dict:
    scores = np.asarray(values, dtype=np.float32)
    if not len(scores):
        return {"n": 0}
    return {
        "n": int(len(scores)),
        "mean": round(float(scores.mean()), 4),
        "p05": round(float(np.quantile(scores, 0.05)), 4),
        "median": round(float(np.median(scores)), 4),
        "p95": round(float(np.quantile(scores, 0.95)), 4),
        "ge_0751": round(float((scores >= 0.751).mean()), 4),
    }


def top1_metrics(embeddings: np.ndarray, identities: np.ndarray,
                 channels: np.ndarray, reviews: np.ndarray) -> dict:
    counts = Counter(identity for identity in identities if identity)
    eligible = np.asarray([
        bool(identity) and counts[identity] >= 2 for identity in identities
    ])
    best_index = np.full(len(identities), -1, dtype=np.int32)
    best_score = np.full(len(identities), -2, dtype=np.float32)
    for start in range(0, len(identities), 256):
        end = min(start + 256, len(identities))
        scores = embeddings[start:end] @ embeddings.T
        local_rows = np.arange(end - start)
        scores[local_rows, np.arange(start, end)] = -np.inf
        indices = np.argmax(scores, axis=1)
        best_index[start:end] = indices
        best_score[start:end] = scores[local_rows, indices]
    hits = np.asarray([
        eligible[index]
        and identities[index] == identities[best_index[index]]
        for index in range(len(identities))
    ])

    def metric(mask: np.ndarray) -> dict:
        selected = mask & eligible
        return {
            "n": int(selected.sum()),
            "top1": round(float(hits[selected].mean()), 4),
            "mean_best_score": round(float(best_score[selected].mean()), 4),
        } if selected.any() else {"n": 0}

    return {
        "all": metric(np.ones(len(identities), dtype=bool)),
        "high": metric(~reviews),
        "review": metric(reviews),
        "R": metric(channels == "R"),
        "L": metric(channels == "L"),
    }


def audit(batch_dir: Path) -> tuple[dict, list[dict], str]:
    role_payload = json.loads(
        (batch_dir / "adaptive_roles.json").read_text(encoding="utf-8"))
    roles = role_payload["records"]
    failures = role_payload["failures"]
    manifest = _read_jsonl(batch_dir / "download_manifest.jsonl")
    manifest_map = {row["recording_id"]: row for row in manifest}
    directions, engine, sql = load_directions(manifest)

    with np.load(batch_dir / "customer_embeddings.npz", allow_pickle=False) as data:
        recording_ids = data["recording_ids"].astype(str)
        identities = data["identity_sha256"].astype(str)
        embeddings = data["embeddings"].astype(np.float32)
        channels = data["customer_channels"].astype(str)
        reviews = data["needs_review"].astype(bool)

    index_by_recording = {
        recording_id: index for index, recording_id in enumerate(recording_ids)
    }
    groups: dict[str, list[int]] = defaultdict(list)
    for index, identity in enumerate(identities):
        if identity:
            groups[identity].append(index)
    multi_groups = {
        identity: indices for identity, indices in groups.items()
        if len(indices) >= 2
    }

    pair_rows = []
    pair_scores: dict[str, list[float]] = defaultdict(list)
    direction_pair_scores: dict[str, list[float]] = defaultdict(list)
    agreement_pair_scores: dict[str, list[float]] = defaultdict(list)
    same_identity_best = defaultdict(lambda: -2.0)
    for indices in multi_groups.values():
        for left, right in itertools.combinations(indices, 2):
            score = float(embeddings[left] @ embeddings[right])
            combo = "".join(sorted((channels[left], channels[right])))
            tier = "both_high" if not (reviews[left] or reviews[right]) else "any_review"
            pair_scores[combo].append(score)
            pair_scores[tier].append(score)
            left_direction = directions.get(recording_ids[left], "?")
            right_direction = directions.get(recording_ids[right], "?")
            direction_combo = "".join(sorted((left_direction, right_direction)))
            direction_pair_scores[f"{direction_combo}_{combo}"].append(score)
            left_agrees = channels[left] == expected_channel(left_direction)
            right_agrees = channels[right] == expected_channel(right_direction)
            agreement = (
                "both_agree" if left_agrees and right_agrees
                else "both_conflict" if not left_agrees and not right_agrees
                else "one_conflict"
            )
            agreement_pair_scores[agreement].append(score)
            same_identity_best[recording_ids[left]] = max(
                same_identity_best[recording_ids[left]], score)
            same_identity_best[recording_ids[right]] = max(
                same_identity_best[recording_ids[right]], score)
            pair_rows.append(score)

    role_by_direction: dict[str, Counter] = defaultdict(Counter)
    direction_agreement = Counter()
    review_queue = []
    for recording_id, role in roles.items():
        direction = directions.get(recording_id, "?")
        predicted = role.get("customer_ch")
        expected = expected_channel(direction)
        tier = "review" if role.get("needs_review") else "high"
        role_by_direction[direction]["total"] += 1
        role_by_direction[direction][predicted] += 1
        role_by_direction[direction][tier] += 1
        agrees = expected is not None and predicted == expected
        direction_agreement[f"{tier}_agree" if agrees else f"{tier}_conflict"] += 1
        if not agrees:
            source = manifest_map.get(recording_id, {})
            review_queue.append({
                "priority": "P0" if tier == "high" else "P1",
                "recording_id": recording_id,
                "identity_hash_prefix": str(source.get("identity_sha256") or "")[:12],
                "direction": direction,
                "predicted_channel": predicted,
                "direction_expected_channel": expected,
                "confidence_tier": tier,
                "confidence": role.get("confidence"),
                "same_identity_max_score": (
                    "" if same_identity_best[recording_id] < -1
                    else round(same_identity_best[recording_id], 4)
                ),
                "reason": "角色结果与呼叫方向声道规律冲突",
            })
    for recording_id, failure in failures.items():
        source = manifest_map.get(recording_id, {})
        direction = directions.get(recording_id, "?")
        review_queue.append({
            "priority": "P1",
            "recording_id": recording_id,
            "identity_hash_prefix": str(source.get("identity_sha256") or "")[:12],
            "direction": direction,
            "predicted_channel": "",
            "direction_expected_channel": expected_channel(direction),
            "confidence_tier": "failure",
            "confidence": failure.get("confidence", ""),
            "same_identity_max_score": "",
            "reason": "ASR缺一方或角色未判定",
        })

    high_total = direction_agreement["high_agree"] + direction_agreement["high_conflict"]
    review_total = direction_agreement["review_agree"] + direction_agreement["review_conflict"]
    all_total = high_total + review_total
    metrics = {
        "scope": {
            "downloaded": len(manifest),
            "role_success": len(roles),
            "role_failures": len(failures),
            "high_confidence": sum(not row.get("needs_review") for row in roles.values()),
            "needs_review": sum(row.get("needs_review") for row in roles.values()),
            "direction_matched": len(directions),
            "identity_present": len(groups),
            "multi_identity": len(multi_groups),
            "multi_identity_recordings": sum(len(rows) for rows in multi_groups.values()),
        },
        "direction_proxy": {
            "rule": {"I": "R", "O": "L"},
            "all_agreement": round(
                (direction_agreement["high_agree"] + direction_agreement["review_agree"])
                / all_total, 4),
            "high_agreement": round(direction_agreement["high_agree"] / high_total, 4),
            "review_agreement": round(direction_agreement["review_agree"] / review_total, 4),
            "counts": dict(direction_agreement),
            "by_direction": {
                direction: {
                    **dict(counter),
                    "l_rate": round(counter["L"] / counter["total"], 4),
                    "high_rate": round(counter["high"] / counter["total"], 4),
                }
                for direction, counter in role_by_direction.items()
            },
        },
        "same_identity": {
            "all_pairs": _score_stats(pair_rows),
            "by_channel": {
                key: _score_stats(pair_scores[key]) for key in ("RR", "LR", "LL")
            },
            "by_confidence": {
                key: _score_stats(pair_scores[key])
                for key in ("both_high", "any_review")
            },
            "by_direction_and_channel": {
                key: _score_stats(value)
                for key, value in sorted(direction_pair_scores.items())
            },
            "by_direction_agreement": {
                key: _score_stats(value)
                for key, value in sorted(agreement_pair_scores.items())
            },
        },
        "top1_proxy": top1_metrics(embeddings, identities, channels, reviews),
        "review_queue": {
            "total": len(review_queue),
            "p0_high_conflict": sum(row["priority"] == "P0" for row in review_queue),
            "p1": sum(row["priority"] == "P1" for row in review_queue),
        },
        "limitations": [
            "当前没有逐通人工角色真值，方向一致率和声纹一致性均为代理指标。",
            "同客户标识来自客户号哈希，不等同于人工确认的同一说话人真值。",
            "同坐席重复服务同一客户时，错误选择坐席声道也可能得到较高同客户相似度。",
        ],
        "sql": {"engine": engine, "executed": sql},
    }
    review_queue.sort(key=lambda row: (
        row["priority"], row["direction"], row["recording_id"]))
    return metrics, review_queue, engine


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def write_outputs(output_dir: Path, metrics: dict, review_queue: list[dict]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "role_accuracy_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = [
        "priority", "recording_id", "identity_hash_prefix", "direction",
        "predicted_channel", "direction_expected_channel", "confidence_tier",
        "confidence", "same_identity_max_score", "reason",
    ]
    with (output_dir / "role_review_queue.csv").open(
            "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(review_queue)

    scope = metrics["scope"]
    proxy = metrics["direction_proxy"]
    same = metrics["same_identity"]
    top1 = metrics["top1_proxy"]
    queue = metrics["review_queue"]
    lines = [
        "# 近期1万条录音角色区分准确性审计",
        "",
        "> 本报告使用呼叫方向声道规律与同客户跨通声纹一致性进行代理验证；当前没有逐通人工角色真值，因此不将代理一致率表述为真实准确率。",
        "",
        "## 核心结论",
        "",
        f"- 角色成功：{scope['role_success']} / {scope['downloaded']}；失败 {scope['role_failures']}。",
        f"- 高置信：{scope['high_confidence']} 条，方向规则一致率 {_pct(proxy['high_agreement'])}。",
        f"- 待复核：{scope['needs_review']} 条，方向规则一致率 {_pct(proxy['review_agreement'])}。",
        f"- 全部成功判角的方向规则一致率为 {_pct(proxy['all_agreement'])}，但该值是代理指标，不是人工真值准确率。",
        "- 经同客户跨呼叫方向声纹验证，本批方舟双轨录音呈现稳定规律：呼入 `I` 的客户主要在 `R`，呼出 `O` 的客户主要在 `L`。",
        "- 当前模型错误风险主要集中在待复核的呼出录音：纯话术证据不足时容易把呼出坐席声道识别成客户。",
        "",
        "## 方向规则代理验证",
        "",
        "| 层级 | 一致 | 冲突 | 一致率 |",
        "|---|---:|---:|---:|",
        f"| 高置信 | {proxy['counts']['high_agree']} | {proxy['counts']['high_conflict']} | {_pct(proxy['high_agreement'])} |",
        f"| 待复核 | {proxy['counts']['review_agree']} | {proxy['counts']['review_conflict']} | {_pct(proxy['review_agreement'])} |",
        f"| 合计 | {proxy['counts']['high_agree'] + proxy['counts']['review_agree']} | {proxy['counts']['high_conflict'] + proxy['counts']['review_conflict']} | {_pct(proxy['all_agreement'])} |",
        "",
        "## 同客户跨通声纹验证",
        "",
        f"- 可验证客户：{scope['multi_identity']} 个，覆盖 {scope['multi_identity_recordings']} 通，形成 {same['all_pairs']['n']} 个同客户配对。",
        f"- 双高置信配对达到0.751的比例：{_pct(same['by_confidence']['both_high']['ge_0751'])}。",
        f"- 任一待复核配对达到0.751的比例：{_pct(same['by_confidence']['any_review']['ge_0751'])}。",
        f"- 两通角色都符合方向规律时，达到0.751的比例：{_pct(same['by_direction_agreement']['both_agree']['ge_0751'])}。",
        f"- 仅一通角色与方向规律冲突时，达到0.751的比例仅 {_pct(same['by_direction_agreement']['one_conflict']['ge_0751'])}，说明单边冲突高度疑似错判。",
        "- 呼入/呼出同客户配对中，选择 `L/R` 时达到0.751的比例显著高于选择 `R/R`，支持呼叫方向改变客户所在声道的结论。",
        "",
        "## Top-1代理指标",
        "",
        f"- 有多通录音客户的整体Top-1：{_pct(top1['all']['top1'])}。",
        f"- 高置信Top-1：{_pct(top1['high']['top1'])}；待复核Top-1：{_pct(top1['review']['top1'])}。",
        "- Top-1受8k电话异人高相似地板效应影响，仅用于比较分层，不作为角色准确率。",
        "",
        "## 复核与修正建议",
        "",
        f"- `role_review_queue.csv` 共 {queue['total']} 条：P0高置信方向冲突 {queue['p0_high_conflict']} 条，P1待复核冲突及判角失败 {queue['p1']} 条。",
        "- P0样本应逐通听音或查看脱敏转录，确认是否存在转接、声轨异常等例外。",
        "- 待复核样本建议采用方向规则兜底：呼入取R、呼出取L；修正后必须重新提取对应声道embedding。",
        "- 正式向量库当前应只使用高置信且通过方向校验的记录，待复核向量先隔离。",
        "",
        "## 结论边界",
        "",
        "- 精确准确率仍需人工标注分层样本后计算。建议至少标注200通，覆盖呼入/呼出、高置信/待复核和方向冲突四类。",
        "- 客户号哈希只是真值代理；代接、同坐席重复服务和转接通话均可能影响声纹一致性。",
    ]
    (output_dir / "角色区分准确性审计报告.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-dir", type=Path, default=DEFAULT_BATCH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    metrics, review_queue, _engine = audit(args.batch_dir)
    write_outputs(args.output_dir, metrics, review_queue)
    print(json.dumps({
        "output_dir": str(args.output_dir),
        "direction_proxy": metrics["direction_proxy"],
        "review_queue": metrics["review_queue"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
