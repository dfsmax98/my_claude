---
name: strategy-analysis
description: "反欺诈策略分析自动化技能(两步执行): Step1特征评估+策略挖掘, Step2通过率/命中率验证, 输出中文表头和Excel百分比格式报告"
---

# 策略分析 Skill (两步执行流程)

> 🔀 Step1: 特征评估(IV/PSI/Lift) + 策略挖掘(≤3特征) → Step2: 近7天全量验证(通过率/命中率)

## 🔄 两步执行流程

`mermaid
flowchart TB
    subgraph Step1[Step1: 特征评估+策略挖掘]
        A[加载数据] --> B[fpd_k30>=0 过滤]
        B --> C[分客群/分月计算IV/PSI/Lift]
        C --> D[筛选: IV≥0.02, PSI≤0.25, Lift≥2.0]
        D --> E[策略挖掘: ≤3特征, 仅>或<]
        E --> F[输出: 有效特征+有效策略]
    end
    
    subgraph Step2[Step2: 策略验证]
        G[加载近7天全量数据] --> H[无fpd_k30过滤]
        H --> I[对Step1策略计算通过率/命中率]
        I --> J[输出: 验证后策略+业务影响评估]
    end
    
    F --> G
`

## 📋 Step1: 特征评估 + 策略挖掘

### 数据要求
| 表类型 | 必填字段 | 过滤条件 |
|--------|----------|----------|
| 贷前 | cust_no,apply_no,apply_result,close_datetime,cust_group_dq,fpd_k30,if_out_30d,if_out_60d,if_in_30d,if_in_60d,f001_decision,[features...] | **fpd_k30 >= 0** 🔒 |
| 贷中 | cust_no,trans_seqno,order_no,rsk_log_id,risk_decision_result,create_datetime,cust_group_dz,new_old,fpd_k30,if_out_30d,if_out_60d,if_in_30d,if_in_60d,[features...] | **fpd_k30 >= 0** 🔒 |

### 评估指标 (无通过率)
- **IV**: 特征区分度, 阈值≥0.02
- **PSI**: 特征稳定性(分客群/分月), 阈值≤0.25
- **Lift**: 风险提升倍数, 阈值≥2.0

### 策略挖掘规则
- ✅ 组合: 1~3个特征
- ✅ 操作符: 仅支持 > 或 < (单方向, 避免局部最优)
- ✅ 质量: min_bad≥10, coverage∈[0.1%,20%], lift≥2.0
- ✅ 去重: Jaccard相似度, 按lift降序

### Step1输出
`
📄 报告: strategy_{scene}_step1_YYYYMMDD.xlsx
📊 Sheet1: 执行摘要 (有效特征数/策略数/平均Lift)
📋 Sheet2: 有效特征清单 (特征名/IV/PSI/Lift/建议)
🎯 Sheet3: 有效策略清单 (规则/特征组合/Lift/覆盖率)
📝 摘要: "本次分析共挖掘出X个有效特征, 推荐Y条策略进入Step2验证"
`

## 📋 Step2: 策略验证 (通过率/命中率)

### 数据要求 (与Step1不同)
| 配置项 | 值 | 说明 |
|--------|-----|------|
| 时间过滤 | **近7天** | 贷前: close_datetime; 贷中: create_datetime |
| fpd_k30过滤 | **❌ 移除** | 使用全量数据评估通过率影响 |
| 输入策略 | Step1输出的有效策略列表 | 仅验证Step1筛选出的策略 |

### 验证指标
| 指标 | 计算方式 | 业务含义 | 参考阈值 |
|------|----------|----------|----------|
| **命中率** | 策略命中样本数 / 总样本数 | 策略覆盖客户比例 | 0.1%~20% |
| **通过率影响** | 策略拒绝的好客户 / 总好客户 | 策略误杀对业务的影响 | <5%为佳 |
| **误报率** | 命中中的好客户 / 总命中 | 策略精准度 | <30%为佳 |
| **稳定性** | 近7天每日指标波动 | 策略效果是否稳定 | PSI≤0.25 |

