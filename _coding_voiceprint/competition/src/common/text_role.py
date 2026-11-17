# -*- coding: utf-8 -*-
"""数据学习型客服/客户文本角色识别，支持无效对话剔除与拒识。"""
from __future__ import annotations

import tempfile
from pathlib import Path

import joblib

from . import asr_role, audio_io


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = (
    PROJECT_ROOT / "models" / "role" / "role_text_v1_20260820"
    / "role_text_model.joblib"
)
_MODEL_CACHE = {}


def load_model(path=DEFAULT_MODEL):
    path = Path(path).resolve()
    if path not in _MODEL_CACHE:
        _MODEL_CACHE[path] = joblib.load(path)
    return _MODEL_CACHE[path]


def channel_valid(features: dict, min_chars=20, min_speech_seconds=5.0) -> bool:
    summary = features.get("summary") or {}
    return (
        len(str(features.get("text") or "").strip()) >= min_chars
        and int(summary.get("char_count") or 0) >= min_chars
        and float(summary.get("speech_duration") or 0.0) >= min_speech_seconds
    )


def classify_features(left: dict, right: dict, model_path=DEFAULT_MODEL,
                      direction=None) -> dict:
    """仅用L/R文本判断客服声道；direction只做事后冲突标记，不参与预测。"""
    model = load_model(model_path)
    quality = model["quality_rule"]
    valid_left = channel_valid(
        left, quality["min_chars"], quality["min_speech_seconds"])
    valid_right = channel_valid(
        right, quality["min_chars"], quality["min_speech_seconds"])
    if not valid_left and not valid_right:
        return {
            "status": "no_effective_dialogue",
            "agent_ch": None,
            "customer_ch": None,
            "needs_review": True,
        }
    if valid_left != valid_right:
        return {
            "status": "one_sided",
            "agent_ch": None,
            "customer_ch": None,
            "needs_review": True,
            "valid_channel": "L" if valid_left else "R",
        }

    texts = [left["text"], right["text"]]
    matrix = model["vectorizer"].transform(texts)
    probabilities = model["classifier"].predict_proba(matrix)[:, 1]
    left_probability = float(probabilities[0])
    right_probability = float(probabilities[1])
    margin = abs(left_probability - right_probability)
    threshold = float(model["abstain_threshold"])
    agent_ch = "L" if left_probability >= right_probability else "R"
    customer_ch = "R" if agent_ch == "L" else "L"
    accepted = margin >= threshold
    expected_customer = {"I": "R", "O": "L"}.get(direction)
    return {
        "status": "identified" if accepted else "needs_review",
        "agent_ch": agent_ch if accepted else None,
        "customer_ch": customer_ch if accepted else None,
        "candidate_agent_ch": agent_ch,
        "candidate_customer_ch": customer_ch,
        "needs_review": not accepted,
        "left_agent_probability": round(left_probability, 6),
        "right_agent_probability": round(right_probability, 6),
        "margin": round(margin, 6),
        "threshold": threshold,
        "direction_conflict": bool(
            accepted and expected_customer is not None
            and customer_ch != expected_customer),
        "model_input": "asr_text_only",
    }


def classify_audio(audio_path, model_path=DEFAULT_MODEL, direction=None,
                   temp_root=None) -> dict:
    """拆双声道、临时转写并识别角色；文本和WAV在返回前删除。"""
    temp_parent = str(temp_root) if temp_root is not None else None
    with tempfile.TemporaryDirectory(prefix="text_role_", dir=temp_parent) as temp_dir:
        features = {}
        for index, channel in ((0, "L"), (1, "R")):
            wav = Path(temp_dir) / f"{channel}.wav"
            audio_io.extract_channel(
                str(audio_path), index, str(wav), dur=None, sr=16000)
            features[channel] = asr_role.transcribe_role_features(str(wav))
        return classify_features(
            features["L"], features["R"], model_path, direction)
