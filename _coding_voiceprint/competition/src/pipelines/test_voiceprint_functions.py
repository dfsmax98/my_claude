# -*- coding: utf-8 -*-
"""执行黑产声纹库级联与跨客户团伙聚类功能测试。"""
import argparse
import csv
import json
import math
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from common import audio_io, embedding, vpdb
from common.gang_cluster import cluster_embeddings, evaluate_clusters

SEED = 20260810
SELF_THRESHOLD = 0.80
TARGET_QUERY_FAR = 0.01
BLACK_DB_SIZES = (10, 30, 50, 100)
GANG_SIZES = (3, 3, 4, 4, 5)


def _normalize(vectors):
    vectors = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.maximum(norms, 1e-12)


def _json_value(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"无法序列化类型: {type(value).__name__}")


def write_json(path, payload):
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_value),
        encoding="utf-8")


def write_csv(path, rows, fieldnames=None):
    rows = list(rows)
    if fieldnames is None:
        fieldnames = list(rows[0]) if rows else []
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_dataset(path):
    with np.load(path, allow_pickle=False) as data:
        payload = {key: data[key].copy() for key in data.files}
    payload["embeddings"] = _normalize(payload["embeddings"])
    grouped = defaultdict(list)
    for index, identity in enumerate(payload["identities"].astype(str)):
        grouped[identity].append(index)
    for identity in grouped:
        grouped[identity].sort(
            key=lambda idx: str(payload["recording_ids"][idx]))
    return payload, dict(grouped)


def select_far_threshold(cases, target_far=TARGET_QUERY_FAR):
    """选择满足整次非黑查询FAR约束的最低阈值，以保留最大召回。"""
    negatives = [case for case in cases if case["case_type"] != "black"]
    positives = [case for case in cases if case["case_type"] == "black"]
    searched_scores = [
        float(case["black_top1_score"])
        for case in cases
        if case.get("black_search_invoked", True)
        and case.get("black_top1_score") not in (None, "")
    ]
    candidates = sorted(set(searched_scores)) or [1.000001]
    candidates.extend(
        float(np.nextafter(score, math.inf)) for score in set(searched_scores))
    candidates.append(1.000001)

    feasible = []
    for threshold in sorted(set(candidates)):
        false_hits = sum(
            case.get("black_search_invoked", True)
            and case.get("black_top1_score") is not None
            and float(case["black_top1_score"]) >= threshold
            for case in negatives)
        true_hits = sum(
            case.get("black_search_invoked", True)
            and case.get("black_top1_score") is not None
            and float(case["black_top1_score"]) >= threshold
            and case.get("black_top1_actor") == case.get("query_identity")
            for case in positives)
        far = false_hits / len(negatives) if negatives else 0.0
        recall = true_hits / len(positives) if positives else 0.0
        if far <= target_far + 1e-12:
            feasible.append((threshold, recall, far, false_hits))
    if not feasible:
        return 1.000001
    best_recall = max(item[1] for item in feasible)
    return float(min(item[0] for item in feasible if item[1] == best_recall))


def _black_db(dataset, grouped, actor_ids):
    records = []
    for actor in actor_ids:
        index = grouped[actor][0]
        records.append({
            "id": str(dataset["recording_ids"][index]),
            "actor_id": actor,
            "emb": dataset["embeddings"][index],
        })
    return {
        "model": "cam++",
        "schema_version": 2,
        "records": records,
    }


def _evaluate_black_case(dataset, grouped, black_db, split, db_size,
                         repeat, case_type, query_identity, claimed_identity):
    query_index = grouped[query_identity][1]
    claim_index = grouped[claimed_identity][0]
    query = dataset["embeddings"][query_index]
    claim = dataset["embeddings"][claim_index]
    self_score = float(np.dot(query, claim))
    mismatch = self_score < SELF_THRESHOLD
    # 全部查询做离线反事实检索，以独立测量1:N排序能力；线上级联判定仍受mismatch约束。
    started = time.perf_counter()
    hits = vpdb.search_by_identity(
        query, black_db, id_key="actor_id", topk=5)
    elapsed_ms = (time.perf_counter() - started) * 1000
    top1 = hits[0] if hits else (None, None, None)
    return {
        "split": split,
        "db_size": db_size,
        "repeat": repeat,
        "case_type": case_type,
        "query_identity": query_identity,
        "query_recording": str(dataset["recording_ids"][query_index]),
        "claimed_identity": claimed_identity,
        "claimed_recording": str(dataset["recording_ids"][claim_index]),
        "self_score": self_score,
        "self_mismatch": bool(mismatch),
        "black_search_invoked": bool(mismatch),
        "black_top1_actor": top1[0],
        "black_top1_score": top1[1],
        "black_top1_recording": top1[2],
        "black_rank": next(
            (rank for rank, hit in enumerate(hits, 1)
             if hit[0] == query_identity), None),
        "black_search_ms": elapsed_ms,
    }


