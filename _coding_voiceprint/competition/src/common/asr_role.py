# -*- coding: utf-8 -*-
"""只保留数值摘要的 ASR 角色识别，不持久化转译文本。"""
import gc

from .model_paths import resolve_model
from .role_id import KW, decide_role_from_scores


_MODEL = None


def get_model():
    """加载不含说话人模型的 ASR + VAD + 标点模型。"""
    global _MODEL
    if _MODEL is None:
        from funasr import AutoModel

        _MODEL = AutoModel(
            model=resolve_model("paraformer-zh"),
            vad_model=resolve_model("fsmn-vad"),
            punc_model=resolve_model("ct-punc"),
            hub="ms",
            disable_update=True,
        )
    return _MODEL


def _empty_summary():
    return {
        "char_count": 0,
        "weighted_hits": 0.0,
        "hits": {category: 0 for category in KW},
        "first_speech": 1e9,
        "speech_duration": 0.0,
        "score": 0.0,
    }


def _consume_text(summary, text):
    """将临时文本立即压缩为计数，不返回或保存原文。"""
    if not text:
        return
    summary["char_count"] += len(text)
    for category, (words, weight) in KW.items():
        count = sum(text.count(word) for word in words)
        summary["hits"][category] += count
        summary["weighted_hits"] += count * weight


def summarize_result(result):
    """把 FunASR 返回值压缩为角色判断所需数值摘要。"""
    summary = _empty_summary()
    record = result[0] if isinstance(result, list) and result else result
    record = record if isinstance(record, dict) else {}
    sentences = record.get("sentence_info") or []
    if sentences:
        for sentence in sentences:
            _consume_text(summary, sentence.get("text", ""))
            start = float(sentence.get("start", 0)) / 1000.0
            end = float(sentence.get("end", 0)) / 1000.0
            summary["first_speech"] = min(summary["first_speech"], start)
            summary["speech_duration"] += max(0.0, end - start)
    else:
        text = record.get("text", "")
        _consume_text(summary, text)
        timestamps = record.get("timestamp") or []
        for timestamp in timestamps:
            if isinstance(timestamp, dict):
                start = float(timestamp.get("start_time", 0))
                end = float(timestamp.get("end_time", 0))
                if max(abs(start), abs(end)) < 10000:
                    start *= 1000.0
                    end *= 1000.0
            elif isinstance(timestamp, (list, tuple)) and len(timestamp) >= 2:
                start, end = float(timestamp[0]), float(timestamp[1])
            else:
                continue
            summary["first_speech"] = min(summary["first_speech"], start / 1000.0)
            summary["speech_duration"] += max(0.0, end - start) / 1000.0

    summary["score"] = (
        summary["weighted_hits"] / max(summary["char_count"], 1) * 1000.0
    )
    summary["weighted_hits"] = round(summary["weighted_hits"], 3)
    summary["first_speech"] = (
        None if summary["first_speech"] == 1e9 else round(summary["first_speech"], 3)
    )
    summary["speech_duration"] = round(summary["speech_duration"], 3)
    summary["score"] = round(summary["score"], 3)
    return summary


def transcribe_summary(audio_path):
    """执行 ASR 并立即丢弃文本，仅返回数值摘要。"""
    features = transcribe_role_features(audio_path)
    return features["summary"]


def transcribe_role_features(audio_path):
    """返回本次角色判断所需的临时文本与摘要；调用方不得持久化文本。"""
    result = get_model().generate(
        input=audio_path,
        batch_size_s=300,
        disable_pbar=True,
        sentence_timestamp=True,
    )
    record = result[0] if isinstance(result, list) and result else result
    record = record if isinstance(record, dict) else {}
    summary = summarize_result(result)
    features = {"text": str(record.get("text", "")).strip(), "summary": summary}
    del result
    gc.collect()
    return features


def decide_from_summaries(left, right):
    first_left = left.get("first_speech")
    first_right = right.get("first_speech")
    if left["char_count"] == 0 or right["char_count"] == 0:
        return {
            "agent_ch": None,
            "customer_ch": None,
            "confidence": "缺一方",
            "ka": left["score"],
            "kb": right["score"],
        }
    return decide_role_from_scores(
        left["score"], right["score"], first_left, first_right,
        evidence_a=left.get("weighted_hits", 0.0),
        evidence_b=right.get("weighted_hits", 0.0),
    )
