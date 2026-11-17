"""双轨ASR、角色识别与客户embedding提取。"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from common import asr_role, audio_io, embedding, text_role


class AudioValidationError(ValueError):
    pass


class AudioPipeline:
    def __init__(self, config: dict):
        self.config = config

    def inspect(self, audio_path: str | Path) -> dict:
        path = Path(audio_path)
        if path.suffix.lower() not in set(self.config["audio"]["allowed_extensions"]):
            raise AudioValidationError(f"不支持的音频格式: {path.suffix}")
        if path.stat().st_size > int(self.config["audio"]["max_upload_bytes"]):
            raise AudioValidationError("录音超过上传大小限制")
        try:
            info = sf.info(str(path))
        except Exception as exc:
            raise AudioValidationError(f"无法读取录音: {exc}") from exc
        if int(info.channels) != 2:
            raise AudioValidationError(f"要求双轨录音，实际声道数={info.channels}")
        if float(info.duration) <= 0:
            raise AudioValidationError("录音时长无效")
        return {
            "bytes": int(path.stat().st_size),
            "duration": round(float(info.duration), 3),
            "channels": int(info.channels),
            "sample_rate": int(info.samplerate),
            "format": str(info.format),
        }

    def process(self, audio_path: str | Path, channel_dir: str | Path) -> dict:
        audio_path = Path(audio_path)
        channel_dir = Path(channel_dir)
        channel_dir.mkdir(parents=True, exist_ok=True)
        audio_info = self.inspect(audio_path)
        left_path = channel_dir / "left.wav"
        right_path = channel_dir / "right.wav"
        audio_io.extract_channel(str(audio_path), 0, str(left_path), dur=None, sr=16000)
        audio_io.extract_channel(str(audio_path), 1, str(right_path), dur=None, sr=16000)

        left = asr_role.transcribe_role_features(str(left_path))
        right = asr_role.transcribe_role_features(str(right_path))
        decision = text_role.classify_features(left, right)
        role = {
            **decision,
            "confidence": "高" if decision.get("status") == "identified" else "待复核",
            "left_summary": left["summary"],
            "right_summary": right["summary"],
            "stage_count": 1,
            "role_model_version": self.config["models"]["role_model_version"],
        }
        transcript = {
            "left": left.get("text", ""),
            "right": right.get("text", ""),
            "customer_ch": role.get("customer_ch"),
            "agent_ch": role.get("agent_ch"),
        }

        vector = None
        if role.get("status") == "identified" and role.get("customer_ch") in {"L", "R"}:
            customer_path = left_path if role["customer_ch"] == "L" else right_path
            vector = embedding.embed(str(customer_path), disable_pbar=True).astype(np.float32)
            if vector.shape != (int(self.config["models"]["embedding_dimension"]),):
                raise RuntimeError(f"embedding维度异常: {vector.shape}")
            if not np.isfinite(vector).all():
                raise RuntimeError("embedding包含非法数值")
            norm = float(np.linalg.norm(vector))
            if norm <= 0:
                raise RuntimeError("embedding为零向量")
            vector /= norm

        return {
            "audio_info": audio_info,
            "role": role,
            "transcript": transcript,
            "embedding": vector,
            "channels": {
                "L": str(left_path),
                "R": str(right_path),
            },
        }
