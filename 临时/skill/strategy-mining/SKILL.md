---
name: strategy-mining
description: 配置驱动的反欺诈特征衍生技能。基于 YAML 配置自动生成防穿越的特征 SQL(单源聚合 + 复合特征合并层)并可建数仓表。适用于将样本表与 APP/通讯录/设备等数据源关联、批量衍生反欺诈特征的场景。
---

# strategy-mining Skill

特征衍生策略挖掘技能，支持配置驱动的反欺诈特征自动生成。

## 📁 目录结构

`
strategy-mining/
├── configs/                    # 特征配置文件
│   ├── feature_template.yaml   # 通用配置模板
│   ├── contact_risk_schema_based.yaml  # 通讯录特征配置
│   └── ...                     # 其他场景配置
├── scripts/                    # 执行脚本
│   ├── generate_feature_sql.py # SQL生成器（核心）
│   └── execute_feature_pipeline.py # 执行器
├── lib/                        # 依赖库
│   └── db_connector.py         # 数据库连接模块
├── assets/                     # 输出产物
│   ├── *_features_preloan.sql  # 贷前特征SQL
│   ├── *_features_inloan.sql   # 贷中特征SQL
│   └── *_dictionary.csv        # 特征字典
└── SKILL.md                    # 本文档
`

## 🚀 快速开始

`ash
# 1. 准备配置（复制模板修改）
copy configs\feature_template.yaml configs\my_features.yaml

# 2. 生成SQL+字典（默认拆分 labeled/recent7d 两套样本）
python scripts\generate_feature_sql.py --config configs\my_features.yaml --output assets\ --single-source

# 3. 执行建表（需按项目SQL安全规范取得CREATE TABLE授权）
python scripts\execute_feature_pipeline.py --config configs\my_features.yaml --sql-dir assets\
`

---

## 🔄 样本拆分模式（2026-07-20）

为减少全量贷前/贷中样本衍生耗时，SQL生成器默认在 `preloan` / `inloan` 之外再拆分两类样本用途：

| 模式 | 过滤条件 | 用途 | 输出表后缀 |
|------|----------|------|------------|
| `labeled` | `s.fpd_k30 >= 0` | 特征效果评估（IV/Lift/PSI、策略挖掘） | `{output_table}_{stage}_labeled_{source}` |
| `recent7d` | `s.{time_field} >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)` | 近7天通过率/命中率影响评估 | `{output_table}_{stage}_recent7d_{source}` |
| `full` | 仅时间字段非空 | 兼容旧全量衍生流程 | `{output_table}_{stage}_{source}` |

### 生成示例

`powershell
python skill\strategy-mining\scripts\generate_feature_sql.py `
  --config skill\strategy-mining\configs\contact_risk_schema_based.yaml `
  --output _temp\feature_sql_mode_check `
  --stages preloan inloan `
  --modes labeled recent7d `
  --single-source
`

### 约束
- `labeled` 模式必须保留 `fpd_k30 >= 0`，只用于有Y标签样本的效果评估。
- `recent7d` 模式不得追加 `fpd_k30 >= 0`，用于全量近7天通过率影响验证。
- 生成SQL使用 `CREATE TABLE IF NOT EXISTS ... AS SELECT`，不生成 `DROP TABLE`；执行建表前仍需用户按项目SQL安全规范授权。

---

## ⚠️ 【重要】聚合字段配置规范（不可修改）

> **此部分为特征衍生核心逻辑，修改可能导致SQL执行失败或数据错误**

### 1. sample_table.target_fields 配置规则

`yaml
sample_table:
  target_fields:
    preloan: [apply_result, cust_group_dq, fpd_k30, if_out_30d, if_out_60d, if_in_30d, if_in_60d, f001_decision]
    inloan: [risk_decision_result, cust_group_dz, new_old, fpd_k30, if_out_30d, if_out_60d, if_in_30d, if_in_60d]
