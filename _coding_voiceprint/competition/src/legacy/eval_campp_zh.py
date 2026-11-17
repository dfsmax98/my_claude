# -*- coding: utf-8 -*-
"""
用中文电话场景声纹模型 3D-Speaker CAM++ (阿里 ModelScope) 跑 N×N 相似度矩阵。
模型: iic/speech_campplus_sv_zh-cn_16k-common (国内可直连, 不受 HF 墙影响)

对比 ECAPA(英文模型)的意义: CAM++ 在中文/电话数据上训练, 理论上对本场景区分度更高。

用法:
  MODELSCOPE_CACHE=./ms_cache python eval_campp_zh.py --wav-dir 0709/channels
"""
import argparse
import glob
import itertools
import os

import numpy as np

MODEL_ID = "iic/speech_campplus_sv_zh-cn_16k-common"

_PIPE = None


def get_pipe():
    global _PIPE
    if _PIPE is None:
        from modelscope.pipelines import pipeline
        _PIPE = pipeline(task="speaker-verification", model=MODEL_ID)
    return _PIPE


def score(pipe, wav1, wav2):
    """返回两段音频的相似度 (余弦, 约 -1~1)。"""
    r = pipe([wav1, wav2])
    # 不同版本返回 key 可能是 'score'
    if isinstance(r, dict):
        for k in ("score", "cosine", "similarity"):
            if k in r:
                return float(r[k])
    raise RuntimeError(f"无法从 pipeline 结果解析相似度: {r}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav-dir", default="0709/channels")
    ap.add_argument("--threshold", type=float, default=0.30)
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.wav_dir, "*.wav")))
    if not files:
        print(f"{args.wav_dir} 下没有 wav")
        return
    names = [os.path.splitext(os.path.basename(f))[0] for f in files]
    short = [n[:20] for n in names]

    print(f"加载 CAM++ 中文模型, 处理 {len(files)} 个声道 ({len(files)*(len(files)-1)//2} 对)...")
    pipe = get_pipe()

    n = len(files)
    mat = np.eye(n)
    for i, j in itertools.combinations(range(n), 2):
        s = score(pipe, files[i], files[j])
        mat[i, j] = mat[j, i] = s
        print(f"  {short[i]} vs {short[j]}: {s:.3f}")

    # 打印矩阵
    print("\n=== CAM++ 余弦相似度矩阵 ===")
    print("        " + "".join(f"{s:>9}" for s in short))
    for i, si in enumerate(short):
        row = f"{si:>8}"
        for j in range(n):
            row += f"{mat[i, j]:>9.3f}"
        print(row)

    # 跨通话高相似对 (排除同通话 L/R, 即前缀相同的)
    def call_of(name):
        return name.split("_")[0] + "_" + (name.split("_")[1] if len(name.split("_")) > 1 else "")

    print("\n=== 跨通话高相似对 (>=0.4, 降序) ===")
    pairs = []
    for i, j in itertools.combinations(range(n), 2):
        if call_of(names[i]) != call_of(names[j]):
            pairs.append((short[i], short[j], mat[i, j]))
    for a, b, s in sorted(pairs, key=lambda x: -x[2]):
        if s >= 0.4:
            print(f"  {a} vs {b}: {s:.3f}")


if __name__ == "__main__":
    main()
