#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据库连接路由模块 (Agent 专用)

功能:
- 统一管理 Hive / StarRocks 两套数据库连接
- 自动故障转移: Hive 连不上 -> 自动切 SR, SR 连不上 -> 自动切 Hive
- Agent 调用接口简洁: get_conn(table_name) -> 返回 (conn, cursor, engine_type)

配置来源:
- 硬编码账号 (来自 db_connector.py 和 hive 到 paimon 映射字段推测.py)
- 支持环境变量覆盖敏感信息

Agent 调用示例:
    from skill.lib.db_router import query_table, describe_table
    
    # 探查表结构 (自动路由)
    columns, sample = describe_table('svl_uld_dq.dfs_dz_fqz_overdue_base')
    
    # 执行查询 (自动路由 + 超时控制)
    df = query_table('SELECT * FROM table LIMIT 100', timeout=300)
"""

import os
import sys
import logging
import pymysql
from typing import Optional, Tuple, List, Dict, Union
from contextlib import contextmanager

# 自动加载同目录/上层的 .env (凭证不硬编码, agent 调用时零手动步骤)
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from env_loader import load_env
    load_env(__file__)
except Exception:
    pass

logger = logging.getLogger(__name__)

# ============ 数据库配置 (全部从环境变量读取, 不保留任何明文默认值) ============
# 运行前需 export: HIVE_HOST/HIVE_PORT/HIVE_USER/HIVE_PASSWORD,
#   HIVE_USER_ALT/HIVE_PASSWORD_ALT, SR_HOST/SR_PORT/SR_USER/SR_PASSWORD 等
# Hive 配置 (Impala/Trino 协议 via PyHive)
HIVE_CONFIG = {
    'host': os.getenv('HIVE_HOST'),
    'port': int(os.getenv('HIVE_PORT', '10009')),
    'user': os.getenv('HIVE_USER'),
    'password': os.getenv('HIVE_PASSWORD'),
    'database': os.getenv('HIVE_DATABASE', 'default'),
    'auth': os.getenv('HIVE_AUTH', 'PLAIN'),
    'timeout': int(os.getenv('HIVE_TIMEOUT', '30')),
}

# 备选 Hive 账号 (model_py)
HIVE_CONFIG_ALT = {
    'host': HIVE_CONFIG['host'],
    'port': HIVE_CONFIG['port'],
    'user': os.getenv('HIVE_USER_ALT'),
    'password': os.getenv('HIVE_PASSWORD_ALT'),
    'database': HIVE_CONFIG['database'],
    'auth': HIVE_CONFIG['auth'],
    'timeout': HIVE_CONFIG['timeout'],
}

# StarRocks 配置 (MySQL 协议 via PyMySQL)
SR_CONFIG = {
    'host': os.getenv('SR_HOST'),
    'port': int(os.getenv('SR_PORT', '9030')),
    'user': os.getenv('SR_USER'),
    'password': os.getenv('SR_PASSWORD'),
    'catalog': os.getenv('SR_CATALOG', 'hc2'),
    'charset': 'utf8mb4',
    'connect_timeout': int(os.getenv('SR_CONNECT_TIMEOUT', '30')),
    'read_timeout': int(os.getenv('SR_READ_TIMEOUT', '300')),
}

# 表名 -> 引擎路由规则 (前缀匹配)
ROUTING_RULES = {
    'd_dq.': 'auto',
    'dwh.': 'auto',
    'fico_test.': 'hive',
    'svl_uld_dq.': 'sr',
    'smy_pc.': 'sr',
    'smy_pc_tmp.': 'sr',
    'lh.': 'sr',
}

DEFAULT_ENGINE = 'auto'


# ============ 密码加密兼容 (StarRocks MySQL 协议) ============
def _sr_scramble(password: Union[str, bytes], message: bytes) -> bytes:
    pwd = password.encode() if isinstance(password, str) else password
    return pwd + b'\x00'


# ============ 连接函数 ============
def connect_hive(config: Optional[Dict] = None, use_alt: bool = False) -> Tuple:
    try:
        from pyhive import hive
        cfg = config or (HIVE_CONFIG_ALT if use_alt else HIVE_CONFIG)
        logger.info(f'Connecting to Hive: {cfg["user"]}@{cfg["host"]}:{cfg["port"]}')
        conn = hive.connect(
            host=cfg['host'], port=cfg['port'], username=cfg['user'],
            password=cfg.get('password', ''), database=cfg.get('database', 'default'),
            auth=cfg.get('auth', 'PLAIN'), configuration={'mapred.job.queue.name': 'default'}
        )
        cursor = conn.cursor()
        logger.info('Hive connection successful')
        return conn, cursor
    except ImportError:
        raise RuntimeError('PyHive not installed. Run: pip install pyhive[hive]')
    except Exception as e:
        logger.error(f'Hive connection failed: {e}')
        raise


def connect_sr(config: Optional[Dict] = None) -> Tuple:
    cfg = config or SR_CONFIG
    pymysql._auth.scramble_native_password = _sr_scramble
    logger.info(f'Connecting to StarRocks: {cfg["user"]}@{cfg["host"]}:{cfg["port"]}')
    try:
        conn = pymysql.connect(
            host=cfg['host'], port=cfg['port'], user=cfg['user'],
            password=cfg.get('password', ''), charset=cfg.get('charset', 'utf8mb4'),
            connect_timeout=cfg.get('connect_timeout', 30),
            read_timeout=cfg.get('read_timeout', 300),
            cursorclass=pymysql.cursors.DictCursor
        )
        cursor = conn.cursor()
        if cfg.get('catalog'):
            try:
                cursor.execute(f"SET catalog = '{cfg['catalog']}'")
            except:
                pass
        try:
            cursor.execute('SET query_timeout = 300')
        except:
            pass
        logger.info('StarRocks connection successful')
        return conn, cursor
    except Exception as e:
        logger.error(f'StarRocks connection failed: {e}')
        raise


# ============ 路由决策 ============
def get_engine_for_table(table_name: str) -> str:
    table_lower = table_name.lower()
    for prefix, engine in ROUTING_RULES.items():
        if table_lower.startswith(prefix.lower()):
            return engine
    return DEFAULT_ENGINE


def get_connection(table_name: Optional[str] = None, 
                  preferred_engine: Optional[str] = None,
                  try_alt_hive: bool = True) -> Tuple:
    if preferred_engine:
        engines_to_try = [preferred_engine]
    else:
        engine_hint = get_engine_for_table(table_name) if table_name else 'auto'
        if engine_hint == 'auto':
            engines_to_try = ['hive', 'sr']
        else:
            engines_to_try = [engine_hint]
    
    last_error = None
    for engine in engines_to_try:
        try:
            if engine == 'hive':
                conn, cursor = connect_hive(use_alt=False)
                return conn, cursor, 'hive'
            elif engine == 'sr':
                conn, cursor = connect_sr()
                return conn, cursor, 'sr'
        except Exception as e:
            last_error = e
            logger.warning(f'{engine} connection failed, trying next...')
            if engine == 'hive' and try_alt_hive:
                try:
                    conn, cursor = connect_hive(use_alt=True)
                    return conn, cursor, 'hive(alt)'
                except Exception as e2:
                    logger.warning(f'Hive alt account also failed: {e2}')
                    last_error = e2
    raise ConnectionError(f'All connection attempts failed. Last error: {last_error}. Tried engines: {engines_to_try}')


# ============ Agent 友好接口 ============
@contextmanager
def db_session(table_name: Optional[str] = None, **kwargs):
    conn, cursor, engine = get_connection(table_name, **kwargs)
    try:
        yield conn, cursor, engine
    finally:
        try:
            cursor.close()
        except:
            pass
        try:
            conn.close()
        except:
            pass


def describe_table(table_name: str, limit: int = 5) -> Dict:
    result = {'success': False, 'columns': [], 'sample': [], 'error': None}
    try:
        with db_session(table_name) as (conn, cursor, engine):
            result['engine'] = engine
            cursor.execute(f'DESCRIBE {table_name}')
            raw_cols = cursor.fetchall()
            for col in raw_cols:
                if isinstance(col, dict):
                    result['columns'].append({
                        'name': col.get('Field') or col.get('column_name'),
                        'type': col.get('Type') or col.get('data_type'),
                        'nullable': col.get('Null', 'YES'),
                        'key': col.get('Key', ''),
                        'default': col.get('Default'),
                        'comment': col.get('Comment', ''),
                    })
                else:
                    result['columns'].append({
                        'name': col[0] if len(col) > 0 else '',
                        'type': col[1] if len(col) > 1 else '',
                        'nullable': col[2] if len(col) > 2 else 'YES',
                        'key': col[3] if len(col) > 3 else '',
                        'default': col[4] if len(col) > 4 else '',
                        'comment': col[5] if len(col) > 5 else '',
                    })
            cursor.execute(f'SELECT * FROM {table_name} LIMIT {limit}')
            rows = cursor.fetchall()
            if rows:
                if hasattr(cursor, 'description') and cursor.description:
                    col_names = [desc[0] for desc in cursor.description]
                else:
                    col_names = [c['name'] for c in result['columns']]
                for row in rows:
                    if isinstance(row, dict):
                        result['sample'].append(row)
                    else:
                        result['sample'].append({
                            col_names[i]: str(val)[:200] if val is not None else None
                            for i, val in enumerate(row)
                        })
            result['success'] = True
            logger.info(f'Describe success: {len(result["columns"])} columns via {engine}')
    except Exception as e:
        result['error'] = str(e)
        logger.error(f'Describe failed: {e}')
    return result


def query_table(sql: str, table_name: Optional[str] = None, 
               timeout: int = 300, as_df: bool = False) -> Union[List[Dict], 'pd.DataFrame']:
    try:
        with db_session(table_name) as (conn, cursor, engine):
            if engine.startswith('hive'):
                cursor.execute('SET mapred.job.queue.name=default')
            else:
                cursor.execute(f'SET query_timeout = {timeout}')
            cursor.execute(sql)
            rows = cursor.fetchall()
            if hasattr(cursor, 'description') and cursor.description:
                col_names = [desc[0] for desc in cursor.description]
            else:
                col_names = []
            if as_df:
                import pandas as pd
                if rows and isinstance(rows[0], dict):
                    return pd.DataFrame(rows)
                elif col_names:
                    return pd.DataFrame(rows, columns=col_names)
                else:
                    return pd.DataFrame()
            else:
                if rows and isinstance(rows[0], dict):
                    return list(rows)
                elif col_names:
                    return [{col_names[i]: val for i, val in enumerate(row)} for row in rows]
                else:
                    return list(rows)
    except Exception as e:
        logger.error(f'Query failed: {e}')
        return None


def health_check() -> Dict[str, bool]:
    results = {}
    try:
        connect_hive(use_alt=False)
        results['hive'] = True
    except:
        results['hive'] = False
    try:
        connect_hive(use_alt=True)
        results['hive_alt'] = True
    except:
        results['hive_alt'] = False
    try:
        connect_sr()
        results['starrocks'] = True
    except:
        results['starrocks'] = False
    return results


if __name__ == '__main__':
    import sys, json
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    if len(sys.argv) > 1 and sys.argv[1] == '--health':
        print('Health check:')
        print(json.dumps(health_check(), indent=2))
    elif len(sys.argv) > 1:
        table = sys.argv[1]
        print(f'Describing: {table}')
        result = describe_table(table)
        if result['success']:
            print(f'\nSuccess via {result["engine"]}')
            print(f'Columns: {len(result["columns"])}')
            for col in result['columns'][:10]:
                print(f'  - {col["name"]}: {col["type"]}')
        else:
            print(f'\nFailed: {result["error"]}')
    else:
        print('Usage: python db_router.py <table_name> | --health')