### Step2输出
`
📄 报告: strategy_{scene}_step2_YYYYMMDD.xlsx
📊 Sheet1: 验证摘要 (验证策略数/平均命中率/通过率影响)
🎯 Sheet2: 验证后策略清单 (规则/Lift/命中率/通过率影响/误报率/建议)
📈 Sheet3: 稳定性趋势 (近7天指标波动)
📝 总结: "经近7天全量验证, Z条策略通过率影响<5%, 建议灰度上线..."
`

## ⚙️ 调用示例

`python
from skill.strategy_analysis.src.analyzer import StrategyAnalyzer

# 初始化 (贷前场景)
analyzer = StrategyAnalyzer(scene="dq", db_config=DB_CONFIG)

# === 方式1: 分步执行 ===
# Step1: 特征评估+策略挖掘
path1, summary1, results1 = analyzer.run_step1(
    feature_table="dwh.gdm_risk_vars_dipa_task_wide_pcr_df",
    output_path="reports/strategy_dq_step1_20260707.xlsx"
)
print(f"Step1摘要: {summary1}")
# 输出: "Step1完成: 42有效特征, 15条策略"

# Step2: 策略验证 (使用Step1输出的策略)
path2, summary2 = analyzer.run_step2(
    feature_table="dwh.gdm_risk_vars_dipa_task_wide_pcr_df",
    step1_strategies=results1["strategies"],
    output_path="reports/strategy_dq_step2_20260707.xlsx"
)
print(f"Step2摘要: {summary2}")
# 输出: "Step2验证: 8条策略, 平均命中率2.1%, 通过率影响1.2%"

# === 方式2: 完整流程 (自动执行Step1+Step2) ===
result = analyzer.run_full(
    feature_table="dwh.gdm_risk_vars_dipa_task_wide_pcr_df",
    output_prefix="reports/strategy_dq_20260707"
)
# 返回: {step1_report, step1_summary, step2_report, step2_summary, ...}
`

## ⚠️ 约束与校验

### Step1约束
1. 🔒 数据必须含 pd_k30 >= 0 过滤
2. 🔒 策略挖掘仅支持 > 或 <, 禁止 =/IN/范围
3. 🔒 策略最多3个特征组合
4. 🔒 IV<0.02或PSI>0.25的特征不参与策略组合

### Step2约束
1. 🔒 时间过滤必须为近7天 (可配置, 默认7天)
2. 🔒 必须使用Step1输出的策略列表, 禁止新增策略
3. 🔒 通过率影响>10%的策略标记为"高风险, 需人工评审"
4. 🔒 报告必须包含稳定性趋势分析

### 通用约束
1. 🔒 Excel报告必须含中文表头
2. 🔒 百分比类指标必须保持数值类型并设置Excel百分比格式，不允许写成 `"12.3%"` 字符串
3. 🔒 每个Sheet必须启用首行筛选、冻结首行，并自动调整列宽
4. 🔒 必须包含自动生成的总结性陈述
5. 🔒 执行结果必须记录到 WORKLOG.md

### 报告格式强制规范

所有 `strategy-analysis` 生成的 Excel 报告必须在保存后调用标准格式化器：

```python
from src.report_formatter import format_excel_report

format_excel_report(output_path)
```

格式化器默认执行：
- 表头中文化：英文列名统一映射为中文业务字段名
- 百分比格式：覆盖率、命中坏率、整体坏率、命中率、上线前/后拒绝率、拒绝率上升等列设置为 `0.00%`
- 可用性格式：首行筛选、冻结首行、表头深蓝底白字、自动列宽

写报告时遵守：
- 比例值写入 `0~1` 的数值，例如 `0.1234`，由 Excel 格式显示为 `12.34%`
- `Lift`、样本数、坏样本数、新增拒绝数保持普通数值格式
- 自定义 SQL 聚合报告或临时报告也必须复用 `src/report_formatter.py`

