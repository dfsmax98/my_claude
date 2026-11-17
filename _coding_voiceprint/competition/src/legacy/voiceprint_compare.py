# -*- coding: utf-8 -*-
"""
开源声纹相似度比对 demo
模型: SpeechBrain ECAPA-TDNN (speechbrain/spkrec-ecapa-voxceleb)

功能:
  1) 1:1 比对   —— 两段录音是否同一人
  2) 1:N 检索   —— 一段待查录音 vs 声纹库, 返回最相似的若干条

用法:
  # 1:1
  python voiceprint_compare.py verify a.wav b.wav

  # 建库: 把一个目录下所有音频注册进声纹库 (文件名作为说话人id)
  python voiceprint_compare.py enroll ./enroll_wavs voiceprint_db.pkl

  # 1:N 检索
  python voiceprint_compare.py search query.wav voiceprint_db.pkl --topk 5

依赖见 requirements.txt。首次运行会自动下载模型 (~80MB) 到 pretrained_models/。
音频建议: 16kHz 单声道 wav; 其它格式/采样率会自动重采样。
"""

import argparse
import os
import pickle
import glob

import torch
import torchaudio
from speechbrain.inference.speaker import EncoderClassifier


# 相似度阈值: ECAPA-VoxCeleb 上余弦相似度经验阈值, 需用自己的数据标定
# 一般 0.25~0.35 之间, 高于阈值判为同一人。请务必用真实业务数据重新校准!
DEFAULT_THRESHOLD = 0.30

_MODEL = None


def get_model():
    """懒加载模型, 避免每次调用都重新加载。"""
    global _MODEL
    if _MODEL is None:
        _MODEL = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir="pretrained_models/spkrec-ecapa-voxceleb",
            run_opts={"device": "cuda" if torch.cuda.is_available() else "cpu"},
        )
    return _MODEL


def load_audio(path, target_sr=16000):
    """读音频 -> 单声道 -> 重采样到 16kHz。返回 (1, T) 张量。"""
    signal, sr = torchaudio.load(path)
    # 多声道取均值转单声道
    if signal.shape[0] > 1:
        signal = signal.mean(dim=0, keepdim=True)
    if sr != target_sr:
        signal = torchaudio.transforms.Resample(sr, target_sr)(signal)
    return signal


def embed(path):
    """把一段录音编码成 L2 归一化后的声纹向量 (numpy, shape=[192])。"""
    model = get_model()
    signal = load_audio(path)
    with torch.no_grad():
        emb = model.encode_batch(signal)          # (1, 1, 192)
    emb = emb.squeeze()                            # (192,)
    emb = torch.nn.functional.normalize(emb, dim=0)  # L2 归一化, 之后点积即余弦
    return emb.cpu().numpy()


def cosine(a, b):
    """两个已归一化向量的余弦相似度。"""
    import numpy as np
    return float(np.dot(a, b))


# ---------------- 子命令实现 ----------------

def cmd_verify(args):
    e1, e2 = embed(args.wav1), embed(args.wav2)
    score = cosine(e1, e2)
    same = score >= args.threshold
    print(f"文件A: {args.wav1}")
    print(f"文件B: {args.wav2}")
    print(f"余弦相似度: {score:.4f}  (阈值 {args.threshold})")
    print(f"判定: {'同一人 ✅' if same else '不同人 ❌'}")


def cmd_enroll(args):
    """把目录下的音频批量注册进声纹库。说话人id = 去扩展名的文件名。"""
    exts = ("*.wav", "*.mp3", "*.flac", "*.m4a")
    files = []
    for e in exts:
        files.extend(glob.glob(os.path.join(args.wav_dir, e)))
    if not files:
        print(f"目录下没有找到音频文件: {args.wav_dir}")
        return

    db = {}
    if os.path.exists(args.db_path):
        with open(args.db_path, "rb") as f:
            db = pickle.load(f)

    for i, path in enumerate(sorted(files), 1):
        spk_id = os.path.splitext(os.path.basename(path))[0]
        db[spk_id] = embed(path)
        print(f"[{i}/{len(files)}] 已注册: {spk_id}")

    with open(args.db_path, "wb") as f:
        pickle.dump(db, f)
    print(f"声纹库已保存: {args.db_path}  (共 {len(db)} 人)")


def cmd_search(args):
    """1:N 检索: 待查录音 vs 声纹库, 返回 topk 最相似。"""
    if not os.path.exists(args.db_path):
        print(f"声纹库不存在: {args.db_path}, 请先用 enroll 建库")
        return
    with open(args.db_path, "rb") as f:
        db = pickle.load(f)

    q = embed(args.query_wav)
    scores = sorted(
        ((spk_id, cosine(q, emb)) for spk_id, emb in db.items()),
        key=lambda x: x[1],
        reverse=True,
    )

    print(f"待查录音: {args.query_wav}   声纹库规模: {len(db)}")
    print(f"{'排名':<4}{'说话人id':<24}{'相似度':<10}{'命中'}")
    for rank, (spk_id, score) in enumerate(scores[:args.topk], 1):
        hit = "✅" if score >= args.threshold else ""
        print(f"{rank:<4}{spk_id:<24}{score:<10.4f}{hit}")

    top_id, top_score = scores[0]
    if top_score >= args.threshold:
        print(f"\n命中: 与【{top_id}】疑似同一人 (相似度 {top_score:.4f})")
    else:
        print(f"\n未命中: 最高相似度 {top_score:.4f} < 阈值 {args.threshold}")


def build_parser():
    p = argparse.ArgumentParser(description="开源声纹相似度比对 demo (ECAPA-TDNN)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pv = sub.add_parser("verify", help="1:1 两段录音是否同一人")
    pv.add_argument("wav1")
    pv.add_argument("wav2")
    pv.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    pv.set_defaults(func=cmd_verify)

    pe = sub.add_parser("enroll", help="批量注册目录音频到声纹库")
    pe.add_argument("wav_dir")
    pe.add_argument("db_path")
    pe.set_defaults(func=cmd_enroll)

    ps = sub.add_parser("search", help="1:N 检索")
    ps.add_argument("query_wav")
    ps.add_argument("db_path")
    ps.add_argument("--topk", type=int, default=5)
    ps.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ps.set_defaults(func=cmd_search)

    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    args.func(args)
