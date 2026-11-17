# -*- coding: utf-8 -*-
"""
声纹相似度矩阵评测:
  读 ./wav_16k/ 下所有 wav, 两两算余弦相似度, 打印 N×N 矩阵。
  自动按文件名前缀(下划线前那段)判定"同人对/异人对", 给出区分度小结。

用法: python eval_matrix.py [--threshold 0.30]
"""
import argparse
import glob
import os

import numpy as np
import soundfile as sf
import torch
import torchaudio
from speechbrain.inference.speaker import EncoderClassifier

WAV_DIR = "wav_16k"

_MODEL = None


def get_model():
    global _MODEL
    if _MODEL is None:
        # Windows 默认 SYMLINK 策略需管理员权限, 改用 COPY 避免 WinError 1314
        from speechbrain.utils.fetching import LocalStrategy
        _MODEL = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir="pretrained_models/spkrec-ecapa-voxceleb",
            run_opts={"device": "cuda" if torch.cuda.is_available() else "cpu"},
            local_strategy=LocalStrategy.COPY,
        )
    return _MODEL


def embed(path):
    # 用 soundfile 读 wav (torchaudio 2.11 默认后端需 torchcodec, 这里绕开)
    data, sr = sf.read(path, dtype="float32", always_2d=True)  # (T, C)
    signal = torch.from_numpy(data.T)                          # (C, T)
    if signal.shape[0] > 1:
        signal = signal.mean(dim=0, keepdim=True)              # 转单声道
    if sr != 16000:
        signal = torchaudio.transforms.Resample(sr, 16000)(signal)
    with torch.no_grad():
        emb = get_model().encode_batch(signal).squeeze()
    emb = torch.nn.functional.normalize(emb, dim=0)
    return emb.cpu().numpy()


def speaker_of(name, label_map=None):
    """判定说话人id: 优先用传入的真实标签映射, 否则回退到文件名前缀(下划线前)。"""
    if label_map and name in label_map:
        return label_map[name]
    base = os.path.splitext(os.path.basename(name))[0]
    return base.split("_")[0]


def parse_labels(s):
    """解析 '1=A,1_1=A,3=A,2=B,4=B' -> {'1':'A','1_1':'A',...}"""
    if not s:
        return None
    m = {}
    for pair in s.split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            m[k.strip()] = v.strip()
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.30)
    ap.add_argument("--labels", type=str, default=None,
                    help="真实说话人标签, 如 '1=A,1_1=A,3=A,2=B,4=B'; 不传则按文件名前缀分组")
    ap.add_argument("--wav-dir", type=str, default=WAV_DIR,
                    help=f"wav 目录, 默认 {WAV_DIR}")
    args = ap.parse_args()
    label_map = parse_labels(args.labels)

    files = sorted(glob.glob(os.path.join(args.wav_dir, "*.wav")))
    if not files:
        print(f"{args.wav_dir}/ 下没有 wav, 请先运行 convert_to_wav.py")
        return

    names = [os.path.splitext(os.path.basename(f))[0] for f in files]
    print(f"加载 {len(files)} 个音频, 计算声纹向量...")
    embs = {n: embed(f) for n, f in zip(names, files)}

    # 相似度矩阵
    print("\n=== 余弦相似度矩阵 ===")
    header = "        " + "".join(f"{n:>9}" for n in names)
    print(header)
    for ni in names:
        row = f"{ni:>8}"
        for nj in names:
            row += f"{float(np.dot(embs[ni], embs[nj])):>9.3f}"
        print(row)

    # 同人/异人对统计
    same_pairs, diff_pairs = [], []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            ni, nj = names[i], names[j]
            score = float(np.dot(embs[ni], embs[nj]))
            pair = (ni, nj, score)
            if speaker_of(ni, label_map) == speaker_of(nj, label_map):
                same_pairs.append(pair)
            else:
                diff_pairs.append(pair)

    print(f"\n=== 配对明细 (阈值 {args.threshold}) ===")
    print("同人对:")
    for ni, nj, s in same_pairs:
        flag = "[OK]判同人" if s >= args.threshold else "[漏报]判异人"
        print(f"  {ni:>6} vs {nj:<6}  {s:.3f}  {flag}")
    print("异人对:")
    for ni, nj, s in diff_pairs:
        flag = "[误报]判同人" if s >= args.threshold else "[OK]判异人"
        print(f"  {ni:>6} vs {nj:<6}  {s:.3f}  {flag}")

    # 区分度小结
    if same_pairs and diff_pairs:
        smin = min(s for *_, s in same_pairs)
        dmax = max(s for *_, s in diff_pairs)
        print("\n=== 区分度小结 ===")
        print(f"同人对最低相似度: {smin:.3f}")
        print(f"异人对最高相似度: {dmax:.3f}")
        gap = smin - dmax
        if gap > 0:
            mid = (smin + dmax) / 2
            print(f"存在清晰间隔 {gap:.3f}, 建议阈值取中点 ≈ {mid:.3f}")
        else:
            print(f"[!] 同人/异人分数区间重叠 {abs(gap):.3f}, 阈值难完美切分")
            print("   电话/短录音常见, 需更多样本标定或换中文模型")


if __name__ == "__main__":
    main()
