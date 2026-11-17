# -*- coding: utf-8 -*-
"""
示例配置：复制此文件改 CONFIG 即可复用生成器。
运行：python gen_feature_join.py example_config.py

字段说明见行内注释。最小必填：dict_path / targets[*].sample_table /
feat_table / join_keys / sample_cols / out。filters 与 column_file 可选。
"""

CONFIG = {
    # 特征字典：制表符分隔、第一列为特征名（按需改 dict_sep / dict_name_col）
    "dict_path": r"d:\my_claude\反欺诈\数据字典\反欺诈数据字典",
    "out_dir": r"d:\my_claude\反欺诈\样本特征关联",
    "dialect": "starrocks",      # 仅用于注释标注
    "agg": "max",                # 去重聚合函数：max / min / sum ...
    "dump_feature_list": "命中特征清单.txt",  # 不需要可删

    # ---- 可选筛选；整个 filters 删掉 = 取字典全量特征 ----
    "filters": {
        "window_max_days": 30,   # 只留时间窗 ≤30 天；None=不按窗口过滤
        "keep_hours": True,      # 保留小时级窗口(1h/4h/12h...)
        # 命中任一正则才保留（异常行为白名单）；空列表/不填 = 不按正则过滤
        "include_regex": [
            r"screenshot", r"screenrecord", r"contract_view", r"is_paste_",
            r"reset_phonenum", r"modify_phone", r"bind_card", r"cancel_acct",
            r"^bs_", r"openid", r"location_diff", r"geohash\d_cnt",
            r"anti_fraud_call", r"foreign_call", r"^serv_", r"complain_",
            r"^fqz_r_", r"fqz_l2_(modtool|clone|remote|vpn)_",
        ],
        # 无时间窗后缀但要保留的标志位
        "nowindow_keep_regex": [
            r"is_paste_", r"nickname_with_", r"if_foreign_", r"^mobile_has_",
        ],
        "exclude_regex": [],     # 命中则剔除（黑名单），可空
    },

    # ---- 目标：可配多个（贷前/贷中…），每个生成一份 SQL ----
    "targets": [
        {
            "name": "贷前",
            "sample_table": "d_dq.dfs_dq_fqz_base_final",
            "feat_table": "dwh.gdm_risk_vars_dipa_task_wide_pcr_df",
            # 关联键：[(样本列, 特征列), ...]，多对即联合键
            "join_keys": [("apply_no", "org_flow_no")],
            "sample_cols": [     # 保留的样本全字段（进 group by）
                "cust_no", "apply_no", "apply_result", "close_datetime",
                "cust_group_dq", "fpd_k30", "if_out_30d", "if_out_60d",
                "if_in_30d", "if_in_60d", "f001_decision",
            ],
            "sample_where": "",  # 样本侧过滤，如 "dt='${dt}'"，可空
            # 可选：真实表列清单文件(每行一列名)，与之取交集防 unknown column
            "column_file": None,
            "out": "关联聚合_贷前_pcr.sql",
        },
        {
            "name": "贷中",
            "sample_table": "d_dq.dfs_dz_fqz_base_fianl",
            "feat_table": "dwh.gdm_risk_vars_dipa_task_wide_rms_df",
            "join_keys": [("rsk_log_id", "req_flow_no")],
            "sample_cols": [
                "cust_no", "trans_seqno", "order_no", "rsk_log_id",
                "risk_decision_result", "create_datetime", "cust_group_dz",
                "new_old", "fpd_k30", "if_out_30d", "if_out_60d",
                "if_in_30d", "if_in_60d",
            ],
            "sample_where": "",
            "column_file": None,
            "out": "关联聚合_贷中_rms.sql",
        },
    ],
}
