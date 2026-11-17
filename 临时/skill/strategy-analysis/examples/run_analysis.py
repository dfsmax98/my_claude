# -*- coding: utf-8 -*-
"""策略分析Skill使用示例"""
import sys
sys.path.insert(0, r"D:\反欺诈策略室\daifansheng\新反欺诈\codex")

from skill.strategy_analysis.src.analyzer import StrategyAnalyzer

# 配置数据库连接 (生产环境请用密钥管理)
DB_CONFIG = {
    "host": "your-starrocks-host",
    "port": 9030,
    "user": "your_username",
    "password": "your_password",
    "database": "d_dq"
}

# 贷前场景分析
def run_pre_loan_analysis():
    analyzer = StrategyAnalyzer(
        scene="dq",  # 贷前
        db_config=DB_CONFIG,
        config={
            "y_targets": ["fpd_k30", "if_out_30d"],
            "evaluation": {"iv_threshold": 0.02, "psi_threshold": 0.25, "lift_threshold": 2.0},
            "mining": {"max_features_per_strategy": 3, "operator_restriction": [">", "<"]},
        }
    )
    
    report_path, summary = analyzer.run(
        feature_table="dwh.gdm_risk_vars_dipa_task_wide_pcr_df",
        output_path="reports/strategy_dq_20260707.xlsx"
    )
    
    print(f"📄 报告: {report_path}")
    print(f"📝 摘要: {summary}")
    return report_path, summary

# 贷中场景分析
def run_in_loan_analysis():
    analyzer = StrategyAnalyzer(
        scene="dz",  # 贷中
        db_config=DB_CONFIG,
    )
    
    report_path, summary = analyzer.run(
        feature_table="dwh.gdm_risk_vars_dipa_task_wide_rms_df",
        output_path="reports/strategy_dz_20260707.xlsx"
    )
    
    print(f"📄 报告: {report_path}")
    print(f"📝 摘要: {summary}")
    return report_path, summary

if __name__ == "__main__":
    # 选择执行
    run_pre_loan_analysis()
    # run_in_loan_analysis()


# === 测试表执行示例 ===
def run_with_test_table():
    """使用内置测试表执行分析 (无需配置特征表join)"""
    from skill.strategy_analysis.src.data_loader import get_test_table, test_connection
    
    # 测试数据库连接
    if not test_connection(DB_CONFIG):
        print("❌ 数据库连接失败, 请检查配置")
        return
    
    # 贷前测试
    analyzer_dq = StrategyAnalyzer(scene="dq", db_config=DB_CONFIG)
    test_table_dq = get_test_table("dq")  # d_dq.dfs_anormal_beh_dq_online_features
    
    result_dq = analyzer_dq.run_full(
        feature_table=test_table_dq,
        output_prefix="reports/test_strategy_dq"
    )
    print(f"🎯 贷前测试: {result_dq['validated_strategies_count']}条策略通过验证")
    
    # 贷中测试
    analyzer_dz = StrategyAnalyzer(scene="dz", db_config=DB_CONFIG)
    test_table_dz = get_test_table("dz")  # d_dq.dfs_anormal_beh_dz_online_features
    
    result_dz = analyzer_dz.run_full(
        feature_table=test_table_dz,
        output_prefix="reports/test_strategy_dz"
    )
    print(f"🎯 贷中测试: {result_dz['validated_strategies_count']}条策略通过验证")
    
    return result_dq, result_dz