`

**规则说明**:
- 	arget_fields 必须按 preloan/inloan 分阶段配置（dict格式）
- 这些字段会**自动加入GROUP BY和SELECT**，确保聚合查询合法
- **禁止修改字段名**，必须与样本表实际字段一致
- **禁止删除字段**，否则复合特征计算会失败

| 阶段 | 必填字段 | 来源表 | 用途 |
|------|---------|--------|------|
| preloan | pply_result, cust_group_dq, f001_decision | d_dq.dfs_dq_fqz_base_final | 审批结果/客群/策略决策 |
| preloan | pd_k30, if_out_30d, if_out_60d, if_in_30d, if_in_60d | 同上 | 标签变量(IV/WOE分析) |
| inloan | isk_decision_result, cust_group_dz, new_old | d_dq.dfs_dz_fqz_base_final | 贷中决策/客群/新老客 |
| inloan | pd_k30, if_out_30d, if_out_60d, if_in_30d, if_in_60d | 同上 | 标签变量(IV/WOE分析) |

### 2. sample_table.primary_keys 配置规则

`yaml
sample_table:
  primary_keys:
    preloan: [cust_no, apply_no]
    inloan: [cust_no, order_no, trans_seqno, rsk_log_id]
`

**规则说明**:
- 主键字段**必须全部加入GROUP BY**
- 贷前: 2个主键 (cust_no, apply_no)
- 贷中: 4个主键 (cust_no, order_no, trans_seqno, rsk_log_id)
- **禁止增删主键字段**，否则会导致数据重复或丢失

### 3. 双层查询结构（自动生成，禁止手动修改）

生成的SQL采用双层结构确保GROUP BY合法：

`sql
CREATE TABLE ... AS (
    -- 外层: 复合特征计算
    SELECT 
        cust_no, apply_no, close_datetime,  -- 主键+时间
        apply_result, fpd_k30, ...,          -- target_fields
        contact_total_cnt, ...,              -- 聚合特征
        CASE WHEN ... END AS contact_ratio   -- 复合特征
    FROM (
        -- 内层: 聚合查询
        SELECT 
            s.cust_no, s.apply_no, s.close_datetime,  -- ✅ 主键+时间
            s.apply_result, s.fpd_k30, ...,           -- ✅ target_fields
            COUNT(...) AS contact_total_cnt, ...      -- ✅ 聚合特征
        FROM sample_table s
        LEFT JOIN ...
        GROUP BY s.cust_no, s.apply_no, s.close_datetime,  -- ✅ 完整GROUP BY
                 s.apply_result, s.fpd_k30, ...
    ) agg
);
`

**禁止事项**:
- ❌ 不要手动编辑生成的 *_features_*.sql 文件
- ❌ 不要修改 generate_feature_sql.py 的GROUP BY逻辑
- ❌ 不要在配置中使用未定义的字段名

### 4. 字段来源校验

所有特征字段必须来自 	able-explorer/output/ 中的真实schema:

`ash
# 校验通讯录表字段
type skill\table-explorer\output\t_bd_cust_relation_info.md
type skill\table-explorer\output\t_cif_cst_cust_immediate_relation_info.md
`

**确认字段存在后再配置**:
- ✅ elation_mobile_no (非 contact_phone)
- ✅ create_datetime (非 create_time)
- ✅ check_status, urgent_contact_flag (紧急联系人表特有)

---

## 🔧 配置参数说明

### 基础配置

| 参数 | 说明 | 示例 |
|------|------|------|
| eature_group | 特征组标识(用于文件命名) | contact_risk |
| stage | 当前生成阶段 | preloan / inloan |
| output_table | 目标表名基础 | d_dq.dfs_contact_risk |

### 数据源配置

`yaml
data_sources:
  - name: contacts                    # 数据源标识(特征引用用)
    table: default.t_bd_cust_relation_info  # 实际表名
    join_field: cust_no               # 与样本表关联字段
    time_field: create_datetime       # 防穿越时间字段
    partition_field: dt               # 分区字段(自动裁剪)
    select_fields: [cust_no, relation_mobile_no, ...]  # SELECT字段(必须真实存在)
    filters:                          # 预过滤条件
      - relation_mobile_no IS NOT NULL
