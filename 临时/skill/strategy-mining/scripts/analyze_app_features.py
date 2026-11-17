"""
APP特征策略分析脚本

功能：
1. 读取APP特征衍生表
2. 计算各特征的FPD率和投诉率
3. 计算IV值评估预测能力
4. 生成策略分析报告

用法：
    python analyze_app_features.py --table d_dq.dfs_applist_risk_features_20260707 --stage preloan
    python analyze_app_features.py --table d_dq.dfs_applist_risk_features_inloan_20260707 --stage inloan
"""

import argparse
import os
import sys
import pymysql

# Password scramble for pymysql
pymysql._auth.scramble_native_password = lambda password, message: password + b'\0'
import pandas as pd
import numpy as np

# 自动加载 skill 根目录 .env (凭证不硬编码)
try:
    _root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    sys.path.insert(0, os.path.join(_root, 'lib'))
    from env_loader import load_env
    load_env(__file__)
except Exception:
    pass


def parse_args():
    parser = argparse.ArgumentParser(description='分析APP特征预测能力')
    parser.add_argument('--table', type=str, required=True, help='特征表名')
    parser.add_argument('--stage', type=str, choices=['preloan', 'inloan'], required=True,
                        help='阶段：preloan(贷前) 或 inloan(贷中)')
    # 数据库连接默认从环境变量读取(见 .env), 不硬编码明文
    parser.add_argument('--host', type=str, default=os.getenv('SM_SR_HOST'), help='StarRocks主机')
    parser.add_argument('--port', type=int, default=int(os.getenv('SM_SR_PORT', '19030')), help='StarRocks端口')
    parser.add_argument('--user', type=str, default=os.getenv('SM_SR_USER'), help='数据库用户')
    parser.add_argument('--password', type=str, default=os.getenv('SM_SR_PASSWORD'), help='数据库密码')
    parser.add_argument('--limit', type=int, default=100000, help='读取数据行数限制')
    parser.add_argument('--bins', type=int, default=10, help='分箱数量')
    return parser.parse_args()


def load_data(table_name, host, port, user, password, limit):
    """从数据库加载特征数据"""
    print(f"Connecting to {host}:{port}...")
    conn = pymysql.connect(host=host, port=port, user=user, password=password)
    cursor = conn.cursor()
    cursor.execute("SET catalog = hc2")
    
    query = f"SELECT * FROM {table_name} LIMIT {limit}"
    print(f"Loading data: {query}")
    cursor.execute(query)
    
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    df = pd.DataFrame(rows, columns=columns)
    print(f"Loaded {len(df)} rows, {len(df.columns)} columns")
    
    return df


def calculate_iv(df, feature_col, target_col, n_bins=10):
    """
    计算特征的IV值
    
    Args:
        df: 数据框
        feature_col: 特征列名
        target_col: 目标列名 (0/1)
        n_bins: 分箱数量
    
    Returns:
        dict: 包含IV值、WOE、分箱统计等信息
    """
    # 过滤有效数据
    valid_df = df[[feature_col, target_col]].dropna()
    
    if len(valid_df) == 0:
        return None
    
    # Convert decimal.Decimal to float for numpy compatibility
    feature_values = valid_df[feature_col]
    if hasattr(feature_values.iloc[0], '__float__'):
        feature_values = feature_values.astype(float)
        valid_df = valid_df.copy()
        valid_df[feature_col] = feature_values
    
    try:
        valid_df['bin'] = pd.qcut(valid_df[feature_col], n_bins, duplicates='drop')
    except ValueError:
        # 如果分箱失败，使用唯一值
        valid_df['bin'] = valid_df[feature_col]
    
    # 计算每箱统计
    bin_stats = valid_df.groupby('bin', observed=True).agg({
        feature_col: ['count', 'sum'],
        target_col: ['sum']
    }).reset_index()
    
    bin_stats.columns = ['bin', 'total_count', 'feature_sum', 'bad_count']
    bin_stats['good_count'] = bin_stats['total_count'] - bin_stats['bad_count']
    bin_stats['bad_rate'] = bin_stats['bad_count'] / bin_stats['total_count']
    
    # 计算总bad/good
    total_bad = bin_stats['bad_count'].sum()
    total_good = bin_stats['good_count'].sum()
    
    if total_bad == 0 or total_good == 0:
        return None
    
    # 计算WOE和IV
    bin_stats['bad_pct'] = bin_stats['bad_count'] / total_bad
    bin_stats['good_pct'] = bin_stats['good_count'] / total_good
    
    # 避免除零
    bin_stats['bad_pct'] = bin_stats['bad_pct'].replace(0, 0.0001)
    bin_stats['good_pct'] = bin_stats['good_pct'].replace(0, 0.0001)
    
    bin_stats['woe'] = np.log(bin_stats['good_pct'] / bin_stats['bad_pct'])
    bin_stats['iv'] = (bin_stats['good_pct'] - bin_stats['bad_pct']) * bin_stats['woe']
    
    total_iv = bin_stats['iv'].sum()
    
    return {
        'iv': total_iv,
        'woe_stats': bin_stats,
        'valid_count': len(valid_df),
        'coverage': len(valid_df) / len(df)
    }