def build_black_cases(dataset, grouped, pool, split, repeats, seed):
    rows = []
    for db_size in BLACK_DB_SIZES:
        for repeat in range(repeats):
            rng = np.random.default_rng(seed + db_size * 1000 + repeat)
            identities = np.asarray(pool, dtype=str).copy()
            rng.shuffle(identities)
            nonblack_count = min(25, (len(identities) - db_size) // 2)
            if nonblack_count < 1:
                raise ValueError(f"{split}身份池不足以测试黑产库规模{db_size}")
            actors = identities[:db_size].tolist()
            victims = identities[db_size:db_size + nonblack_count].tolist()
            ordinary = identities[
                db_size + nonblack_count:db_size + nonblack_count * 2].tolist()
            black_db = _black_db(dataset, grouped, actors)

            for index, actor in enumerate(actors):
                rows.append(_evaluate_black_case(
                    dataset, grouped, black_db, split, db_size, repeat,
                    "black", actor, victims[index % len(victims)]))
            for index, identity in enumerate(ordinary):
                rows.append(_evaluate_black_case(
                    dataset, grouped, black_db, split, db_size, repeat,
                    "ordinary", identity, victims[index % len(victims)]))
            for identity in victims:
                rows.append(_evaluate_black_case(
                    dataset, grouped, black_db, split, db_size, repeat,
                    "genuine", identity, identity))
    return rows


def _ratio(numerator, denominator):
    return float(numerator / denominator) if denominator else 0.0


def summarize_black_cases(cases, thresholds):
    output = {}
    for db_size in BLACK_DB_SIZES:
        rows = [row for row in cases
                if row["split"] == "evaluation" and row["db_size"] == db_size]
        threshold = thresholds[db_size]
        by_type = {
            kind: [row for row in rows if row["case_type"] == kind]
            for kind in ("black", "ordinary", "genuine")
        }
        black = by_type["black"]
        ordinary = by_type["ordinary"]
        genuine = by_type["genuine"]
        nonblack = ordinary + genuine
        searches = [row for row in rows if row["black_search_invoked"]]

        def is_black_hit(row):
            return (
                row["black_search_invoked"]
                and row["black_top1_actor"] == row["query_identity"]
                and row["black_top1_score"] >= threshold)

        def is_false_hit(row):
            return (
                row["black_search_invoked"]
                and row["black_top1_score"] >= threshold)

        latencies = sorted(float(row["black_search_ms"]) for row in searches)
        output[str(db_size)] = {
            "black_threshold": threshold,
            "target_query_far": TARGET_QUERY_FAR,
            "cases": {key: len(value) for key, value in by_type.items()},
            "self_mismatch_rate": {
                key: _ratio(sum(row["self_mismatch"] for row in value), len(value))
                for key, value in by_type.items()
            },
            "retrieval_recall_at_1": _ratio(
                sum(row["black_rank"] == 1 for row in black), len(black)),
            "retrieval_recall_at_5": _ratio(
                sum(row["black_rank"] is not None and row["black_rank"] <= 5
                    for row in black), len(black)),
            "end_to_end_black_recall": _ratio(
                sum(is_black_hit(row) for row in black), len(black)),
            "ordinary_false_black_rate": _ratio(
                sum(is_false_hit(row) for row in ordinary), len(ordinary)),
            "genuine_false_black_rate": _ratio(
                sum(is_false_hit(row) for row in genuine), len(genuine)),
            "combined_nonblack_query_far": _ratio(
                sum(is_false_hit(row) for row in nonblack), len(nonblack)),
            "searched_nonblack_far": _ratio(
                sum(is_false_hit(row) for row in nonblack),
                sum(row["black_search_invoked"] for row in nonblack)),
            "black_search_latency_ms": {
                "count": len(latencies),
                "p50": float(np.percentile(latencies, 50)) if latencies else None,
                "p95": float(np.percentile(latencies, 95)) if latencies else None,
            },
        }
        output[str(db_size)]["query_far_target_met"] = (
            output[str(db_size)]["combined_nonblack_query_far"]
            <= TARGET_QUERY_FAR)
    return output


def run_black_test(dataset, grouped, output_dir, seed=SEED):
    eligible = sorted(identity for identity, indices in grouped.items()
                      if len(indices) >= 2)
    rng = np.random.default_rng(seed)
    shuffled = np.asarray(eligible, dtype=str)
    rng.shuffle(shuffled)
    midpoint = len(shuffled) // 2
    calibration_pool = sorted(shuffled[:midpoint].tolist())
    evaluation_pool = sorted(shuffled[midpoint:].tolist())
    calibration = build_black_cases(
        dataset, grouped, calibration_pool, "calibration", 5, seed + 100000)
    thresholds = {
        size: select_far_threshold(
            [row for row in calibration if row["db_size"] == size])
        for size in BLACK_DB_SIZES
    }
    evaluation = build_black_cases(
        dataset, grouped, evaluation_pool, "evaluation", 10, seed + 200000)
    all_cases = calibration + evaluation
    for row in all_cases:
        threshold = thresholds[row["db_size"]]
        row["black_threshold"] = threshold
        row["black_decision"] = bool(
            row["black_search_invoked"]
            and row["black_top1_score"] >= threshold)
        row["expected_black"] = row["case_type"] == "black"
        row["decision_correct"] = (
            row["black_decision"] == row["expected_black"])

    metrics = {
        "seed": seed,
        "model": "CAM++ 192维",
        "self_threshold": SELF_THRESHOLD,
        "threshold_calibration": "独立校准身份池，整次非黑查询FAR<=1%",
        "eligible_two_recording_identities": len(eligible),
        "calibration_identity_pool": len(calibration_pool),
        "evaluation_identity_pool": len(evaluation_pool),
        "calibration_cases": len(calibration),
        "evaluation_cases": len(evaluation),
        "by_db_size": summarize_black_cases(evaluation, thresholds),
    }
    write_csv(output_dir / "black_test_cases.csv", all_cases)
    write_json(output_dir / "black_metrics.json", metrics)
    write_black_report(output_dir / "黑产库功能测试报告.md", metrics)
    return metrics


def _pct(value):
    return f"{value * 100:.2f}%"


def write_black_report(path, metrics):
    lines = [
        "# 黑产声纹库功能测试报告",
        "",
        "> 使用真实客户侧 CAM++ embedding，验证“1:1 不匹配后再进入黑产库 1:N”的完整级联。",
        "",
        "## 测试口径",
        "",
        f"- 固定随机种子：`{metrics['seed']}`",
        f"- 可做留一录音测试的客户：{metrics['eligible_two_recording_identities']} 个",
        f"- 校准/评估身份池：{metrics['calibration_identity_pool']} / {metrics['evaluation_identity_pool']}，互不重叠",
        f"- 1:1 阈值：{metrics['self_threshold']:.3f}",
        "- 黑产本人第一通录音入库，第二通独立录音查询；普通客户和本人查询均不进入黑产库真值。",
        "- 黑产阈值仅用校准集确定，各库规模按整次非黑查询 FAR 不高于 1% 选取，不复用 1:1 阈值。",
        "",
        "## 实测结果",
        "",
        "| 黑产身份数 | 黑产阈值 | Recall@1 | Recall@5 | 端到端黑产召回 | 普通客户误报 | 本人误报 | 综合查询FAR | 检索P95(ms) |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for size in BLACK_DB_SIZES:
        item = metrics["by_db_size"][str(size)]
        lines.append(
            f"| {size} | {item['black_threshold']:.4f} | "
            f"{_pct(item['retrieval_recall_at_1'])} | "
            f"{_pct(item['retrieval_recall_at_5'])} | "
            f"{_pct(item['end_to_end_black_recall'])} | "
            f"{_pct(item['ordinary_false_black_rate'])} | "
            f"{_pct(item['genuine_false_black_rate'])} | "
            f"{_pct(item['combined_nonblack_query_far'])}"
            f"{'（达标）' if item['query_far_target_met'] else '（未达标）'} | "
            f"{item['black_search_latency_ms']['p95']:.3f} |")
    lines.extend([
        "",
        "## 结果解释",
        "",
        "- `Recall@1/@5` 对全部黑产查询做离线反事实检索，只衡量 1:N 排名；端到端召回还包含 1:1 是否触发以及阈值判定，因此更接近上线效果。",
        "- `综合查询FAR` 的分母包含未触发黑产检索的非黑查询；`searched_nonblack_far` 可在 JSON 中查看进入检索后的条件误报率。",
        "- 本报告是功能与离线回放验证，不替代跨时间、跨设备、真实黑产标签上的生产验收。",
        "",
        "## 明细文件",
        "",
        "- `black_test_cases.csv`：逐查询的客户号、1:1 分数、黑产排名、阈值和最终判定。",
        "- `black_metrics.json`：各库规模完整指标。",
    ])
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _candidate_windows(audio_path, count, seconds=30):
    import soundfile as sf

    with sf.SoundFile(audio_path) as source:
        sample_rate = source.samplerate
        frames = int(seconds * sample_rate)
        candidates = []
        for index in range(len(source) // frames):
            source.seek(index * frames)
            signal = source.read(frames, dtype="float32", always_2d=True)
            energy = float(np.sqrt(np.mean(np.square(signal))))
            candidates.append((energy, index * seconds))
    candidates.sort(reverse=True)
    return candidates[:count]


def _select_gang_sources(dataset, grouped, seed):
    candidates = []
    for identity, indices in grouped.items():
        best = max(indices, key=lambda idx: float(dataset["durations"][idx]))
        candidates.append((identity, best, float(dataset["durations"][best])))
    rng = np.random.default_rng(seed)
    rng.shuffle(candidates)
    selected = []
    used = set()
    for gang_index, size in enumerate(GANG_SIZES, 1):
        valid = [item for item in candidates
                 if item[0] not in used and item[2] >= size * 30]
        if not valid:
            raise RuntimeError(f"找不到可切出{size}个30秒片段的客户录音")
        identity, index, duration = valid[0]
        selected.append({
            "gang": f"gang_{gang_index}",
            "size": size,
            "identity": identity,
            "index": index,
            "duration": duration,
        })
        used.add(identity)
    return selected


def build_segment_embeddings(dataset, grouped, temp_dir, seed):
    cache = temp_dir / "gang_segment_embeddings.npz"
    if cache.exists():
        with np.load(cache, allow_pickle=False) as data:
            return {key: data[key].copy() for key in data.files}

    selected = _select_gang_sources(dataset, grouped, seed)
    segment_dir = temp_dir / "gang_segments"
    segment_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    vectors = []
    embedding.get_model()
    for gang in selected:
        source = str(dataset["audio_paths"][gang["index"]])
        windows = _candidate_windows(source, gang["size"])
        if len(windows) != gang["size"]:
            raise RuntimeError(f"{source} 可用30秒窗口不足")
        windows.sort(key=lambda item: item[1])
        for member_index, (energy, offset) in enumerate(windows, 1):
            synthetic_id = f"{gang['gang']}_customer_{member_index}"
            wav = segment_dir / f"{synthetic_id}.wav"
            audio_io.extract_channel(
                source, 0, str(wav), offset=offset, dur=30, sr=16000)
            vector = embedding.embed(str(wav), disable_pbar=True)
            rows.append({
                "node_id": synthetic_id,
                "true_label": gang["gang"],
                "source_identity": gang["identity"],
                "source_audio": source,
                "offset_seconds": float(offset),
                "energy": energy,
            })
            vectors.append(vector)
            print(
                f"GANG_EMBED {len(rows)}/{sum(GANG_SIZES)} "
                f"{synthetic_id} offset={offset}s", flush=True)
    payload = {
        "node_ids": np.asarray([row["node_id"] for row in rows]),
        "true_labels": np.asarray([row["true_label"] for row in rows]),
        "source_identities": np.asarray([row["source_identity"] for row in rows]),
        "source_audio": np.asarray([row["source_audio"] for row in rows]),
        "offset_seconds": np.asarray([row["offset_seconds"] for row in rows], dtype=np.float32),
        "energy": np.asarray([row["energy"] for row in rows], dtype=np.float32),
        "embeddings": _normalize(np.stack(vectors)),
    }
    np.savez_compressed(cache, **payload)
    return payload


def identity_centroids(dataset, grouped, excluded=None):
    excluded = set(excluded or [])
    identities = []
    vectors = []
    for identity in sorted(grouped):
        if identity in excluded:
            continue
        centroid = dataset["embeddings"][grouped[identity]].mean(axis=0)
        centroid /= max(float(np.linalg.norm(centroid)), 1e-12)
        identities.append(identity)
        vectors.append(centroid)
    return identities, np.asarray(vectors, dtype=np.float32)


def _cluster_rows(result, node_ids, true_labels=None):
    rows = []
    for cluster_index, cluster in enumerate(result["clusters"], 1):
        for node_index in cluster:
            row = {
                "cluster_id": cluster_index,
                "cluster_size": len(cluster),
                "node_index": node_index,
                "node_id": node_ids[node_index],
            }
            if true_labels is not None:
                row["true_label"] = true_labels[node_index]
            rows.append(row)
    return rows


def _edge_rows(result, node_ids):
    return [{
        "left_index": left,
        "left_id": node_ids[left],
        "right_index": right,
        "right_id": node_ids[right],
        "score": score,
    } for left, right, score in result["edges"]]


def _choose_gang_config(sweep):
    constrained = [row for row in sweep
                   if row["pair_precision"] >= 0.95
                   and row["false_clusters"] == 0]
    candidates = constrained or sweep
    return max(candidates, key=lambda row: (
        row["gang_detection_recall"], row["pair_f1"],
        row["pair_precision"], -row["threshold"], -row["topk"]))


def run_gang_test(dataset, grouped, output_dir, temp_dir, seed=SEED):
    segments = build_segment_embeddings(dataset, grouped, temp_dir, seed)
    source_identities = set(segments["source_identities"].astype(str).tolist())
    background_ids, background_vectors = identity_centroids(
        dataset, grouped, excluded=source_identities)
    rng = np.random.default_rng(seed + 300000)
    order = rng.permutation(len(background_ids))[:min(200, len(background_ids))]
    background_ids = [background_ids[index] for index in order]
    background_vectors = background_vectors[order]

    segment_ids = segments["node_ids"].astype(str).tolist()
    segment_labels = segments["true_labels"].astype(str).tolist()
    node_ids = segment_ids + [f"background_customer_{item}" for item in background_ids]
    true_labels = segment_labels + [f"background_{item}" for item in background_ids]
    vectors = np.vstack([segments["embeddings"], background_vectors])

    sweep = []
    result_cache = {}
    for threshold in (0.80, 0.825, 0.85, 0.875, 0.90, 0.925, 0.95):
        for topk in (2, 3, 5, 8):
            result = cluster_embeddings(vectors, threshold, topk, 3)
            metrics = evaluate_clusters(true_labels, result["clusters"])
            row = {"threshold": threshold, "topk": topk,
                   "edge_count": len(result["edges"]), **metrics}
            sweep.append(row)
            result_cache[(threshold, topk)] = result
    selected = _choose_gang_config(sweep)
    best_detection = max(sweep, key=lambda row: (
        row["gang_detection_recall"], row["pair_precision"], row["pair_f1"]))
    selected_result = result_cache[(selected["threshold"], selected["topk"])]
    write_csv(output_dir / "gang_parameter_sweep.csv", sweep)
    write_csv(output_dir / "gang_edges.csv", _edge_rows(selected_result, node_ids))
    write_csv(
        output_dir / "gang_clusters.csv",
        _cluster_rows(selected_result, node_ids, true_labels),
        ["cluster_id", "cluster_size", "node_index", "node_id", "true_label"])

    shadow_ids, shadow_vectors = identity_centroids(dataset, grouped)
    shadow = cluster_embeddings(
        shadow_vectors, selected["threshold"], selected["topk"], 3)
    write_csv(output_dir / "shadow_edges.csv", _edge_rows(shadow, shadow_ids))
    write_csv(
        output_dir / "shadow_clusters.csv",
        _cluster_rows(shadow, shadow_ids),
        ["cluster_id", "cluster_size", "node_index", "node_id"])

    segment_manifest = [{
        "node_id": segments["node_ids"][index].item(),
        "true_label": segments["true_labels"][index].item(),
        "source_identity": segments["source_identities"][index].item(),
        "source_audio": segments["source_audio"][index].item(),
        "offset_seconds": float(segments["offset_seconds"][index]),
        "energy": float(segments["energy"][index]),
    } for index in range(len(segments["node_ids"]))]
    metrics = {
        "seed": seed,
        "model": "CAM++ 192维",
        "synthetic_gangs": len(GANG_SIZES),
        "synthetic_gang_sizes": list(GANG_SIZES),
        "segment_seconds": 30,
        "segment_count": len(segment_ids),
        "background_customer_count": len(background_ids),
        "selection_constraint": "优先pair_precision>=95%且false_clusters=0，再最大化团伙检出率和pair_f1",
        "selected": selected,
        "best_detection": best_detection,
        "high_precision_function_passed": bool(
            selected["pair_precision"] >= 0.95
            and selected["false_clusters"] == 0
            and selected["gang_detected"] > 0),
        "segment_manifest": segment_manifest,
        "shadow": {
            "customer_count": len(shadow_ids),
            "edge_count": len(shadow["edges"]),
            "cluster_count": len(shadow["clusters"]),
            "clustered_customers": sum(len(item) for item in shadow["clusters"]),
            "max_cluster_size": max(
                (len(item) for item in shadow["clusters"]), default=0),
            "note": "真实库无团伙真值，仅作为影子跑批候选，不计精确率或召回率",
        },
    }
    write_json(output_dir / "gang_metrics.json", metrics)
    write_gang_report(output_dir / "团伙簇功能测试报告.md", metrics)
    return metrics


def write_gang_report(path, metrics):
    selected = metrics["selected"]
    best_detection = metrics["best_detection"]
    shadow = metrics["shadow"]
    lines = [
        "# 声纹团伙簇功能测试报告",
        "",
        "> 使用真实客户声道的独立音频片段构造可验证真值，再对全量客户质心执行无标签影子跑批。",
        "",
        "## 测试口径",
        "",
        f"- 固定随机种子：`{metrics['seed']}`",
        f"- 真值团伙：{metrics['synthetic_gangs']} 个，规模为 `{metrics['synthetic_gang_sizes']}`",
        f"- 团伙节点：{metrics['segment_count']} 个；每个节点来自同一真实说话人的不同高能量 30 秒窗口，并重新提取 CAM++ embedding",
        f"- 背景客户：{metrics['background_customer_count']} 个真实客户质心",
        "- 图规则：达到阈值且互为 Top-K 才连边，至少 3 个节点才输出团伙簇。",
        "",
        "## 参数选择结果",
        "",
        f"- 阈值：{selected['threshold']:.3f}",
        f"- 互为 Top-K：{selected['topk']}",
        f"- 边数/簇数：{selected['edge_count']} / {selected['cluster_count']}",
        f"- Pair Precision / Recall / F1：{_pct(selected['pair_precision'])} / {_pct(selected['pair_recall'])} / {_pct(selected['pair_f1'])}",
        f"- 团伙检出率：{_pct(selected['gang_detection_recall'])}",
        f"- 加权纯度：{_pct(selected['weighted_purity'])}",
        f"- 错误簇/碎片化团伙：{selected['false_clusters']} / {selected['fragmented_gangs']}",
        f"- ARI / NMI：{selected['ari']:.4f} / {selected['nmi']:.4f}",
        f"- 高精度功能测试：{'通过' if metrics['high_precision_function_passed'] else '未通过'}；在 Precision≥95% 且错误簇为0的约束下检出 {selected['gang_detected']}/{selected['gang_count']} 个已知团伙",
        "",
        "## 检出率上限对照",
        "",
        f"- 最高团伙检出配置：阈值 {best_detection['threshold']:.3f}、互为Top-{best_detection['topk']}",
        f"- 检出 {best_detection['gang_detected']}/{best_detection['gang_count']} 个团伙，但 Pair Precision 仅 {_pct(best_detection['pair_precision'])}，错误簇 {best_detection['false_clusters']} 个",
        "- 当前模型与聚类规则在本批数据上存在明显精度/召回冲突，不能把最高检出配置直接用于风险判定。",
        "",
        "## 全库影子跑批",
        "",
        f"- 客户质心：{shadow['customer_count']} 个",
        f"- 候选边：{shadow['edge_count']} 条",
        f"- 候选簇：{shadow['cluster_count']} 个",
        f"- 入簇客户：{shadow['clustered_customers']} 个",
        f"- 最大簇：{shadow['max_cluster_size']} 个客户",
        "- 影子跑批没有真实团伙标签，输出只能作为人工调查候选，不能据此宣称真实检出率。",
        "",
        "## 明细文件",
        "",
        "- `gang_parameter_sweep.csv`：全部阈值和 Top-K 组合指标。",
        "- `gang_edges.csv` / `gang_clusters.csv`：带真值功能测试的边和簇。",
        "- `shadow_edges.csv` / `shadow_clusters.csv`：493 客户全库候选边和候选簇。",
        "- `gang_metrics.json`：选定参数、片段来源与完整指标。",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_overview(path, black, gang):
    selected = gang["selected"]
    lines = [
        "# 声纹功能测试总览",
        "",
        "> 本次测试覆盖黑产库级联 1:1→1:N 与客户声纹库 N:N 团伙聚类。",
        "",
        "## 数据与隔离",
        "",
        f"- 模型：{black['model']}，仅使用已确认角色的客户声道",
        f"- 最终客户库：493 个客户；可做独立两通录音验证：{black['eligible_two_recording_identities']} 个",
        "- 黑产阈值校准身份与评估身份完全隔离；黑产入库录音与查询录音分离。",
        "- 团伙真值由真实客户音频的互不重叠 30 秒片段构造，没有复制 embedding。",
        "",
        "## 核心结果",
        "",
        "| 功能 | 核心实测结果 | 结论边界 |",
        "|---|---|---|",
        f"| 黑产库级联 | 已测试 10/30/50/100 身份库；各规模端到端召回与查询FAR见 `黑产库功能测试报告.md` | 离线模拟，不代替真实黑产标签验收 |",
        f"| 团伙簇 | 选定阈值 {selected['threshold']:.3f}、互为Top-{selected['topk']}；团伙检出率 {_pct(selected['gang_detection_recall'])}、Pair F1 {_pct(selected['pair_f1'])} | 全库影子簇仍需人工确认 |",
        "",
        "## 输出索引",
        "",
        "- `黑产库功能测试报告.md` / `black_metrics.json` / `black_test_cases.csv`",
        "- `团伙簇功能测试报告.md` / `gang_metrics.json` / `gang_parameter_sweep.csv`",
        "- `gang_edges.csv` / `gang_clusters.csv` / `shadow_edges.csv` / `shadow_clusters.csv`",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input", type=Path,
        default=ROOT / "reports" / "kesu_customer_refresh_20260731" / "customer_embeddings.npz")
    parser.add_argument(
        "--output-dir", type=Path,
        default=ROOT / "reports" / "voiceprint_function_test_20260810")
    parser.add_argument(
        "--temp-dir", type=Path,
        default=ROOT / "_temp" / "voiceprint_function_test_20260810")
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.temp_dir.mkdir(parents=True, exist_ok=True)
    dataset, grouped = load_dataset(args.input)
    print(
        f"DATA records={len(dataset['embeddings'])} identities={len(grouped)}",
        flush=True)
    black = run_black_test(dataset, grouped, args.output_dir, args.seed)
    print("BLACK_TEST_DONE", flush=True)
    gang = run_gang_test(
        dataset, grouped, args.output_dir, args.temp_dir, args.seed)
    print("GANG_TEST_DONE", flush=True)
    write_overview(args.output_dir / "测试总览.md", black, gang)
    print(f"DONE output={args.output_dir}", flush=True)


if __name__ == "__main__":
    main()
