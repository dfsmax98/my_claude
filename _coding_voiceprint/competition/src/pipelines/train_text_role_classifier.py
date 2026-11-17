# -*- coding: utf-8 -*-
"""训练纯文本客服/客户角色模型，并在客户隔离测试集上分层评估。"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score


MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from common.role_id import kw_evidence  # noqa: E402


DEFAULT_CORPUS = MODULE_ROOT / "_temp" / "role_text_corpus_20260820"
DEFAULT_OUTPUT = MODULE_ROOT / "reports" / "role_text_model_20260820"
DEFAULT_MODEL = MODULE_ROOT / "models" / "role" / "role_text_v1_20260820"
TARGET_ACCURACY = 0.95
VALIDATION_TARGET = 0.97
MIN_CHARS = 20
MIN_SPEECH_SECONDS = 5.0


def _atomic_json(path: Path, payload: dict) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def stable_split(group_key: str) -> str:
    bucket = int(hashlib.sha256(
        f"role-model-split-v1:{group_key}".encode("utf-8")
    ).hexdigest()[:8], 16) % 100
    if bucket < 70:
        return "train"
    if bucket < 85:
        return "validation"
    return "test"


def channel_is_valid(channel: dict) -> bool:
    summary = channel.get("summary") or {}
    return (
        len(str(channel.get("text") or "").strip()) >= MIN_CHARS
        and int(summary.get("char_count") or 0) >= MIN_CHARS
        and float(summary.get("speech_duration") or 0.0) >= MIN_SPEECH_SECONDS
    )


def quality_band(record: dict) -> str:
    left = record["channels"]["L"]
    right = record["channels"]["R"]
    if not channel_is_valid(left) or not channel_is_valid(right):
        return "invalid"
    min_chars = min(
        int(left["summary"]["char_count"]),
        int(right["summary"]["char_count"]),
    )
    min_speech = min(
        float(left["summary"]["speech_duration"]),
        float(right["summary"]["speech_duration"]),
    )
    if min_chars < 50 or min_speech < 10:
        return "sparse"
    if min_chars < 150 or min_speech < 30:
        return "normal"
    return "rich"


def load_corpus(corpus_dir: Path) -> tuple[list[dict], dict]:
    records = []
    for path in sorted((corpus_dir / "records").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        record["quality_band"] = quality_band(record)
        group_key = str(record.get("identity_sha256") or "").strip()
        record["model_eligible"] = bool(
            group_key and record["quality_band"] != "invalid")
        # 缺失客户哈希时无法证明客户级隔离，不得回退到录音ID进入评估。
        record["split"] = stable_split(group_key) if group_key else "excluded"
        # 方向仅由代理标签反推用于分层报告，不进入文本特征。
        record["direction"] = "I" if record["agent_channel"] == "L" else "O"
        records.append(record)
    summary_path = corpus_dir / "corpus_summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    else:
        selection = json.loads(
            (corpus_dir / "corpus_selection.json").read_text(encoding="utf-8"))
        summary = selection["summary"]
        summary["records_written"] = len(records)
        summary["failures"] = None
    return records, summary


def channel_dataset(records: list[dict], split: str) -> tuple[list[str], np.ndarray]:
    texts = []
    labels = []
    for record in records:
        if record["split"] != split or not record["model_eligible"]:
            continue
        for channel in ("L", "R"):
            texts.append(record["channels"][channel]["text"])
            labels.append(1 if channel == record["agent_channel"] else 0)
    return texts, np.asarray(labels, dtype=np.int8)


def pair_predictions(records: list[dict], split: str,
                     vectorizer: TfidfVectorizer,
                     classifier: LogisticRegression) -> list[dict]:
    selected = [
        record for record in records
        if record["split"] == split and record["model_eligible"]
    ]
    texts = []
    for record in selected:
        texts.extend([
            record["channels"]["L"]["text"],
            record["channels"]["R"]["text"],
        ])
    if not texts:
        return []
    probabilities = classifier.predict_proba(vectorizer.transform(texts))[:, 1]
    rows = []
    for index, record in enumerate(selected):
        left_probability = float(probabilities[index * 2])
        right_probability = float(probabilities[index * 2 + 1])
        predicted = "L" if left_probability >= right_probability else "R"
        rows.append({
            "recording_id": record["recording_id"],
            "split": split,
            "direction": record["direction"],
            "quality_band": record["quality_band"],
            "expected_agent_channel": record["agent_channel"],
            "predicted_agent_channel": predicted,
            "left_agent_probability": round(left_probability, 6),
            "right_agent_probability": round(right_probability, 6),
            "margin": round(abs(left_probability - right_probability), 6),
            "correct": predicted == record["agent_channel"],
        })
    return rows


def choose_abstain_threshold(rows: list[dict], target: float) -> dict:
    if not rows:
        raise ValueError("验证集为空")
    margins = sorted({0.0, *[float(row["margin"]) for row in rows]})
    candidates = []
    total = len(rows)
    for threshold in margins:
        accepted = [row for row in rows if float(row["margin"]) >= threshold]
        if not accepted:
            continue
        accuracy = sum(row["correct"] for row in accepted) / len(accepted)
        candidates.append({
            "threshold": threshold,
            "accepted": len(accepted),
            "coverage": len(accepted) / total,
            "accuracy": accuracy,
        })
    qualified = [row for row in candidates if row["accuracy"] >= target]
    if qualified:
        return max(qualified, key=lambda row: (
            row["coverage"], row["accuracy"], -row["threshold"]))
    return max(candidates, key=lambda row: (
        row["accuracy"], row["coverage"], -row["threshold"]))


def evaluate_rows(rows: list[dict], threshold: float) -> dict:
    accepted = [row for row in rows if float(row["margin"]) >= threshold]
    rejected = [row for row in rows if float(row["margin"]) < threshold]
    raw_accuracy = sum(row["correct"] for row in rows) / len(rows) if rows else None
    accepted_accuracy = (
        sum(row["correct"] for row in accepted) / len(accepted)
        if accepted else None
    )
    return {
        "total": len(rows),
        "raw_accuracy": raw_accuracy,
        "threshold": threshold,
        "accepted": len(accepted),
        "rejected": len(rejected),
        "coverage": len(accepted) / len(rows) if rows else 0.0,
        "accepted_accuracy": accepted_accuracy,
    }


def evaluate_slices(rows: list[dict], threshold: float) -> dict:
    output = {"all": evaluate_rows(rows, threshold)}
    for field, values in (
        ("direction", ("I", "O")),
        ("quality_band", ("sparse", "normal", "rich")),
    ):
        for value in values:
            output[f"{field}={value}"] = evaluate_rows(
                [row for row in rows if row[field] == value], threshold)
    return output


def baseline_keyword_accuracy(records: list[dict], split: str) -> dict:
    rows = []
    for record in records:
        if record["split"] != split or not record["model_eligible"]:
            continue
        left_score = kw_evidence(record["channels"]["L"]["text"])[0]
        right_score = kw_evidence(record["channels"]["R"]["text"])[0]
        predicted = "L" if left_score >= right_score else "R"
        rows.append(predicted == record["agent_channel"])
    return {"total": len(rows), "accuracy": sum(rows) / len(rows) if rows else None}


def _clean_phrase(phrase: str) -> str:
    return phrase.strip(" \t\r\n，。！？、；：,.!?;:\"'“”‘’（）()【】[]")


def export_phrases(path: Path, vectorizer: TfidfVectorizer,
                   classifier: LogisticRegression, limit: int = 300) -> None:
    features = vectorizer.get_feature_names_out()
    coefficients = classifier.coef_[0]
    rows = []
    for role, reverse in (("客服", True), ("客户", False)):
        best = {}
        for index, raw_phrase in enumerate(features):
            phrase = _clean_phrase(str(raw_phrase))
            if len(phrase) < 2 or not re.search(r"[\u4e00-\u9fff]", phrase):
                continue
            weight = float(coefficients[index])
            previous = best.get(phrase)
            if previous is None or (reverse and weight > previous) or (
                    not reverse and weight < previous):
                best[phrase] = weight
        ordered = sorted(
            best.items(), key=lambda item: item[1], reverse=reverse)[:limit]
        for rank, (phrase, weight) in enumerate(ordered, 1):
            rows.append({
                "role": role,
                "rank": rank,
                "phrase": phrase,
                "weight": round(weight, 6),
            })
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["role", "rank", "phrase", "weight"])
        writer.writeheader()
        writer.writerows(rows)


def train(records: list[dict]) -> tuple[TfidfVectorizer, LogisticRegression, dict]:
    train_texts, train_labels = channel_dataset(records, "train")
    validation_texts, validation_labels = channel_dataset(records, "validation")
    vectorizer = TfidfVectorizer(
        analyzer="char",
        ngram_range=(2, 6),
        min_df=5,
        max_df=0.995,
        max_features=300_000,
        sublinear_tf=True,
        norm="l2",
        dtype=np.float32,
    )
    train_matrix = vectorizer.fit_transform(train_texts)
    validation_matrix = vectorizer.transform(validation_texts)
    candidates = []
    models = {}
    for c_value in (0.5, 1.0, 2.0, 4.0, 8.0):
        classifier = LogisticRegression(
            C=c_value,
            max_iter=1000,
            solver="liblinear",
            random_state=20260820,
        )
        classifier.fit(train_matrix, train_labels)
        channel_accuracy = accuracy_score(
            validation_labels, classifier.predict(validation_matrix))
        validation_pairs = pair_predictions(
            records, "validation", vectorizer, classifier)
        pair_accuracy = sum(row["correct"] for row in validation_pairs) / len(validation_pairs)
        candidates.append({
            "C": c_value,
            "channel_accuracy": float(channel_accuracy),
            "pair_accuracy": float(pair_accuracy),
        })
        models[c_value] = classifier
    selected = max(candidates, key=lambda row: (
        row["pair_accuracy"], row["channel_accuracy"], -row["C"]))
    return vectorizer, models[selected["C"]], {
        "candidates": candidates,
        "selected": selected,
        "train_channels": len(train_labels),
        "validation_channels": len(validation_labels),
        "features": len(vectorizer.get_feature_names_out()),
    }


def write_predictions(path: Path, rows: list[dict], threshold: float) -> None:
    fields = [
        "recording_id", "split", "direction", "quality_band",
        "expected_agent_channel", "predicted_agent_channel",
        "left_agent_probability", "right_agent_probability",
        "margin", "accepted", "correct",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                **row,
                "accepted": float(row["margin"]) >= threshold,
            })


def pct(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.2f}%"


def write_report(path: Path, metrics: dict) -> None:
    corpus = metrics["corpus"]
    validation = metrics["validation"]
    test = metrics["test"]
    baseline = metrics["baseline"]
    lines = [
        "# 客服/客户文本角色模型优化报告",
        "",
        "> 模型仅使用ASR文本中的字符n-gram，不使用呼叫方向、左右声道、客户标识或测试标签作为输入。方向只用于构造独立代理标签，因此本报告为代理测试结果；真实准确率仍需人工金标集确认。",
        "",
        "## 数据质量分层",
        "",
        f"- 原始录音：{sum(corpus['quality_counts'].values())} 通。",
        f"- 有效双边对话：{corpus['quality_counts']['valid_dialogue']} 通。",
        f"- 单边有效语音：{corpus['quality_counts']['one_sided']} 通，剔除。",
        f"- 双方均无足够有效对话：{corpus['quality_counts']['no_effective_dialogue']} 通，剔除。",
        f"- 训练语料：{corpus['records_written']} 通，其中呼入 {corpus['selected_direction']['I']}、呼出 {corpus['selected_direction']['O']}。",
        f"- 客户隔离可用语料：{metrics['eligibility']['model_eligible']} 通；缺少客户身份哈希 {metrics['eligibility']['missing_identity_excluded']} 通，剔除且不进入准确率分母。",
        "- 有效门槛：左右声道均不少于20个ASR字符且不少于5秒有效语音。",
        "",
        "## 防止预设答案与泄漏",
        "",
        "- 特征只包含ASR文本字符2至6元片段。",
        "- 呼叫方向只用于生成代理标签，不输入模型。",
        "- 有客户身份哈希的录音按SHA-256固定落入同一数据分区，训练、验证、测试客户不交叉；缺失哈希的录音直接剔除。",
        "- 超参数和拒识阈值只使用训练集与验证集选择，测试集在模型冻结后只评估一次。",
        "",
        "## 测试结果",
        "",
        f"- 旧关键词密度基线：{pct(baseline['accuracy'])}。",
        f"- 新模型测试集原始准确率：{pct(test['all']['raw_accuracy'])}。",
        f"- 验证集冻结拒识阈值：{validation['selected_threshold']:.6f}。",
        f"- 新模型可判定子集准确率：{pct(test['all']['accepted_accuracy'])}。",
        f"- 可判定覆盖率：{pct(test['all']['coverage'])}，拒识 {test['all']['rejected']} / {test['all']['total']}。",
        "",
        "| 测试分层 | 样本数 | 原始准确率 | 可判定准确率 | 覆盖率 |",
        "|---|---:|---:|---:|---:|",
    ]
    labels = {
        "direction=I": "呼入",
        "direction=O": "呼出",
        "quality_band=sparse": "稀疏对话",
        "quality_band=normal": "常规对话",
        "quality_band=rich": "信息充分",
    }
    for key, label in labels.items():
        row = test[key]
        lines.append(
            f"| {label} | {row['total']} | {pct(row['raw_accuracy'])} | "
            f"{pct(row['accepted_accuracy'])} | {pct(row['coverage'])} |")
    lines.extend([
        "",
        "## 话术权重",
        "",
        "- `learned_phrases.csv`分别列出客服与客户的高权重表达，权重完全由训练集学习。",
        "- 客服高权重短语提高客服概率，客户高权重短语反向降低客服概率。",
        "- 模型比较同一通录音L/R两侧的客服概率，差值不足阈值时返回待复核，不强行猜测。",
        "",
        "## 接入方式",
        "",
        "- `common/text_role.py`提供双声道文本特征判断和音频端到端判断接口。",
        "- `pipelines/classify_roles_adaptive.py`已切换到该模型；ASR全文仅在内存中参与判断，检查点不落完整转录。",
        "- 旧的右声道客户先验已禁止启用，批处理不会通过声道位置预设角色。",
        "",
        "## 使用边界",
        "",
        "- 空录音、单边录音、有效语音不足不进入角色准确率分母，单独标为数据质量异常。",
        "- 代理测试达到95%不等于人工真值准确率达到95%；上线前仍需至少200通人工双盲标注测试集。",
        "- 转接、三方通话、双方互相复述客服话术等场景应保留拒识能力。",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.model_dir.mkdir(parents=True, exist_ok=True)

    records, corpus_summary = load_corpus(args.corpus_dir)
    vectorizer, classifier, training = train(records)
    validation_rows = pair_predictions(
        records, "validation", vectorizer, classifier)
    threshold_choice = choose_abstain_threshold(
        validation_rows, VALIDATION_TARGET)
    uncertainty_floor = float(np.quantile(
        [float(row["margin"]) for row in validation_rows], 0.05))
    threshold = max(float(threshold_choice["threshold"]), uncertainty_floor)
    threshold_choice["uncertainty_floor_p05"] = uncertainty_floor
    threshold_choice["final_threshold"] = threshold
    test_rows = pair_predictions(records, "test", vectorizer, classifier)
    validation_metrics = evaluate_slices(validation_rows, threshold)
    validation_metrics["threshold_selection"] = threshold_choice
    validation_metrics["selected_threshold"] = threshold
    test_metrics = evaluate_slices(test_rows, threshold)
    baseline = baseline_keyword_accuracy(records, "test")

    split_counts = {
        split: sum(record["split"] == split for record in records)
        for split in ("train", "validation", "test")
    }
    group_splits = defaultdict(set)
    for record in records:
        if not record["model_eligible"]:
            continue
        group = record["identity_sha256"]
        group_splits[group].add(record["split"])
    leakage_groups = sum(len(splits) > 1 for splits in group_splits.values())
    eligibility = {
        "total_records": len(records),
        "model_eligible": sum(record["model_eligible"] for record in records),
        "missing_identity_excluded": sum(
            not str(record.get("identity_sha256") or "").strip()
            for record in records),
        "invalid_quality_excluded": sum(
            record["quality_band"] == "invalid" for record in records),
    }
    metrics = {
        "target_accuracy": TARGET_ACCURACY,
        "validation_target": VALIDATION_TARGET,
        "target_met": bool(
            test_metrics["all"]["accepted_accuracy"] is not None
            and test_metrics["all"]["accepted_accuracy"] >= TARGET_ACCURACY),
        "corpus": corpus_summary,
        "eligibility": eligibility,
        "split_counts": split_counts,
        "group_leakage_count": leakage_groups,
        "training": training,
        "baseline": baseline,
        "validation": validation_metrics,
        "test": test_metrics,
        "limitations": [
            "测试标签来自呼叫方向声道规律，不是人工逐通金标。",
            "模型不读取方向或声道位置，测试集客户与训练集隔离。",
            "人工金标准确率达到95%前，不应宣称生产准确率达到95%。",
        ],
    }
    _atomic_json(args.output_dir / "metrics.json", metrics)
    write_predictions(
        args.output_dir / "test_predictions.csv", test_rows, threshold)
    export_phrases(
        args.output_dir / "learned_phrases.csv", vectorizer, classifier)
    write_report(args.output_dir / "文本角色模型优化报告.md", metrics)
    joblib.dump({
        "vectorizer": vectorizer,
        "classifier": classifier,
        "abstain_threshold": threshold,
        "quality_rule": {
            "min_chars": MIN_CHARS,
            "min_speech_seconds": MIN_SPEECH_SECONDS,
        },
        "model_input": "ASR text only; no direction/channel/identity",
    }, args.model_dir / "role_text_model.joblib", compress=3)
    _atomic_json(args.model_dir / "model_card.json", {
        "version": "role-text-v1-20260820",
        "metrics_path": str(args.output_dir / "metrics.json"),
        "target_met": metrics["target_met"],
        "abstain_threshold": threshold,
        "input": "左右声道ASR文本",
        "output": "客服声道L/R或待复核",
        "ground_truth": "方向规则代理标签；待人工金标复验",
    })
    print(json.dumps({
        "target_met": metrics["target_met"],
        "baseline": baseline,
        "validation_threshold": threshold_choice,
        "test": test_metrics["all"],
        "split_counts": split_counts,
        "group_leakage_count": leakage_groups,
    }, ensure_ascii=False, indent=2))
    if not metrics["target_met"]:
        raise SystemExit("可判定测试子集未达到95%目标")


if __name__ == "__main__":
    main()
