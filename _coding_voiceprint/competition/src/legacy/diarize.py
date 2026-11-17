# -*- coding: utf-8 -*-
"""
说话人分离 + 转录 (Speaker Diarization) —— 基于 FunASR AutoModel。

两种分离模式(自动选择):
  1) 双轨模式(优选): 电话录音底层是双声道立体声,一方一个声道。此时说话人身份
     直接来自声道(左=说话人0, 右=说话人1), 每个声道独立转录, 100% 准确、无模糊
     边界; 真实抢话自然呈现为两条时间重叠的句子。
  2) 单轨回退: 输入非双轨(已混音/单声道)时, 回退到 CAM++ 声纹聚类猜说话人。

为什么用 FunASR 而非 modelscope.pipelines:
  modelscope 的 speaker-diarization pipeline 在 Python 3.14 上导入链会段错误(原生库冲突),
  而 FunASR AutoModel 可正常运行, 且 spk_model=cam++ 自带说话人分离。
  额外好处: 一次产出「转录文本 + 每句是谁说的 + 时间段」, 比纯分离更适合反催收分析。

输出:
  - 屏幕打印每个说话人的时长 + 带说话人标记的对话文本
  - <out_dir>/<录音名>_diar.json    句级结果(说话人+起止+文本)
  - <out_dir>/<录音名>_spk{N}.wav   每个说话人拼接音频(供后续声纹比对)
  - <out_dir>/<录音名>_对话.md      可读的对话稿(标注说话人)

用法:
  MODELSCOPE_CACHE=./ms_cache python diarize.py <录音.wav/mp3/m4a> [--out-dir diar_out] [--min-seg 0.5]
  [--force-mixed]  强制走单轨 CAM++ 聚类(即使输入是双轨)
"""
import argparse
import json
import os
import subprocess

_MODEL = None


def get_model():
    """FunASR 模型: paraformer 转录 + vad + punc + cam++。

    注意: 双轨模式也用这个模型 —— 纯转录(不带 spk_model)不输出 sentence_info,
    拿不到句级时间戳。带 cam++ 才有 sentence_info; 双轨模式只用它的时间戳/文本,
    忽略其聚类出的 spk, 把说话人强制设为声道号。
    """
    global _MODEL
    if _MODEL is None:
        from funasr import AutoModel
        # hub=ms 走 ModelScope(国内直连); spk_model=cam++ 提供句级 sentence_info
        _MODEL = AutoModel(model="paraformer-zh", vad_model="fsmn-vad",
                           punc_model="ct-punc", spk_model="cam++",
                           hub="ms", disable_update=True)
    return _MODEL


