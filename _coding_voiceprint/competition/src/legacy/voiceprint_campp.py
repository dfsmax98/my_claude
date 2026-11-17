# -*- coding: utf-8 -*-
"""
CAM++ 声纹库 + 1:N 检索 —— 黑产声纹库核心工具 (P1)。

为什么不用 voiceprint_compare.py(ECAPA)/eval_campp_zh.py(modelscope.pipelines):
  1. ECAPA 是英文模型, 8k 电话录音上掉点(客户簇 0.709), CAM++ 顶到 0.805。
  2. modelscope.pipelines 在 Python 3.14 上导入即段错误(退出码139)。
  经实测: FunASR 的 AutoModel(model='cam++') 用的是同一个中文 CAM++ 权重,
  且能正常取出 192 维 spk_embedding, 无段错误。本脚本即走这条路。

声纹向量: 192 维, L2 归一化后点积即余弦相似度。

声纹库格式 (pickle):
  {
    "model": "cam++",
    "records": [ {"id": str, "emb": ndarray(192,), "source": str, "added": str}, ... ]
  }

用法:
  # 1:1 验证 两段录音是否同一人
  MODELSCOPE_CACHE=./ms_cache python voiceprint_campp.py verify a.wav b.wav

  # 建库: 把目录下所有音频注册进声纹库 (说话人id = 去扩展名文件名, 可加前缀)
  MODELSCOPE_CACHE=./ms_cache python voiceprint_campp.py enroll ./wavs black_db.pkl --id-prefix 0709_

  # 1:N 检索: 待查录音 vs 声纹库, 返回 topk
  MODELSCOPE_CACHE=./ms_cache python voiceprint_campp.py search query.wav black_db.pkl --topk 5

  # 查看库内容
  MODELSCOPE_CACHE=./ms_cache python voiceprint_campp.py info black_db.pkl
"""
import argparse
import datetime
import glob
import os
import pickle

import numpy as np

# CAM++ 电话中文场景经验阈值。0709 案例: 同一客户 0.66~0.805, 异人更低。
# 这是临时值, 必须用可标注数据(交接文档 task 3)重新标定电话/高清两套阈值!
DEFAULT_THRESHOLD = 0.50

_MODEL = None


def get_model():
    """懒加载 FunASR CAM++ 说话人模型。"""
    global _MODEL
    if _MODEL is None:
        from funasr import AutoModel
        _MODEL = AutoModel(model="cam++", hub="ms", disable_update=True)
    return _MODEL


def embed(path):
    """把一段录音编码成 L2 归一化的 192 维声纹向量 (numpy float32)。"""
    model = get_model()
    res = model.generate(input=path)
    rec = res[0] if isinstance(res, list) else res
    emb = np.asarray(rec["spk_embedding"], dtype=np.float32).reshape(-1)  # (192,)
    norm = np.linalg.norm(emb)
    if norm > 0:
        emb = emb / norm
    return emb


def cosine(a, b):
    """两个已归一化向量的余弦相似度。"""
    return float(np.dot(a, b))


# ---------------- 声纹库读写 ----------------

def load_db(db_path):
    if os.path.exists(db_path):
        with open(db_path, "rb") as f:
            db = pickle.load(f)
        db.setdefault("model", "cam++")
        db.setdefault("records", [])
        return db
    return {"model": "cam++", "records": []}


def save_db(db, db_path):
    with open(db_path, "wb") as f:
        pickle.dump(db, f)


# ---------------- 子命令 ----------------

def cmd_verify(args):
    e1, e2 = embed(args.wav1), embed(args.wav2)
    s = cosine(e1, e2)
    same = s >= args.threshold
    print(f"文件A: {args.wav1}")
    print(f"文件B: {args.wav2}")
    print(f"余弦相似度: {s:.4f}  (阈值 {args.threshold})")
    print(f"判定: {'同一人 ✅' if same else '不同人 ❌'}")


def cmd_enroll(args):
    exts = ("*.wav", "*.mp3", "*.flac", "*.m4a")
    files = []
    for e in exts:
        files.extend(glob.glob(os.path.join(args.wav_dir, e)))
    files = sorted(set(files))
    if not files:
        print(f"目录下没有找到音频文件: {args.wav_dir}")
        return

    db = load_db(args.db_path)
    existing = {r["id"] for r in db["records"]}
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    added = 0
    for i, path in enumerate(files, 1):
        spk_id = args.id_prefix + os.path.splitext(os.path.basename(path))[0]
        if spk_id in existing:
            print(f"[{i}/{len(files)}] 跳过(已存在): {spk_id}")
            continue
        db["records"].append({
            "id": spk_id,
            "emb": embed(path),
            "source": os.path.abspath(path),
            "added": now,
        })
        existing.add(spk_id)
        added += 1
        print(f"[{i}/{len(files)}] 已注册: {spk_id}")

    save_db(db, args.db_path)
    print(f"声纹库已保存: {args.db_path}  (新增 {added}, 共 {len(db['records'])} 条)")


def cmd_search(args):
    db = load_db(args.db_path)
    if not db["records"]:
        print(f"声纹库为空或不存在: {args.db_path}, 请先用 enroll 建库")
        return

    q = embed(args.query_wav)
    embs = np.stack([r["emb"] for r in db["records"]])  # (N, 192)
    scores = embs @ q  # 已归一化 -> 余弦
    order = np.argsort(-scores)

    print(f"待查录音: {args.query_wav}   声纹库规模: {len(db['records'])}")
    print(f"{'排名':<4}{'说话人id':<40}{'相似度':<10}{'命中'}")
    for rank, idx in enumerate(order[:args.topk], 1):
        rid = db["records"][idx]["id"]
        s = float(scores[idx])
        hit = "✅" if s >= args.threshold else ""
        print(f"{rank:<4}{rid:<40}{s:<10.4f}{hit}")

    top_idx = int(order[0])
    top_id, top_score = db["records"][top_idx]["id"], float(scores[top_idx])
    if top_score >= args.threshold:
        print(f"\n命中: 与【{top_id}】疑似同一人 (相似度 {top_score:.4f})")
    else:
        print(f"\n未命中: 最高相似度 {top_score:.4f} < 阈值 {args.threshold}")


def cmd_info(args):
    db = load_db(args.db_path)
    print(f"声纹库: {args.db_path}")
    print(f"模型: {db.get('model')}   记录数: {len(db['records'])}")
    for r in db["records"]:
        print(f"  {r['id']:<40} added={r.get('added','?')}  src={r.get('source','?')}")


def build_parser():
    p = argparse.ArgumentParser(description="CAM++ 声纹库 + 1:N 检索 (黑产声纹库)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pv = sub.add_parser("verify", help="1:1 两段录音是否同一人")
    pv.add_argument("wav1")
    pv.add_argument("wav2")
    pv.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    pv.set_defaults(func=cmd_verify)

    pe = sub.add_parser("enroll", help="批量注册目录音频到声纹库")
    pe.add_argument("wav_dir")
    pe.add_argument("db_path")
    pe.add_argument("--id-prefix", default="", help="说话人id前缀, 便于区分来源批次")
    pe.set_defaults(func=cmd_enroll)

    ps = sub.add_parser("search", help="1:N 检索")
    ps.add_argument("query_wav")
    ps.add_argument("db_path")
    ps.add_argument("--topk", type=int, default=5)
    ps.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ps.set_defaults(func=cmd_search)

    pi = sub.add_parser("info", help="查看声纹库内容")
    pi.add_argument("db_path")
    pi.set_defaults(func=cmd_info)

    return p


if __name__ == "__main__":
    a = build_parser().parse_args()
    a.func(a)
