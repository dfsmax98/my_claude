# -*- coding: utf-8 -*-
"""
音频 IO —— 合并现有 3 处重复的 ffmpeg 提声道/转码逻辑。

统一了此前散落在 split_channels.py / diarize.py / 0728/compare_0728.py 里的实现
(offset 0/10/15、dur 60/120/全长 各不相同, 是隐性 bug 源)。
现在默认全长, 由调用方按需显式传 offset/dur。

用 imageio_ffmpeg 自带静态 ffmpeg(免装系统 ffmpeg)。
电话 8k 上采样到 16k 适配 CAM++。
"""
import os
import subprocess

try:
    import imageio_ffmpeg
except ImportError:
    imageio_ffmpeg = None

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe() if imageio_ffmpeg else None


def _resample(signal, source_sr, target_sr):
    if source_sr == target_sr:
        return signal
    from math import gcd
    from scipy.signal import resample_poly

    factor = gcd(source_sr, target_sr)
    return resample_poly(signal, target_sr // factor, source_sr // factor)


def _extract_channel_without_ffmpeg(src, ch, out, offset, dur, sr):
    import soundfile as sf

    with sf.SoundFile(src) as source:
        source_sr = source.samplerate
        if ch >= source.channels:
            raise ValueError(f"输入只有{source.channels}个声道，无法提取声道{ch}")
        source.seek(min(int(offset * source_sr), len(source)))
        frames = -1 if dur is None else int(dur * source_sr)
        data = source.read(frames=frames, dtype="float32", always_2d=True)
    signal = _resample(data[:, ch], source_sr, sr)
    sf.write(out, signal, sr, subtype="PCM_16")
    return out


def extract_channel(src, ch, out, offset=0, dur=None, sr=16000):
    """提取指定声道为单声道 wav。

    ch: 0=左(L), 1=右(R)
    offset: 起始秒(默认 0, 不跳过)
    dur: 截取秒数(默认 None=全长)
    sr: 输出采样率(默认 16000)
    """
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    if FFMPEG is None:
        return _extract_channel_without_ffmpeg(src, ch, out, offset, dur, sr)

    cmd = [FFMPEG, "-y"]
    if offset:
        cmd += ["-ss", str(offset)]
    if dur:
        cmd += ["-t", str(dur)]
    cmd += ["-i", src, "-af", f"pan=mono|c0=c{ch}", "-ar", str(sr), out]
    subprocess.run(cmd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out


def ensure_wav16k(path, tmp_dir):
    """非 wav 输入先转成 16k 单声道 wav; 已是 wav 直接返回原路径。"""
    if path.lower().endswith(".wav"):
        return path
    os.makedirs(tmp_dir, exist_ok=True)
    out = os.path.join(tmp_dir, os.path.splitext(os.path.basename(path))[0] + ".wav")
    if FFMPEG is None:
        import soundfile as sf

        data, source_sr = sf.read(path, dtype="float32", always_2d=True)
        signal = _resample(data.mean(axis=1), source_sr, 16000)
        sf.write(out, signal, 16000, subtype="PCM_16")
        return out

    subprocess.run([FFMPEG, "-y", "-i", path, "-ac", "1", "-ar", "16000", out],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out
