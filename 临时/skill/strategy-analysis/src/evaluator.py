# -*- coding: utf-8 -*-
"""特征评估模块: IV/PSI/全局Lift/尾部Lift计算 + 拒绝率影响评估"""
from __future__ import annotations
import logging, pandas as pd, numpy as np
from typing import Dict, List

logger = logging.getLogger(__name__)

def calculate_iv(df: pd.DataFrame, feature: str, target: str, n_bins: int = 20) -> float:
    """计算IV"""
    if feature not in df.columns or target not in df.columns:
        return -1.0
    df_clean = df[[feature, target]].dropna()
    if len(df_clean) == 0:
        return 0.0
    if pd.api.types.is_numeric_dtype(df_clean[feature]):
        df_clean = df_clean.copy()
        if hasattr(df_clean[feature].iloc[0], '__float__'):
            df_clean[feature] = df_clean[feature].astype(float)
        df_clean["bin"] = pd.qcut(df_clean[feature], q=n_bins, duplicates="drop", labels=False)
    else:
        df_clean["bin"] = df_clean[feature]
    pivot = df_clean.groupby("bin")[target].agg(["sum","count"]).rename(columns={"sum":"bad","count":"total"})
    pivot["good"] = pivot["total"] - pivot["bad"]
    total_bad, total_good = pivot["bad"].sum(), pivot["good"].sum()
    if total_bad == 0 or total_good == 0:
        return 0.0
    iv = sum((row["bad"]/total_bad - row["good"]/total_good) * np.log((row["bad"]/total_bad)/(row["good"]/total_good)) 
             for _, row in pivot.iterrows() if row["bad"]>0 and row["good"]>0)
    return round(iv, 4)

def calculate_psi(df_base: pd.DataFrame, df_compare: pd.DataFrame, feature: str, n_bins: int = 20) -> float:
    """计算PSI"""
    if feature not in df_base.columns or feature not in df_compare.columns:
        return -1.0
    df_b, df_c = df_base[[feature]].dropna(), df_compare[[feature]].dropna()
    if len(df_b)==0 or len(df_c)==0:
        return 0.0
    if pd.api.types.is_numeric_dtype(df_b[feature]):
        bins = pd.qcut(df_b[feature], q=n_bins, duplicates="drop", retbins=True)[1]
        df_b["bin"], df_c["bin"] = pd.cut(df_b[feature], bins=bins, labels=False), pd.cut(df_c[feature], bins=bins, labels=False)
    else:
        df_b["bin"], df_c["bin"] = df_b[feature], df_c[feature]
    pct_b, pct_c = df_b["bin"].value_counts(normalize=True), df_c["bin"].value_counts(normalize=True)
    psi = sum((pct_c.get(b,0.0001)-pct_b.get(b,0.0001))*np.log(pct_c.get(b,0.0001)/pct_b.get(b,0.0001)) for b in set(pct_b.index)|set(pct_c.index))
    return round(abs(psi), 4)

def calculate_lift(df: pd.DataFrame, condition: str, target: str) -> float:
    """计算Lift"""
    if target not in df.columns:
        return 1.0
    overall = df[target].mean()
    if overall == 0:
        return 1.0
    try:
        filtered = df.query(condition)
        return round(filtered[target].mean()/overall, 2) if len(filtered)>0 else 0.0
    except:
        return 1.0

def calculate_tail_lift(df: pd.DataFrame, feature: str, target: str, 
                        tail_pcts: List[float] = [0.01, 0.02, 0.05, 0.10]) -> Dict:
    """计算尾部Lift"""
    if feature not in df.columns or target not in df.columns:
        return {}
    df_clean = df[[feature, target]].dropna()
    if len(df_clean) == 0:
        return {}
    if hasattr(df_clean[feature].iloc[0], '__float__'):
        df_clean[feature] = df_clean[feature].astype(float)
    overall_bad_rate = df_clean[target].mean()
    if overall_bad_rate == 0:
        return {}
    df_sorted = df_clean.sort_values(feature, ascending=False)
    result = {}
    for pct in tail_pcts:
        n_tail = int(len(df_sorted) * pct)
        if n_tail < 10:
            continue
        tail_data = df_sorted.head(n_tail)
        tail_bad_rate = tail_data[target].mean()
        tail_lift = tail_bad_rate / overall_bad_rate
        result[f"tail_lift_top_{int(pct*100)}pct"] = round(tail_lift, 2)
        result[f"tail_count_top_{int(pct*100)}pct"] = int(tail_data[target].sum())
        bottom_data = df_sorted.tail(n_tail)
        bottom_bad_rate = bottom_data[target].mean()
        bottom_lift = bottom_bad_rate / overall_bad_rate
        result[f"tail_lift_bottom_{int(pct*100)}pct"] = round(bottom_lift, 2)
        result[f"tail_count_bottom_{int(pct*100)}pct"] = int(bottom_data[target].sum())
    return result