## 📊 输出指标说明

| 指标 | Step1 | Step2 | 计算方式 |
|------|-------|-------|----------|
| IV | ✅ | ❌ | Σ(坏%-好%)×ln(坏%/好%) |
| PSI | ✅ | ✅(稳定性) | Σ(实际%-预期%)×ln(实际%/预期%) |
| Lift | ✅ | ✅ | (命中坏样本率)/(整体坏样本率) |
| 命中率 | ❌ | ✅ | 命中样本数/总样本数 |
| 通过率影响 | ❌ | ✅ | 拒绝的好客户/总好客户 |
| 误报率 | ❌ | ✅ | 命中中的好客户/总命中 |

---
> 🔄 维护: 新增逻辑时同步更新 src/evaluator.py 和 templates/
> 📋 记录: Step1和Step2执行结果均需追加到 WORKLOG.md


## 🧪 测试表支持

### 内置测试表
| 场景 | 表名 | 用途 |
|------|------|------|
| 贷前 | d_dq.dfs_anormal_beh_dq_online_features | 贷前异常行为特征测试 |
| 贷中 | d_dq.dfs_anormal_beh_dz_online_features | 贷中异常行为特征测试 |

### 使用测试表执行分析
`python
from skill.strategy_analysis.src.analyzer import StrategyAnalyzer
from skill.strategy_analysis.src.data_loader import get_test_table, test_connection

# 1. 测试数据库连接
db_config = {"host": "sr-host", "port": 9030, "user": "xxx", "password": "xxx", "database": "d_dq"}
if not test_connection(db_config):
    print("❌ 数据库连接失败")
    exit(1)

# 2. 获取测试表名
analyzer = StrategyAnalyzer(scene="dq", db_config=db_config)
test_table = get_test_table("dq")  # 返回: d_dq.dfs_anormal_beh_dq_online_features

# 3. 执行完整分析
result = analyzer.run_full(
    feature_table=test_table,  # 使用测试表
    output_prefix="reports/test_strategy_dq"
)

print(f"✅ 测试完成: {result['validated_strategies_count']}条策略通过验证")
`

### 测试表字段说明
测试表 d_dq.dfs_anormal_beh_*_online_features 已预包含:
- ✅ 必填字段: cust_no, fpd_k30, if_out_30d, if_out_60d, if_in_30d, if_in_60d
- ✅ 时间字段: close_datetime (贷前) / create_datetime (贷中)
- ✅ 客群字段: cust_group_dq / cust_group_dz
- ✅ 特征字段: 预计算的异常行为特征 (以 f_ 或 var_ 开头)

> 💡 测试表可直接用于功能验证, 无需join样本表, 执行更快

## ⚙️ 配置文件说明 (config.yaml)

### 配置文件位置
`
skill/strategy-analysis/config.yaml
`

### 数据库配置
连接信息全部从 skill 根目录 `.env` 读取(见 `.env.example`), config.yaml 用 `${VAR}` 占位, 由 config_loader 自动展开:
`yaml
db:
  # StarRocks (主用)
  starrocks_host: ${SA_SR_HOST}
  starrocks_port: ${SA_SR_PORT}
  starrocks_user: ${SA_SR_USER}
  starrocks_password: ${SA_SR_PASSWORD}
  starrocks_database: d_dq

  # Impala (备用)
  impala_host: ${IMPALA_HOST}
  impala_port: ${IMPALA_PORT}
  impala_user: ${IMPALA_USER}
  impala_password: ${IMPALA_PASSWORD}
`

### 多环境配置 (db_profiles)
各环境的 host/user/password 同样用 `${VAR}` 占位, 真值放 `.env`:
`yaml
db_profiles:
  dev:   # 开发环境
    starrocks_host: ${SA_SR_HOST}
    starrocks_database: d_dq
  prod:  # 生产环境
    starrocks_host: ${SR_PROD_HOST}
    starrocks_user: ${SR_PROD_USER}
    starrocks_password: ${SR_PROD_PASSWORD}
    starrocks_database: d_dq_prod
`

