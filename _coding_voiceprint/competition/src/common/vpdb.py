# -*- coding: utf-8 -*-
"""
声纹库读写 + 检索抽象 —— 抽自 voiceprint_campp.py 并扩展身份聚合语义。

库结构(pickle, 向后兼容现有 black_db.pkl):
  {"model":"cam++", "schema_version":2,
   "identities": {<身份键>: {...聚合信息...}},   # 可选, 新增
   "records": [{"id","emb"(192,),...}, ...]}      # 扁平列表, 兼容旧结构

检索:
  search(q, db, topk)              —— 逐条 record 最高分(旧语义, 兼容)
  search_by_identity(q, db, key)   —— 按身份聚合取最大余弦(上线语义)

底层用 numpy 矩阵运算(embs @ q, 已归一化即余弦), 万级以下够用;
达 Faiss 迁移触发条件时, 只需替换本文件检索实现, 业务层不变。
"""
import os
import pickle
import datetime

import numpy as np


def load_db(db_path):
    """读库; 不存在返回空库。补齐缺省字段保证向后兼容。"""
    if os.path.exists(db_path):
        with open(db_path, "rb") as f:
            db = pickle.load(f)
        db.setdefault("model", "cam++")
        db.setdefault("records", [])
        db.setdefault("schema_version", 1)
        return db
    return {"model": "cam++", "schema_version": 2, "identities": {}, "records": []}


def save_db(db, db_path):
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    with open(db_path, "wb") as f:
        pickle.dump(db, f)


def now_ts():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _emb_matrix(records):
    """堆叠所有 record 的 emb 成 (N,192) 矩阵。"""
    return np.stack([r["emb"] for r in records]) if records else np.zeros((0, 192), np.float32)


def search(q, db, topk=5):
    """1:N 逐条检索(旧语义)。返回 [(id, score), ...] 降序 topk。"""
    recs = db["records"]
    if not recs:
        return []
    scores = _emb_matrix(recs) @ q   # 已归一化 -> 余弦
    order = np.argsort(-scores)[:topk]
    return [(recs[int(i)]["id"], float(scores[int(i)])) for i in order]


def search_by_identity(q, db, id_key="cust_no", topk=5):
    """按身份聚合检索(上线语义): 每个身份取其模板集的最大余弦(max-pooling)。

    id_key: 身份字段名(客户库用 'cust_no', 黑产库用 'actor_id')。
    返回 [(身份键, 最大分, 命中record_id), ...] 降序 topk。
    """
    recs = db["records"]
    if not recs:
        return []
    scores = _emb_matrix(recs) @ q
    best = {}   # 身份 -> (最大分, record_id)
    for r, s in zip(recs, scores):
        key = r.get(id_key) or r.get("id")
        s = float(s)
        if key not in best or s > best[key][0]:
            best[key] = (s, r["id"])
    ranked = sorted(best.items(), key=lambda kv: -kv[1][0])[:topk]
    return [(k, v[0], v[1]) for k, v in ranked]
