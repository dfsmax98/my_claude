# -*- coding: utf-8 -*-
"""报告生成模块: 支持两步执行的Excel报告(中文表头+自动总结)"""
from __future__ import annotations
import logging, pandas as pd
from typing import Dict, List, Optional
from datetime import datetime
from .report_formatter import format_excel_report

logger = logging.getLogger(__name__)

# 中文字段映射
CHINESE_HEADERS_STEP1 = {
    "feature_name": "特征名称", "iv": "IV值", "psi": "PSI稳定性",
    "lift_fpd_k30": "Lift(首逾30天)", "lift_if_out_30d": "Lift(30天投诉)",
    "recommendation": "建议", "strategy_rule": "策略规则",
    "feature_combo": "特征组合数", "coverage": "覆盖率", "lift": "风险Lift"
}

CHINESE_HEADERS_STEP2 = {
    **CHINESE_HEADERS_STEP1,
    "hit_rate": "命中率",
    "pre_reject_rate": "上线前拒绝率",
    "post_reject_rate": "上线后拒绝率",
    "absolute_increase": "绝对上升",
    "relative_increase": "相对上升",
    "new_reject_count": "新增拒绝数",
    "stability_psi": "7天稳定PSI",
    "validation_result": "验证结论"
}

def _translate_headers(df: pd.DataFrame, mapping: Dict) -> pd.DataFrame:
    return df.rename(columns={k: v for k, v in mapping.items() if k in df.columns})

def _generate_step1_summary(valid_features: List[str], strategies: List[Dict], config: Dict) -> str:
    """Step1自动总结 (决策树策略挖掘; 特征指标评估见 feature_eval 报告)"""
    feat_count, strat_count = len(valid_features), len(strategies)
    if strat_count > 0:
        single = len([s for s in strategies if s.get("n_features", 1) == 1])
        multi = strat_count - single
        top = strategies[0]
        return (f"Step1完成: 基于{feat_count}个候选特征用决策树挖掘出{strat_count}条策略"
                f"(单变量{single}条, 多变量{multi}条), 进入Step2验证。"
                f"核心策略'{top['rule']}' Lift={top['lift']}, 覆盖率{top['coverage']*100:.1f}%.")
    return f"Step1完成: {feat_count}个候选特征, 未发现满足条件的策略。"

def _generate_step2_summary(validated: List[Dict], config: Dict) -> str:
    """Step2自动总结 (含拒绝率影响)"""
    count = len(validated)
    if count > 0:
        avg_hit = sum(s["hit_rate"] for s in validated) / count
        avg_abs = sum(s.get("absolute_increase", 0) for s in validated) / count
        avg_rel = sum(s.get("relative_increase", 0) for s in validated) / count
        safe = [s for s in validated if s.get("absolute_increase", 0) < 0.05]
        rec = f"推荐{len(safe)}条低风险策略灰度上线" if safe else "建议人工评审后决策"
        return (f"Step2验证: {count}条策略经近7天全量验证, 平均命中率{avg_hit*100:.1f}%, "
                f"平均拒绝率绝对上升{avg_abs*100:.1f}pp, 相对上升{avg_rel*100:.1f}%. {rec}.")
    return "Step2验证: 无策略通过验证, 建议调整Step1阈值或补充特征后重试。"

