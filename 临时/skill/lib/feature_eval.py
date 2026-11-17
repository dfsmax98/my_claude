# -*- coding: utf-8 -*-
"""
精简特征评估模块 (替代 DDViz 的评估部分, 无 optbinning/xlwings 依赖)。

指标: IV / KS / PSI / 最大风险倍数(lift), 支持分月(dt_cut) + 分客群(group_cols)。
分箱: quantile(等频, 默认) 或 tree(决策树, sklearn)。缺失值单独成箱。
输出: 对齐 out_all_in_one 模板的多 sheet Excel(openpyxl, 无需本机 Excel)。

对外主接口:
    evaluate_features(df, features, y_list, dt_col, dt_cut, group_cols,
                      output_path, bin_method='quantile', n_bins=20, special_codes=(-99,))

仅依赖: pandas, numpy, scikit-learn, openpyxl
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MISS_LABEL = "-1_missing"


# ---------------- 分箱 ----------------

def _split_special(series, special_codes):
    """把缺失/特殊值(如 -99, NaN)与正常值分开。返回(正常值mask, 特殊值mask)。"""
    sp = set(special_codes) if special_codes else set()
    is_special = series.isna()
    for code in sp:
        is_special = is_special | (series == code)
    return ~is_special, is_special


def _bin_quantile(series, normal_mask, n_bins):
    """等频分箱, 返回每行的区间标签(带序号前缀), 特殊值行为 MISS_LABEL。"""
    labels = pd.Series([MISS_LABEL] * len(series), index=series.index, dtype=object)
    vals = series[normal_mask]
    if len(vals) == 0:
        return labels
    try:
        binned, edges = pd.qcut(vals.astype(float), q=n_bins, duplicates="drop", retbins=True)
    except (ValueError, TypeError):
        # 全常量或不可分 -> 单箱
        labels[normal_mask] = "00_all"
        return labels
    codes = binned.cat.codes
    cats = list(binned.cat.categories)
    for i, cat in enumerate(cats):
        lab = "{:02d}_{}".format(i, str(cat))
        labels[vals.index[codes == i]] = lab
    return labels


def _bin_tree(series, normal_mask, y, n_bins):
    """决策树分箱(以 y 为目标监督切分), 返回区间标签。"""
    from sklearn.tree import DecisionTreeClassifier
    labels = pd.Series([MISS_LABEL] * len(series), index=series.index, dtype=object)
    x = series[normal_mask].astype(float)
    yy = y[normal_mask]
    if len(x) == 0 or yy.nunique() < 2:
        labels[normal_mask] = "00_all"
        return labels
    clf = DecisionTreeClassifier(max_leaf_nodes=max(2, n_bins),
                                 min_samples_leaf=max(1, int(0.01 * len(x))))
    clf.fit(x.values.reshape(-1, 1), yy)
    thr = sorted(t for t in clf.tree_.threshold if t != -2)  # -2 = 叶子节点
    edges = [-np.inf] + thr + [np.inf]
    cut = pd.cut(x, bins=edges, labels=False, include_lowest=True)
    for i in range(len(edges) - 1):
        lab = "{:02d}_({:.4g}, {:.4g}]".format(i, edges[i], edges[i + 1])
        labels[x.index[cut == i]] = lab
    return labels


def bin_feature(df, feat, y, method, n_bins, special_codes):
    normal_mask, _ = _split_special(df[feat], special_codes)
    if method == "tree":
        return _bin_tree(df[feat], normal_mask, y, n_bins)
    return _bin_quantile(df[feat], normal_mask, n_bins)


# ---------------- 指标 ----------------

def group_perf(df, feat_bin, y):
    """分组好坏统计 + 每组 lift。返回 DataFrame(group, total, good, bad, bad_rate, lift)。"""
    g = df.groupby(feat_bin)[y].agg(total="count", bad="sum")
    g["good"] = g["total"] - g["bad"]
    overall_bad_rate = df[y].mean()
    g["bad_rate"] = g["bad"] / g["total"]
    g["lift"] = (g["bad_rate"] / overall_bad_rate) if overall_bad_rate > 0 else 0.0
    return g.reset_index().rename(columns={feat_bin.name or "index": "group"})


def calc_iv(g):
    """基于分组统计算 IV。g 需含 good/bad 列。"""
    tot_good, tot_bad = g["good"].sum(), g["bad"].sum()
    if tot_good == 0 or tot_bad == 0:
        return 0.0
    iv = 0.0
    for _, r in g.iterrows():
        pg, pb = r["good"] / tot_good, r["bad"] / tot_bad
        if pg > 0 and pb > 0:
            iv += (pb - pg) * np.log(pb / pg)
    return round(iv, 4)


def calc_ks(g):
    """基于分组统计算 KS = max|累计好% - 累计坏%|。按 bad_rate 排序累计。"""
    tot_good, tot_bad = g["good"].sum(), g["bad"].sum()
    if tot_good == 0 or tot_bad == 0:
        return 0.0
    gs = g.sort_values("bad_rate", ascending=False)
    cum_good = (gs["good"].cumsum() / tot_good).values
    cum_bad = (gs["bad"].cumsum() / tot_bad).values
    return round(float(np.max(np.abs(cum_bad - cum_good))), 4)


def calc_max_lift(g):
    """最大风险倍数 = 各组 lift 的最大值(仅计有一定样本量的组)。"""
    valid = g[g["total"] >= 1]
    return round(float(valid["lift"].max()) if len(valid) else 0.0, 4)


def calc_psi(base_g, cur_g):
    """PSI: 用分组占比对比。base_g/cur_g 为同一分箱下两个时段的 group->total 计数。"""
    b = base_g.set_index("group")["total"]
    c = cur_g.set_index("group")["total"]
    b_pct = (b / b.sum()).reindex(c.index.union(b.index)).fillna(1e-4)
    c_pct = (c / c.sum()).reindex(c.index.union(b.index)).fillna(1e-4)
    psi = float(np.sum((c_pct - b_pct) * np.log(c_pct / b_pct)))
    return round(abs(psi), 4)


# ---------------- 时间切分 ----------------

def make_time_key(df, dt_col, dt_cut):
    """按 dt_cut(month/week/day) 生成时间片键(字符串, 如 202504)。"""
    s = pd.to_datetime(df[dt_col], errors="coerce")
    if dt_cut == "week":
        return s.dt.strftime("%Y%W")
    if dt_cut == "day":
        return s.dt.strftime("%Y%m%d")
    return s.dt.strftime("%Y%m")  # month 默认


# ---------------- 主编排 ----------------

def evaluate_features(df, features, y_list, dt_col=None, dt_cut="month",
                      group_cols=None, output_path="feature_eval_report.xlsx",
                      bin_method="quantile", n_bins=20, special_codes=(-99,)):
    """特征评估主接口: 分箱 -> 按(时间片[, 客群])算 IV/KS/PSI/最大风险倍数 -> 多 sheet Excel。

    df          : 含 features / y / dt_col / group_cols 的 DataFrame
    features    : 待评估特征名列表
    y_list      : 标签列(取第一个为主标签算 IV/KS/lift)
    dt_col      : 时间列; None 则不分月, 只出 All 列
    group_cols  : 分客群维度(如 ['cust_group_dq','new_old']); None 则不分客群
    返回        : {'output_path':..., 'summary': DataFrame}
    """
    y = y_list[0]
    df = df.copy()
    # 只保留主标签有效(>=0)的行参与 IV/KS/lift; PSI 用全量分箱占比
    if y in df.columns:
        df = df[pd.to_numeric(df[y], errors="coerce").notna()]
        df[y] = df[y].astype(float)

    # 时间片
    if dt_col and dt_col in df.columns:
        df["_dt"] = make_time_key(df, dt_col, dt_cut)
        slices = sorted([s for s in df["_dt"].dropna().unique()])
    else:
        df["_dt"] = "All"
        slices = []

    # 每个特征全局分箱一次(跨月可比)
    feat_bins = {}
    for feat in features:
        if feat not in df.columns:
            continue
        feat_bins[feat] = bin_feature(df, feat, df[y] if y in df.columns else None,
                                      bin_method, n_bins, special_codes)
        df[feat + "__bin"] = feat_bins[feat]

    valid_feats = list(feat_bins.keys())
    col_order = ["All"] + slices

    # 指标透视表: 行=特征, 列=[All, 各时间片]
    iv_tbl, ks_tbl, psi_tbl, lift_tbl = {}, {}, {}, {}
    detail_rows = []

    for feat in valid_feats:
        bincol = feat + "__bin"
        iv_row, ks_row, psi_row, lift_row = {}, {}, {}, {}
        # All 列(全量)
        g_all = group_perf(df, df[bincol], y)
        iv_row["All"] = calc_iv(g_all); ks_row["All"] = calc_ks(g_all); lift_row["All"] = calc_max_lift(g_all)
        psi_row["All"] = 0.0
        # base 时段(最早片)用于 PSI
        base_g = None
        if slices:
            base_df = df[df["_dt"] == slices[0]]
            base_g = group_perf(base_df, base_df[bincol], y)
        for sl in slices:
            sdf = df[df["_dt"] == sl]
            gs = group_perf(sdf, sdf[bincol], y)
            iv_row[sl] = calc_iv(gs); ks_row[sl] = calc_ks(gs); lift_row[sl] = calc_max_lift(gs)
            psi_row[sl] = 0.0 if (base_g is None or sl == slices[0]) else calc_psi(base_g, gs)
            # 分组明细
            for _, r in gs.iterrows():
                detail_rows.append({"dt_cut": sl, "feature": feat, "group": r["group"],
                                    "total": int(r["total"]), "good": int(r["good"]),
                                    "bad": int(r["bad"]), "bad_rate": round(r["bad_rate"], 4),
                                    "lift": round(r["lift"], 4)})
        iv_tbl[feat], ks_tbl[feat], psi_tbl[feat], lift_tbl[feat] = iv_row, ks_row, psi_row, lift_row

    def _pivot(tbl):
        return pd.DataFrame(tbl).T.reindex(columns=col_order)

    iv_df, ks_df, psi_df, lift_df = _pivot(iv_tbl), _pivot(ks_tbl), _pivot(psi_tbl), _pivot(lift_tbl)
    detail_df = pd.DataFrame(detail_rows)

    # 综合指标: 每特征取 All 列汇总 + 建议
    summary = pd.DataFrame({
        "IV(All)": iv_df["All"], "KS(All)": ks_df["All"],
        "最大风险倍数(All)": lift_df["All"],
        "PSI(max)": psi_df.drop(columns=["All"]).max(axis=1) if slices else 0.0,
    })
    summary["建议"] = np.where(
        (summary["IV(All)"] >= 0.02) & (summary["最大风险倍数(All)"] >= 1.2),
        "有效", "关注/剔除")

    # 分客群明细(可选): 对每个客群维度分别算 All 列 IV/KS/lift
    group_detail = []
    for gc in (group_cols or []):
        if gc not in df.columns:
            continue
        for gval, gdf in df.groupby(gc):
            for feat in valid_feats:
                g = group_perf(gdf, gdf[feat + "__bin"], y)
                group_detail.append({"客群维度": gc, "客群值": gval, "特征": feat,
                                     "IV": calc_iv(g), "KS": calc_ks(g),
                                     "最大风险倍数": calc_max_lift(g), "样本数": len(gdf)})
    group_df = pd.DataFrame(group_detail)

    # 写多 sheet Excel(openpyxl, 无需本机 Excel)
    with pd.ExcelWriter(output_path, engine="openpyxl") as w:
        summary.to_excel(w, sheet_name="综合指标")
        iv_df.to_excel(w, sheet_name="IV值")
        ks_df.to_excel(w, sheet_name="KS值")
        psi_df.to_excel(w, sheet_name="PSI")
        lift_df.to_excel(w, sheet_name="最大风险倍数")
        if not group_df.empty:
            group_df.to_excel(w, sheet_name="分客群指标", index=False)
        if not detail_df.empty:
            detail_df.to_excel(w, sheet_name="分组明细", index=False)

    return {"output_path": output_path, "summary": summary}
