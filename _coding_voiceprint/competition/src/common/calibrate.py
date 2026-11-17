# -*- coding: utf-8 -*-
"""
阈值标定工具 —— 移植自 0728/calibrate.py 的 compute_eer / hist_text。

供降噪 A/B 验证、阈值复标、扩样监控复用。
"""
import numpy as np


def compute_eer(genuine, impostor):
    """扫阈值求 EER(FAR==FRR 的点)。返回 (thr, eer)。

    genuine: 同人对相似度列表; impostor: 异人对相似度列表。
    任一为空返回 (None, None)。
    """
    g = np.array(genuine)
    im = np.array(impostor)
    if len(g) == 0 or len(im) == 0:
        return None, None
    thrs = np.unique(np.concatenate([g, im]))
    best = (1e9, None, 0.0, 0.0)
    for t in thrs:
        frr = float((g < t).mean())      # 同人被拒
        far = float((im >= t).mean())    # 异人被纳
        if abs(far - frr) < best[0]:
            best = (abs(far - frr), t, far, frr)
    return best[1], (best[2] + best[3]) / 2   # thr, eer≈(far+frr)/2


def hist_text(vals, lo=0.0, hi=1.0, bins=20, width=40):
    """文本直方图(相似度分布可视化)。"""
    vals = np.asarray(vals)
    if not len(vals):
        return "  (空)"
    h, edges = np.histogram(vals, bins=bins, range=(lo, hi))
    mx = max(h.max(), 1)
    out = []
    for i in range(bins):
        bar = "#" * int(h[i] / mx * width)
        out.append(f"  {edges[i]:.2f}-{edges[i+1]:.2f} | {bar} {h[i]}")
    return "\n".join(out)
