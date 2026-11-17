# -*- coding: utf-8 -*-
"""
固化的客户声纹提取管线 —— 上线系统的核心可复用入口。

离线建库与实时核验共用同一条链, 保证"建库怎么提、核验就怎么提"、避免不一致。

链路(编排 common 组件):
  1. 双轨校验     diarize._is_dual_track —— 非双轨抛异常(业务约束"一定双轨")
  2. 说话人分离   diarize.diarize —— 双轨转写 + 每声道拼接 wav
  3. 角色定位     role_id.decide_role —— 定客户声道; 低置信标 meta
  4. VAD 提纯     vad.energy_vad(可开关, 默认 OFF 以与标定基线一致)
  5. 质检门槛     有效语音 <MIN_DUR -> quality=reject
  6. 降噪         denoise.apply(可开关, 默认 OFF, A/B 有正收益才 ON)
  7. embedding    embedding.embed -> 192维归一化向量

用法:
  from common.extract import extract_customer_embedding
  emb = extract_customer_embedding("xxx.mp3")
  emb, meta = extract_customer_embedding("xxx.mp3", return_meta=True)
"""
import os
import json

import numpy as np
import soundfile as sf

from . import audio_io, diarize as D, role_id, vad, denoise, embedding

MIN_DUR = 3.0          # 客户声道有效音频质检门槛(秒)
SPK_CH = {"L": 0, "R": 1}


class NotDualTrackError(ValueError):
    """输入不是双轨录音(业务约束要求一定双轨), 属数据异常需暴露。"""


def _wav_dur(path):
    try:
        info = sf.info(path)
        return info.frames / info.samplerate
    except Exception:
        return 0.0


def extract_customer_embedding(audio_path, out_dir=None, use_vad=False,
                               use_denoise=None, return_meta=False):
    """从一通双轨电话录音提取客户声纹向量。

    audio_path: 录音路径(mp3/wav, 8k 双声道)
    out_dir: diarize 中间产物目录, 默认 <录音同级>/_extract_work
    use_vad: 是否对客户声道跑能量 VAD(默认 False, 与标定基线一致)
    use_denoise: 是否降噪; None=读 denoise.ENABLED 全局开关
    return_meta: True 时返回 (emb, meta)

    返回: emb(192,) 或 (emb, meta)。
      质检不过(reject)时 emb 可能为 None, meta.quality='reject'。
    异常: 非双轨抛 NotDualTrackError。
    """
    name = os.path.splitext(os.path.basename(audio_path))[0]
    if out_dir is None:
        out_dir = os.path.join(os.path.dirname(os.path.abspath(audio_path)), "_extract_work")

    meta = {"name": name, "customer_ch": None, "role_confidence": None,
            "dur": 0.0, "quality": "ok", "denoise_applied": False,
            "vad_applied": bool(use_vad), "model": "cam++"}

    # 1. 双轨校验
    if not D._is_dual_track(audio_path):
        raise NotDualTrackError(f"{name}: 非双轨录音, 不符合业务约束(一方一声道)")

    # 2. 说话人分离(产出 _diar.json + _spkN.wav)
    D.diarize(audio_path, out_dir=out_dir, min_seg=0.5)
    jpath = os.path.join(out_dir, name + "_diar.json")

    # 3. 角色定位客户声道
    agg = role_id.load_diar(jpath)
    role = role_id.decide_role(agg)
    if role["customer_ch"] is None:
        meta["quality"] = "reject"
        meta["role_confidence"] = role["confidence"]
        return (None, meta) if return_meta else None
    meta["customer_ch"] = role["customer_ch"]
    meta["role_confidence"] = role["confidence"]

    cust_wav = os.path.join(out_dir, f"{name}_spk{SPK_CH[role['customer_ch']]}.wav")
    if not os.path.exists(cust_wav):
        meta["quality"] = "reject"
        return (None, meta) if return_meta else None

    # 5. 质检门槛
    dur = _wav_dur(cust_wav)
    meta["dur"] = round(dur, 1)
    if dur < MIN_DUR:
        meta["quality"] = "reject"
        return (None, meta) if return_meta else None

    # 4/6. VAD + 降噪(可选; 都关时直接 embed spk wav, 与标定基线逐位一致)
    do_denoise = denoise.is_enabled() if use_denoise is None else use_denoise
    if not use_vad and not do_denoise:
        emb = embedding.embed(cust_wav)
    else:
        sig, sr = sf.read(cust_wav, dtype="float32")
        if sig.ndim > 1:
            sig = sig.mean(axis=1)
        if use_vad:
            sig = vad.energy_vad(sig, sr)
        if do_denoise:
            sig = denoise.apply(sig, sr)
            meta["denoise_applied"] = True
        proc_wav = os.path.join(out_dir, f"{name}_cust_proc.wav")
        sf.write(proc_wav, sig, sr)
        emb = embedding.embed(proc_wav)

    return (emb, meta) if return_meta else emb
