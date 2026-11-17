#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
批量探查反欺诈常用表（优化版）
"""

import sys
import subprocess
from pathlib import Path

# 反欺诈常用表列表
# 格式: (表名, 分区过滤条件, 是否跳过COUNT)
# 分区字段: 宽表使用 partition_date，设备表使用 dt
# 分区日期请手动更新为最新可用日期
PARTITION_DATE = "2026-07-06"

TABLES = [
    # 样本表（数据量较小，可以COUNT）
    ("d_dq.dfs_dq_fqz_base_final", None, False),      # 贷前样本表
    ("d_dq.dfs_dz_fqz_base_final", None, False),      # 贷中样本表
    
    # 宽表（数据量大，跳过COUNT，使用分区过滤）
    ("dwh.gdm_risk_vars_dipa_task_wide_pcr_df", f"partition_date='{PARTITION_DATE}'", True),  # 贷前宽表
    ("dwh.gdm_risk_vars_dipa_task_wide_rms_df", f"partition_date='{PARTITION_DATE}'", True),  # 贷中宽表
    
    # 原始数据表（数据量中等，跳过COUNT）
    ("t_bd_credit_cust_app_info", None, True),                        # APPLIST表
    ("t_bd_local_calls_records", None, True),                         # 通话记录表
    ("t_bd_cust_relation_info", None, True),                          # 通讯录表
    ("t_cif_cst_cust_immediate_relation_info", None, True),           # 紧急联系人表
    
    # 设备表（需要model_py账号权限，当前账号无权限）
    # ("smy_pc.uld_dwd.dwd_risk_rms_rsk_device_log_di", f"dt='{PARTITION_DATE}'", True),    # SMY设备表
    # ("smy_pc_tmp.uld_dwd.dwd_risk_rms_rt_device_log_di", f"dt='{PARTITION_DATE}'", True), # TD设备表
    # ("smy_pc_tmp.uld_dwd.dwd_risk_afp_bang_sheng_fingerprint_di", f"dt='{PARTITION_DATE}'", True),  # BS设备表
]

def main():
    script_path = Path(__file__).parent / "explore_table.py"
    
    print(f"[INFO] 开始批量探查 {len(TABLES)} 张表")
    print("=" * 60)
    
    success = []
    failed = []
    
    for idx, (table_name, partition_filter, no_count) in enumerate(TABLES, 1):
        print(f"\n[{idx}/{len(TABLES)}] 探查: {table_name}")
        if partition_filter:
            print(f"       分区过滤: {partition_filter}")
        print("-" * 60)
        
        try:
            # 构建命令参数
            cmd = [sys.executable, str(script_path), table_name]
            
            if no_count:
                cmd.append("--no-count")
            
            if partition_filter:
                cmd.extend(["--partition", partition_filter])
            
            result = subprocess.run(
                cmd,
                cwd=script_path.parent.parent,
                check=True,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            print(result.stdout)
            success.append(table_name)
            
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] 探查失败: {e}")
            print(e.stderr)
            failed.append((table_name, str(e)))
            
        except subprocess.TimeoutExpired:
            print(f"[ERROR] 探查超时: {table_name}")
            failed.append((table_name, "Timeout"))
    
    print("\n" + "=" * 60)
    print("[SUMMARY] 探查完成")
    print(f"成功: {len(success)} 张表")
    print(f"失败: {len(failed)} 张表")
    
    if failed:
        print("\n失败的表:")
        for table_name, error in failed:
            print(f"  - {table_name}: {error}")
    
    print(f"\n文档输出目录: {script_path.parent.parent / 'output'}")

if __name__ == '__main__':
    main()
