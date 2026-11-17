# -*- coding: utf-8 -*-
"""
strategy-analysis Skill 全链路功能测试脚本
测试表: d_dq.dfs_anormal_beh_dq/dz_online_features
执行流程: DB连接 → Step1特征评估 → Step2策略验证 → 报告生成 → WORKLOG记录
"""
import sys
import os
import logging
from datetime import datetime

# 添加项目路径
BASE_DIR = r"D:\反欺诈策略室\daifansheng\新反欺诈\codex"
sys.path.insert(0, BASE_DIR)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(BASE_DIR, "logs", "strategy_test.log"), encoding="utf-8", mode="a")
    ]
)
logger = logging.getLogger("strategy_test")

# 确保日志目录存在
os.makedirs(os.path.join(BASE_DIR, "logs"), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "reports"), exist_ok=True)


def get_db_config() -> dict:
    """
    获取数据库配置
    🔐 生产环境请使用密钥管理服务, 此处为测试示例
    """
    return {
        "host": os.getenv("SR_HOST", "your-starrocks-host"),
        "port": int(os.getenv("SR_PORT", "9030")),
        "user": os.getenv("SR_USER", "your_username"),
        "password": os.getenv("SR_PASSWORD", "your_password"),
        "database": os.getenv("SR_DATABASE", "d_dq")
    }


def test_scene(scene: str, db_config: dict, output_dir: str) -> dict:
    """
    测试单个场景(贷前/贷中)的完整流程
    
    Args:
        scene: "dq" (贷前) 或 "dz" (贷中)
        db_config: 数据库连接配置
        output_dir: 报告输出目录
        
    Returns:
        dict: 测试结果汇总
    """
    from skill.strategy_analysis.src.analyzer import StrategyAnalyzer
    from skill.strategy_analysis.src.data_loader import get_test_table, test_connection
    
    logger.info(f"\n{'='*60}")
    logger.info(f"🚀 开始测试: {scene} (场景)")
    logger.info(f"{'='*60}")
    
    result = {"scene": scene, "success": False, "error": None}
    
    try:
        # 1. 测试数据库连接
        logger.info("🔗 步骤1/5: 测试数据库连接...")
        if not test_connection(db_config):
            raise ConnectionError("数据库连接测试失败")
        logger.info("✅ 数据库连接成功")
        
        # 2. 初始化分析器
        logger.info("🔧 步骤2/5: 初始化StrategyAnalyzer...")
        analyzer = StrategyAnalyzer(
            scene=scene,
            db_config=db_config,
            config={
                "evaluation": {"iv_threshold": 0.02, "psi_threshold": 0.25, "lift_threshold": 2.0},
                "mining": {"max_features_per_strategy": 3, "operator_restriction": [">", "<"]},
                "step2_days": 7,
                "output": {"chinese_headers": True, "include_summary": True}
            }
        )
        logger.info("✅ 分析器初始化完成")
        
        # 3. 获取测试表名
        test_table = get_test_table(scene)
        if not test_table:
            raise ValueError(f"未找到{scene}场景的测试表")
        logger.info(f"📊 测试表: {test_table}")
        
        # 4. 执行完整流程 (Step1 + Step2)
        logger.info("⚙️  步骤3/5: 执行Step1 (特征评估+策略挖掘)...")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        output_prefix = os.path.join(output_dir, f"test_{scene}_{timestamp}")
        
        full_result = analyzer.run_full(
            feature_table=test_table,
            output_prefix=output_prefix
        )
        logger.info("✅ Step1 + Step2 执行完成")
        
        # 5. 输出结果摘要
        logger.info("📋 步骤4/5: 输出结果摘要...")
        print(f"\n{'='*60}")
        print(f"📊 {scene.upper()} 场景测试结果")
        print(f"{'='*60}")
        print(f"✅ Step1有效特征: {full_result['valid_features_count']}个")
        print(f"✅ Step2验证策略: {full_result['validated_strategies_count']}条")
        print(f"📄 Step1报告: {full_result['step1_report']}")
        print(f"📄 Step2报告: {full_result['step2_report']}")
        print(f"📝 Step1摘要: {full_result['step1_summary']}")
        print(f"📝 Step2摘要: {full_result['step2_summary']}")
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
        
        # 6. 记录到WORKLOG.md
        logger.info("📝 步骤5/5: 记录到WORKLOG.md...")
        _log_to_worklog(scene, result, test_table)
        logger.info("✅ WORKLOG记录完成")
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}", exc_info=True)
        result["error"] = str(e)
        # 记录失败到WORKLOG
        _log_to_worklog(scene, result, get_test_table(scene), failed=True)
    
    return result


def _log_to_worklog(scene: str, result: dict, table: str, failed: bool = False):
    """记录测试结果到WORKLOG.md"""
    worklog_path = os.path.join(BASE_DIR, "WORKLOG.md")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    status = "❌ 失败" if failed else "✅ 成功"
    entry = f"""

### 🤖 策略分析全链路测试 - {scene.upper()} ({status})
- **时间**: {timestamp}
- **测试表**: {table}
- **场景**: {"贷前" if scene=="dq" else "贷中"}
"""
    if not failed:
        entry += f"""- **Step1有效特征**: {result.get('valid_features_count', 0)}个
- **Step2验证策略**: {result.get('validated_strategies_count', 0)}条
- **Step1报告**: `{result.get('step1_report', 'N/A')}`
- **Step2报告**: `{result.get('step2_report', 'N/A')}`
- **Step1摘要**: {result.get('step1_summary', 'N/A')}
- **Step2摘要**: {result.get('step2_summary', 'N/A')}
"""
    else:
        entry += f"""- **错误信息**: {result.get('error', '未知错误')}
"""
    entry += "- **备注**: 测试表执行, 生产环境请使用正式特征表\n"
    
    try:
        with open(worklog_path, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception as e:
        logger.warning(f"⚠️ WORKLOG记录失败: {e}")


def main():
    """主入口: 测试贷前+贷中两个场景"""
    logger.info("🎯 strategy-analysis 全链路功能测试启动")
    
    # 获取配置
    db_config = get_db_config()
    output_dir = os.path.join(BASE_DIR, "reports", "test_runs")
    os.makedirs(output_dir, exist_ok=True)
    
    # 检查必要配置
    if db_config["host"] == "your-starrocks-host":
        logger.warning("⚠️  请使用环境变量配置真实数据库连接:")
        logger.warning("   export SR_HOST=xxx SR_PORT=9030 SR_USER=xxx SR_PASSWORD=xxx")
        logger.info("💡 或使用默认配置(可能需要修改代码)")
    
    # 执行测试
    results = []
    
    # 测试贷前场景
    results.append(test_scene("dq", db_config, output_dir))
    
    # 测试贷中场景
    results.append(test_scene("dz", db_config, output_dir))
    
    # 输出汇总
    logger.info("\n" + "="*60)
    logger.info("🏁 全链路测试完成")
    logger.info("="*60)
    
    success_count = sum(1 for r in results if r.get("success"))
    logger.info(f"✅ 成功: {success_count}/{len(results)} 场景")
    
    for r in results:
        scene = r["scene"].upper()
        status = "✅" if r.get("success") else "❌"
        logger.info(f"{status} {scene}: {r.get('error', 'OK')}")
    
    # 返回退出码
    return 0 if success_count == len(results) else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)