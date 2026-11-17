# -*- coding: utf-8 -*-
"""
说话人分离 + 转录 —— 移植自 diarize.py 顶层逻辑, 内部改用 common/audio_io。

双轨模式(优选): 电话录音一方一声道, speaker0=左L, speaker1=右R, 每声道独立
转录, 100% 准确无模糊边界。单轨回退: CAM++ 声纹聚类。

为什么用 FunASR 而非 modelscope.pipelines: 后者在 Python 3.14 段错误(139)。
FunASR AutoModel + spk_model=cam++ 自带句级 sentence_info。

产出:
  <out_dir>/<name>_diar.json    句级(speaker/start/end/text)
  <out_dir>/<name>_spk{N}.wav   每说话人拼接音频(供声纹比对)
  <out_dir>/<name>_对话.md      可读对话稿
"""
import json
import os

import numpy as np

from . import audio_io
from .model_paths import resolve_model

_MODEL = None


def get_model():
    """FunASR: paraformer 转录 + vad + punc + cam++(提供句级 sentence_info)。"""
    global _MODEL
    if _MODEL is None:
        from funasr import AutoModel
        _MODEL = AutoModel(model=resolve_model("paraformer-zh"),
                           vad_model=resolve_model("fsmn-vad"),
                           punc_model=resolve_model("ct-punc"),
                           spk_model=resolve_model("cam++"),
                           hub="ms", disable_update=True)
    return _MODEL


def _is_dual_track(audio_path):
    """判断是否「一方一声道」分轨录音。

    条件: 双声道 + 左右低相关(abs(corr)<0.3) + 单方独占发声占比>70%。
    """
    import soundfile as sf
    try:
        info = sf.info(audio_path)
    except Exception:
        return False
    if info.channels != 2:
        return False
    data, _ = sf.read(audio_path, dtype="float32")
    if data.ndim != 2 or data.shape[1] != 2:
        return False
    L, R = data[:, 0], data[:, 1]
    if L.std() < 1e-6 or R.std() < 1e-6:
        return False
    corr = float(np.corrcoef(L, R)[0, 1])
    if abs(corr) >= 0.3:
        return False
    la, ra = np.abs(L) > 3e-3, np.abs(R) > 3e-3
    voiced = (la | ra).sum()
    if voiced == 0:
        return False
    solo = ((la & ~ra).sum() + (~la & ra).sum()) / voiced
    return solo > 0.70


def _parse_sentences(res, speaker, min_seg):
    """从 FunASR 结果解析句级 segs, speaker 固定为传入值。"""
    info = res[0].get("sentence_info", []) if res else []
    segs = []
    for s in info:
        start, end = s.get("start", 0) / 1000.0, s.get("end", 0) / 1000.0
        if end - start >= min_seg:
            segs.append({"start": round(start, 2), "end": round(end, 2),
                         "speaker": speaker, "text": s.get("text", "").strip()})
    return segs


def _diarize_dual_track(audio_path, out_dir, name, min_seg):
    """双轨: 左右声道各当一个说话人, 独立转录后按时间归并。

    返回 (segs, chan_wavs), chan_wavs[speaker]=该声道 16k wav 路径。
    """
    tmp_dir = os.path.join(out_dir, "_channels")
    model = get_model()
    segs, chan_wavs = [], {}
    for ch in (0, 1):
        tag = "L" if ch == 0 else "R"
        wav = audio_io.extract_channel(
            audio_path, ch, os.path.join(tmp_dir, f"{name}_{tag}.wav"))
        chan_wavs[ch] = wav
        res = model.generate(input=wav, batch_size_s=300)
        segs.extend(_parse_sentences(res, ch, min_seg))
    segs.sort(key=lambda s: s["start"])
    return segs, chan_wavs


def _diarize_mixed(wav, min_seg):
    """单轨回退: CAM++ 声纹聚类猜说话人。"""
    model = get_model()
    res = model.generate(input=wav, batch_size_s=300)
    info = res[0].get("sentence_info", []) if res else []
    segs = []
    for s in info:
        start, end = s.get("start", 0) / 1000.0, s.get("end", 0) / 1000.0
        if end - start >= min_seg:
            segs.append({"start": round(start, 2), "end": round(end, 2),
                         "speaker": int(s.get("spk", 0)), "text": s.get("text", "").strip()})
    return segs


def diarize(audio_path, out_dir="diar_out", min_seg=0.5, force_mixed=False):
    """顶层编排。返回句级 segs 列表, 并落盘 json/对话稿/每说话人 wav。"""
    os.makedirs(out_dir, exist_ok=True)
    name = os.path.splitext(os.path.basename(audio_path))[0]

    chan_wavs = None
    if not force_mixed and _is_dual_track(audio_path):
        segs, chan_wavs = _diarize_dual_track(audio_path, out_dir, name, min_seg)
    else:
        wav = audio_io.ensure_wav16k(audio_path, os.path.join(out_dir, "_wav16k"))
        segs = _diarize_mixed(wav, min_seg)

    jpath = os.path.join(out_dir, name + "_diar.json")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(segs, f, ensure_ascii=False, indent=2)

    mode = "双轨天然分离" if chan_wavs is not None else "CAM++ 说话人分离"
    with open(os.path.join(out_dir, name + "_对话.md"), "w", encoding="utf-8") as f:
        f.write(f"# {name} 对话稿\n\n> FunASR 转录 + {mode}\n\n")
        for s in segs:
            f.write(f"**[说话人{s['speaker']}] {s['start']:.1f}-{s['end']:.1f}s**: {s['text']}\n\n")

    _export_per_speaker(segs, out_dir, name, chan_wavs, audio_path)
    return segs


def _export_per_speaker(segs, out_dir, name, chan_wavs=None, audio_path=None):
    """把每个说话人的片段拼成一个 wav。双轨从对应声道切(避免串音), 单轨从混音切。"""
    import soundfile as sf

    if chan_wavs is not None:
        chan_data = {}
        for spk, wpath in chan_wavs.items():
            d, sr = sf.read(wpath)
            if d.ndim > 1:
                d = d.mean(axis=1)
            chan_data[spk] = (d, sr)
        by_spk = {}
        for s in segs:
            d, sr = chan_data[s["speaker"]]
            a, b = int(s["start"] * sr), int(s["end"] * sr)
            by_spk.setdefault(s["speaker"], []).append(d[a:b])
        _sr = next(iter(chan_data.values()))[1]
    else:
        wav = audio_io.ensure_wav16k(audio_path, os.path.join(out_dir, "_wav16k"))
        data, _sr = sf.read(wav)
        if data.ndim > 1:
            data = data.mean(axis=1)
        by_spk = {}
        for s in segs:
            a, b = int(s["start"] * _sr), int(s["end"] * _sr)
            by_spk.setdefault(s["speaker"], []).append(data[a:b])

    for spk, chunks in by_spk.items():
        merged = np.concatenate(chunks) if chunks else np.array([])
        out = os.path.join(out_dir, f"{name}_spk{spk}.wav")
        sf.write(out, merged, _sr)