### 策略分析配置
`yaml
strategy_analysis:
  # 评估阈值
  evaluation:
    iv_threshold: 0.02      # IV≥0.02
    psi_threshold: 0.25     # PSI≤0.25
    lift_threshold: 2.0     # Lift≥2.0
  
  # 策略挖掘约束
  mining:
    max_features_per_strategy: 3    # ≤3特征组合
    operator_restriction: [">", "<"] # 仅单方向判断
  
  # Step2验证
  validation:
    step2_days: 7                   # 近7天数据
    pass_rate_impact_threshold: 0.05 # >5%标记高风险
`

### 环境变量支持
配置中使用 \ 格式, 加载时自动展开:
`yaml
# config.yaml
starrocks_password: \

# Shell设置
export SR_PASSWORD="your-secret"
# 或 PowerShell
\ = "your-secret"
`

## 🚀 配置加载调用方式

### 方式1: 手动加载 (灵活)
`python
from skill.strategy_analysis.src.config_loader import load_config, get_db_config

config = load_config()  # 读取config.yaml
db_cfg = get_db_config(config, engine="starrocks")

analyzer = StrategyAnalyzer(
    scene="dq",
    db_config=db_cfg,
    config=config.get("strategy_analysis", {})
)
`

### 方式2: from_config类方法 (推荐)
`python
analyzer = StrategyAnalyzer.from_config(
    scene="dq",
    profile="dev",  # 使用db_profiles.dev配置
    output={"top_n_features": 20}  # 覆盖部分配置
)
`

### 方式3: 环境变量覆盖敏感配置
`ash
# 设置生产环境变量
export SR_PROD_HOST="prod-starrocks"
export SR_PROD_PASSWORD="secret-key"

# Python代码
config = load_config(profile="prod")  # 自动展开\
`

## 🔐 安全最佳实践

1. ✅ **密码管理**: 生产环境使用环境变量或密钥管理服务
2. ✅ **配置隔离**: config.yaml 加入 .gitignore 避免提交
3. ✅ **环境分离**: 使用 db_profiles 区分 dev/test/prod
4. ✅ **权限最小化**: 数据库用户仅授予必要权限
5. ✅ **定期轮换**: 定期更新数据库密码并同步配置

> 💡 提示: 首次使用时, 复制 config.yaml 为 config.local.yaml 进行本地修改, 避免覆盖模板

---

## 🤖 Agent 调用指引（Codex 专用）

> 此部分供 Codex Agent 内部调用参考，用户无感知

### 触发条件
当用户请求分析特征表效果时，Agent 按以下流程执行：

1. **确认参数**：
   - 特征表名（若未提供，从最近 mining 输出或宽表默认值中选择）
   - 场景：dq(贷前) / dz(贷中) - 默认从表名推断
   - 两步验证：默认 Yes，用户可跳过 Step2

2. **执行分析**：
   `python
   # Agent 内部执行
   from src.analyzer import StrategyAnalyzer
   
   analyzer = StrategyAnalyzer(scene=scene, db_config=load_db_config())
   
   # Step1: 特征评估 + 策略挖掘 (fpd_k30>=0 过滤)
   path1, summary1, results1 = analyzer.run_step1(
       feature_table=feature_table,
       output_path=f"_temp/analysis/{scene}_{get_table_name(feature_table)}_step1.xlsx"
   )
   
   # Step2: 通过率验证 (仅当用户确认或配置启用)
   if two_step and results1.get('strategies'):
       path2, summary2 = analyzer.run_step2(
           feature_table=feature_table,
           step1_strategies=results1['strategies'],
           output_path=f"_temp/analysis/{scene}_{get_table_name(feature_table)}_step2.xlsx"
       )
   `