`

### 特征定义

**聚合特征**:
`yaml
- name: contact_total_cnt
  desc: 通讯录联系人总数
  source: contacts           # 对应data_sources的name
  agg: COUNT_DISTINCT        # 聚合函数
  field: relation_mobile_no  # 聚合字段
  condition: LENGTH(field)=11  # 可选过滤条件
  window: 365d               # 时间窗口(自动注入防穿越)
`

**复合特征**:
`yaml
- name: contact_valid_ratio
  desc: 有效手机号占比
  type: composite            # 标记为复合特征
  logic: CASE WHEN contact_total_cnt > 0 THEN CAST(contact_valid_phone_cnt AS DECIMAL(10,4)) / contact_total_cnt ELSE 0 END
`

> ⚠️ 复合特征的 logic 中只能引用**已定义的聚合特征名**，不能直接引用原始字段

---

## 🧪 验证与测试

`sql
-- 1. 行数验证
SELECT COUNT(*) FROM d_dq.dfs_contact_risk_schema_based_preloan;

-- 2. 字段完整性验证
SELECT cust_no, apply_no, apply_result, fpd_k30, 
       contact_total_cnt, contact_comprehensive_flag
FROM d_dq.dfs_contact_risk_schema_based_preloan
LIMIT 5;

-- 3. 标签分布验证(IV分析前置)
SELECT apply_result, COUNT(*) as cnt, AVG(fpd_k30) as fpd_rate
FROM d_dq.dfs_contact_risk_schema_based_preloan
GROUP BY apply_result;
`

---

## 🔄 扩展新场景

1. 复制 configs/feature_template.yaml 为新文件
2. 修改 eature_group, output_table
3. 配置 data_sources (参考table-explorer输出)
4. 定义 eatures (聚合+复合)
5. **确保 	arget_fields 按阶段正确配置** ⚠️
6. 运行生成器

`ash
python scripts\generate_feature_sql.py --config configs\new_scenario.yaml --output assets\
`

---

## 🆘 故障排查

| 错误 | 可能原因 | 解决方案 |
|------|---------|---------|
| Column 'xxx' cannot be resolved | 使用了不存在的字段 | 检查 	able-explorer/output/ 确认字段名 |
| Expression not in GROUP BY key | target_fields配置缺失 | 确保 sample_table.target_fields.{stage} 包含所有业务字段 |
| Duplicate column name | 特征名重复 | 检查 eatures[].name 唯一性 |
| Access denied | 数据库账号/密码错误 | 检查 lib/db_connector.py 账号配置 |

---

## 📞 维护联系人

- 技能维护: strategy-mining team
- 数据schema确认: table-explorer skill output目录
- 数据库权限: DBA团队

> **最后更新**: 2026-07-08  
> **版本**: v2.0 (支持双阶段+完整GROUP BY)

---

## 🤖 Agent 调用指引（Codex 专用）

> 此部分供 Codex Agent 内部调用参考，用户无感知

### 触发条件
当用户请求衍生新特征时，Agent 按以下流程执行：

1. **解析需求**：提取特征业务含义、适用场景(dq/dz)、时间窗口
2. **检查配置**：
   - 若 configs/{feature_group}.yaml 已存在 → 直接使用
   - 若不存在 → 复制 eature_template.yaml 并内部确认配置
3. **执行生成**：
   `python
   # Agent 内部执行（用户无感知）
   python scripts/generate_feature_sql.py --config configs/{feature_group}.yaml --output assets/
   `
4. **(可选) 执行建表**：若用户确认或配置 uto_execute: true
   `python
   python scripts/execute_feature_pipeline.py --config configs/{feature_group}.yaml
   `
5. **返回结果**：
   - 成功：返回 {"target_table": "d_dq.dfs.xxx", "dict_file": "assets/xxx.csv", "success": True}
   - 失败：返回 {"error": "原因", "suggestion": "修复建议"}

### 协作输出规范
生成完成后，Agent 自动建议用户下一步：
`
✅ 特征表 d_dq.dfs.xxx 已就绪
📄 特征字典: assets/xxx_dictionary.csv
🔗 是否需要执行策略分析评估效果？(回复"分析xxx"即可)
`

### 内部工具函数
`python
# 供 Agent 直接调用，不暴露给用户
def generate_features_for_agent(feature_group: str, stage: str, config_overrides: dict = None) -> dict:
    """Agent 内部: 执行特征衍生，返回结构化结果"""
    from scripts.generate_feature_sql import main as generate_sql
    from lib.db_connector import DBConnector
    
    # 1. 加载/生成配置
    config = load_or_create_config(feature_group, stage, config_overrides)
    
    # 2. 生成 SQL + 字典
    sql_path, dict_path = generate_sql(config)
    
    # 3. (可选) 执行建表
    if config.get('auto_execute'):
        exec_success = execute_pipeline(config)
    else:
        exec_success = None
    
    return {
        'success': True,
        'target_table': config['output_table'] + '_' + stage + '_' + get_date_suffix(),
        'sql_file': sql_path,
        'dict_file': dict_path,
        'executed': exec_success
    }