def calculate_rejection_impact(df: pd.DataFrame, condition: str, 
                                result_col: str = "apply_result") -> Dict:
    """
    计算策略对拒绝率的影响 (Step2专用)
    
    自动检测决策字段:
    - 贷前: apply_result
    - 贷中: risk_decision_result
    """
    # 自动检测决策字段
    if result_col not in df.columns:
        if "risk_decision_result" in df.columns:
            result_col = "risk_decision_result"
        elif "apply_result" in df.columns:
            result_col = "apply_result"
        else:
            return {
                "hit_rate": 0, "pre_reject_rate": 0, "post_reject_rate": 0,
                "absolute_increase": 0, "relative_increase": 0,
                "hit_count": 0, "original_reject_count": 0, "new_reject_count": 0
            }
    
    total = len(df)
    try:
        filtered = df.query(condition)
    except:
        return {
            "hit_rate": 0, "pre_reject_rate": 0, "post_reject_rate": 0,
            "absolute_increase": 0, "relative_increase": 0,
            "hit_count": 0, "original_reject_count": 0, "new_reject_count": 0
        }
    
    hit = len(filtered)
    if hit == 0:
        return {
            "hit_rate": 0, "pre_reject_rate": 0, "post_reject_rate": 0,
            "absolute_increase": 0, "relative_increase": 0,
            "hit_count": 0, "original_reject_count": 0, "new_reject_count": 0
        }
    
    hit_rate = hit / total
    # 鲁棒识别"已拒绝": 兼容 reject/拒绝/N/0 等取值(旧代码硬编码 'N'/'Y' 与实际 pass/reject 不符)
    REJECT_TOKENS = {"reject", "rejected", "拒绝", "拒绝通过", "n", "0", "false"}
    def _is_reject(col):
        return col.astype(str).str.strip().str.lower().isin(REJECT_TOKENS)
    already_reject = _is_reject(df[result_col])
    original_reject = int(already_reject.sum())
    pre_reject_rate = original_reject / total
    # 上线策略后: 原本已拒绝 或 被策略命中 的都算拒绝
    post_reject_mask = already_reject | df.index.isin(filtered.index)
    post_reject_count = int(post_reject_mask.sum())
    post_reject_rate = post_reject_count / total
    absolute_increase = post_reject_rate - pre_reject_rate
    relative_increase = absolute_increase / pre_reject_rate if pre_reject_rate > 0 else 0
    # 新增拒绝 = 命中策略 且 原先未被拒绝(pass/review)的样本
    new_reject_count = int((~_is_reject(filtered[result_col])).sum())
    
    return {
        "hit_rate": round(hit_rate, 4),
        "pre_reject_rate": round(pre_reject_rate, 4),
        "post_reject_rate": round(post_reject_rate, 4),
        "absolute_increase": round(absolute_increase, 4),
        "relative_increase": round(relative_increase, 4),
        "hit_count": hit,
        "original_reject_count": int(original_reject),
        "new_reject_count": int(new_reject_count)
    }