3. **返回摘要**（关键！用户可见）：
   `
   📊 {feature_table} 分析完成:
   - 有效特征: X 个 (IV≥0.02, PSI≤0.25)
   - 候选策略: Y 条 (Lift≥2.0, coverage∈[0.1%,20%])
   - 通过验证: Z 条 (通过率影响<5%)
   
   🔝 Top3 推荐策略:
   1. {rule_str}: Lift={lift:.2f}, Coverage={cov*100:.1f}%, Grade={grade}
   2. ...
   
   📄 详细报告: {output_path}
   `

4. **兜底逻辑**：
   若 strategy-analysis 执行失败（数据库/权限/超时），自动 fallback：
   `python
   from anti_fraud_analyzer import AnalysisPipeline
   # 调用基础分析生成简化报告
   `
   并告知用户：
   `
   ⚠️ 高级分析暂不可用，已生成基础评估报告
   📄 基础报告: {basic_report_path}
   💡 建议: 检查数据库连接后重试完整流程
   `

### 内部工具函数
`python
def analyze_strategy_for_agent(feature_table: str, scene: str = None, 
                              two_step: bool = True, 
                              config_overrides: dict = None) -> dict:
    """Agent 内部: 执行策略评估，返回结构化结果 + 用户摘要"""
    
    # 1. 推断场景
    if scene is None:
        scene = 'dz' if 'inloan' in feature_table or '_dz_' in feature_table else 'dq'
    
    # 2. 加载配置
    config = load_config()
    if config_overrides:
        config.get('strategy_analysis', {}).update(config_overrides)
    
    # 3. 执行分析
    analyzer = StrategyAnalyzer(scene=scene, db_config=config.get('db', {}))
    
    try:
        if two_step:
            result = analyzer.run_full(
                feature_table=feature_table,
                output_prefix=f"_temp/analysis/{scene}_{get_table_name(feature_table)}"
            )
            summary = format_two_step_summary(result)
        else:
            path, summary_str, results = analyzer.run_step1(
                feature_table=feature_table,
                output_path=f"_temp/analysis/{scene}_{get_table_name(feature_table)}_step1.xlsx"
            )
            result = {'step1_report': path, 'step1_summary': summary_str, 'strategies': results}
            summary = format_step1_summary(results)
        
        return {'success': True, 'result': result, 'user_summary': summary}
        
    except Exception as e:
        # Fallback to basic analysis
        basic_result = fallback_basic_analysis(feature_table, scene)
        return {
            'success': False,
            'fallback': True,
            'result': basic_result,
            'user_summary': f"⚠️ 高级分析暂不可用，已生成基础报告: {basic_result['report_path']}"
        }

def format_two_step_summary(result: dict) -> str:
    """格式化两步验证结果为用户可读摘要"""
    s1 = result.get('step1_summary', '')
    s2 = result.get('step2_summary', '')
    return f"{s1}\n{s2}" if s2 else s1

def format_step1_summary(results: dict) -> str:
    """格式化 Step1 结果为用户可读摘要"""
    n_features = len(results.get('valid_features', []))
    n_strategies = len(results.get('strategies', []))
    return f"✅ Step1 完成: {n_features} 个有效特征, {n_strategies} 条候选策略"
`

### 参数校验（Agent 内部执行）
`python
def validate_analysis_params(feature_table: str, scene: str) -> tuple[bool, str]:
    """校验分析参数，返回 (是否有效, 错误信息)"""
    # 1. 表名格式校验
    if not feature_table.startswith('d_dq.dfs_') and not feature_table.startswith('dwh.gdm_'):
        return False, "特征表名需以 d_dq.dfs_ 或 dwh.gdm_ 开头"
    
    # 2. 场景与表名一致性
    if scene == 'dq' and '_dz_' in feature_table:
        return False, "贷前场景(dq)不兼容贷中特征表(_dz_)"
    if scene == 'dz' and '_dq_' in feature_table:
        return False, "贷中场景(dz)不兼容贷前特征表(_dq_)"
    
    # 3. 必填字段校验 (通过 table-explorer 或 schema 缓存)
    required = ['cust_no', 'fpd_k30'] + (['apply_no'] if scene=='dq' else ['trans_seqno'])
    # ... 校验逻辑 ...
    
    return True, ""
`