def ensure_wav16k(path, tmp_dir):
    """非 16k 单声道 wav 先转码。"""
    if path.lower().endswith(".wav"):
        return path
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    os.makedirs(tmp_dir, exist_ok=True)
    out = os.path.join(tmp_dir, os.path.splitext(os.path.basename(path))[0] + ".wav")
    subprocess.run([ffmpeg, "-y", "-i", path, "-ac", "1", "-ar", "16000", out],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out


def _is_dual_track(audio_path):
    """判断是否为「一方一声道」的分轨录音。

    条件: 双声道 + 左右低相关(abs(corr)<0.3) + 单方独占发声时间占比 > 70%。
    直接读原始音频(不能先混单轨), 用能量活跃度估计独占比例。
    返回 True 表示可按声道天然分离。
    """
    import soundfile as sf
    import numpy as np
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
        return False  # 有一路是死声道, 不是真分轨
    corr = float(np.corrcoef(L, R)[0, 1])
    if abs(corr) >= 0.3:
        return False  # 高相关 = 假立体声(同内容双声道)
    # 独占发声比例: 双方各自单独发声的时间 / 总发声时间
    la, ra = np.abs(L) > 3e-3, np.abs(R) > 3e-3
    voiced = (la | ra).sum()
    if voiced == 0:
        return False
    solo = ((la & ~ra).sum() + (~la & ra).sum()) / voiced
    return solo > 0.70


def _extract_channel(audio_path, ch, tmp_dir, name):
    """用 ffmpeg 提取指定声道(0=左,1=右)为全长 16kHz 单声道 wav。"""
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    os.makedirs(tmp_dir, exist_ok=True)
    tag = "L" if ch == 0 else "R"
    out = os.path.join(tmp_dir, f"{name}_{tag}.wav")
    # pan 滤镜提取单声道(同 split_channels.py), 不加 -ss/-t, 要全长
    subprocess.run([ffmpeg, "-y", "-i", audio_path, "-af", f"pan=mono|c0=c{ch}",
                    "-ar", "16000", out],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out


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
    """双轨模式: 左右声道各当一个已知说话人, 独立转录后按时间归并。

    返回 (segs, chan_wavs) —— chan_wavs[speaker] = 该声道 16k wav 路径,
    供 _export_per_speaker 从对应声道切片(避免切进对方串音)。
    """
    print("检测到双轨录音, 按声道天然分离(左=说话人0, 右=说话人1)")
    tmp_dir = os.path.join(out_dir, "_channels")
    model = get_model()
    segs = []
    chan_wavs = {}
    for ch in (0, 1):
        wav = _extract_channel(audio_path, ch, tmp_dir, name)
        chan_wavs[ch] = wav
        res = model.generate(input=wav, batch_size_s=300)
        segs.extend(_parse_sentences(res, ch, min_seg))
    segs.sort(key=lambda s: s["start"])
    return segs, chan_wavs


def _diarize_mixed(wav, min_seg):
    """单轨回退模式: CAM++ 声纹聚类猜说话人。返回 segs。"""
    print("未检测到双轨, 回退 CAM++ 声纹聚类分离")
    model = get_model()
    res = model.generate(input=wav, batch_size_s=300)
    # res[0]['sentence_info'] = [{'text','start'(ms),'end'(ms),'spk'}, ...]
    info = res[0].get("sentence_info", []) if res else []
    segs = []
    for s in info:
        start, end = s.get("start", 0) / 1000.0, s.get("end", 0) / 1000.0
        if end - start >= min_seg:
            segs.append({"start": round(start, 2), "end": round(end, 2),
                         "speaker": int(s.get("spk", 0)), "text": s.get("text", "").strip()})
    return segs


def diarize(audio_path, out_dir="diar_out", min_seg=0.5, force_mixed=False):
    os.makedirs(out_dir, exist_ok=True)
    name = os.path.splitext(os.path.basename(audio_path))[0]

    # 选择分离模式: 双轨天然分离(优选) vs 单轨 CAM++ 聚类(回退)
    chan_wavs = None
    if not force_mixed and _is_dual_track(audio_path):
        segs, chan_wavs = _diarize_dual_track(audio_path, out_dir, name, min_seg)
    else:
        wav = ensure_wav16k(audio_path, os.path.join(out_dir, "_wav16k"))
        segs = _diarize_mixed(wav, min_seg)

    # 说话人时长统计
    spk_dur = {}
    for s in segs:
        spk_dur[s["speaker"]] = spk_dur.get(s["speaker"], 0) + (s["end"] - s["start"])
    print(f"=== {name}: {len(spk_dur)} 个说话人, {len(segs)} 句 ===")
    for spk in sorted(spk_dur):
        print(f"  说话人{spk}: 总时长 {spk_dur[spk]:.1f}s")

    # json
    jpath = os.path.join(out_dir, name + "_diar.json")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(segs, f, ensure_ascii=False, indent=2)

    # 可读对话稿
    mode = "双轨天然分离" if chan_wavs is not None else "CAM++ 说话人分离"
    mpath = os.path.join(out_dir, name + "_对话.md")
    with open(mpath, "w", encoding="utf-8") as f:
        f.write(f"# {name} 对话稿\n\n> FunASR 转录 + {mode}\n\n")
        for s in segs:
            f.write(f"**[说话人{s['speaker']}] {s['start']:.1f}-{s['end']:.1f}s**: {s['text']}\n\n")
    print(f"对话稿: {mpath}")
    print(f"分离结果: {jpath}")

    _export_per_speaker(segs, out_dir, name, chan_wavs, audio_path)
    return segs


def _export_per_speaker(segs, out_dir, name, chan_wavs=None, audio_path=None):
    """把每个说话人的片段拼成一个 wav, 供后续声纹比对。

    双轨模式(chan_wavs 给定): 从对应声道的独立 wav 切片, 避免切进对方串音。
    单轨模式: 从 16k 混音 wav 按 segs 时间切片(原逻辑)。
    """
    import soundfile as sf
    import numpy as np

    if chan_wavs is not None:
        # 双轨: 每个 speaker 从自己的声道 wav 切
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
        # 单轨: 从混音 wav 切
        wav = ensure_wav16k(audio_path, os.path.join(out_dir, "_wav16k"))
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
        print(f"  说话人{spk}音频: {out} ({len(merged)/_sr:.1f}s)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--out-dir", default="diar_out")
    ap.add_argument("--min-seg", type=float, default=0.5)
    ap.add_argument("--force-mixed", action="store_true",
                    help="强制走单轨 CAM++ 聚类(即使输入是双轨)")
    args = ap.parse_args()
    diarize(args.audio, args.out_dir, args.min_seg, args.force_mixed)


if __name__ == "__main__":
    main()