class ExcelReporter:
    def __init__(self, config: Dict):
        self.cfg = config.get("output", {})
        self.chinese = self.cfg.get("chinese_headers", True)
        self.include_summary = self.cfg.get("include_summary", True)
        self.top_n_feat = self.cfg.get("top_n_features", 50)
        self.top_n_strat = self.cfg.get("top_n_strategies", 30)
    
    def generate_step1_report(self, output_path: str, eval_results: Dict, 
                               valid_features: List[str], strategies: List[Dict],
                               config: Dict) -> str:
        """生成Step1报告 (不含通过率)"""
        logger.info(f"Generating Step1 report: {output_path}")
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            single_cnt = len([s for s in strategies if s.get("n_features", 1) == 1])
            multi_cnt = len(strategies) - single_cnt
            # Sheet1: 执行摘要
            summary_df = pd.DataFrame([
                {"指标": "候选特征数", "数值": len(valid_features)},
                {"指标": "可验证策略数", "数值": len(strategies)},
                {"指标": "单变量策略数", "数值": single_cnt},
                {"指标": "多变量策略数", "数值": multi_cnt},
                {"指标": "策略平均Lift", "数值": round(sum(s["lift"] for s in strategies)/len(strategies),2) if strategies else 0},
                {"指标": "平均覆盖率", "数值": round(sum(s['coverage'] for s in strategies)/len(strategies), 6) if strategies else 0}
            ])
            summary_df.to_excel(writer, sheet_name="执行摘要", index=False)

            # Sheet2: 候选特征清单 (特征效果指标见 feature_eval 报告, 此处只列名)
            if valid_features:
                pd.DataFrame({"候选特征": valid_features[:self.top_n_feat]}).to_excel(
                    writer, sheet_name="候选特征", index=False)

            # Sheet3: 有效策略清单 (决策树, 含单/多变量标记)
            if strategies:
                rows = []
                for s in strategies[:self.top_n_strat]:
                    rows.append({
                        "strategy_rule": s["rule"],
                        "strategy_type": s.get("strategy_type", ""),
                        "feature_combo": s.get("n_features", s["rule"].lower().count(" and ")+1),
                        "coverage": s["coverage"], "lift": s["lift"],
                        "bad_count": s.get("bad_count", 0), "y_target": s.get("y_target", ""),
                    })
                df = pd.DataFrame(rows)
                if self.chinese:
                    df = _translate_headers(df, {**CHINESE_HEADERS_STEP1, "strategy_type":"策略类型", "bad_count":"命中坏样本", "y_target":"目标标签"})
                df.to_excel(writer, sheet_name="有效策略", index=False)
            
            # Sheet4: 总结
            if self.include_summary:
                pd.DataFrame([{"总结陈述": _generate_step1_summary(valid_features, strategies, config)}]).to_excel(writer, sheet_name="总结", index=False)
        format_excel_report(output_path)
        
        return _generate_step1_summary(valid_features, strategies, config)
    
    def generate_step2_report(self, output_path: str, validated_strategies: List[Dict], config: Dict) -> str:
        """生成Step2报告 (含拒绝率影响评估)"""
        logger.info(f"Generating Step2 report: {output_path}")
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            # Sheet1: 验证摘要
            if validated_strategies:
                avg_hit = sum(s["hit_rate"] for s in validated_strategies)/len(validated_strategies)
                avg_abs = sum(s.get("absolute_increase", 0) for s in validated_strategies)/len(validated_strategies)
                avg_rel = sum(s.get("relative_increase", 0) for s in validated_strategies)/len(validated_strategies)
                safe_count = len([s for s in validated_strategies if s.get("absolute_increase", 0) < 0.05])
            else:
                avg_hit = avg_abs = avg_rel = safe_count = 0
            summary_df = pd.DataFrame([
                {"指标": "验证策略数", "数值": len(validated_strategies)},
                {"指标": "平均命中率", "数值": round(avg_hit, 6)},
                {"指标": "平均拒绝率绝对上升", "数值": round(avg_abs, 6)},
                {"指标": "平均拒绝率相对上升", "数值": round(avg_rel, 6)},
                {"指标": "低风险策略数(绝对上升<5pp)", "数值": safe_count}
            ])
            summary_df.to_excel(writer, sheet_name="验证摘要", index=False)
            
            # Sheet2: 验证后策略清单
            if validated_strategies:
                rows = []
                for s in validated_strategies[:self.top_n_strat]:
                    abs_inc = s.get("absolute_increase", 0)
                    risk_level = "✅低风险" if abs_inc < 0.05 else "⚠️需评审" if abs_inc < 0.1 else "🔴高风险"
                    rows.append({
                        "strategy_rule": s["rule"],
                        "lift": s["lift"],
                        "hit_rate": s["hit_rate"],
                        "pre_reject_rate": s.get("pre_reject_rate", 0),
                        "post_reject_rate": s.get("post_reject_rate", 0),
                        "absolute_increase": abs_inc,
                        "relative_increase": s.get("relative_increase", 0),
                        "new_reject_count": s.get("new_reject_count", 0),
                        "stability_psi": s.get("stability_psi", 0),
                        "validation_result": risk_level
                    })
                df = pd.DataFrame(rows)
                if self.chinese:
                    df = _translate_headers(df, CHINESE_HEADERS_STEP2)
                df.to_excel(writer, sheet_name="验证后策略", index=False)
            
            # Sheet3: 稳定性趋势 (简化: 实际需计算近7天每日指标)
            trend_df = pd.DataFrame([{"日期": (datetime.now().date()-pd.Timedelta(days=i)).strftime("%Y-%m-%d"), 
                                     "策略平均Lift": "-", "命中率": "-", "拒绝率影响": "-"} for i in range(7)])
            if self.chinese:
                trend_df = trend_df.rename(columns={"日期":"日期","策略平均Lift":"策略平均Lift","命中率":"命中率","拒绝率影响":"拒绝率影响"})
            trend_df.to_excel(writer, sheet_name="稳定性趋势", index=False)
            
            # Sheet4: 总结
            if self.include_summary:
                pd.DataFrame([{"总结陈述": _generate_step2_summary(validated_strategies, config)}]).to_excel(writer, sheet_name="总结", index=False)
        format_excel_report(output_path)
        
        return _generate_step2_summary(validated_strategies, config)
