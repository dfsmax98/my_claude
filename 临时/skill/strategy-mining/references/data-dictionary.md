## 数据字典

### 设备表 (Device Tables)

#### 1. smy_pc.uld_dwd.dwd_risk_rms_rsk_device_log_di (SMY设备日志)
- **用途**: SMY渠道设备指纹采集日志
- **字段数**: 61
- **关联键**: `rsk_log_id` (风控日志ID), `cust_no`, `device_unique_id`
- **时间字段**: `create_datetime`, `dt` (分区)
- **关键字段**:
  - `device_unique_id`: 设备唯一标识
  - `imei`: 设备IMEI
  - `device_id`: 设备ID
  - `brand`: 设备品牌
  - `phone_model`: 手机型号
  - `operation_sys`: 操作系统
  - `event_type`: 事件类型 (activate/login等)
  - `is_emulator`: 是否模拟器
  - `smart_id`: 智能设备ID
  - `tags`: 设备标签

#### 2. smy_pc.uld_dwd.dwd_risk_rms_rt_device_log_di (TD设备日志)
- **用途**: TD渠道设备指纹采集日志
- **字段数**: 58
- **关联键**: `rsk_log_id`, `device_id`, `udid`
- **时间字段**: `create_time`, `dt` (分区)
- **关键字段**:
  - `device_id`: 设备ID
  - `udid`: 唯一设备标识
  - `idfv`: iOS设备标识
  - `is_root`: 是否Root
  - `jail_break`: 是否越狱
  - `platform`: 平台类型
  - `os` / `os_version`: 操作系统及版本
  - `wifi_mac` / `blue_mac`: 网络MAC地址
  - `carrier`: 运营商
  - `network_type`: 网络类型

#### 3. smy_pc.uld_dwd.dwd_risk_afp_bang_sheng_fingerprint_di (邦盛设备指纹)
- **用途**: 邦盛反欺诈设备指纹
- **字段数**: 31
- **关联键**: `cust_no`, `bang_sheng_dfp`, `bang_sheng_dfp_uuid`
- **时间字段**: `event_time`, `dt` (分区)
- **关键字段**:
  - `bang_sheng_dfp`: 邦盛设备指纹
  - `bang_sheng_dfp_uuid`: 邦盛设备UUID
  - `bang_sheng_out_code`: 邦盛输出码
  - `brand`: 设备品牌
  - `device_name`: 设备名称
  - `platform`: 平台
  - `is_rooted`: 是否Root
  - `is_vm`: 是否虚拟机
  - `scene`: 采集场景
  - `terminal_type`: 终端类型

### 策略子表 (Strategy Sub-tables)

#### 1. fico_test.prd_t_res_rule_log_pcr_f001 (贷前F001策略日志)
- **用途**: 贷前F001策略决策日志
- **字段数**: 517
- **关联键**: `apply_no` = `org_flow_no`
- **时间字段**: `create_datetime`, `dt` (分区)
- **关键字段**:
  - `apply_no` / `fico_apply_no`: 申请编号
  - `org_flow_no`: 原始流程号
  - `cust_no`, `mobile_no`, `t_mobile_no`: 客户标识
  - `success`: 是否成功
  - `apply_result`: 申请结果
  - `decision`: 决策结果
  - `policy_code`: 命中策略码
  - `next_step_policy_code`: 下一步策略码
  - `approve_result`: 审批结果
  - `reject_reason`: 拒绝原因

#### 2. fico_test.prd_t_res_rule_log_rms_f001 (贷中F001策略日志)
- **用途**: 贷中F001策略决策日志
- **字段数**: 490
- **关联键**: `rsk_log_id` = `org_flow_no`
- **时间字段**: `create_datetime`, `dt` (分区)
- **关键字段**:
  - `rsk_log_id` / `fico_apply_no`: 风控日志ID
  - `org_flow_no`: 原始流程号
  - `cust_no`, `mobile_no`, `t_mobile_no`: 客户标识
  - `success`: 是否成功
  - `decision`: 决策结果
  - `policy_code`: 命中策略码
  - `approve_result`: 审批结果
  - `reject_reason`: 拒绝原因

