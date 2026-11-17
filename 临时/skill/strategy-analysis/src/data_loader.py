# -*- coding: utf-8 -*-
"""数据加载模块: 直接使用pymysql连接StarRocks"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
logger = logging.getLogger(__name__)
import pandas as pd
import sys
import os
from typing import Dict, Optional

import pymysql
pymysql._auth.scramble_native_password = lambda password, message: password + b'\0'

# 自动加载 skill 根目录的 .env (凭证不硬编码)
try:
    _root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    sys.path.insert(0, os.path.join(_root, 'lib'))
    from env_loader import load_env
    load_env(__file__)
except Exception:
    pass

# Required fields
PRE_LOAN_REQUIRED = [
    'cust_no', 'apply_no', 'apply_result', 'close_datetime',
    'cust_group_dq', 'fpd_k30', 'if_out_30d', 'if_out_60d',
    'if_in_30d', 'if_in_60d', 'f001_decision'
]

IN_LOAN_REQUIRED = [
    'cust_no', 'trans_seqno', 'order_no', 'rsk_log_id',
    'risk_decision_result', 'create_datetime', 'cust_group_dz',
    'new_old', 'fpd_k30', 'if_out_30d', 'if_out_60d',
    'if_in_30d', 'if_in_60d'
]


def _connect(db_config: Dict):
    """创建数据库连接"""
    conn = pymysql.connect(
        host=db_config.get('host') or os.getenv('SA_SR_HOST'),
        port=int(db_config.get('port') or os.getenv('SA_SR_PORT', 19030)),
        user=db_config.get('user') or os.getenv('SA_SR_USER'),
        password=db_config.get('password') or os.getenv('SA_SR_PASSWORD'),
    )
    cur = conn.cursor()
    cur.execute('SET catalog=hc2')
    cur.execute('SET query_timeout=600')
    return conn, cur


def _execute_query(db_config: Dict, sql: str) -> pd.DataFrame:
    """执行查询并返回DataFrame"""
    conn, cur = _connect(db_config)
    try:
        logger.info(f"Executing SQL query...")
        cur.execute(sql)
        columns = [desc[0] for desc in cur.description]
        data = cur.fetchall()
        df = pd.DataFrame(data, columns=columns)
        logger.info(f"Query returned {len(df)} rows")
        return df
    finally:
        cur.close()
        conn.close()


def _validate_columns(df: pd.DataFrame, required: list, table_type: str):
    """校验必填字段"""
    missing = set(required) - set(df.columns)
    if missing:
        logger.warning(f"{table_type}表缺少字段: {missing}, 继续执行")
    else:
        logger.info(f"{table_type}字段校验通过: {len(required)}个必填字段")


def load_data_step1(feature_table: str, db_config: Dict, config: Dict, scene: str) -> pd.DataFrame:
    """
    Step1数据加载: fpd_k30 >= 0 过滤
    """
    required = PRE_LOAN_REQUIRED if scene == "dq" else IN_LOAN_REQUIRED
    time_col = "close_datetime" if scene == "dq" else "create_datetime"
    dt_start = config.get("dt_start", "2024-01-01")
    dt_end = config.get("dt_end", datetime.now().strftime("%Y-%m-%d"))
    
    # 特征表已包含样本字段，直接查询
    sql = f"""
SELECT *
FROM {feature_table}
WHERE fpd_k30 >= 0
  AND {time_col} BETWEEN '{dt_start}' AND '{dt_end}'
"""
    
    logger.info(f"Step1: Loading from {feature_table} with fpd_k30>=0")
    df = _execute_query(db_config, sql)
    
    _validate_columns(df, required, f"Step1-{scene}")
    
    if "fpd_k30" in df.columns:
        df = df[df["fpd_k30"] >= 0].copy()
        logger.info(f"fpd_k30>=0过滤后: {len(df)}行")
    
    return df


def load_data_step2(feature_table: str, db_config: Dict, config: Dict, scene: str, days: int = 7) -> pd.DataFrame:
    """
    Step2数据加载: 近N天全量数据, 无fpd_k30>=0过滤
    """
    required = PRE_LOAN_REQUIRED if scene == "dq" else IN_LOAN_REQUIRED
    time_col = "close_datetime" if scene == "dq" else "create_datetime"
    
    sql = f"""
SELECT *
FROM {feature_table}
WHERE {time_col} >= CURRENT_DATE - INTERVAL {days} DAY
"""
    
    logger.info(f"Step2: Loading from {feature_table} recent {days} days, NO fpd_k30 filter")
    df = _execute_query(db_config, sql)
    
    _validate_columns(df, required, f"Step2-{scene}")
    
    if time_col in df.columns:
        df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
        cutoff = datetime.now() - timedelta(days=days)
        df = df[df[time_col] >= cutoff].copy()
        logger.info(f"近{days}天过滤后: {len(df)}行")
    
    return df


def test_connection(db_config: Dict) -> bool:
    """测试数据库连接"""
    try:
        conn, cur = _connect(db_config)
        cur.execute("SELECT 1")
        cur.close()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        return False


def get_test_table(scene: str, config: Optional[Dict] = None) -> str:
    """获取测试表名"""
    if scene == "dq":
        return "d_dq.dfs_applist_risk_features_20260708"
    else:
        return "d_dq.dfs_applist_risk_features_inloan_20260708"
