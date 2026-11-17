# -*- coding: utf-8 -*-
"""
strategy-analysis Skill 使用示例: 从config.yaml加载配置
参考: skill/table-explorer/config.yaml 格式
"""
import sys
import os
from datetime import datetime

BASE_DIR = r"D:\反欺诈策略室\daifansheng\新反欺诈\codex"
sys.path.insert(0, BASE_DIR)

from skill.strategy_analysis.src.analyzer import StrategyAnalyzer
from skill.strategy_analysis.src.config_loader import load_config, get_db_config, get_test_table


def main():
    """主函数: 演示从配置文件执行策略分析"""
    
    print("=" * 60)
    print("🎯 strategy-analysis: 从config.yaml执行分析")
    print("=" * 60)
    
    # ========== 方式1: 使用默认配置文件 ==========
    print("\n📋 方式1: 使用默认config.yaml")
    
    # 加载配置 (自动读取 skill/strategy-analysis/config.yaml)
    config = load_config()
    
    # 提取数据库配置
    db_config = get_db_config(config, engine="starrocks")
    print(f"🔗 数据库: {db_config['host']}:{db_config['port']} / {db_config['database']}")
    
    # 提取策略分析配置
    strategy_cfg = config.get("strategy_analysis", {})
    
    # 创建分析器 (贷前场景)
    analyzer = StrategyAnalyzer(
        scene="dq",
        db_config=db_config,
        config=strategy_cfg
    )
    
    # 获取测试表名 (从config.yaml读取)
    test_table = get_test_table(config, "dq")
    print(f"📊 测试表: {test_table}")
    
    # 执行完整分析
    print("\n⚙️  执行分析 (Step1 + Step2)...")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    output_prefix = os.path.join(BASE_DIR, "reports", f"config_test_dq_{timestamp}")
    
    result = analyzer.run_full(
        feature_table=test_table,
        output_prefix=output_prefix
    )
    
    # 输出结果
    print(f"\n✅ 分析完成!")
    print(f"   📊 有效特征: {result['valid_features_count']}个")
    print(f"   🎯 验证策略: {result['validated_strategies_count']}条")
    print(f"   📄 Step1报告: {result['step1_report']}")
    print(f"   📄 Step2报告: {result['step2_report']}")
    print(f"   📝 摘要: {result['step2_summary'][:120]}...")
    
    # ========== 方式2: 使用from_config类方法 (更简洁) ==========
    print("\n" + "=" * 60)
    print("📋 方式2: 使用 from_config() 类方法 (推荐)")
    
    analyzer2 = StrategyAnalyzer.from_config(
        scene="dz",  # 贷中场景
        profile="dev",  # 使用dev profile配置
        output={"top_n_features": 20}  # 覆盖部分配置
    )
    
    test_table_dz = get_test_table(load_config(), "dz")
    print(f"📊 贷中测试表: {test_table_dz}")
    
    # 仅执行Step1 (特征评估)
    path1, summary1, results1 = analyzer2.run_step1(
        feature_table=test_table_dz,
        output_path=os.path.join(BASE_DIR, "reports", f"config_dz_step1_{timestamp}.xlsx")
    )
    print(f"✅ Step1完成: {summary1}")
    
    # ========== 方式3: 使用环境变量覆盖配置 ==========
    print("\n" + "=" * 60)
    print("📋 方式3: 使用环境变量覆盖敏感配置")
    print("   设置环境变量: export SR_PROD_PASSWORD='your-secret'")
    print("   配置中使用: starrocks_password: ${SR_PROD_PASSWORD}")
    
    # 加载配置时展开环境变量
    config_with_env = load_config(profile="prod")  # prod profile使用${VAR}格式
    print(f"🔐 生产环境配置已加载 (密码已展开)")
    
    print("\n" + "=" * 60)
    print("✅ 所有示例执行完成!")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    exit(main())