### 输出规范
Agent 回复用户时，必须包含：
1. ✅/⚠️ 状态标识
2. 📊 关键指标摘要（有效特征数/策略数/通过率影响）
3. 🔝 Top3 策略推荐（规则条件+Lift+覆盖率+分级）
4. 📄 报告文件路径（可点击打开）
5. 💡 下一步建议（如"需要调整阈值请回复..."）


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


## 🔧 DDV报告格式修复说明 (2026-07-15)

### 问题
分组明细 Sheet列数与模板out_all_in_one_template.xlsx不匹配，导致筛选器/透视表联动失效。

### 修复
修改 anti_fraud_analyzer/ddv_reporter.py 的 _calc_group_detail 方法，确保输出36列完全匹配模板：
dt_cut, group, total, good, bad, pct, risk, lift, tot_amt, bad_amt, avg_amt, risk_amt, lift_amt, amt_xiaolv, total_cust, bad_cust, avg_amt_cust, risk_cust, lift_cust, IV, KS, WoE, Mono, x, y, psi, bin_method, remove_miss_group, remove_total_group, 综合指标剔除, x1, x2, x1_group, x2_group, x1_missing, x2_missing

### 验证方法
from openpyxl import load_workbook
wb = load_workbook(output_path, data_only=True)
ws = wb[分组明细]
cols = [str(c.value) for c in ws[1] if c.value]
assert len(cols) == 36

### 报告模式选择
| 模式 | 适用场景 | 优点 | 限制 |
| openpyxl(默认) | 跨平台/无Excel环境 | 兼容性好，数据结构正确 | 丢失条件格式/筛选器 |
| xlwings | Windows+Excel环境 | 保留完整模板格式 | 需COM环境，可能刷新警告 |

cfg[output][reporter_mode] = xlwings  # 或 openpyxl

---

## 📦 APPLIST特征挖掘流程

### 配置示例 (_temp/applist_feature_config.yaml)
feature_group: applist_risk
stage: preloan
output_table: d_dq.dfs_applist_risk_features_20260715
sample_table:
  table:
    preloan: d_dq.dfs_dq_fqz_base_final
  primary_keys:
    preloan: [cust_no, apply_no]
  time_field:
    preloan: close_datetime
  target_fields:
    preloan: [apply_result, cust_group_dq, fpd_k30, if_out_30d, if_in_30d, f001_decision]

data_sources:
  - name: applist
    table: default.t_bd_credit_cust_app_info
    join_field: cust_no
    time_field: create_datetime
    partition_field: dt
    select_fields: [app_name, app_category, install_time, risk_level]

features:
  - name: f_app_loan_cnt_2y
    desc: 近2年借贷类APP安装数
    source: applist
    agg_func: count
    agg_field: app_name
    time_window: 2y
  - name: f_app_loan_ratio
    desc: 借贷APP占比
    source: derived
    formula: f_app_loan_cnt_2y / nullif(f_app_total_cnt_2y, 0)

### 执行步骤
1. 生成SQL+字典: python skill/strategy-mining/scripts/generate_feature_sql.py --config _temp/applist_feature_config.yaml --output _temp/
2. 执行建表: python skill/strategy-mining/scripts/execute_feature_pipeline.py --config _temp/applist_feature_config.yaml
3. 策略分析: 使用anti_fraud_analyzer对衍生特征进行IV/Lift评估

### 注意事项
1. 时间防穿越: install_time < close_datetime
2. 客群区分: 贷前cust_group_dq / 贷中cust_group_dz
3. 标签选择: fpd_k30(短逾) / if_out_30d(外诉) / if_in_30d(内诉)
4. 建表命名: d_dq.dfs_{feature_group}_{stage}_YYYYMMDD
