# -*- coding: utf-8 -*-
"""
本人主簇聚类 —— 冷启动定"本人 vs 代接"。

历史录音里同一客户号有多通, 不知哪通是本人。方案:
  1. 对该客户号名下所有客户声道 embedding 做图聚类(余弦>=阈值连边, 连通分量成簇)
  2. 主簇 = 最大簇(先验: 本人接听最多) -> 本人模板
  3. 其余簇 = aux(代接/他人), 保留但不参与本人判定
  4. 平票/只1-2通无法成簇 -> undecided(进人工复核, 不硬定)

连接阈值复用标定的 0.725(与判同阈值同源, 不引第二套魔法数)。
样本量小(一人几通到几十通), 纯 numpy 连通分量即可, 无需 faiss。
"""
import numpy as np

LINK_THRESHOLD = 0.725   # 聚类连边阈值(= 8k 电话 EER 阈值)


def _connected_components(adj):
    """邻接布尔矩阵 -> 连通分量列表(每个是索引 list)。"""
    n = len(adj)
    seen = [False] * n
    comps = []
    for i in range(n):
        if seen[i]:
            continue
        stack, comp = [i], []
        seen[i] = True
        while stack:
            u = stack.pop()
            comp.append(u)
            for v in range(n):
                if adj[u][v] and not seen[v]:
                    seen[v] = True
                    stack.append(v)
        comps.append(sorted(comp))
    return comps


def cluster_identity(embs, threshold=LINK_THRESHOLD):
    """对一个身份(客户号)名下的多条 embedding 聚类, 定主簇。

    embs: list[ndarray(192,)] 或 (N,192) 矩阵, 已 L2 归一化。
    返回 dict:
      {'primary': [idx...] | None,   # 主簇索引; undecided 时 None
       'aux': [[idx...], ...],        # 其余簇
       'n_clusters': int,
       'status': 'ok' | 'undecided',  # undecided: 无法可靠定本人
       'n_voices': int}               # 出现的不同声音数(= 簇数, 画像信号)
    """
    E = np.asarray(embs, dtype=np.float32)
    if E.ndim == 1:
        E = E.reshape(1, -1)
    n = len(E)
    if n == 0:
        return {"primary": None, "aux": [], "n_clusters": 0,
                "status": "undecided", "n_voices": 0}
    if n == 1:
        # 单通无法自证本人 vs 代接
        return {"primary": None, "aux": [[0]], "n_clusters": 1,
                "status": "undecided", "n_voices": 1}

    S = E @ E.T
    adj = S >= threshold
    np.fill_diagonal(adj, True)
    comps = _connected_components(adj)
    comps.sort(key=len, reverse=True)

    n_clusters = len(comps)
    # 主簇判定: 最大簇需显著大于次簇(严格大于), 否则 undecided
    if len(comps) == 1:
        primary, aux, status = comps[0], [], "ok"
    elif len(comps[0]) > len(comps[1]):
        primary, aux, status = comps[0], comps[1:], "ok"
    else:
        # 平票(最大簇不唯一大) -> 无法可靠定本人
        primary, aux, status = None, comps, "undecided"

    return {"primary": primary, "aux": aux, "n_clusters": n_clusters,
            "status": status, "n_voices": n_clusters}


def centroid(embs, idxs):
    """主簇质心(L2 归一化), 作 1:1 核验参照向量。"""
    E = np.asarray(embs, dtype=np.float32)
    c = E[idxs].mean(axis=0)
    nrm = np.linalg.norm(c)
    return c / nrm if nrm > 0 else c
