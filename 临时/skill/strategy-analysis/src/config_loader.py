# -*- coding: utf-8 -*-
"""配置加载模块: 加载config.yaml并支持环境变量替换"""
from __future__ import annotations
import os
import re
import sys
import yaml
from pathlib import Path
from typing import Any, Dict, Optional

# 自动加载 skill 根目录 .env, 使 config.yaml 里的 ${VAR} 能取到真实凭证
try:
    _root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    sys.path.insert(0, os.path.join(_root, "lib"))
    from env_loader import load_env
    load_env(__file__)
except Exception:
    pass

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def _expand_env_vars(value: Any) -> Any:
    """递归展开配置中的环境变量 ${VAR_NAME}"""
    if isinstance(value, str):
        # 匹配 ${VAR_NAME} 格式
        pattern = r'\$\{([^}]+)\}'
        def replacer(match):
            var_name = match.group(1)
            return os.getenv(var_name, match.group(0))  # 未设置则保留原值
        return re.sub(pattern, replacer, value)
    elif isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_expand_env_vars(item) for item in value]
    return value


def load_config(config_path: Optional[str] = None, 
                profile: Optional[str] = None,
                overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    加载策略分析配置
    
    Args:
        config_path: 配置文件路径 (默认: skill/strategy-analysis/config.yaml)
        profile: 配置profile名称 (dev/test/prod, 可选)
        overrides: 额外配置覆盖 (可选)
    
    Returns:
        Dict: 合并后的配置字典
    """
    # 确定配置文件路径
    if config_path:
        path = Path(config_path)
    else:
        path = DEFAULT_CONFIG_PATH
    
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    
    # 加载YAML
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    
    # 展开环境变量
    config = _expand_env_vars(config)
    
    # 应用profile配置 (如果指定)
    if profile and "db_profiles" in config and profile in config["db_profiles"]:
        # 合并profile配置到db
        if "db" not in config:
            config["db"] = {}
        config["db"].update(config["db_profiles"][profile])
    
    # 应用额外覆盖
    if overrides:
        _deep_merge(config, overrides)
    
    return config


def _deep_merge(base: Dict, override: Dict) -> Dict:
    """深度合并两个字典 (override优先)"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def get_db_config(config: Dict, engine: str = "starrocks") -> Dict[str, str]:
    """
    提取数据库连接配置
    
    Args:
        config: 完整配置字典
        engine: 数据库引擎 (starrocks/hive)
    
    Returns:
        Dict: 数据库连接参数字典
    """
    db_cfg = config.get("db", {})
    prefix = engine
    
    return {
        "host": db_cfg.get(f"{prefix}_host", "localhost"),
        "port": db_cfg.get(f"{prefix}_port", 9030 if engine == "starrocks" else 10000),
        "user": db_cfg.get(f"{prefix}_user", "root"),
        "password": db_cfg.get(f"{prefix}_password", ""),
        "database": db_cfg.get(f"{prefix}_database", "default"),
        "auth_mechanism": db_cfg.get(f"{prefix}_auth_mechanism", "PLAIN") if engine == "hive" else None
    }


def get_strategy_config(config: Dict) -> Dict[str, Any]:
    """提取策略分析相关配置"""
    return config.get("strategy_analysis", {})


def get_test_table(config: Dict, scene: str) -> Optional[str]:
    """获取测试表名"""
    test_tables = config.get("strategy_analysis", {}).get("test_tables", {})
    return test_tables.get(scene)