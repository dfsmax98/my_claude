#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
表结构探查工具（优化版）
自动探查数据库表结构并生成Markdown文档
"""

import argparse
import os
import sys
from pathlib import Path
from datetime import datetime

import yaml
import pandas as pd
from impala.dbapi import connect

import re

# 自动加载 skill 根目录 .env (凭证不硬编码)
try:
    _root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    sys.path.insert(0, os.path.join(_root, 'lib'))
    from env_loader import load_env
    load_env(__file__)
except Exception:
    pass


def _expand_env(value):
    """递归展开配置中的 ${VAR} 为环境变量值"""
    if isinstance(value, str):
        return re.sub(r'\$\{([^}]+)\}', lambda m: os.getenv(m.group(1), m.group(0)), value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def load_config():
    """加载配置文件 (展开 ${VAR} 环境变量)"""
    config_path = Path(__file__).parent.parent / 'config.yaml'
    with open(config_path, 'r', encoding='utf-8') as f:
        return _expand_env(yaml.safe_load(f))


def load_field_comments():
    """加载字段注释映射文件"""
    comments_file = Path(__file__).parent.parent / 'field_comments.yaml'
    if not comments_file.exists():
        return {}
    
    with open(comments_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    comments = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip()
            comments[key] = value
    
    return comments


def get_field_comment(table_name, field_name, comments_dict):
    """获取字段注释，支持通配符匹配"""
    exact_key = f"{table_name}.{field_name}"
    if exact_key in comments_dict:
        return comments_dict[exact_key]
    
    wildcard_key = f"*.{field_name}"
    if wildcard_key in comments_dict:
        return comments_dict[wildcard_key]
    
    return ''


def connect_impala(config, profile='default'):
    """连接Impala数据库（支持多profile）"""
    profiles = config.get('db_profiles', {})
    db_config = profiles.get(profile, profiles.get('default', config['db']))
    conn = connect(
        host=db_config['impala_host'],
        port=db_config['impala_port'],
        database=db_config['impala_database'],
        auth_mechanism=db_config['impala_auth_mechanism'],
        user=db_config['impala_user'],
        password=db_config['impala_password']
    )
    return conn


def get_table_schema(cursor, table_name):
    """获取表结构信息"""
    cursor.execute(f"DESCRIBE {table_name}")
    rows = cursor.fetchall()
    
    schema = []
    for row in rows:
        if len(row) >= 2:
            schema.append({
                'col_name': row[0],
                'data_type': row[1],
                'comment': row[2] if len(row) > 2 else ''
            })
    
    return pd.DataFrame(schema)


def get_table_count(cursor, table_name, partition_filter=None, limit=10000):
    """Get table record count (uses LIMIT for fast estimation)"""
    try:
        if partition_filter:
            sql = f"SELECT COUNT(*) FROM (SELECT 1 FROM {table_name} WHERE {partition_filter} LIMIT {limit}) t"
        else:
            sql = f"SELECT COUNT(*) FROM (SELECT 1 FROM {table_name} LIMIT {limit}) t"
        cursor.execute(sql)
        result = cursor.fetchone()
        count = result[0] if result else 0
        if count >= limit:
            return f">={limit}"
        return count
    except Exception as e:
        print(f"[WARN] Cannot count: {e}")
        return None

def get_sample_data(cursor, table_name, schema_df, limit=100, partition_filter=None, max_cols=50):
    """获取样本数据（支持分区过滤和字段限制）"""
    # 如果字段太多，只选择前max_cols个字段
    all_cols = schema_df['col_name'].tolist()
    if len(all_cols) > max_cols:
        selected_cols = all_cols[:max_cols]
        col_list = ', '.join(selected_cols)
        truncated = True
    else:
        col_list = '*'
        selected_cols = all_cols
        truncated = False
    
    if partition_filter:
        sql = f"SELECT {col_list} FROM {table_name} WHERE {partition_filter} LIMIT {limit}"
    else:
        sql = f"SELECT {col_list} FROM {table_name} LIMIT {limit}"
    
    cursor.execute(sql)
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    
    df = pd.DataFrame(rows, columns=columns)
    
    if truncated:
        print(f"[INFO] 字段过多({len(all_cols)}个)，样本数据仅展示前{max_cols}个字段")
    
    return df


def identify_key_fields(schema_df, config):
    """识别关键字段"""
    patterns = config['explorer']['key_field_patterns']
    
    primary_keys = []
    time_fields = []
    foreign_keys = []
    info_fields = []
    
    for _, row in schema_df.iterrows():
        col_name = row['col_name'].lower()
        
        for pattern in patterns['primary_keys']:
            if pattern.lower() in col_name or col_name == pattern.lower():
                primary_keys.append(row['col_name'])
                break
        
        for pattern in patterns['time_fields']:
            if pattern.lower() in col_name:
                time_fields.append(row['col_name'])
                break
        
        for pattern in patterns['foreign_keys']:
            if pattern.lower() in col_name and row['col_name'] not in primary_keys:
                foreign_keys.append(row['col_name'])
                break
        
        for pattern in patterns['info_fields']:
            if pattern.lower() in col_name:
                info_fields.append(row['col_name'])
                break
    
    return {
        'primary_keys': primary_keys,
        'time_fields': time_fields,
        'foreign_keys': foreign_keys,
        'info_fields': info_fields
    }


def analyze_enum_values(sample_df, config):
    """分析枚举值"""
    threshold = config['explorer']['enum_threshold']
    max_values = config['explorer']['max_enum_values']
    
    enum_analysis = {}
    
    for col in sample_df.columns:
        try:
            nunique = sample_df[col].nunique()
            if nunique <= threshold and nunique > 0:
                value_counts = sample_df[col].value_counts().head(max_values)
                enum_analysis[col] = {
                    'cardinality': nunique,
                    'values': value_counts.to_dict()
                }
        except Exception:
            continue
    
    return enum_analysis


def generate_markdown(table_name, schema_df, sample_df, key_fields, enum_analysis, table_count, comments_dict, partition_filter=None):
    """生成Markdown文档"""
    lines = []
    
    lines.append(f"# {table_name} 表结构文档\n")
    lines.append(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    lines.append("## 基本信息\n")
    lines.append(f"- **表名**: {table_name}")
    if partition_filter:
        lines.append(f"- **分区过滤**: {partition_filter}")
    lines.append(f"- **记录数**: {table_count if table_count is not None else 'N/A'}")
    lines.append(f"- **字段数**: {len(schema_df)}\n")
    
    lines.append("## 字段列表\n")
    lines.append("| 序号 | 字段名 | 数据类型 | 注释 |")
    lines.append("|------|--------|----------|------|")
    
    for idx, row in schema_df.iterrows():
        col_name = row['col_name']
        data_type = row['data_type']
        comment = row.get('comment', '')
        
        if not comment or comment == '':
            comment = get_field_comment(table_name, col_name, comments_dict)
        
        comment = comment.replace('|', '\\|')
        
        lines.append(f"| {idx+1} | {col_name} | {data_type} | {comment} |")
    
    lines.append("")
    
    lines.append("## 关键字段\n")
    
    if key_fields['primary_keys']:
        lines.append("### 主键字段\n")
        for field in key_fields['primary_keys']:
            comment = get_field_comment(table_name, field, comments_dict)
            lines.append(f"- {field}: {comment}")
        lines.append("")
    
    if key_fields['time_fields']:
        lines.append("### 时间字段\n")
        for field in key_fields['time_fields']:
            comment = get_field_comment(table_name, field, comments_dict)
            lines.append(f"- {field}: {comment}")
        lines.append("")
    
    if key_fields['foreign_keys']:
        lines.append("### 外键字段\n")
        for field in key_fields['foreign_keys'][:10]:
            comment = get_field_comment(table_name, field, comments_dict)
            lines.append(f"- {field}: {comment}")
        if len(key_fields['foreign_keys']) > 10:
            lines.append(f"- ... 共 {len(key_fields['foreign_keys'])} 个外键字段")
        lines.append("")
    
    if key_fields['info_fields']:
        lines.append("### 信息字段\n")
        for field in key_fields['info_fields'][:10]:
            comment = get_field_comment(table_name, field, comments_dict)
            lines.append(f"- {field}: {comment}")
        if len(key_fields['info_fields']) > 10:
            lines.append(f"- ... 共 {len(key_fields['info_fields'])} 个信息字段")
        lines.append("")
    
    lines.append("## 样本数据 (前10条)\n")
    lines.append("")
    lines.append(sample_df.head(10).to_string())
    lines.append("\n")
    
    if enum_analysis:
        lines.append("## 枚举值分析\n")
        for col, info in enum_analysis.items():
            cardinality = info['cardinality']
            values = info['values']
            
            comment = get_field_comment(table_name, col, comments_dict)
            lines.append(f"### {col} (基数: {cardinality})\n")
            if comment:
                lines.append(f"{comment}\n")
            
            lines.append("| 值 | 数量 |")
            lines.append("|----|------|")
            for val, count in values.items():
                lines.append(f"| {val} | {count} |")
            lines.append("")
    
    return '\n'.join(lines)


def explore_table(table_name, output_path=None, no_count=False, partition_filter=None, profile='default'):
    """探查表结构"""
    print(f"[INFO] 探查表: {table_name}")
    if partition_filter:
        print(f"[INFO] 分区过滤: {partition_filter}")
    
    config = load_config()
    comments_dict = load_field_comments()
    
    print("[INFO] 连接Impala...")
    conn = connect_impala(config, profile)
    cursor = conn.cursor()
    print("[OK] 连接成功")
    
    try:
        print("[INFO] 获取表结构...")
        schema_df = get_table_schema(cursor, table_name)
        print(f"[OK] 找到 {len(schema_df)} 个字段")
        
        table_count = None
        if not no_count:
            print("[INFO] 统计记录数...")
            table_count = get_table_count(cursor, table_name, partition_filter)
            if table_count is not None:
                print(f"[OK] 记录数: {table_count}")
            else:
                print("[WARN] 无法获取记录数")
        else:
            print("[INFO] 跳过记录数统计")
        
        print("[INFO] 获取样本数据...")
        sample_df = get_sample_data(cursor, table_name, schema_df, limit=100, partition_filter=partition_filter, max_cols=50)
        print(f"[OK] 获取 {len(sample_df)} 条样本")
        
        print("[INFO] 识别关键字段...")
        key_fields = identify_key_fields(schema_df, config)
        print(f"[OK] 主键: {len(key_fields['primary_keys'])}, 时间: {len(key_fields['time_fields'])}")
        
        print("[INFO] 分析枚举值...")
        enum_analysis = analyze_enum_values(sample_df, config)
        print(f"[OK] 找到 {len(enum_analysis)} 个枚举字段")
        
        print("[INFO] 生成文档...")
        markdown = generate_markdown(
            table_name, schema_df, sample_df, 
            key_fields, enum_analysis, table_count, comments_dict, partition_filter
        )
        
        if not output_path:
            output_dir = Path(__file__).parent.parent / 'output'
            output_dir.mkdir(exist_ok=True)
            table_short_name = table_name.replace('.', '_')
            output_path = output_dir / f"{table_short_name}.md"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown)
        
        print(f"[OK] 文档已保存: {output_path}")
        print("[DONE] 探查完成")
        
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='表结构探查工具（优化版）')
    parser.add_argument('table_name', help='表名 (如: d_dq.dfs_dq_fqz_base_final)')
    parser.add_argument('--output', '-o', help='输出文件路径')
    parser.add_argument('--no-count', action='store_true', help='跳过全表COUNT统计')
    parser.add_argument('--partition', '-p', help='分区过滤条件 (如: dt=\'20260707\')')
    
    parser.add_argument('--profile', type=str, default='default', help='数据库配置文件 (default 或 dss_mx)')
    args = parser.parse_args()
    explore_table(args.table_name, args.output, args.no_count, args.partition, args.profile)
