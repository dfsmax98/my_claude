# -*- coding: utf-8 -*-
"""
strategy-analysis Skill 全链路功能测试 - 模拟模式
功能: 验证代码逻辑流程, 无需真实数据库连接
适用: 开发调试/CI测试/代码审查
"""
import sys
import os
import logging
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# 添加项目路径
BASE_DIR = r"D:\反欺诈策略室\daifansheng\新反欺诈\codex"
sys.path.insert(0, BASE_DIR)

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("strategy_test_mock")


def generate_mock_data(scene: str, n_rows: int = 1000) -> pd.DataFrame:
    """生成模拟测试数据"""
    np = __import__("numpy")
    
    # 基础字段
    df = pd.DataFrame({
        "cust_no": [f"CUST_{i:06d}" for i in range(n_rows)],
        "fpd_k30": np.random.choice([0, 1], size=n_rows, p=[0.95, 0.05]),  # 5%坏样本
        "if_out_30d": np.random.choice([0, 1], size=n_rows, p=[0.98, 0.02]),
        "if_out_60d": np.random.choice([0, 1], size=n_rows, p=[0.97, 0.03]),
        "if_in_30d": np.random.choice([0, 1], size=n_rows, p=[0.99, 0.01]),
        "if_in_60d": np.random.choice([0, 1], size=n_rows, p=[0.98, 0.02]),
    })
    
    # 场景特定字段
    if scene == "dq":
        df["apply_no"] = [f"APP_{i:08d}" for i in range(n_rows)]
        df["apply_result"] = np.random.choice(["pass", "reject"], size=n_rows, p=[0.7, 0.3])
        df["close_datetime"] = [datetime.now() - timedelta(days=i) for i in np.random.randint(0, 30, n_rows)]
        df["cust_group_dq"] = np.random.choice(["group_A", "group_B", "group_C"], size=n_rows)
        df["f001_decision"] = np.random.choice(["approve", "manual", "reject"], size=n_rows)
    else:  # dz
        df["trans_seqno"] = [f"TXN_{i:08d}" for i in range(n_rows)]
        df["order_no"] = [f"ORD_{i:08d}" for i in range(n_rows)]
        df["rsk_log_id"] = [f"RISK_{i:08d}" for i in range(n_rows)]
        df["risk_decision_result"] = np.random.choice(["pass", "review", "reject"], size=n_rows)
        df["create_datetime"] = [datetime.now() - timedelta(days=i) for i in np.random.randint(0, 30, n_rows)]
        df["cust_group_dz"] = np.random.choice(["group_X", "group_Y"], size=n_rows)
        df["new_old"] = np.random.choice(["new", "old"], size=n_rows)
    
    # 添加模拟特征 (10个)
    for i in range(10):
        df[f"f_feature_{i:02d}"] = np.random.randn(n_rows)
    
    logger.info(f"Generated mock data: {len(df)} rows, {len(df.columns)} columns")
    return df


