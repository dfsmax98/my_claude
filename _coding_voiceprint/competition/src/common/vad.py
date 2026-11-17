# -*- coding: utf-8 -*-
"""
能量 VAD 去静音 —— 移植自 vad_trim.py 的 energy_vad(纯 numpy, 零改动)。

把单声道信号里的静音/低能量帧剔除, 只保留说话主体语音, 拼接返回。
用于声纹比对前提纯: 去掉声道里的静音间隙和对方串音低能量段。
基于短时能量 + 百分位动态阈值, 离线无依赖(不需 pyannote/webrtcvad)。
"""
import numpy as np


def energy_vad(signal, sr, frame_sec=0.025, pct=60, min_keep_sec=3.0):
    """返回去静音后的语音信号。

    frame_sec: 帧长(秒), 默认 25ms
    pct: 能量阈值百分位, 保留能量高于第 pct 百分位的帧
    min_keep_sec: 至少保留秒数, 切太狠则放宽阈值, 仍不足则返回原始
    """
    flen = max(1, int(sr * frame_sec))
    n_frames = len(signal) // flen
    if n_frames < 4:
        return signal  # 太短不处理

    frames = signal[:n_frames * flen].reshape(n_frames, flen)
    energy = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-10)  # 每帧 RMS

    thr = np.percentile(energy, pct)
    keep = energy >= thr
    kept = frames[keep].reshape(-1)

    # 保底: 切得只剩很少 -> 放宽到第30百分位; 仍太短 -> 用原始
    if len(kept) < min_keep_sec * sr:
        kept = frames[energy >= np.percentile(energy, 30)].reshape(-1)
    if len(kept) < min_keep_sec * sr:
        return signal
    return kept
