# -*- coding: utf-8 -*-
"""策略分析核心引擎: 两步执行流程
Step1: 特征评估+策略挖掘 (fpd_k30>=0过滤, 无通过率评估)
Step2: 策略验证 (近7天全量数据, 评估通过率/命中率)
"""
from __future__ import annotations
from .config_loader import load_config, get_db_config
import logging
import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class StrategyAnalyzer:
    """策略分析主类: 协调数据加载→评估→挖掘→报告全流程"""
    
    def __init__(self, scene: str, db_config: Optional[Dict] = None, 
                 config: Optional[Dict] = None, config_path: Optional[str] = None):
        """
        Args:
            scene: "dq" (贷前) or "dz" (贷中)
            db_config: 数据库连接配置 (可选, 从config.yaml加载)
            config: 分析配置参数 (可选, 从config.yaml加载)
            config_path: 配置文件路径 (可选, 默认使用skill/strategy-analysis/config.yaml)
        """
        self.scene = scene
        
        # 加载配置文件 (如果提供)
        if config_path or db_config is None:
            loaded_cfg = load_config(config_path=config_path)
            if db_config is None:
                self.db_config = get_db_config(loaded_cfg, engine="starrocks")
            else:
                self.db_config = db_config
            # 合并配置: 文件配置 < 传入config参数
            self.config = loaded_cfg.get("strategy_analysis", {})
            if config:
                self.config.update(config)
        else:
            self.db_config = db_config
            self.config = config or {}
        
        self._setup_defaults()
        self.step1_results = None
        self.step2_results = None
    
    def _setup_defaults(self):
        """设置默认配置"""
        defaults = {
            "y_targets": ["fpd_k30", "if_out_30d"],
            "primary_key": "apply_no" if self.scene=="dq" else "trans_seqno",
            "cust_group": f"cust_group_{self.scene}",
            "time_column": "close_datetime" if self.scene=="dq" else "create_datetime",
            "step1_filter": "fpd_k30 >= 0",
            "step2_days": 7,
            "evaluation": {"iv_threshold":0.02,"psi_threshold":0.25,"lift_threshold":2.0,"time_split":"month"},
            "mining": {"max_features_per_strategy":3,"operator_restriction":[">","<"],"min_bad":10,"min_coverage_pct":0.001,"max_coverage_pct":0.20},
            "output": {"chinese_headers":True,"include_summary":True,"top_n_features":50,"top_n_strategies":30}
        }
        for k,v in defaults.items():
            if k not in self.config:
                self.config[k] = v
            elif isinstance(v, dict) and isinstance(self.config[k], dict):
                for dk, dv in v.items():
                    self.config[k].setdefault(dk, dv)
    
    # ========== 候选特征提取 ==========
    def _candidate_features(self, df: pd.DataFrame, features: Optional[List[str]] = None) -> List[str]:
        """从数据列提取候选特征: 排除主键/标签/时间/客群等元字段。
        特征指标评估(IV/KS/PSI)已交由 feature_eval 模块, 此处不再筛; 决策树挖掘自行选特征。
        """
        if features:
            return [f for f in features if f in df.columns]
        exclude = set(self.config.get("y_targets", []) + [
            "cust_no", "apply_no", "trans_seqno", "order_no", "rsk_log_id",
            "fpd_k30", "if_out_30d", "if_out_60d", "if_in_30d", "if_in_60d",
            "apply_result", "risk_decision_result", "f001_decision",
            "close_datetime", "create_datetime", "new_old",
            self.config.get("cust_group", ""),
        ])
        return [c for c in df.columns
                if c not in exclude and pd.api.types.is_numeric_dtype(df[c])]

    # ========== Step 1: 策略挖掘 (决策树, 单+多变量) ==========
    def run_step1(self, feature_table: str, output_path: Optional[str]=None,
                  features: Optional[List[str]]=None) -> Tuple[str, str, Dict]:
        """Step1: 从有表现样本(fpd_k30>=0)挖掘策略。特征评估已由 feature_eval 负责, 此处只挖策略。"""
        logger.info(f"🚀 Step1: 策略挖掘(决策树), scene={self.scene}")

        # 1. 加载数据 (带fpd_k30>=0过滤)
        df = self._load_data_step1(feature_table)

        # 2. 确定候选特征 (不再做 IV/PSI 筛选; 可由调用方/pipeline 传入 feature_eval 选出的有效特征)
        candidate_features = self._candidate_features(df, features)
        logger.info(f"📋 候选特征: {len(candidate_features)}个")

        # 3. 决策树策略挖掘 (单变量 + 多变量)
        strategies = self._mine_strategies(df, candidate_features)
        logger.info(f"🎯 Step1挖掘策略: {len(strategies)}条")

        # 4. 生成报告
        if not output_path:
            output_path = f"reports/strategy_{self.scene}_step1_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        summary1 = self._generate_step1_report(output_path, {}, candidate_features, strategies)

        # 缓存结果
        self.step1_results = {"valid_features": candidate_features, "strategies": strategies, "eval_results": {}}

        logger.info(f"📄 Step1报告: {output_path}")
        return output_path, summary1, self.step1_results
    
    # ========== Step 2: 策略验证 ==========
    def run_step2(self, feature_table: str, step1_strategies: List[Dict], output_path: Optional[str]=None) -> Tuple[str, str]:
        """Step2: 策略验证 - 通过率/命中率评估 (近7天全量)"""
        logger.info(f"🚀 Step2: 策略验证, scene={self.scene}")
        
        if not step1_strategies:
            raise ValueError("Step2需要Step1输出的有效策略列表")
        
        # 1. 加载近7天全量数据 (无fpd_k30>=0过滤)
        df = self._load_data_step2(feature_table)
        logger.info(f"📊 Step2数据: {len(df)}行 (近{self.config['step2_days']}天全量)")
        
        # 2. 验证策略
        validated_strategies = self._validate_strategies(df, step1_strategies)
        logger.info(f"✅ Step2验证通过策略: {len(validated_strategies)}条")

        # 3. 生成报告
        if not output_path:
            output_path = f"reports/strategy_{self.scene}_step2_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        summary2 = self._generate_step2_report(output_path, validated_strategies)

        # 缓存验证结果, 供 run_full 正确统计
        self.step2_results = {"validated_strategies": validated_strategies}

        logger.info(f"📄 Step2报告: {output_path}")
        return output_path, summary2
    
    # ========== 完整流程 ==========
    def run_full(self, feature_table: str, output_prefix: Optional[str]=None) -> Dict:
        """执行完整两步流程"""
        path1 = f"{output_prefix}_step1.xlsx" if output_prefix else None
        path1, summary1, results1 = self.run_step1(feature_table, output_path=path1)
        
        path2 = f"{output_prefix}_step2.xlsx" if output_prefix else None
        path2, summary2 = self.run_step2(feature_table, step1_strategies=results1["strategies"], output_path=path2)

        # 用真实的 Step2 验证通过数(而非 Step1 候选策略数)
        validated_count = len((self.step2_results or {}).get("validated_strategies", []))
        return {
            "step1_report": path1, "step1_summary": summary1,
            "step2_report": path2, "step2_summary": summary2,
            "candidate_features_count": len(results1["valid_features"]),
            "step1_strategies_count": len(results1["strategies"]),
            "validated_strategies_count": validated_count
        }
    
    # ========== 数据加载方法 ==========
    def _load_data_step1(self, feature_table: str) -> pd.DataFrame:
        """Step1数据加载: 带fpd_k30>=0过滤"""
        from .data_loader import load_data_step1
        return load_data_step1(feature_table, self.db_config, self.config, self.scene)
    
    def _load_data_step2(self, feature_table: str) -> pd.DataFrame:
        """Step2数据加载: 近7天全量, 无fpd_k30过滤"""
        from .data_loader import load_data_step2
        days = self.config.get("step2_days", 7)
        return load_data_step2(feature_table, self.db_config, self.config, self.scene, days)
    
    def test_db_connection(self) -> bool:
        """测试数据库连接"""
        from .data_loader import test_connection
        return test_connection(self.db_config)
    
    # ========== 评估方法 (Placeholder - 实际调用evaluator模块) ==========
    def _evaluate_features(self, df: pd.DataFrame) -> Dict:
        """评估特征: IV/PSI/Lift"""
        from .evaluator import FeatureEvaluator
        evaluator = FeatureEvaluator(self.config)
        return evaluator.evaluate_all(
            df=df,
            y_targets=self.config["y_targets"],
            group_by=self.config["cust_group"],
            time_col=self.config["time_column"],
            time_split=self.config["evaluation"]["time_split"]
        )
    
    def _filter_valid_features(self, results: Dict) -> List[str]:
        """筛选有效特征"""
        from .evaluator import FeatureEvaluator
        evaluator = FeatureEvaluator(self.config)
        cfg = self.config["evaluation"]
        return evaluator.filter_valid_features(
            results, cfg["iv_threshold"], cfg["psi_threshold"], cfg["lift_threshold"]
        )
    
    def _mine_strategies(self, df: pd.DataFrame, features: List[str]) -> List[Dict]:
        """挖掘策略: ≤3特征组合, 仅>或<"""
        from .strategy_miner import StrategyMiner
        miner = StrategyMiner(self.config)
        return miner.mine_strategies(
            df=df, valid_features=features,
            y_targets=self.config["y_targets"],
            max_features=self.config["mining"]["max_features_per_strategy"],
            operators=self.config["mining"]["operator_restriction"]
        )
    
    def _validate_strategies(self, df: pd.DataFrame, strategies: List[Dict]) -> List[Dict]:
        """验证策略: 计算通过率/命中率"""
        from .evaluator import FeatureEvaluator
        evaluator = FeatureEvaluator(self.config)
        return evaluator.validate_strategies(df, strategies)
    
    # ========== 报告生成方法 ==========
    def _generate_step1_report(self, path: str, eval_results: Dict, valid: List[str], strategies: List[Dict]) -> str:
        """生成Step1报告"""
        from .reporter import ExcelReporter
        reporter = ExcelReporter(self.config)
        return reporter.generate_step1_report(path, eval_results, valid, strategies, self.config)
    
    def _generate_step2_report(self, path: str, validated: List[Dict]) -> str:
        """生成Step2报告"""
        from .reporter import ExcelReporter
        reporter = ExcelReporter(self.config)
        return reporter.generate_step2_report(path, validated, self.config)

    @classmethod
    def from_config(cls, scene: str, config_path: Optional[str] = None, 
                    profile: Optional[str] = None, **overrides) -> "StrategyAnalyzer":
        """
        从配置文件创建分析器实例
        
        Args:
            scene: "dq" or "dz"
            config_path: 配置文件路径 (可选)
            profile: 配置profile (dev/test/prod)
            **overrides: 额外配置覆盖
            
        Returns:
            StrategyAnalyzer实例
        """
        config = load_config(config_path=config_path, profile=profile)
        db_config = get_db_config(config, engine="starrocks")
        strategy_cfg = config.get("strategy_analysis", {})
        strategy_cfg.update(overrides)
        return cls(scene=scene, db_config=db_config, config=strategy_cfg, config_path=config_path)