class FeatureEvaluator:
    def __init__(self, config: Dict):
        self.cfg = config.get("evaluation", {})
        self.iv_thresh = self.cfg.get("iv_threshold", 0.02)
        self.psi_thresh = self.cfg.get("psi_threshold", 0.25)
        self.lift_thresh = self.cfg.get("lift_threshold", 2.0)
        self.tail_lift_thresh = self.cfg.get("tail_lift_threshold", 1.5)
    
    def evaluate_all(self, df: pd.DataFrame, y_targets: List[str], 
                     group_by: str, time_col: str, time_split: str = "month") -> Dict:
        """评估所有特征: IV/PSI/Lift/尾部Lift (Step1使用)"""
        results = {}
        exclude = ["cust_no","apply_no","trans_seqno","order_no","rsk_log_id","fpd_k30","if_out_30d",
                  "if_out_60d","if_in_30d","if_in_60d","apply_result","risk_decision_result",
                  "close_datetime","create_datetime",group_by,"new_old"]
        features = [c for c in df.columns if c not in exclude]
        n_bins = self.cfg.get("n_bins", 20)

        # 预切分时间片(按 time_split), 用于计算 PSI 稳定性: 以最早一片为基准, 与其余片逐一比较取最大 PSI
        time_slices = self._split_by_time(df, time_col, time_split) if time_col in df.columns else []

        for feat in features:
            feat_res = {}
            # PSI 与 target 无关, 对每个特征只算一次
            global_psi, psi_by_slice = self._feature_psi(feat, time_slices, n_bins)
            for y in y_targets:
                if y not in df.columns:
                    continue
                iv = calculate_iv(df, feat, y, n_bins)
                tail_lifts = calculate_tail_lift(df, feat, y)
                # 特征级 lift: 取尾部(高分段)最大 lift 作为该特征的区分提升度,
                # 而非旧版恒为1的"非空"lift
                lift = max([v for k, v in tail_lifts.items() if k.startswith("tail_lift_top_")] or [0.0])
                feat_res[y] = {
                    "iv": iv,
                    "lift": lift,
                    "psi_by_slice": psi_by_slice,
                    "global_psi": global_psi,
                    **tail_lifts
                }
            results[feat] = feat_res
        return results

    @staticmethod
    def _split_by_time(df: pd.DataFrame, time_col: str, time_split: str) -> List[pd.DataFrame]:
        """按 month/week/day 把 df 切成多个时间片(按时间升序)。"""
        s = pd.to_datetime(df[time_col], errors="coerce")
        if s.notna().sum() == 0:
            return []
        if time_split == "week":
            key = s.dt.strftime("%Y-%W")
        elif time_split == "day":
            key = s.dt.strftime("%Y-%m-%d")
        else:
            key = s.dt.strftime("%Y-%m")
        slices = [g for _, g in df.assign(_tk=key).groupby("_tk", sort=True)]
        return slices

    def _feature_psi(self, feat: str, time_slices: List[pd.DataFrame], n_bins: int):
        """以最早时间片为基准, 与其余每片算 PSI, 返回(最大PSI, 各片PSI字典)。片数<2 时返回0。"""
        if len(time_slices) < 2 or feat not in time_slices[0].columns:
            return 0.0, {}
        base = time_slices[0]
        psi_by_slice = {}
        for i, cur in enumerate(time_slices[1:], start=1):
            psi = calculate_psi(base, cur, feat, n_bins)
            if psi >= 0:
                psi_by_slice[f"slice_{i}"] = psi
        global_psi = max(psi_by_slice.values()) if psi_by_slice else 0.0
        return round(global_psi, 4), psi_by_slice
    
    def filter_valid_features(self, eval_results: Dict, iv_thresh: float, psi_thresh: float, lift_thresh: float) -> List[str]:
        """筛选有效特征"""
        valid = []
        for feat, y_results in eval_results.items():
            for y, m in y_results.items():
                if m["iv"]>=iv_thresh and m.get("global_psi",0)<=psi_thresh and m["lift"]>=lift_thresh:
                    valid.append(feat)
                    break
                tail_lift_1 = m.get("tail_lift_top_1pct", 0)
                tail_lift_2 = m.get("tail_lift_top_2pct", 0)
                tail_lift_5 = m.get("tail_lift_top_5pct", 0)
                tail_lift_10 = m.get("tail_lift_top_10pct", 0)
                if (tail_lift_1 >= self.tail_lift_thresh or 
                    tail_lift_2 >= self.tail_lift_thresh or 
                    tail_lift_5 >= self.tail_lift_thresh or
                    tail_lift_10 >= self.tail_lift_thresh):
                    valid.append(feat)
                    break
        return valid
    
    def validate_strategies(self, df: pd.DataFrame, strategies: List[Dict]) -> List[Dict]:
        """验证策略: 计算拒绝率影响 (Step2使用)"""
        validated = []
        for s in strategies:
            validation = calculate_rejection_impact(df, s["rule"])
            if validation["hit_rate"] > 0:
                validated.append({**s, **validation})
        return validated