def analyze_features(df, stage, n_bins=10):
    """分析所有特征的预测能力"""
    
    # 确定目标变量
    if stage == 'preloan':
        target_cols = ['fpd_k30', 'if_out_30d', 'if_out_60d', 'if_in_30d', 'if_in_60d']
    else:  # inloan
        target_cols = ['fpd_k30', 'if_out_30d', 'if_out_60d', 'if_in_30d', 'if_in_60d']
    
    # 获取特征列（排除样本表字段和目标变量）
    exclude_cols = ['cust_no', 'apply_no', 'close_datetime', 'trans_seqno', 'order_no', 
                   'rsk_log_id', 'apply_result', 'cust_group_dq', 'cust_group_dz', 
                   'fpd_k30', 'if_out_30d', 'if_out_60d', 'if_in_30d', 'if_in_60d',
                   'f001_decision', 'create_datetime', 'risk_decision_result', 'new_old']
    
    feature_cols = [col for col in df.columns if col not in exclude_cols and col.startswith('app_')]
    
    print(f"\nAnalyzing {len(feature_cols)} features against {len(target_cols)} targets...")
    
    results = []
    
    for feature_col in feature_cols:
        feature_result = {'feature': feature_col}
        
        for target_col in target_cols:
            if target_col not in df.columns:
                feature_result[f'{target_col}_iv'] = None
                continue
            
            iv_result = calculate_iv(df, feature_col, target_col, n_bins)
            
            if iv_result:
                feature_result[f'{target_col}_iv'] = iv_result['iv']
                feature_result['coverage'] = iv_result['coverage']
            else:
                feature_result[f'{target_col}_iv'] = None
        
        results.append(feature_result)
    
    results_df = pd.DataFrame(results)
    
    return results_df


def generate_report(results_df, stage):
    """生成策略分析报告"""
    
    print(f"\n{'='*80}")
    print(f"APP特征策略分析报告 ({stage})")
    print(f"{'='*80}\n")
    
    # 1. FPD预测能力TOP 20
    print("【FPD预测能力 TOP 20】")
    print("-" * 80)
    
    fpd_col = 'fpd_k30_iv'
    if fpd_col in results_df.columns:
        fpd_results = results_df.dropna(subset=[fpd_col]).sort_values(fpd_col, ascending=False).head(20)
        
        for idx, row in fpd_results.iterrows():
            iv_val = row[fpd_col]
            coverage = row.get('coverage', 0)
            
            # IV解读
            if iv_val >= 0.5:
                level = "极强(检查泄露)"
            elif iv_val >= 0.3:
                level = "强"
            elif iv_val >= 0.1:
                level = "中等"
            elif iv_val >= 0.02:
                level = "弱"
            else:
                level = "无"
            
            print(f"{row['feature']:<50} IV={iv_val:.4f} ({level}) 覆盖率={coverage:.2%}")
    
    # 2. 投诉预测能力TOP 10
    print(f"\n{'='*80}")
    print("【投诉预测能力 TOP 10】")
    print("="*80)
    
    complaint_cols = ['if_out_30d_iv', 'if_out_60d_iv', 'if_in_30d_iv', 'if_in_60d_iv']
    
    for complaint_col in complaint_cols:
        if complaint_col in results_df.columns:
            complaint_name = complaint_col.replace('_iv', '')
            print(f"\n{complaint_name}:")
            print("-" * 80)
            
            complaint_results = results_df.dropna(subset=[complaint_col]).sort_values(
                complaint_col, ascending=False).head(10)
            
            for idx, row in complaint_results.iterrows():
                iv_val = row[complaint_col]
                coverage = row.get('coverage', 0)
                print(f"{row['feature']:<50} IV={iv_val:.4f} 覆盖率={coverage:.2%}")
    
    # 3. 高覆盖率特征
    print(f"\n{'='*80}")
    print("【高覆盖率特征 (覆盖率 > 10%)】")
    print("="*80)
    
    if 'coverage' in results_df.columns:
        high_coverage = results_df[results_df['coverage'] > 0.1].sort_values('coverage', ascending=False)
        
        for idx, row in high_coverage.iterrows():
            fpd_iv = row.get('fpd_k30_iv', 0) if 'fpd_k30_iv' in row else 0
            print(f"{row['feature']:<50} 覆盖率={row['coverage']:.2%} FPD_IV={fpd_iv:.4f}")
    
    print(f"\n{'='*80}")


def main():
    args = parse_args()
    
    # 加载数据
    df = load_data(args.table, args.host, args.port, args.user, args.password, args.limit)
    
    # 分析特征
    results_df = analyze_features(df, args.stage, args.bins)
    
    # 生成报告
    generate_report(results_df, args.stage)
    
    # 保存详细结果
    output_file = f'app_feature_analysis_{args.stage}.csv'
    results_df.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"\n详细分析结果已保存: {output_file}")


if __name__ == '__main__':
    main()
