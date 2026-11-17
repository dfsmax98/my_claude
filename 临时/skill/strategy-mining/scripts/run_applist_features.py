"""
APP特征衍生表执行脚本

功能：
1. 执行建表SQL（CREATE TABLE + INSERT）
2. 读取衍生表数据
3. 调用策略分析脚本

用法：
    python run_applist_features.py --table d_dq.dfs_applist_risk_features_20260707 --stage preloan
    python run_applist_features.py --table d_dq.dfs_applist_risk_features_inloan_20260707 --stage inloan
"""

import argparse
import os
import sys
import pymysql
import pandas as pd

# 自动加载 skill 根目录 .env (凭证不硬编码)
try:
    _root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    sys.path.insert(0, os.path.join(_root, 'lib'))
    from env_loader import load_env
    load_env(__file__)
except Exception:
    pass


def parse_args():
    parser = argparse.ArgumentParser(description='执行APP特征衍生')
    parser.add_argument('--table', type=str, required=True, help='目标表名')
    parser.add_argument('--stage', type=str, choices=['preloan', 'inloan'], required=True,
                        help='阶段：preloan(贷前) 或 inloan(贷中)')
    parser.add_argument('--sql', type=str, required=True, help='SQL文件路径')
    # 数据库连接默认从环境变量读取(见 .env), 不硬编码明文
    parser.add_argument('--host', type=str, default=os.getenv('SM_SR_HOST'), help='StarRocks主机')
    parser.add_argument('--port', type=int, default=int(os.getenv('SM_SR_PORT', '19030')), help='StarRocks端口')
    parser.add_argument('--user', type=str, default=os.getenv('SM_SR_USER'), help='数据库用户')
    parser.add_argument('--password', type=str, default=os.getenv('SM_SR_PASSWORD'), help='数据库密码')
    parser.add_argument('--limit', type=int, default=10000, help='读取数据行数限制')
    return parser.parse_args()


def execute_sql(sql_file, host, port, user, password):
    """执行SQL文件中的所有语句"""
    print(f"Connecting to {host}:{port}...")
    conn = pymysql.connect(host=host, port=port, user=user, password=password)
    cursor = conn.cursor()
    
    # 设置catalog
    cursor.execute("SET catalog = hc2")
    
    # 读取SQL文件
    with open(sql_file, 'r', encoding='utf-8') as f:
        sql_content = f.read()
    
    # 按分号分割SQL语句
    statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip() and not stmt.strip().startswith('--')]
    
    print(f"Executing {len(statements)} SQL statements...")
    for i, stmt in enumerate(statements, 1):
        print(f"  [{i}/{len(statements)}] {stmt[:80]}...")
        try:
            cursor.execute(stmt)
            conn.commit()
        except Exception as e:
            print(f"    ERROR: {e}")
            conn.rollback()
            raise
    
    cursor.close()
    conn.close()
    print("SQL execution completed.")


def read_table(table_name, host, port, user, password, limit):
    """读取表数据"""
    print(f"\nReading data from {table_name} (limit {limit})...")
    conn = pymysql.connect(host=host, port=port, user=user, password=password)
    cursor = conn.cursor()
    cursor.execute("SET catalog = hc2")
    
    query = f"SELECT * FROM {table_name} LIMIT {limit}"
    cursor.execute(query)
    
    # 获取列名
    columns = [desc[0] for desc in cursor.description]
    
    # 获取数据
    rows = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    # 转换为DataFrame
    df = pd.DataFrame(rows, columns=columns)
    print(f"Loaded {len(df)} rows, {len(df.columns)} columns")
    
    return df


def main():
    args = parse_args()
    
    # 执行SQL建表
    execute_sql(args.sql, args.host, args.port, args.user, args.password)
    
    # 读取数据
    df = read_table(args.table, args.host, args.port, args.user, args.password, args.limit)
    
    # 显示基本信息
    print(f"\n=== 数据概览 ===")
    print(f"样本数: {len(df)}")
    print(f"特征数: {len(df.columns)}")
    print(f"\n列名:")
    for col in df.columns:
        print(f"  - {col}")
    
    print(f"\n=== 完成 ===")
    print(f"表已创建并填充数据: {args.table}")
    print(f"下一步: 运行策略分析脚本")
    print(f"  python analyze_app_features.py --table {args.table} --stage {args.stage}")


if __name__ == '__main__':
    main()
