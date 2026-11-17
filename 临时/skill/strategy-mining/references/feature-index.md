# Feature Index - 反欺诈特征字典

本文档整理了反欺诈常用的线上特征，按数据源分类。

## 目录

1. [通讯录特征 (txl_*)](#通讯录特征)
2. [通话记录特征 (call_record_*)](#通话记录特征)
3. [APPLIST特征 (f_dq_app_*, fqz_q_*)](#applist特征)
4. [设备特征 (t_bs_device_*, rt_rt_device_*)](#设备特征)
5. [原始表字段](#原始表字段)

---

## 通讯录特征

**数据源**: 通讯录 (t_bd_cust_relation_info)  
**特征前缀**: 	xl_*  
**所在宽表**: dwh.gdm_risk_vars_dipa_task_wide_pcr_df (贷前), dwh.gdm_risk_vars_dipa_task_wide_rms_df (贷中)

### 关联统计类

| 字段名 | 字段含义 | 数据类型 |
|--------|----------|----------|
| txl_relation_apply_n_cust_num | 通讯录关联的N度申请客户数 | INT |
| txl_relation_cust_cnt | 通讯录关联客户总数 | INT |
| txl_relation_apply_n_cust_pct | 通讯录关联申请客户占比 | DECIMAL |
| txl_black_mobile_cnt | 通讯录黑名单手机号数 | INT |
| txl_overdue_mobile_cnt | 通讯录逾期手机号数 | INT |
| txl_complaint_mobile_cnt | 通讯录投诉手机号数 | INT |

### 行为特征类

| 字段名 | 字段含义 | 数据类型 |
|--------|----------|----------|
| txl_history_overdue_days_pct | 通讯录历史逾期天数占比 | DECIMAL |
| txl_avg_relation_age | 通讯录联系人平均注册时长 | INT |
| txl_relation_concentration | 通讯录关联集中度 | DECIMAL |

### 时间窗口类

| 字段名 | 字段含义 | 数据类型 |
|--------|----------|----------|
| txl_recent_7d_cnt | 近7天新增联系人数 | INT |
| txl_recent_30d_cnt | 近30天新增联系人数 | INT |
| txl_recent_90d_cnt | 近90天新增联系人数 | INT |

---

## 通话记录特征

**数据源**: 通话记录 (t_bd_local_calls_records)  
**特征前缀**: call_record_*  
**所在宽表**: dwh.gdm_risk_vars_dipa_task_wide_pcr_df (贷前), dwh.gdm_risk_vars_dipa_task_wide_rms_df (贷中)

### 通话统计类

| 字段名 | 字段含义 | 数据类型 |
|--------|----------|----------|
| call_record_total_cnt | 总通话次数 | INT |
| call_record_total_duration | 总通话时长(秒) | INT |
| call_record_avg_duration | 平均通话时长(秒) | DECIMAL |
| call_record_unique_contact_cnt | 通话联系人数 | INT |

### 风险关联类

| 字段名 | 字段含义 | 数据类型 |
|--------|----------|----------|
| call_record_relation_apply_n_cust_num | 通话关联N度申请客户数 | INT |
| call_record_relation_cust_cnt | 通话关联客户总数 | INT |
| call_record_relation_apply_n_cust_pct | 通话关联申请客户占比 | DECIMAL |
| call_record_black_mobile_cnt | 通话黑名单手机号数 | INT |
| call_record_overdue_mobile_cnt | 通话逾期手机号数 | INT |

### 时间分布类

| 字段名 | 字段含义 | 数据类型 |
|--------|----------|----------|
| call_record_night_cnt | 夜间通话次数(22:00-06:00) | INT |
| call_record_weekend_cnt | 周末通话次数 | INT |
| call_record_recent_7d_cnt | 近7天通话次数 | INT |
| call_record_recent_30d_cnt | 近30天通话次数 | INT |

---

## APPLIST特征

**数据源**: APPLIST (t_bd_credit_cust_app_info)  
**特征前缀**: _dq_app_*, qz_q_*  
**所在宽表**: dwh.gdm_risk_vars_dipa_task_wide_pcr_df (贷前), dwh.gdm_risk_vars_dipa_task_wide_rms_df (贷中)

### 应用统计类

| 字段名 | 字段含义 | 数据类型 |
|--------|----------|----------|
| f_dq_app_total_cnt | 应用总数 | INT |
| f_dq_app_finance_cnt | 金融类应用数 | INT |
| f_dq_app_loan_cnt | 贷款类应用数 | INT |
| f_dq_app_gambling_cnt | 赌博类应用数 | INT |
| f_dq_app_game_cnt | 游戏类应用数 | INT |
| f_dq_app_social_cnt | 社交类应用数 | INT |

### 风险标签类

| 字段名 | 字段含义 | 数据类型 |
|--------|----------|----------|
| fqz_q_black_app_cnt | 黑名单应用数 | INT |
| fqz_q_high_risk_app_cnt | 高风险应用数 | INT |
| fqz_q_new_app_cnt | 新安装应用数(近30天) | INT |
| fqz_q_uninstall_cnt | 卸载应用数 | INT |

### 时间窗口类

| 字段名 | 字段含义 | 数据类型 |
|--------|----------|----------|
| f_dq_app_recent_7d_cnt | 近7天新增应用数 | INT |
| f_dq_app_recent_30d_cnt | 近30天新增应用数 | INT |
| f_dq_app_recent_90d_cnt | 近90天新增应用数 | INT |

---

## 设备特征

**数据源**: 设备指纹 (SMY/TD/BS三源)  
**特征前缀**: 	_bs_device_*, 
t_rt_device_*  
**所在宽表**: dwh.gdm_risk_vars_dipa_task_wide_pcr_df (贷前), dwh.gdm_risk_vars_dipa_task_wide_rms_df (贷中)

### 设备关联类

| 字段名 | 字段含义 | 数据类型 |
|--------|----------|----------|
| t_bs_device_cust_cnt | 设备关联客户数 | INT |
| t_bs_device_apply_cnt | 设备关联申请数 | INT |
| t_bs_device_unique_device_cnt | 唯一设备数 | INT |
| rt_rt_device_2degree_cust_cnt | 设备2度关联客户数 | INT |

### 风险标签类

| 字段名 | 字段含义 | 数据类型 |
|--------|----------|----------|
| t_bs_device_root_flag | 设备是否Root | INT |
| t_bs_device_emulator_flag | 设备是否模拟器 | INT |
| t_bs_device_vpn_flag | 设备是否使用VPN | INT |
| t_bs_device_risk_score | 设备风险评分 | DECIMAL |

### 时间窗口类

| 字段名 | 字段含义 | 数据类型 |
|--------|----------|----------|
| t_bs_device_recent_7d_apply_cnt | 近7天设备申请数 | INT |
| t_bs_device_recent_30d_apply_cnt | 近30天设备申请数 | INT |
| t_bs_device_recent_90d_apply_cnt | 近90天设备申请数 | INT |

---

## 原始表字段

### APPLIST表 (t_bd_credit_cust_app_info)

| 字段名 | 字段含义 | 数据类型 |
|--------|----------|----------|
| apply_no | 申请单号 | STRING |
| cust_no | 客户编号 | STRING |
| app_package | 应用包名 | STRING |
| app_name | 应用名称 | STRING |
| install_time | 安装时间 | DATETIME |
| is_system_app | 是否系统应用 | INT |

### 通话记录表 (t_bd_local_calls_records)

| 字段名 | 字段含义 | 数据类型 |
|--------|----------|----------|
| apply_no | 申请单号 | STRING |
| cust_no | 客户编号 | STRING |
| call_number | 通话号码 | STRING |
| call_type | 通话类型(in/out) | STRING |
| call_duration | 通话时长(秒) | INT |
| call_time | 通话时间 | DATETIME |

### 通讯录表 (t_bd_cust_relation_info)

| 字段名 | 字段含义 | 数据类型 |
|--------|----------|----------|
| apply_no | 申请单号 | STRING |
| cust_no | 客户编号 | STRING |
| contact_name | 联系人姓名 | STRING |
| contact_phone | 联系人电话 | STRING |
| relation_type | 关系类型 | STRING |
| add_time | 添加时间 | DATETIME |

### 紧急联系人表 (t_cif_cst_cust_immediate_relation_info)

| 字段名 | 字段含义 | 数据类型 |
|--------|----------|----------|
| cust_no | 客户编号 | STRING |
| relation_name | 联系人姓名 | STRING |
| relation_phone | 联系人电话 | STRING |
| relation_type | 关系类型 | STRING |
| id_card | 身份证号 | STRING |

### 设备表 (SMY/TD/BS)

**SMY表**: smy_pc.uld_dwd.dwd_risk_rms_rsk_device_log_di  
**TD表**: smy_pc_tmp.uld_dwd.dwd_risk_rms_rt_device_log_di  
**BS表**: smy_pc_tmp.uld_dwd.dwd_risk_afp_bang_sheng_fingerprint_di

| 字段名 | 字段含义 | 数据类型 |
|--------|----------|----------|
| apply_no | 申请单号 | STRING |
| cust_no | 客户编号 | STRING |
| device_id | 设备ID | STRING |
| device_type | 设备类型 | STRING |
| device_brand | 设备品牌 | STRING |
| device_model | 设备型号 | STRING |
| os_version | 操作系统版本 | STRING |
| ip_address | IP地址 | STRING |
| create_time | 创建时间 | DATETIME |

**BS特有字段**:
- cross_device_id: 跨端设备ID（可关联多设备）

---

## 表关联关系与数据流

### 核心原则：防止数据穿越
在进行特征衍生时，样本表与其他原始业务表（如APPLIST、通讯录、通话记录等）关联**必须严格使用 cust_no + 时间字段 进行约束**。
- **约束条件**：业务表的时间字段必须 **早于** 样本表的时间字段（如贷前的 close_datetime，贷中的 create_datetime）。
- **目的**：防止数据穿越（Data Leakage），确保模型训练和策略回测时只使用申请/交易发生前的历史数据。

### 贷前数据流 (Pre-loan)

**样本表**: d_dq.dfs_dq_fqz_base_final
- **主键**: cust_no, pply_no
- **时间约束字段**: close_datetime

| 关联目标 | 关联表名 | 关联条件 | 场景说明 |
|----------|----------|----------|----------|
| **特征宽表** | dwh.gdm_risk_vars_dipa_task_wide_pcr_df | pply_no = 
eq_flow_no | 获取贷前PCR特征 |
| **策略子表** | 贷前策略决策表 | pply_no = org_flow_no | 获取贷前策略执行结果 |
| **原始业务表** | APPLIST/通讯录/通话记录等 | cust_no = cust_no **AND** 业务时间 < close_datetime | 特征衍生（防穿越） |

### 贷中数据流 (In-loan)

**样本表**: d_dq.dfs_dz_fqz_base_final
- **主键**: cust_no, 	rans_seqno, order_no, 
sk_log_id
- **时间约束字段**: create_datetime

**主键语义与使用场景区分**:
- **	rans_seqno (交易流水号)**: 客户发起交易时即生成（无论交易最终是否成功）。**核心用途**：分析贷中**通过率**、拦截率。
- **order_no (订单编号)**: 只有交易审批通过后才生成。**核心用途**：分析贷中**风险表现**（如逾期、FPD）。
- **
sk_log_id (风控日志ID)**: 风控系统生成的唯一标识。**核心用途**：关联风控决策数据和特征宽表。

| 关联目标 | 关联表名 | 关联条件 | 场景说明 |
|----------|----------|----------|----------|
| **特征宽表** | dwh.gdm_risk_vars_dipa_task_wide_rms_df | 
sk_log_id = 
eq_flow_no | 获取贷中RMS特征 |
| **策略子表** | 贷中策略决策表 | 
sk_log_id = org_flow_no | 获取贷中策略执行结果 |
| **原始业务表** | APPLIST/通讯录/通话记录等 | cust_no = cust_no **AND** 业务时间 < create_datetime | 特征衍生（防穿越） |

### 典型 SQL 模板

#### 1. 贷前样本关联宽表
`sql
SELECT 
    base.apply_no,
    base.cust_no,
    base.close_datetime,
    base.fpd_k30,
    wide.*  -- PCR特征
FROM d_dq.dfs_dq_fqz_base_final base
LEFT JOIN dwh.gdm_risk_vars_dipa_task_wide_pcr_df wide 
    ON base.apply_no = wide.req_flow_no  -- 注意：关联键是 req_flow_no
    AND wide.partition_date = '2026-07-06'
`

#### 2. 贷中样本关联宽表
`sql
SELECT 
    base.trans_seqno,
    base.order_no,
    base.rsk_log_id,
    base.cust_no,
    base.risk_decision_result,
    wide.*  -- RMS特征
FROM d_dq.dfs_dz_fqz_base_final base
LEFT JOIN dwh.gdm_risk_vars_dipa_task_wide_rms_df wide 
    ON base.rsk_log_id = wide.req_flow_no  -- 注意：关联键是 req_flow_no
    AND wide.partition_date = '2026-07-06'
`

#### 3. 特征衍生（严格防穿越示例）
`sql
-- 衍生：申请前30天内的通讯录新增联系人数量
SELECT 
    base.apply_no,
    base.cust_no,
    COUNT(DISTINCT rel.relation_mobile_no) AS txl_new_contact_cnt_30d
FROM d_dq.dfs_dq_fqz_base_final base
LEFT JOIN t_bd_cust_relation_info rel 
    ON base.cust_no = rel.cust_no
    -- 核心：时间约束，严格防止数据穿越
    AND rel.create_datetime < base.close_datetime
    AND rel.create_datetime >= DATE_SUB(base.close_datetime, INTERVAL 30 DAY)
GROUP BY base.apply_no, base.cust_no
`

---\n\n## 使用指南

### 查找特征

1. 根据数据源类型定位到对应章节
2. 根据特征含义查找具体字段名
3. 确认特征所在宽表

### 衍生特征

如果线上特征不满足需求，可从原始表衍生：

1. 确定原始表和数据源
2. 根据分析目标设计衍生逻辑
3. 使用SQL从原始表计算特征

### 样本拼接

`sql
-- 贷前样本
SELECT 
    base.apply_no,
    base.cust_no,
    base.fpd_k30,  -- 目标标签
    wide.*         -- 特征字段
FROM d_dq.dfs_dq_fqz_base_final base
LEFT JOIN dwh.gdm_risk_vars_dipa_task_wide_pcr_df wide 
    ON base.apply_no = wide.apply_no

-- 贷中样本
SELECT 
    base.order_no,
    base.cust_no,
    base.fpd_k30,
    wide.*
FROM d_dq.dfs_dz_fqz_base_final base
LEFT JOIN dwh.gdm_risk_vars_dipa_task_wide_rms_df wide 
    ON base.order_no = wide.order_no
`

---

## 设备表字段 (Device Tables)

### SMY设备日志 (smy_pc.uld_dwd.dwd_risk_rms_rsk_device_log_di)

**关联键**: `rsk_log_id` (风控日志ID), `cust_no`, `device_unique_id`  
**时间字段**: `create_datetime`, `dt` (分区)  
**用途**: SMY渠道设备指纹采集

| 字段名 | 字段含义 | 数据类型 |
|--------|----------|----------|
| device_unique_id | 设备唯一标识 | STRING |
| imei | 设备IMEI | STRING |
| device_id | 设备ID | STRING |
| brand | 设备品牌 | STRING |
| phone_model | 手机型号 | STRING |
| operation_sys | 操作系统 | STRING |
| event_type | 事件类型 (activate/login等) | STRING |
| is_emulator | 是否模拟器 | STRING |
| smart_id | 智能设备ID | STRING |
| tags | 设备标签 | STRING |
| cust_no | 客户编号 | STRING |
| rsk_log_id | 风控日志ID | STRING |
| create_datetime | 创建时间 | TIMESTAMP |
| dt | 日期分区 | STRING |

### TD设备日志 (smy_pc.uld_dwd.dwd_risk_rms_rt_device_log_di)

**关联键**: `rsk_log_id`, `device_id`, `udid`  
**时间字段**: `create_time`, `dt` (分区)  
**用途**: TD渠道设备指纹采集

| 字段名 | 字段含义 | 数据类型 |
|--------|----------|----------|
| device_id | 设备ID | STRING |
| udid | 唯一设备标识 | STRING |
| idfv | iOS设备标识 | STRING |
| is_root | 是否Root | STRING |
| jail_break | 是否越狱 | STRING |
| platform | 平台类型 | STRING |
| os | 操作系统 | STRING |
| os_version | 操作系统版本 | STRING |
| wifi_mac | WiFi MAC地址 | STRING |
| blue_mac | 蓝牙MAC地址 | STRING |
| carrier | 运营商 | STRING |
| network_type | 网络类型 | STRING |
| cust_no | 客户编号 | STRING |
| rsk_log_id | 风控日志ID | STRING |
| create_time | 创建时间 | TIMESTAMP |
| dt | 日期分区 | STRING |

### 邦盛设备指纹 (smy_pc.uld_dwd.dwd_risk_afp_bang_sheng_fingerprint_di)

**关联键**: `cust_no`, `bang_sheng_dfp`, `bang_sheng_dfp_uuid`  
**时间字段**: `event_time`, `dt` (分区)  
**用途**: 邦盛反欺诈设备指纹

| 字段名 | 字段含义 | 数据类型 |
|--------|----------|----------|
| bang_sheng_dfp | 邦盛设备指纹 | STRING |
| bang_sheng_dfp_uuid | 邦盛设备UUID | STRING |
| bang_sheng_out_code | 邦盛输出码 | STRING |
| brand | 设备品牌 | STRING |
| device_name | 设备名称 | STRING |
| platform | 平台 | STRING |
| is_rooted | 是否Root | STRING |
| is_vm | 是否虚拟机 | STRING |
| scene | 采集场景 | STRING |
| terminal_type | 终端类型 | STRING |
| cust_no | 客户编号 | STRING |
| event_time | 事件时间 | TIMESTAMP |
| dt | 日期分区 | STRING |

---

## 策略子表字段 (Strategy Sub-tables)

### 贷前F001策略日志 (fico_test.prd_t_res_rule_log_pcr_f001)

**关联键**: `apply_no` = `org_flow_no`  
**时间字段**: `create_datetime`, `dt` (分区)  
**用途**: 贷前F001策略决策日志

| 字段名 | 字段含义 | 数据类型 |
|--------|----------|----------|
| apply_no | 申请编号 | STRING |
| fico_apply_no | FICO申请编号 | STRING |
| org_flow_no | 原始流程号 | STRING |
| cust_no | 客户编号 | STRING |
| mobile_no | 手机号 | STRING |
| t_mobile_no | 备用手机号 | STRING |
| success | 是否成功 | STRING |
| apply_result | 申请结果 | STRING |
| decision | 决策结果 | STRING |
| policy_code | 命中策略码 | STRING |
| next_step_policy_code | 下一步策略码 | STRING |
| approve_result | 审批结果 | STRING |
| reject_reason | 拒绝原因 | STRING |
| create_datetime | 创建时间 | TIMESTAMP |
| dt | 日期分区 | STRING |

### 贷中F001策略日志 (fico_test.prd_t_res_rule_log_rms_f001)

**关联键**: `rsk_log_id` = `org_flow_no`  
**时间字段**: `create_datetime`, `dt` (分区)  
**用途**: 贷中F001策略决策日志

| 字段名 | 字段含义 | 数据类型 |
|--------|----------|----------|
| rsk_log_id | 风控日志ID | STRING |
| fico_apply_no | FICO申请编号 | STRING |
| org_flow_no | 原始流程号 | STRING |
| cust_no | 客户编号 | STRING |
| mobile_no | 手机号 | STRING |
| t_mobile_no | 备用手机号 | STRING |
| success | 是否成功 | STRING |
| decision | 决策结果 | STRING |
| policy_code | 命中策略码 | STRING |
| approve_result | 审批结果 | STRING |
| reject_reason | 拒绝原因 | STRING |
| create_datetime | 创建时间 | TIMESTAMP |
| dt | 日期分区 | STRING |

### 贷中F003策略日志 (fico_test.prd_t_res_rule_log_rms_f003)

**关联键**: `rsk_log_id` = `org_flow_no`  
**时间字段**: `create_datetime`, `dt` (分区)  
**用途**: 贷中F003策略决策日志

| 字段名 | 字段含义 | 数据类型 |
|--------|----------|----------|
| rsk_log_id | 风控日志ID | STRING |
| fico_apply_no | FICO申请编号 | STRING |
| org_flow_no | 原始流程号 | STRING |
| cust_no | 客户编号 | STRING |
| mobile_no | 手机号 | STRING |
| success | 是否成功 | STRING |
| decision | 决策结果 | STRING |
| dicision | 决策结果(备用) | STRING |
| policy_code | 命中策略码 | STRING |
| apply_type | 申请类型 | STRING |
| approve_day | 审批日期 | STRING |
| approve_month | 审批月份 | STRING |
| create_datetime | 创建时间 | TIMESTAMP |
| dt | 日期分区 | STRING |

### 贷中F005策略日志 (fico_test.prd_t_res_rule_log_rms_f005)

**关联键**: `rsk_log_id` = `org_flow_no`  
**时间字段**: `create_datetime`, `dt` (分区)  
**用途**: 贷中F005策略决策日志

| 字段名 | 字段含义 | 数据类型 |
|--------|----------|----------|
| rsk_log_id | 风控日志ID | STRING |
| fico_apply_no | FICO申请编号 | STRING |
| org_flow_no | 原始流程号 | STRING |
| cust_no | 客户编号 | STRING |
| mobile_no | 手机号 | STRING |
| t_mobile_no | 备用手机号 | STRING |
| success | 是否成功 | STRING |
| decision | 决策结果 | STRING |
| policy_code | 命中策略码 | STRING |
| scfpordersign | 订单签名 | STRING |
| call_record_black_mobile_cnt_1d | 通话黑名单数 | INT |
| create_datetime | 创建时间 | TIMESTAMP |
| dt | 日期分区 | STRING |

---

## 客户信息表字段 (Customer Info Tables)

### 客户基础信息 (v_cif_cst_cust_info)

**关联键**: `cust_no`  
**用途**: 客户基础信息视图

| 字段名 | 字段含义 | 数据类型 |
|--------|----------|----------|
| cust_no | 客户编号 | STRING |
| cust_name | 客户姓名 | STRING |
| id_no | 身份证号 | STRING |
| mobile_phone_no | 手机号 | STRING |
| fraud_code | 欺诈码 (201,202,211,212,222) | STRING |
| fraud_code_date | 欺诈码日期 | STRING |
| cust_status | 客户状态 | STRING |
| create_datetime | 创建时间 | TIMESTAMP |

### 客户身份证信息 (v_cif_cst_cust_id_info)

**关联键**: `cust_no`, `id_no`  
**用途**: 客户身份证信息视图

| 字段名 | 字段含义 | 数据类型 |
|--------|----------|----------|
| cust_no | 客户编号 | STRING |
| id_no | 身份证号 | STRING |
| id_type | 证件类型 | STRING |
| id_valid_date | 证件有效期 | STRING |
| id_issue_authority | 发证机关 | STRING |

### 注销客户信息 (v_cif_t_cancel_cust_info)

**关联键**: `cust_no`  
**用途**: 注销客户信息视图

| 字段名 | 字段含义 | 数据类型 |
|--------|----------|----------|
| cust_no | 客户编号 | STRING |
| cancel_date | 注销日期 | STRING |
| cancel_reason | 注销原因 | STRING |
| cancel_operator | 注销操作员 | STRING |

### 注销客户身份证信息 (v_cif_t_cancel_cust_id_info)

**关联键**: `cust_no`, `id_no`  
**用途**: 注销客户身份证信息视图

| 字段名 | 字段含义 | 数据类型 |
|--------|----------|----------|
| cust_no | 客户编号 | STRING |
| id_no | 身份证号 | STRING |
| cancel_date | 注销日期 | STRING |

---

## APPLIST标签表字段 (APPLIST Tag Table)

### APPLIST标签表 (d_dq.dfs_applist_tag_new)

**关联键**: `app_name`, `tag`  
**用途**: APPLIST应用标签

| 字段名 | 字段含义 | 数据类型 |
|--------|----------|----------|
| app_name | 应用名称 | STRING |
| tag | 标签 (如: 借贷, 赌博, 色情等) | STRING |
| tag_type | 标签类型 | STRING |
| create_time | 创建时间 | TIMESTAMP |

---

## 数据探查状态

已完成探查的反欺诈常用表 (20张):

### 样本表 (2张)
- `d_dq.dfs_dq_fqz_base_final` - 贷前样本表
- `d_dq.dfs_dz_fqz_base_final` - 贷中样本表

### 宽表 (2张)
- `dwh.gdm_risk_vars_dipa_task_wide_pcr_df` - 贷前特征宽表 (20081字段)
- `dwh.gdm_risk_vars_dipa_task_wide_rms_df` - 贷中特征宽表 (25887字段)

### 业务表 (5张)
- `t_bd_credit_cust_app_info` - 客户申请信息表
- `t_bd_cust_relation_info` - 通讯录关系表
- `t_bd_local_calls_records` - 本地通话记录表
- `t_cif_cst_cust_immediate_relation_info` - 紧急联系人表
- `d_dq.dfs_applist_tag_new` - APPLIST标签表

### 客户信息表 (4张)
- `v_cif_cst_cust_info` - 客户基础信息
- `v_cif_cst_cust_id_info` - 客户身份证信息
- `v_cif_t_cancel_cust_info` - 注销客户信息
- `v_cif_t_cancel_cust_id_info` - 注销客户身份证信息

### 策略子表 (4张) - 使用 dss_mx 账号
- `fico_test.prd_t_res_rule_log_pcr_f001` - 贷前F001策略日志 (517字段)
- `fico_test.prd_t_res_rule_log_rms_f001` - 贷中F001策略日志 (490字段)
- `fico_test.prd_t_res_rule_log_rms_f003` - 贷中F003策略日志 (285字段)
- `fico_test.prd_t_res_rule_log_rms_f005` - 贷中F005策略日志 (438字段)

### 设备表 (3张) - 使用 dss_mx + StarRocks
- `smy_pc.uld_dwd.dwd_risk_rms_rsk_device_log_di` - SMY设备日志 (61字段)
- `smy_pc.uld_dwd.dwd_risk_rms_rt_device_log_di` - TD设备日志 (58字段)
- `smy_pc.uld_dwd.dwd_risk_afp_bang_sheng_fingerprint_di` - 邦盛设备指纹 (31字段)

**详细schema文档位置**: `skill/table-explorer/output/`

---

