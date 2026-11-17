# -*- coding: utf-8 -*-
"""
把双声道电话录音拆成左右两个独立声道的 16kHz 单声道 wav, 并限长(避免超长录音内存爆)。
用于: 通话录音一方一个声道时, 分别提取双方声纹。

输出到 <src>/channels/  文件名形如  <别名>_L.wav / <别名>_R.wav

用法:
  python split_channels.py <src_dir> [--dur 60] [--offset 15]
  --dur    每段截取秒数(默认60); --offset 从第几秒开始截(默认15,跳过开场铃声/IVR)
"""
import argparse
import glob
import os
import subprocess

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# 文件名 -> 短别名 (取日期+主叫号码片段, 便于矩阵可读)
def alias(fname):
    base = os.path.splitext(os.path.basename(fname))[0]
    parts = base.split("_")
    date = parts[0].split("-")[0] if parts else base[:8]
    # 找一个像手机号的片段
    phone = ""
    for p in parts:
        if p.isdigit() and 10 <= len(p) <= 12:
            phone = p
            break
    return f"{date}_{phone}" if phone else date


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src_dir")
    ap.add_argument("--dur", type=int, default=60, help="每段截取秒数")
    ap.add_argument("--offset", type=int, default=15, help="起始偏移秒(跳过开场)")
    ap.add_argument("--exts", nargs="+", default=["mp3", "wav", "m4a"])
    args = ap.parse_args()

    out_dir = os.path.join(args.src_dir, "channels")
    os.makedirs(out_dir, exist_ok=True)

    files = []
    for e in args.exts:
        files.extend(glob.glob(os.path.join(args.src_dir, f"*.{e}")))
    files = sorted(set(files))
    if not files:
        print(f"{args.src_dir} 下没有音频")
        return

    for f in files:
        a = alias(f)
        for ch, tag in [(0, "L"), (1, "R")]:
            out = os.path.join(out_dir, f"{a}_{tag}.wav")
            # pan 滤镜提取单声道; -ss 偏移 -t 时长; -ar 16k
            cmd = [FFMPEG, "-y", "-ss", str(args.offset), "-t", str(args.dur),
                   "-i", f, "-af", f"pan=mono|c0=c{ch}", "-ar", "16000", out]
            subprocess.run(cmd, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"拆分完成: {os.path.basename(f)} -> {a}_L.wav / {a}_R.wav")
    print(f"\n全部完成 ({len(files)} 通 x2 声道), 输出目录: {out_dir}/")


if __name__ == "__main__":
    main()
