# -*- coding: utf-8 -*-
"""
CAM++ 声纹 embedding —— 上线系统唯一 embedding 来源。

抽自 voiceprint_campp.py, 保持行为一致:
  - FunASR AutoModel(model='cam++'), 走 ModelScope (hub='ms'), 避开 modelscope.pipelines
    在 Python 3.14 上的段错误(退出码139)。
  - 192 维, L2 归一化后点积即余弦相似度。
  - 懒加载单例, 避免每次调用重载模型(~60s)。
"""
import numpy as np

from .model_paths import resolve_model

_MODEL = None


def get_model():
    """懒加载 FunASR CAM++ 说话人模型(单例)。"""
    global _MODEL
    if _MODEL is None:
        from funasr import AutoModel
        _MODEL = AutoModel(model=resolve_model("cam++"), hub="ms",
                           disable_update=True)
    return _MODEL


def embed(path, **generate_kwargs):
    """把一段录音编码成 L2 归一化的 192 维声纹向量 (numpy float32)。"""
    model = get_model()
    res = model.generate(input=path, **generate_kwargs)
    rec = res[0] if isinstance(res, list) else res
    emb = np.asarray(rec["spk_embedding"], dtype=np.float32).reshape(-1)  # (192,)
    norm = np.linalg.norm(emb)
    if norm > 0:
        emb = emb / norm
    return emb


def cosine(a, b):
    """两个已归一化向量的余弦相似度。"""
    return float(np.dot(a, b))
