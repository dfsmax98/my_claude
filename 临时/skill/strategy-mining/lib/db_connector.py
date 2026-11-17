#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""strategy-mining skill - 通用数据库连接模块 (extended timeout)"""
import os, sys, logging, pymysql

# 自动加载 skill 根目录的 .env (凭证不硬编码)
try:
    _root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    sys.path.insert(0, os.path.join(_root, 'lib'))
    from env_loader import load_env
    load_env(__file__)
except Exception:
    pass

logger = logging.getLogger(__name__)

# Apply custom scramble function for StarRocks MySQL protocol compatibility
pymysql._auth.scramble_native_password = lambda password, message: (password.encode() if isinstance(password, str) else password) + b'\x00'

# 账号信息全部从环境变量读取, 不在代码中保留任何明文密码/IP。
# 运行前需 export 对应变量, 例如:
#   export SM_SR_HOST=... SM_SR_PORT=19030 SM_SR_USER=... SM_SR_PASSWORD=...
#   export SM_HIVE_HOST=... SM_HIVE_PORT=10009 SM_MODEL_PY_USER=... SM_MODEL_PY_PASSWORD=...
ACCOUNTS = {
    'model_py': {
        'host': os.getenv('SM_HIVE_HOST'), 'port': int(os.getenv('SM_HIVE_PORT', '10009')),
        'user': os.getenv('SM_MODEL_PY_USER'), 'password': os.getenv('SM_MODEL_PY_PASSWORD'),
        'catalog': os.getenv('SM_CATALOG', 'hc2'), 'schema': 'default', 'auth': 'PLAIN'},
    'zhengce_py': {
        'host': os.getenv('SM_HIVE_HOST'), 'port': int(os.getenv('SM_HIVE_PORT', '10009')),
        'user': os.getenv('SM_ZHENGCE_PY_USER'), 'password': os.getenv('SM_ZHENGCE_PY_PASSWORD'),
        'catalog': os.getenv('SM_CATALOG', 'hc2'), 'schema': 'default', 'auth': 'PLAIN'},
    'starrocks_mysql': {
        'host': os.getenv('SM_SR_HOST'), 'port': int(os.getenv('SM_SR_PORT', '19030')),
        'user': os.getenv('SM_SR_USER'), 'password': os.getenv('SM_SR_PASSWORD'),
        'catalog': os.getenv('SM_CATALOG', 'hc2'), 'schema': 'default'}
}

def get_connection(account_name='starrocks_mysql', use_trino=False):
    """
    获取数据库连接
    推荐: use_trino=False 使用pymysql连接StarRocks MySQL协议端口
    """
    if account_name not in ACCOUNTS:
        raise ValueError('Unknown account: '+account_name)
    
    cfg = ACCOUNTS[account_name].copy()
    
    # 使用pymysql连接StarRocks MySQL协议 (更稳定)
    try:
        logger.info('Connecting via pymysql: '+cfg['user']+'@'+cfg['host']+':'+str(cfg['port']))
        
        conn = pymysql.connect(
            host=cfg['host'],
            port=cfg['port'],
            user=cfg['user'],
            password=cfg.get('password',''),
            charset='utf8mb4',
            connect_timeout=30,      # 连接超时: 30秒
            read_timeout=3600,       # 读取超时: 1小时 (放宽)
            write_timeout=3600       # 写入超时: 1小时 (放宽)
        )
        cursor = conn.cursor()
        
        # 设置catalog (StarRocks特有)
        if cfg.get('catalog'):
            cursor.execute('SET catalog='+cfg['catalog'])
            logger.info('SET catalog='+cfg['catalog'])
        
        # 设置查询超时 (放宽至1小时)
        cursor.execute('SET query_timeout=3600')
        logger.info('SET query_timeout=3600')
        
        # 设置其他优化参数
        cursor.execute('SET exec_mem_limit=8589934592')  # 8GB内存限制
        logger.info('SET exec_mem_limit=8GB')
        
        logger.info('Connection successful with extended timeout')
        return conn, cursor
    except Exception as e:
        logger.error('pymysql connection failed: '+str(e))
        raise

def test_accounts():
    """测试所有账号连接"""
    results = {}
    for name in ACCOUNTS:
        try:
            conn, cursor = get_connection(name, use_trino=False)
            cursor.execute('SELECT 1')
            results[name] = {'status':'OK','result':cursor.fetchone()}
            cursor.close()
            conn.close()
        except Exception as e:
            results[name] = {'status':'FAIL','error':str(e)[:80]}
    return results

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    print('Testing accounts...')
    for name, res in test_accounts().items():
        status = 'OK' if res['status']=='OK' else 'FAIL'
        print(status+': '+name+' - '+str(res))