#### 3. fico_test.prd_t_res_rule_log_rms_f003 (贷中F003策略日志)
- **用途**: 贷中F003策略决策日志
- **字段数**: 285
- **关联键**: `rsk_log_id` = `org_flow_no`
- **时间字段**: `create_datetime`, `dt` (分区)
- **关键字段**:
  - `rsk_log_id` / `fico_apply_no`: 风控日志ID
  - `org_flow_no`: 原始流程号
  - `cust_no`, `mobile_no`: 客户标识
  - `success`: 是否成功
  - `decision` / `dicision`: 决策结果
  - `policy_code`: 命中策略码
  - `apply_type`: 申请类型
  - `approve_day` / `approve_month`: 审批日期

#### 4. fico_test.prd_t_res_rule_log_rms_f005 (贷中F005策略日志)
- **用途**: 贷中F005策略决策日志
- **字段数**: 438
- **关联键**: `rsk_log_id` = `org_flow_no`
- **时间字段**: `create_datetime`, `dt` (分区)
- **关键字段**:
  - `rsk_log_id` / `fico_apply_no`: 风控日志ID
  - `org_flow_no`: 原始流程号
  - `cust_no`, `mobile_no`, `t_mobile_no`: 客户标识
  - `success`: 是否成功
  - `decision`: 决策结果
  - `policy_code`: 命中策略码
  - `scfpordersign`: 订单签名
  - `call_record_black_mobile_cnt_1d`: 通话黑名单数

### 客户信息表 (Customer Info Tables)

#### 1. v_cif_cst_cust_info (客户基础信息)
- **用途**: 客户基础信息视图
- **字段数**: 56
- **关联键**: `cust_no`
- **关键字段**:
  - `cust_no`: 客户编号
  - `cust_name`: 客户姓名
  - `id_no`: 身份证号
  - `mobile_phone_no`: 手机号
  - `fraud_code`: 欺诈码 (201,202,211,212,222)
  - `fraud_code_date`: 欺诈码日期
  - `cust_status`: 客户状态
  - `create_datetime`: 创建时间

#### 2. v_cif_cst_cust_id_info (客户身份证信息)
- **用途**: 客户身份证信息视图
- **字段数**: 25
- **关联键**: `cust_no`, `id_no`
- **关键字段**:
  - `cust_no`: 客户编号
  - `id_no`: 身份证号
  - `id_type`: 证件类型
  - `id_valid_date`: 证件有效期
  - `id_issue_authority`: 发证机关

#### 3. v_cif_t_cancel_cust_info (注销客户信息)
- **用途**: 注销客户信息视图
- **字段数**: 54
- **关联键**: `cust_no`
- **关键字段**:
  - `cust_no`: 客户编号
  - `cancel_date`: 注销日期
  - `cancel_reason`: 注销原因
  - `cancel_operator`: 注销操作员

#### 4. v_cif_t_cancel_cust_id_info (注销客户身份证信息)
- **用途**: 注销客户身份证信息视图
- **字段数**: 29
- **关联键**: `cust_no`, `id_no`
- **关键字段**:
  - `cust_no`: 客户编号
  - `id_no`: 身份证号
  - `cancel_date`: 注销日期

### APPLIST标签表

#### d_dq.dfs_applist_tag_new (APPLIST标签表)
- **用途**: APPLIST应用标签
- **字段数**: 8
- **关联键**: `app_name`, `tag`
- **关键字段**:
  - `app_name`: 应用名称
  - `tag`: 标签 (如: 借贷, 赌博, 色情等)
  - `tag_type`: 标签类型
  - `create_time`: 创建时间

---

### Additional Resources
- **references/feature-index.md** > 表关联关系与数据流: Join key rules, anti-leakage principles, and data flow diagrams
- **references/feature-index.md** > 特征字典: 1800+ features organized by data source
- **skill/table-explorer/output/**: Auto-generated schema docs for all 20 explored tables
- **数据字典章节 (above)**: Device tables, strategy sub-tables, customer info tables field reference
