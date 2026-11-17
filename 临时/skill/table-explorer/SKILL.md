---
name: table-explorer
description: 数据库表结构探查与文档生成工具。自动连接数据库，探查表结构，识别关键字段，分析枚举值，并生成结构化的Markdown文档。适用于策略分析前的数据探索阶段。
---

# Table Explorer

自动探查数据库表结构并生成分析文档，帮助策略分析师快速了解表结构和字段含义。

## 功能特性

- **表结构探查**: 获取表的所有字段、数据类型、注释信息
- **记录数统计**: 快速获取表的记录总数
- **样本数据预览**: 提取前N条样本数据供人工审查
- **关键字段识别**: 自动识别主键、时间字段、外键、信息字段
- **枚举值分析**: 识别低基数字段并统计枚举值分布
- **文档生成**: 生成结构化的Markdown文档，包含使用建议

## 使用方法

### 命令行使用

`ash
# 基本用法（探查贷前样本表）
python scripts/explore_table.py d_dq.dfs_dq_fqz_base_final

# 指定输出路径
python scripts/explore_table.py d_dq.dfs_dq_fqz_base_final -o output/sample_table.md

# 指定样本数量
python scripts/explore_table.py d_dq.dfs_dq_fqz_base_final -l 200

# 使用StarRocks引擎
python scripts/explore_table.py d_dq.dfs_dq_fqz_base_final -e starrocks
`

### 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| 	able_name | 表名（必填） | - |
| -o, --output | 输出文件路径 | output/{table_name}.md |
| -l, --limit | 样本数据条数 | 100 |
| -e, --engine | 数据库引擎 (hive/starrocks) | hive |

### 配置说明

配置文件: config.yaml

主要配置项:
- **数据库连接**: Hive和StarRocks的连接信息
- **探查规则**: 关键字段识别模式、枚举值阈值等

## 输出文档结构

生成的Markdown文档包含以下部分:

1. **基本信息**: 表名、记录数、字段数
2. **关键字段识别**: 主键、时间字段、外键、信息字段
3. **完整字段列表**: 所有字段的详细信息表格
4. **样本数据**: 前10条样本数据预览
5. **枚举值分析**: 低基数字段的值分布
6. **使用建议**: 表关联和常见用法示例

## 典型使用场景

### 场景1: 策略分析前的数据探索

`ash
# 探查样本表
python scripts/explore_table.py d_dq.dfs_dq_fqz_base_final

# 探查特征表
python scripts/explore_table.py dwh.gdm_risk_vars_dipa_task_wide_pcr_df

# 探查数据源表
python scripts/explore_table.py t_bd_cust_relation_info
python scripts/explore_table.py t_bd_local_calls_records
python scripts/explore_table.py t_bd_credit_cust_app_info
`

### 场景2: 验证表关联关系

通过查看各表的主键字段，确认表之间的关联关系:
- 样本表主键: pply_no (贷前) / 	rans_seqno (贷中)
- 特征表主键: pply_no / order_no
- 数据源表主键: cust_no / pply_no

### 场景3: 识别枚举字段

自动识别标签字段（如 pd_k30, if_out_30d）并统计分布，帮助理解标签定义。

## 技术实现

### 依赖

- pandas: 数据处理
- pyhive: Hive连接（可选）
- pymysql: StarRocks连接（可选）
- pyyaml: 配置文件解析

### 核心模块

1. **DBConnector**: 数据库连接管理（复用 anti_fraud_analyzer）
2. **get_table_schema**: 获取表结构（DESCRIBE语句）
3. **get_sample_data**: 获取样本数据（SELECT * LIMIT N）
4. **identify_key_fields**: 基于字段名模式识别关键字段
5. **analyze_enum_values**: 统计低基数字段的值分布
6. **generate_markdown**: 生成结构化文档

## 注意事项

1. **数据库连接**: 确保 config.yaml 中的数据库配置正确
2. **权限**: 需要对目标表有SELECT权限
3. **性能**: 大表的COUNT(*)可能较慢，可通过跳过记录数统计优化
4. **采样**: 样本数据使用LIMIT，可能不具代表性，建议结合业务理解

## 输出示例

`markdown
# 表结构文档: d_dq.dfs_dq_fqz_base_final

> 生成时间: 2026-07-07 11:30:00

## 基本信息
- **表名**: d_dq.dfs_dq_fqz_base_final
- **记录数**: 1234567
- **字段数**: 15

## 关键字段识别

### 主键/标识字段
- pply_no
- cust_no

### 时间字段
- close_datetime
- create_time

### 枚举值分析
- pd_k30: 基数 2 (0: 95%, 1: 5%)
- if_out_30d: 基数 2 (0: 90%, 1: 10%)
`

## 相关文件

- scripts/explore_table.py: 主脚本
- config.yaml: 配置文件
- output/: 输出目录


---

## 🤖 Agent 专用调用指引

> 此 skill 主要供 Codex Agent 内部调用，用于确认表结构后再执行特征衍生
> 用户通常无感知，仅在明确请求"查看表结构"时输出简化结果

### 触发词（Agent 识别）
| 用户输入关键词 | Agent 动作 |
|---------------|-----------|
| 探查{table}字段 | 执行完整探查，返回字段清单 |
| {table}有哪些枚举值 | 仅提取枚举型字段的 distinct 值 |
| 确认{field}是否在{table}中 | 快速校验单字段存在性 |
| {table}主键是什么 | 返回主键/联合主键信息 |

### Agent 执行流程
1. 检查缓存 output/{table}.md (24h 内有效)
2. 若缓存有效 → 解析返回结构化结果
3. 若缓存无效 → 执行 explore_table.py 重新探查
4. 返回精简结果供 strategy-mining 使用

### 返回结果规范（Agent 内部使用）
`json
{
  "table": "t_bd_cust_relation_info",
  "fields": ["cust_no", "relation_mobile_no", "relation_type", "create_datetime"],
  "time_field": "create_datetime",
  "join_key": "cust_no",
  "sample_filters": ["relation_mobile_no IS NOT NULL", "LENGTH=11"],
  "success": true
}
`

### 用户可见输出（仅当用户明确请求时）
- 字段清单表格（前 5-10 个关键字段）
- 主键/时间字段标识
- 可衍生特征建议（COUNT/SUM/AVG 示例）
- 下一步行动建议（"需要衍生这些特征吗？"）

### 与 strategy-mining 协作
探查完成后，Agent 自动建议：
"✅ 已确认 {table} 字段结构
💡 可衍生: 联系人总数/紧急联系人占比/亲属联系人数
🔗 需要我帮你衍生这些特征吗？(回复'衍生通讯录特征'即可)"


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
