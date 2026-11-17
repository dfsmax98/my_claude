# -*- coding: utf-8 -*-
"""
能量 VAD 去静音: 把单声道 wav 里的静音/低能量帧剔除, 只保留说话主体语音, 拼接输出。
用于声纹比对前的预处理——去掉声道里的静音间隙和对方串音低能量段, 提纯说话人语音。

纯 numpy + soundfile 实现, 无需 pyannote / webrtcvad, 离线可跑。

用法:
  python vad_trim.py <wav_dir> [--out <out_dir>] [--frame 0.025] [--pct 60] [--min-keep 3]
  --frame    帧长(秒), 默认 0.025 (25ms)
  --pct      能量阈值百分位, 默认 60 (保留能量高于第60百分位的帧)
  --min-keep 至少保留秒数, 不足则跳过 VAD 用原始(避免切太狠)
"""
import argparse
import glob
import os

import numpy as np
import soundfile as sf


def energy_vad(signal, sr, frame_sec=0.025, pct=60, min_keep_sec=3.0):
    """返回去静音后的语音信号。基于短时能量 + 百分位动态阈值。"""
    flen = max(1, int(sr * frame_sec))
    n_frames = len(signal) // flen
    if n_frames < 4:
        return signal  # 太短不处理

    frames = signal[:n_frames * flen].reshape(n_frames, flen)
    energy = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-10)  # 每帧 RMS

    # 动态阈值: 能量的第 pct 百分位; 同时不低于全局能量的一个下限
    thr = np.percentile(energy, pct)
    keep = energy >= thr

    kept = frames[keep].reshape(-1)
    # 保底: 若切得只剩很少, 放宽到保留全部非极低能量帧
    if len(kept) < min_keep_sec * sr:
        thr2 = np.percentile(energy, 30)
        kept = frames[energy >= thr2].reshape(-1)
    if len(kept) < min_keep_sec * sr:
        return signal  # 仍太短, 用原始
    return kept


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wav_dir")
    ap.add_argument("--out", default=None, help="输出目录, 默认 <wav_dir>/vad")
    ap.add_argument("--frame", type=float, default=0.025)
    ap.add_argument("--pct", type=float, default=60)
    ap.add_argument("--min-keep", type=float, default=3.0)
    args = ap.parse_args()

    out_dir = args.out or os.path.join(args.wav_dir, "vad")
    os.makedirs(out_dir, exist_ok=True)

    files = sorted(glob.glob(os.path.join(args.wav_dir, "*.wav")))
    if not files:
        print(f"{args.wav_dir} 下没有 wav")
        return

    for f in files:
        data, sr = sf.read(f, dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)
        orig_sec = len(data) / sr
        kept = energy_vad(data, sr, args.frame, args.pct, args.min_keep)
        kept_sec = len(kept) / sr
        out = os.path.join(out_dir, os.path.basename(f))
        sf.write(out, kept, sr)
        print(f"{os.path.basename(f)}: {orig_sec:.1f}s -> {kept_sec:.1f}s (保留 {kept_sec/orig_sec*100:.0f}%)")
    print(f"\n完成, 输出目录: {out_dir}/")


if __name__ == "__main__":
    main()