def test_with_mock_data(scene: str, output_dir: str) -> dict:
    """使用模拟数据测试完整流程"""
    from skill.strategy_analysis.src.analyzer import StrategyAnalyzer
    from skill.strategy_analysis.src.data_loader import load_data_step1, load_data_step2
    
    logger.info(f"\n{'='*60}")
    logger.info(f"🚀 [MOCK] 开始测试: {scene} (场景)")
    logger.info(f"{'='*60}")
    
    result = {"scene": scene, "success": False, "error": None}
    
    try:
        # Mock数据库连接相关函数
        with patch("skill.strategy_analysis.src.data_loader.DBConnector") as mock_db:
            # 配置mock返回
            mock_conn = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_conn
            mock_db.return_value.__exit__.return_value = False
            
            # 生成模拟数据
            mock_df = generate_mock_data(scene, n_rows=1000)
            
            # Mock Step1数据加载 (带fpd_k30>=0过滤)
            def mock_load_step1(*args, **kwargs):
                df = mock_df[mock_df["fpd_k30"] >= 0].copy()
                logger.info(f"[MOCK] Step1数据: {len(df)}行 (fpd_k30>=0过滤后)")
                return df
            
            # Mock Step2数据加载 (近7天全量)
            def mock_load_step2(*args, **kwargs):
                df = mock_df.copy()
                # 模拟时间过滤
                time_col = "close_datetime" if scene == "dq" else "create_datetime"
                cutoff = datetime.now() - timedelta(days=7)
                df[time_col] = pd.to_datetime(df[time_col])
                df = df[df[time_col] >= cutoff].copy()
                logger.info(f"[MOCK] Step2数据: {len(df)}行 (近7天过滤后)")
                return df
            
            # 应用mock
            import skill.strategy_analysis.src.data_loader as dl_module
            dl_module.load_data_step1 = mock_load_step1
            dl_module.load_data_step2 = mock_load_step2
            
            # 初始化分析器
            logger.info("🔧 初始化StrategyAnalyzer...")
            analyzer = StrategyAnalyzer(
                scene=scene,
                db_config={"host": "mock", "port": 9030},  # mock配置
                config={
                    "evaluation": {"iv_threshold": 0.02, "psi_threshold": 0.25, "lift_threshold": 2.0},
                    "mining": {"max_features_per_strategy": 3, "operator_restriction": [">", "<"]},
                    "step2_days": 7,
                    "output": {"chinese_headers": True, "include_summary": True}
                }
            )
            
            # 执行完整流程
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            output_prefix = os.path.join(output_dir, f"mock_test_{scene}_{timestamp}")
            
            logger.info("⚙️  执行Step1 (特征评估+策略挖掘)...")
            full_result = analyzer.run_full(
                feature_table=f"mock.{scene}_table",  # mock表名
                output_prefix=output_prefix
            )
            
            # 输出结果
            print(f"\n{'='*60}")
            print(f"📊 [MOCK] {scene.upper()} 场景测试结果")
            print(f"{'='*60}")
            print(f"✅ Step1有效特征: {full_result['valid_features_count']}个")
            print(f"✅ Step2验证策略: {full_result['validated_strategies_count']}条")
            print(f"📄 Step1报告: {full_result['step1_report']}")
            print(f"📄 Step2报告: {full_result['step2_report']}")
            print(f"📝 Step1摘要: {full_result['step1_summary'][:100]}...")
            print(f"📝 Step2摘要: {full_result['step2_summary'][:100]}...")
            print(f"{'='*60}\n")
            
            result.update({
                "success": True,
                "valid_features_count": full_result["valid_features_count"],
                "validated_strategies_count": full_result["validated_strategies_count"],
                "step1_report": full_result["step1_report"],
                "step2_report": full_result["step2_report"],
                "step1_summary": full_result["step1_summary"],
                "step2_summary": full_result["step2_summary"]
            })
            
            # 记录到WORKLOG
            _log_to_worklog_mock(scene, result)
            
    except Exception as e:
        logger.error(f"❌ [MOCK] 测试失败: {e}", exc_info=True)
        result["error"] = str(e)
        _log_to_worklog_mock(scene, result, failed=True)
    
    return result


def _log_to_worklog_mock(scene: str, result: dict, failed: bool = False):
    """记录模拟测试结果到WORKLOG.md"""
    worklog_path = os.path.join(BASE_DIR, "WORKLOG.md")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    status = "❌ 失败(MOCK)" if failed else "✅ 成功(MOCK)"
    entry = f"""

### 🤖 策略分析全链路测试(MOCK) - {scene.upper()} ({status})
- **时间**: {timestamp}
- **模式**: 模拟数据 (无真实数据库连接)
- **场景**: {"贷前" if scene=="dq" else "贷中"}
"""
    if not failed:
        entry += f"""- **Step1有效特征**: {result.get('valid_features_count', 0)}个
- **Step2验证策略**: {result.get('validated_strategies_count', 0)}条
- **Step1报告**: `{result.get('step1_report', 'N/A')}`
- **Step2报告**: `{result.get('step2_report', 'N/A')}`
"""
    else:
        entry += f"""- **错误信息**: {result.get('error', '未知错误')}
"""
    entry += "- **备注**: 模拟测试, 仅验证代码逻辑流程\n"
    
    try:
        with open(worklog_path, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception as e:
        logger.warning(f"⚠️ WORKLOG记录失败: {e}")


def main():
    """主入口: 模拟测试贷前+贷中"""
    logger.info("🎯 [MOCK] strategy-analysis 全链路功能测试启动")
    logger.info("💡 模式: 模拟数据, 无需真实数据库连接")
    
    output_dir = os.path.join(BASE_DIR, "reports", "mock_runs")
    os.makedirs(output_dir, exist_ok=True)
    
    results = []
    
    # 测试贷前
    logger.info("\n🔄 执行贷前场景测试...")
    results.append(test_with_mock_data("dq", output_dir))
    
    # 测试贷中
    logger.info("\n🔄 执行贷中场景测试...")
    results.append(test_with_mock_data("dz", output_dir))
    
    # 汇总
    logger.info("\n" + "="*60)
    logger.info("🏁 [MOCK] 全链路测试完成")
    logger.info("="*60)
    
    success_count = sum(1 for r in results if r.get("success"))
    logger.info(f"✅ 成功: {success_count}/{len(results)} 场景")
    
    for r in results:
        scene = r["scene"].upper()
        status = "✅" if r.get("success") else "❌"
        logger.info(f"{status} {scene}: {r.get('error', 'OK')}")
    
    return 0 if success_count == len(results) else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)