`

### 错误处理
| 错误类型 | Agent 应对策略 |
|----------|---------------|
| 字段不存在 | 调用 table-explorer 重新探查，建议用户确认字段名 |
| GROUP BY 失败 | 检查 sample_table.target_fields 配置，自动补全缺失字段 |
| 数据库连接失败 | fallback 到 dry-run 模式，仅生成 SQL 不执行建表 |
| 超时 | 建议用户缩小时间窗口或增加过滤条件 |


---

## 🔌 数据库连接 (Agent 统一入口)

> 所有数据库操作请通过 skill/lib/db_router.py 调用，**不要直接使用 pymysql/pyhive**

### Agent 调用规范

`python
from skill.lib.db_router import describe_table, query_table, db_session

# 方式 1: 探查表结构 (推荐)
result = describe_table('svl_uld_dq.dfs_dz_fqz_overdue_base')
if result['success']:
    columns = result['columns']      # 字段清单
    sample = result['sample']        # 样本数据
    engine = result['engine']        # 实际使用的引擎: 'hive'/'sr'

# 方式 2: 执行查询
df = query_table(
    sql='SELECT cust_no, fpd_k30 FROM table LIMIT 100',
    table_name='d_dq.dfs_xxx',
    as_df=True  # 返回 pandas DataFrame
)

# 方式 3: 上下文管理器 (复杂操作)
with db_session('my_table') as (conn, cursor, engine):
    cursor.execute('SELECT COUNT(*) FROM my_table')
    count = cursor.fetchone()
`

### 自动路由规则

| 表名前缀 | 优先引擎 | 故障转移 |
|----------|----------|----------|
| svl_uld_dq. / smy_pc. / lh. | StarRocks | 不转移 (强制 SR) |
| ico_test. | Hive | 失败→SR |
| d_dq. / dwh. / 其他 | auto | Hive→SR 依次尝试 |

### 账号配置 (硬编码 + 环境变量)

- HIVE / HIVE_ALT / SR 的连接信息(host/port/user/password)全部从 skill 根目录 `.env` 读取。
- 见 `.env.example` 模板; 不在文档/代码中保留明文账号与 IP。

环境变量覆盖: export HIVE_PASSWORD='xxx' / export SR_PASSWORD='yyy'

### 错误处理建议

`python
result = describe_table('unknown_table')
if not result['success']:
    error = result['error']
    if 'Authentication' in error:
        return '数据库认证失败，请确认账号权限'
    elif 'Unknown catalog' in error or 'Table not found' in error:
        return f'未找到表，请确认表名格式'
    elif 'timeout' in error.lower():
        return '查询超时，请尝试缩小数据范围或稍后重试'
    else:
        return '数据库操作失败，请稍后重试'
`
