# -*- coding: utf-8 -*-
"""
把指定目录下的音频 (m4a/mp3/flac/wav 等) 转成 16kHz 单声道 wav (放到 <目录>/wav_16k/)。
用 imageio-ffmpeg 自带的 ffmpeg 静态二进制, 无需系统安装 ffmpeg。

用法:
  python convert_to_wav.py [目录] [--exts m4a mp3 flac ...]
  默认目录=当前目录; 默认格式= m4a mp3 flac wav
"""
import argparse
import glob
import os
import subprocess

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
DEFAULT_EXTS = ["m4a", "mp3", "flac", "wav", "aac", "ogg"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src_dir", nargs="?", default=".", help="源音频目录")
    ap.add_argument("--exts", nargs="+", default=DEFAULT_EXTS, help="要转换的扩展名")
    args = ap.parse_args()

    out_dir = os.path.join(args.src_dir, "wav_16k")
    os.makedirs(out_dir, exist_ok=True)

    files = []
    for e in args.exts:
        files.extend(glob.glob(os.path.join(args.src_dir, f"*.{e}")))
    files = sorted(set(files))
    if not files:
        print(f"{args.src_dir} 下没有匹配的音频文件 (格式: {args.exts})")
        return

    for f in files:
        name = os.path.splitext(os.path.basename(f))[0]
        out = os.path.join(out_dir, name + ".wav")
        # -ac 1 单声道, -ar 16000 重采样到 16kHz (电话 8kHz 会上采样以适配模型)
        cmd = [FFMPEG, "-y", "-i", f, "-ac", "1", "-ar", "16000", out]
        subprocess.run(cmd, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"转换完成: {os.path.basename(f)} -> {out}")
    print(f"\n全部完成 ({len(files)} 个), 输出目录: {out_dir}/")


if __name__ == "__main__":
    main()
