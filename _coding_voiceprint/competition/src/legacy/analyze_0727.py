# -*- coding: utf-8 -*-
"""
0727 批次声纹分析: 5 通录音的内部相似度矩阵 + 每段 vs black_db 的 1:N 检索。
沿用 0709 方法 (FunASR diarize -> CAM++ embedding -> 余弦)。
输出全部 print 到 stdout, 由外层重定向到日志; embedding 缓存到 npz 避免重跑。
"""
import os, glob, itertools
import numpy as np
import voiceprint_campp as V

DIR = "0727/diar_out/"
CACHE = "0727/_emb_cache.npz"

# 短标签: 通话日期时间 + 说话人号 (角色列后面按矩阵判定, 不预设)
def short(fn):
    b = os.path.basename(fn)
    date = b[:13]                      # 20250624-1623
    spk = b.split("_spk")[1].split(".")[0]
    return f"{date}_spk{spk}"

files = sorted(glob.glob(DIR + "*_spk*.wav"))
labels = [short(f) for f in files]

# ---- 提 embedding (带缓存) ----
if os.path.exists(CACHE):
    d = np.load(CACHE, allow_pickle=True)
    cached = {k: d[k] for k in d.files}
else:
    cached = {}
embs = []
for f, lab in zip(files, labels):
    if lab in cached:
        embs.append(cached[lab])
    else:
        print("embedding", lab, flush=True)
        e = V.embed(f)
        cached[lab] = e
        embs.append(e)
np.savez(CACHE, **cached)
embs = np.stack(embs)
n = len(files)

# ---- 内部 N×N 矩阵 ----
print("\nMATRIX_START", flush=True)
hdr = "              " + "".join(f"{l[9:]:>10}" for l in labels)   # 只显示时分_spkN 省宽
print(hdr)
for i in range(n):
    row = f"{labels[i]:>13} "
    for j in range(n):
        row += f"{float(np.dot(embs[i], embs[j])):>10.3f}"
    print(row)

# ---- 跨通高相似对 (排除同一通话内部) ----
def call_id(lab):
    return lab[:13]
print("\nCROSS_CALL_PAIRS (>=0.45, 降序):")
pairs = []
for i, j in itertools.combinations(range(n), 2):
    if call_id(labels[i]) != call_id(labels[j]):
        pairs.append((labels[i], labels[j], float(np.dot(embs[i], embs[j]))))
for a, b, s in sorted(pairs, key=lambda x: -x[2]):
    if s >= 0.45:
        print(f"  {a}  vs  {b}: {s:.3f}")

# ---- 每段 vs black_db (0709 换号客户库) ----
print("\nBLACKDB_SEARCH_START", flush=True)
db = V.load_db("black_db.pkl")
db_embs = np.stack([r["emb"] for r in db["records"]])
db_ids = [r["id"] for r in db["records"]]
for i in range(n):
    sc = db_embs @ embs[i]
    order = np.argsort(-sc)
    best_id, best = db_ids[int(order[0])], float(sc[order[0]])
    hit = "HIT" if best >= 0.50 else ""
    print(f"  {labels[i]:>13}: top={best_id} {best:.3f} {hit}")
print("ANALYSIS_DONE", flush=True)
