# -*- coding: utf-8 -*-
"""策略挖掘模块 (决策树版):
- 单变量策略: 对单个特征拟合决策树, 提取高风险叶子路径作为规则
- 多变量策略: 对多个特征(<=max_features)拟合决策树, 根到叶路径即 AND 组合规则
决策树天然产出单方向阈值的 AND 组合, 替代旧的分位数穷举组合。
"""
from __future__ import annotations
import logging
import pandas as pd
import numpy as np
from itertools import combinations
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

MISS_FILL = -99  # 缺失填充哨兵, 决策树可将其单独切出


def _extract_leaf_rules(clf, feature_names: List[str]) -> Dict[int, List[str]]:
    """遍历决策树, 返回 {叶子节点id: [根到叶的条件字符串列表]}。"""
    t = clf.tree_
    rules: Dict[int, List[str]] = {}

    def recurse(node, conds):
        if t.children_left[node] == t.children_right[node]:  # 叶子
            rules[node] = list(conds)
            return
        f = feature_names[t.feature[node]]
        thr = t.threshold[node]
        recurse(t.children_left[node], conds + [f"{f} <= {thr:.4f}"])
        recurse(t.children_right[node], conds + [f"{f} > {thr:.4f}"])

    recurse(0, [])
    return rules


def _consolidate(conds: List[str]) -> str:
    """合并同一特征的多个同向条件(如 f>1 且 f>2 → f>2), 提升规则可读性。"""
    ub, lb = {}, {}  # feature -> 最紧的 <= / > 阈值
    others = []
    for c in conds:
        parts = c.rsplit(" ", 2)
        if len(parts) == 3 and parts[1] in ("<=", ">"):
            f, op, v = parts[0], parts[1], float(parts[2])
            if op == "<=":
                ub[f] = min(ub.get(f, np.inf), v)
            else:
                lb[f] = max(lb.get(f, -np.inf), v)
        else:
            others.append(c)
    out = []
    for f in dict.fromkeys([p.rsplit(" ", 2)[0] for p in conds]):
        if f in lb:
            out.append(f"{f} > {lb[f]:.4f}")
        if f in ub:
            out.append(f"{f} <= {ub[f]:.4f}")
    return " and ".join(out + others)


def _fit_tree(X: pd.DataFrame, y: pd.Series, max_leaf_nodes: int, min_leaf_frac: float):
    from sklearn.tree import DecisionTreeClassifier
    clf = DecisionTreeClassifier(
        max_leaf_nodes=max(2, max_leaf_nodes),
        min_samples_leaf=max(1, int(min_leaf_frac * len(X))),
        random_state=0,
    )
    clf.fit(X, y)
    return clf


def _eval_leaves(df, clf, feats, rules, y, min_bad, min_cov, max_cov, lift_thresh, n_features):
    """对每个叶子计算 coverage/lift/bad_count, 返回达标策略。"""
    X = df[feats].fillna(MISS_FILL)
    leaf_of = clf.apply(X)
    total = len(df)
    overall_bad = df[y].mean()
    if overall_bad == 0:
        return []
    out = []
    for leaf_id, cond_list in rules.items():
        mask = leaf_of == leaf_id
        hit = int(mask.sum())
        if hit == 0:
            continue
        cov = hit / total
        if cov < min_cov or cov > max_cov:
            continue
        bad = int(df.loc[mask, y].sum())
        if bad < min_bad:
            continue
        lift = (df.loc[mask, y].mean() / overall_bad)
        if lift < lift_thresh:
            continue
        out.append({
            "rule": _consolidate(cond_list),
            "coverage": round(cov, 4),
            "lift": round(float(lift), 2),
            "bad_count": bad,
            "hit_count": hit,
            "n_features": n_features,
            "strategy_type": "单变量" if n_features == 1 else f"{n_features}变量",
        })
    return out


class StrategyMiner:
    def __init__(self, config: Dict):
        m = config.get("mining", {})
        self.max_features = m.get("max_features_per_strategy", 3)
        self.min_bad = m.get("min_bad", 10)
        self.min_cov = m.get("min_coverage_pct", 0.001)
        self.max_cov = m.get("max_coverage_pct", 0.20)
        self.lift_thresh = m.get("lift_threshold", config.get("evaluation", {}).get("lift_threshold", 2.0))
        self.max_leaf_nodes = m.get("tree_max_leaf_nodes", 8)
        self.min_leaf_frac = m.get("tree_min_leaf_frac", 0.01)

    def mine_strategies(self, df: pd.DataFrame, valid_features: List[str],
                        y_targets: List[str], max_features: Optional[int] = None,
                        operators: Optional[List[str]] = None) -> List[Dict]:
        """决策树挖掘: 单变量(每特征一棵树) + 多变量(特征组合建树, 根到叶=AND规则)。"""
        if max_features:
            self.max_features = max_features
        feats = [f for f in valid_features if f in df.columns]
        all_strategies = []

        for y in y_targets:
            if y not in df.columns:
                continue
            yv = pd.to_numeric(df[y], errors="coerce")
            work = df[yv.notna()].copy()
            work[y] = yv[yv.notna()].astype(int)
            if work[y].nunique() < 2:
                continue

            # --- 单变量: 每个特征单独建树 ---
            for f in feats:
                X = work[[f]].fillna(MISS_FILL)
                try:
                    clf = _fit_tree(X, work[y], self.max_leaf_nodes, self.min_leaf_frac)
                except Exception as e:
                    logger.debug(f"单变量树失败 {f}: {e}")
                    continue
                rules = _extract_leaf_rules(clf, [f])
                for s in _eval_leaves(work, clf, [f], rules, y, self.min_bad,
                                      self.min_cov, self.max_cov, self.lift_thresh, 1):
                    s["y_target"] = y
                    all_strategies.append(s)

            # --- 多变量: 2..max_features 个特征组合建树 ---
            for k in range(2, min(self.max_features, len(feats)) + 1):
                for combo in combinations(feats, k):
                    X = work[list(combo)].fillna(MISS_FILL)
                    try:
                        clf = _fit_tree(X, work[y], self.max_leaf_nodes, self.min_leaf_frac)
                    except Exception as e:
                        logger.debug(f"多变量树失败 {combo}: {e}")
                        continue
                    rules = _extract_leaf_rules(clf, list(combo))
                    for s in _eval_leaves(work, clf, list(combo), rules, y, self.min_bad,
                                          self.min_cov, self.max_cov, self.lift_thresh, k):
                        s["y_target"] = y
                        all_strategies.append(s)

        # 按规则去重(同规则取首个), 按 lift 降序
        seen, deduped = set(), []
        for s in sorted(all_strategies, key=lambda x: x["lift"], reverse=True):
            if s["rule"] not in seen:
                seen.add(s["rule"])
                deduped.append(s)
        logger.info(f"决策树挖掘: {len(deduped)} 条策略 (单变量+多变量, lift>={self.lift_thresh})")
        return deduped
