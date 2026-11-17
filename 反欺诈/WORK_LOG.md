# 反欺诈项目 工作日志

---

## 2026-05-20

### App 打标（第一轮试跑 · 1000 条）

**任务**: 从约 9850 条未打标 app 中随机采样 1000 条，调用 Claude Haiku API 自动打标。

**脚本**: `run_tagging.py`  
**输出**: `tagging_tmp/batch_001.json` ~ `batch_020.json`，汇总至 `applist_tag_result_1000.xlsx`  
**耗时**: 约 24 分钟（20 批，每批 50 条）

**风险分布**:

| 风险类型 | 数量 | 占比 |
|--------|------|------|
| 正常 | 597 | 59.7% |
| 山寨低质 | 132 | 13.2% |
| 色情 | 104 | 10.4% |
| 伪冒仿冒 | 47 | 4.7% |
| 其他高风险 | 41 | 4.1% |
| 隐私窃取 | 33 | 3.3% |
| 黑产工具 | 24 | 2.4% |
| 网赚刷量 | 22 | 2.2% |

---

### App 打标（全量 · 剩余 ~8850 条）

**任务**: 对剩余全部未打标 app 进行打标，续接第一轮批次编号。

**脚本**: `run_tagging.py`（更新版，支持全量 + 断点续跑）  
**批次文件**: `tagging_tmp/batch_021.json` 起  
**样本文件**: `tagging_tmp/sample_full.csv`  
**状态**: 全部完成 ✓

**实际批次**: batch_021 ~ batch_198，共 178 批，8867 条（最后一批 17 条）  
**标签版本**: v4（含赌博/现金贷/翻墙VPN/虚拟货币风险/改机工具/反催收等新类别）  
**输出**: `tagging_tmp/applist_tag_result_full.xlsx`（含全部 198 批共 9867 条）

**风险类型最终分布（全量 9867 条）**:

| risk_type | 数量 | 占比 |
|-----------|------|------|
| 正常 | 5609 | 56.9% |
| 色情 | 1364 | 13.8% |
| 山寨低质 | 891 | 9.0% |
| 赌博 | 462 | 4.7% |
| 其他高风险 | 366 | 3.7% |
| 伪冒仿冒 | 360 | 3.6% |
| 现金贷 | 219 | 2.2% |
| 网赚刷量 | 168 | 1.7% |
| 黑产工具 | 146 | 1.5% |
| 翻墙VPN | 144 | 1.5% |
| 隐私窃取 | 79 | 0.8% |
| 虚拟货币风险 | 59 | 0.6% |

---

### 标签系统优化（v2）

**原因**: 第一轮打标发现贷款类、赌博类、虚拟货币类被笼统归入"其他高风险"，颗粒度不足

**app_type 新增**（6个）:
`生活服务`, `视频影视`, `棋牌赌博`, `贷款`, `虚拟货币`, `VPN代理`

**risk_type 新增**（4个）:
`现金贷`, `赌博`, `虚拟货币风险`, `翻墙VPN`

**影响**: 删除 batch_021~060（旧标签，共40批），重新从 batch_021 打标

### 标签系统优化（v3）+ 模型升级

**新增 app_type**（3个）: `投诉平台`（黑猫投诉等）、`改机工具`（APP分身/多开/设备伪装等）、`反催收`（反催收话术/拦截催收/债务优化）

**模型**: Haiku 4.5 → Opus 4.6

**Prompt 更新**: 改机工具映射至 risk_type=黑产工具；投诉平台为正常类；补充对应包名关键词规则

### 全量标签整合

**任务**: 合并人工标注（labels_batch1~3）+ 自动打标（batch_001~198）到单一 CSV，去重并归一化标签  
**输出**: `applist_tag_all.csv`  
**关键数据**: 9980 条（人工 150 + 自动 9830，去重 37 条）  
**归一化处理**: 人工标注中 `防检测作弊`→`黑产工具`（5条）、`加密币诈骗`→`虚拟货币风险`（2条）、`加密币区块链`→`虚拟货币`（2条）

---

## 2026-05-20

### 敏感词库搭建（v1.0）

**任务**: 针对通讯录备注 & 客服聊天场景，按8类风险搭建初版敏感词库
**脚本/工具**: `敏感词库/sensitive_words.py`、`敏感词库/export_sensitive_words.py`
**输出**: `敏感词库/反欺诈敏感词库_v1.0.xlsx`
**关键数据**: 8 类，共 235 条词条（赌博43、涉黑32、涉毒28、传销30、催收30、金额异常23、贷款26、套现23）

---

### 敏感词库优化（v2.0）

**任务**: 解决初版误杀问题（兄弟/大哥/还款/手续费等），重构为 L1/L2 两层词库，区分通讯录备注和客服聊天场景
**脚本**: `敏感词库/sensitive_words.py`（全量重写）
**输出**: 更新 `sensitive_words.py`；相关文件移入 `敏感词库/` 子目录
**核心变更**:
- L1 精准词：专有词/短语，单词命中即触发，通讯录+客服均适用
- L2 辅助词：通用词，客服聊天场景同类命中 ≥2 才触发
- 从 L1 删除：兄弟、大哥、还款、逾期、手续费、保证金、变现、救急、溜冰等高误杀词

---

### 敏感词库扩充（v2.1）- 新增反催收 & 征信修复

**任务**: 新增"反催收"和"征信修复"两个类别
**脚本**: `敏感词库/sensitive_words.py`
**关键数据**:
- 反催收 L1：10条（核心词：反催收/催收拦截/债务优化/反催收话术等）
- 反催收 L2：8条（协商还款/停止催收/债务协商等）
- 征信修复 L1：13条（核心词：征信修复/征信铲单/征信代修/删除逾期记录等）；原贷款欺诈类中的征信修复词归并至此
- 征信修复 L2：8条（征信差/黑户/不良记录等，"有逾期"因误杀风险高未纳入）

---

## 2026-05-21

### App 打标新流程试跑（sample_200）

**任务**: 用新设计的两级反欺诈标签体系（label_l1 / label_l2 + risk_level + confidence + reason）对 sample_200.csv 试跑，验证 prompt、缓存、JSON 容错、包名对齐校验、并发 batch 流程
**脚本**: `run_sample_200.py`（独立运行，沿用 `applist_label_cache.sqlite` 缓存）
**输出**: `sample_200_labeled.csv`
**耗时**: 37.6s（7 个 batch，每批 30 条，4 并发）
**模型**: claude-opus-4-7

**风险等级分布**:

| risk_level | 数量 | 占比 | 平均 confidence |
|------------|-----|------|----------------|
| 低 | 88 | 44.0% | 0.76 |
| 高 | 58 | 29.0% | 0.85 |
| 未知 | 38 | 19.0% | 0.26 |
| 中 | 16 | 8.0% | 0.58 |

**一级标签分布**: 正常应用 85 / 未知 42 / 色情低俗 32 / 黑灰产工具 16 / 金融借贷 10 / 赌博博彩 5 / 加密货币 4 / 兼职薅羊毛 4 / 游戏 1 / 社交通讯 1

**观察**:
- 高风险召回符合预期：涉黄（29）+ 现金贷（7）+ VPN（7）+ 多开分身（5）+ 改机（3）+ 赌博（4）+ 加密货币（4），核心黑灰产覆盖到位
- "未知"占比 19%，主要是乱码包名 + 无 app 描述的样本（仅有 app_Name + app_package 两列时上限就在这里）；置信度自动压到 0.26 符合设计意图，避免幻觉
- 未知类的平均置信度（0.26）vs 高风险类（0.85）区分明显，可作为人工抽检的天然过滤阈值
- 与旧 taxonomy（app_type/risk_type 23 类 + 12 类）相比，新体系（一级 9 类 + 二级 30 类）粒度更适合策略分层使用

**备注**: 已有的 `applist_tag.csv`（9980 条全量标签）流程不动，新流程仅作平行试验。后续可考虑：(1) 用 sample_200 上的旧标签做一致性对比；(2) 引入第三方应用市场描述补全长尾，降低未知率

---

### 标签体系 v2 重构 + sample_200 重跑

**任务**: 重构标签体系为三个独立维度（app_l1 应用大类 / app_l2 应用子类 / risk_type 风险类型）；risk_type 改为风险类型枚举（不再分高中低）；黑灰产工具判定严格化，破解版默认归山寨低质，多开/分身归独立的"改机软件"
**脚本**: `run_sample_200.py`（更新版） + `taxonomy_v2.md`（标签体系文档）
**输出**: `sample_200_labeled.csv` / `sample_200_labeled.xlsx`（多 sheet：全量 + 分布汇总 + 高风险明细 + 按 risk_type 分 sheet）
**缓存**: 新建 `applist_label_cache_v2.sqlite`（与 v1 隔离）
**耗时**: 47.7s（7 batch × 30 条，4 并发）
**模型**: claude-opus-4-7

**风险类型分布**:

| risk_type | 数量 | 平均 conf |
|---|---|---|
| 无 | 71 (35.5%) | 0.79 |
| 未知 | 46 (23.0%) | 0.34 |
| 色情 | 32 (16.0%) | 0.88 |
| 山寨低质 | 12 (6.0%) | 0.64 |
| 小额现金贷 | 7 (3.5%) | 0.79 |
| 改机软件 | 6 (3.0%) | 0.93 |
| 翻墙VPN | 6 (3.0%) | 0.90 |
| 伪冒仿冒 | 5 (2.5%) | 0.76 |
| 赌博 | 4 (2.0%) | 0.86 |
| 网赚刷量 | 4 (2.0%) | 0.69 |
| 区块链 | 3 (1.5%) | 0.87 |
| 其他高风险 | 3 (1.5%) | 0.57 |
| 黑灰产工具 | 1 (0.5%) | 0.90 |

**判定效果验证**:
- 破解版（KiMi破解版）正确归入 山寨低质，未被错判为黑灰产工具 ✓
- 改机软件 6 条精准命中：隐藏图标软件、DiDi防检测、多开分身类 ✓
- 黑灰产工具仅 1 条（Temp Mail 接码），判定严格生效 ✓
- 现金贷 7 条均为无资质类（月月钱包/惠民花等），未误标持牌借贷 ✓
- 未知类置信度 0.34 vs 高风险均值 0.85+，置信度区分度好

**已知问题**:
- 未知率 23%，根因仍是输入仅 app_Name + app_package；要降需引入应用市场描述
- 高风险中"其他高风险"占 3 条，可观察是否需要新增专门类别

---

### 全量打标 v2（applist_tag.csv · 9957 条）

**任务**: 用 v2 三维标签体系（app_l1 / app_l2 / risk_type）对全量 applist_tag.csv 打标；prompt 允许合理推理，乱码无信号才标"未知"
**脚本**: `run_label_v2.py`（参数化版本，支持断点续跑 + 每批 JSON 文件 + 每 50 批分布快照）
**模型**: claude-opus-4-6
**输出**:
- `applist_tag_v2.csv` / `applist_tag_v2.xlsx`
- 每批 `tagging_tmp/applist_tag_v2_NNN.json`（含 app_Name）
- 分布快照 `tagging_tmp/_snapshot_*.txt` + `tagging_tmp/_final_distribution.txt`
**缓存**: `applist_label_cache_applist_tag_v2.sqlite`（9957 条）
**耗时**: 1308s（约 22 分钟，6 并发 × batch_size=30，280 批）

**风险类型分布**:

| risk_type | 数量 | 占比 |
|---|---|---|
| 无 | 6145 | 61.7% |
| 色情 | 1353 | 13.6% |
| 赌博 | 467 | 4.7% |
| 小额现金贷 | 427 | 4.3% |
| 山寨低质 | 397 | 4.0% |
| 未知 | 316 | 3.2% |
| 网赚刷量 | 213 | 2.1% |
| 翻墙VPN | 200 | 2.0% |
| 伪冒仿冒 | 114 | 1.1% |
| 改机软件 | 90 | 0.9% |
| 区块链 | 79 | 0.8% |
| 其他高风险 | 77 | 0.8% |
| 黑灰产工具 | 59 | 0.6% |
| 隐私窃取 | 14 | 0.1% |
| 投诉平台 | 5 | 0.1% |
| 反催收 | 1 | 0.0% |

**关键指标**:
- 平均 confidence 0.723；app_l1=未知 占比 2.7%（v2 sample_200 时 23%，新增"允许推理"规则后大幅下降）
- 高风险召回（除"无/未知"）合计 3496 条 / 35.1%
- 黑灰产工具仅 59 条（严格判定生效）；改机软件作为独立类 90 条
- 反催收 1 条偏低，与 sample_200 一致 —— 仅靠 app 名称难以识别，需结合通讯录/聊天敏感词联动

**备注**:
- 同一脚本中曾出现两次后台进程并发跑同一份 cache（SQLite WAL 多写无冲突），未污染结果
- 早期 18 批 JSON 漏写 app_Name，已回填
- 控制台日志中文在 Windows GBK 下乱码，分布快照已改写 UTF-8 文件，参见 `tagging_tmp/_final_distribution.txt`

---

## 2026-05-27

### App 打标 0522 批次（全量 · 84562 unique 包）

**任务**: 对 `applist_tag_0522.csv`（101736 行，84562 unique 包）做反欺诈打标，复用 v2 已有缓存。
**脚本**: `prefill_cache_0522.py`（预填 v2 缓存）+ `run_label_v2.py applist_tag_0522.csv applist_tag_0522_v2`
**输出**: `applist_tag_0522_v2.csv` / `applist_tag_0522_v2.xlsx`
**缓存**: `applist_label_cache_applist_tag_0522_v2.sqlite`
**耗时**: 首轮约 ~3h（含 ~8637 条 LLM 调用失败）+ 重打 ~1650s
**关键数据**:
- 总 unique 包 84562，最终失败残留 95 条（0.11%）
- 高风险召回（除"无/未知"）20030 条 / 23.7%
- 风险 Top: 色情 6.8% / 赌博 3.6% / 山寨低质 3.4% / 小额现金贷 2.9% / 网赚刷量 2.6% / VPN 1.6%
- app_l1=未知 1.6%（推理规则继续生效）

**备注**:
- 首轮跑完发现 8637 条 reason='LLM调用失败'（API 偶发故障导致整 batch 失败），删除后重跑只剩 95 条
- `run_label_v2.py:219` 有 bug：批次 JSON 字段写成 `app_Name`（大写 N），导致 app 名称未落盘到批次文件；已修复，并用 `tagging_tmp_fill_name.py` 回填 1487 个批次文件中 44591 条 app_name
- 不影响最终 csv/xlsx（这两份是从 SQLite + 原 CSV merge 出的）


### 0522 批次 · 标签复核与修正

**任务**: 对 0522 批次打标结果做四轮质量审计与修正。
**脚本**: 见 `审计/` 相关脚本

**第 1 轮 · 未知二次打标** (`relabel_unknown.py`)
- 对 1428 条 app_l1=未知 / risk=未知 的（有 app_name）重打，禁止返"未知"
- 残留未知 246 条（全是 app_name 为空，无信息可推断）
- 耗时 ~17min

**第 2 轮 · 一致性修正** (`fix_consistency.py`)
- 修正 905 条 risk_type 与 app_l1/l2 不一致
- 色情→色情成人 824 条，赌博→棋牌赌博 36 条，区块链→区块链加密 17 条，改机软件 l2→改机工具 28 条

**第 3 轮 · 漏标复审** (`audit_labels_v2.py` + `review_suspects.py`)
- 规则筛出 182 条 "risk=无 但名称含可疑词"
- LLM 复审：9 条改为高风险（确实漏标），173 条保留无风险（确为误报：如房贷计算器/模拟器游戏/企业 VPN）

**第 4 轮 · 反向复审** (`audit_overlabeled.py` + `review_overlabeled.py`)
- 规则筛出 237 条 "高风险但疑似误标"（含正规品牌词/低confidence/正规机构名等）
- LLM 保守复审：仅 8 条改动（1 条改无风险=网易有灵众包；7 条在高风险类型间调整更精确）
- 保留率 97%，验证原打标质量

**最终输出**:
- `applist_tag_0522_v2.csv` / `applist_tag_0522_v2.xlsx`（unique 84565，行 101736）
- 高风险召回（除"无/未知"）约 21380 条 / 25.3%
- 残留未知 246 条（app_name 为空，无法推断）

**备注**:
- 反向审计最大启示：含正规品牌词的"高风险"标签绝大多数**不是误标**——它们是仿冒包/破解版/多开分身（包名 com.qihoo.magic.*、乱码包名等）。LLM 在第 1 轮就已正确识别这些为高风险
- `name_map` 旧 bug 修复后，新批次 JSON `app_name` 字段已正确写入


---

## 2026-06-05

### run_label_v2.py 优化重构

**任务**: 按 review 出的几个问题修 `run_label_v2.py`
**脚本/工具**: `run_label_v2.py`
**输出**: `run_label_v2.py`（重写）

**修改内容**:
- 模型名 `claude-opus-4-6`（不存在）→ `claude-sonnet-4-6`
- 输出从 free-text JSON + 正则解析 → `tool_use` 结构化输出（定义 `LABEL_TOOL`，强制 `tool_choice`），彻底消除 `extract_json_array` 的解析风险
- 新增 `validate_label()`：落库前做 `app_l1` / `app_l2`（按 l1 归口）/ `risk_type` 白名单兜底，l1 不合法直接全置"未知"
- 新增规则前置 `apply_rules()`：精确包名 `RULE_LABELS`（44 条头部 app，置信度 1.0）+ 正则前缀 `RULE_PATTERNS`（系统应用/厂商应用/银行，17 条，置信度 0.9），命中后直接写缓存，不送 LLM
- 系统提示词追加 `FEW_SHOT_TEXT`（12 条边界示例：助贷 vs 现金贷、模拟器、多开、投诉平台、挖矿、网赚等）
- `max_tokens` 4096 → 8192，避免长包名/长 reason 截断
- 重试分层：`RateLimitError` 读 `retry-after` header，`APIStatusError` / `APIConnectionError` 指数回退，解析错误立即重试

**关键数据**:
- 规则前置预估在万级 applist 中能命中 30%+，按 6 worker × 30 batch 节流，整体成本降 ~30%
- `validate_label` 防止以前会污染缓存的造词标签（如 "金融" / "短视频应用" 等）

**备注**:
- 模型名改用 Sonnet 4.6 而非 Opus 4.7：打标是分类任务，Sonnet 性价比更高；如需切回 Opus 改 `MODEL` 常量即可
- `RULE_LABELS` / `RULE_PATTERNS` 是 starter 集，建议跑完一遍后从 LLM 高置信结果里再补 200~500 条头部 app
- 未做的优化：低置信度二次复审、`app_name` 变化触发重打标 —— 留待后续按需加

### applist 标签体系优化 (RISK_TYPES v2)

**任务**: L1/L2 严格按功能划分, 风险信号全部上到 risk_type; 落实 review 中 5/6/7/8 四点
**脚本/工具**: `run_label_v2.py`
**输出**: `run_label_v2.py`（v2.2 标签体系）

**RISK_TYPES 17 → 20 项**:
- **新增** (5): 远程控制 / 代还套现 / 撸口子指南 / AI伪造 / 走私换汇
- **合并** (2→1): 山寨低质 + 伪冒仿冒 → 仿冒山寨
- **删除** (1): 隐私窃取（LLM 仅凭包名/app_name 无法可靠判断, 真要标走黑名单规则）
- **约束**: `未知` 仅当 `l1=未知` 时使用; `validate_label` 强制双向对齐, l1 已知但 LLM 给 risk=未知 时降级为 `其他高风险`

**新风险类型业务含义**:
| risk_type | 触发场景 | 策略价值 |
| --- | --- | --- |
| 远程控制 | TeamViewer/向日葵/AnyDesk 等 | 电诈高发, 高危信号 |
| 代还套现 | 信用卡代还/智能还款/花呗套现 | 反催收产业链上游 |
| 撸口子指南 | 网贷口子论坛/多头借贷指引 | 多头借贷强信号 |
| AI伪造 | 换脸/Deepfake/AI变声 | 反 KYC 伪造工具 |
| 走私换汇 | USDT 兑换/外汇黑市/跨境换汇 | 黑产洗钱关联 |

**SYSTEM_PROMPT 调整**:
- 顶部加 "L1/L2 = 功能, 风险全上 risk_type" 总原则
- 规则段 16 → 22 条, 新增 17-21 对应 5 个新风险类型, 22 条约束 risk=未知 用法
- FEW_SHOT_TEXT 加 6 条新示例覆盖远控/代还/口子/AI/USDT/仿冒

**未做的事**:
- L1 砍掉退化类目（银行/政务/旅游）—— 用户未选, 保留现状以免触发缓存全量重打
- 区块链 risk_type 拆 3 个 —— 用户未选, 保持现状
- 多标签 risk_type —— 同上

**备注**:
- 既有 SQLite 缓存里旧 risk_type (山寨低质 / 伪冒仿冒 / 隐私窃取) **不会自动迁移**;
  建议下次跑前手动执行: `UPDATE label_cache SET risk_type='仿冒山寨' WHERE risk_type IN ('山寨低质','伪冒仿冒'); UPDATE label_cache SET risk_type='其他高风险' WHERE risk_type='隐私窃取';`

### applist 打标稳定性加固 (v2.3)

**任务**: 检查打标逻辑, 确保稳定不造词
**脚本/工具**: `run_label_v2.py`
**输出**: `run_label_v2.py` (v2.3)

**排查到的不稳定源 + 修复**:
| 问题 | 修复 |
| --- | --- |
| 默认温度 (~1.0) → 同输入跨次结果可能漂移 | `temperature=0` |
| `app_l2` 无 enum 约束, LLM 可能造新 l2 名 | 新增 `ALL_L2` (扁平化 L2_MAP, 79 项), 写入 tool_use schema enum |
| `LLM未返回` / `LLM调用失败` 也写缓存 → 下次复用永久"未知", 不重试 | `run()` 里过滤后再 save_cache |
| SYSTEM_PROMPT 没明确禁止造词 | 总原则段加 "三字段必须严格从枚举选, 不允许自创新词/近义词/组合词" + "同输入应给出完全一致结果" |

**已经在 v2.1/v2.2 就稳定的部分** (无需改):
- `app_l1` / `risk_type` 在 tool_use schema 用 enum 约束
- `validate_label` 落库前白名单兜底 (l1 / l2 按 l1 归口 / risk_type)
- 同 pkg 在打标前已 `drop_duplicates`, 只会进同一 batch
- tool_use 返回顺序不定 → 用 `by_pkg` dict 重排对齐输入
- 规则前置 (RULE_LABELS / RULE_PATTERNS) 完全确定性
- SQLite 缓存 = 跨次稳定的最强保证

**剩余可控变动**:
- Anthropic 不承诺 temp=0 严格确定 (kernel 浮点非确定), 但漂移率应该 <1%
- 完美的 per-l1 l2 约束需要 JSON schema oneOf, 过于复杂, ALL_L2 enum + validate 已足够

**备注**:
- 旧缓存 (v2.0~v2.2 打的标) 仍有效, 不需要重打
- 如要彻底重置, 删除 `applist_label_cache_*.sqlite` 重跑即可

---

## 2026-06-05

### v2 打标体系 vs 0605_2 外部体系 对比分析

**任务**: 把 v2 当前标签体系(23 L1 / 79 L2 / 20 risk_type)与清洗后的外部 applist_tag_0605_2(35 L1 / 180 L2 / 7 risk_tag + 28 quality_tag) 做侧对侧对比, 找出 v2 体系的盲区与外部体系的可借鉴点.

**输出**: `对比_v2_vs_0605_2.md`

**关键发现**:
- v2 缺 3 个高 ROI risk_type: **诈骗 / 传销 / 跑分** (0605_2 共标 2631 个 app)
- v2 缺整个 **quality_tag (画像)** 维度 (0605_2 有 28 项, 1616 app)
- 0605_2 贷款 L2 拆 14 项, v2 只有 6 项, 建议补 网络小贷 / 持牌消金 / 租赁手机 / 投资类
- 工具 L2 0605_2 有 21 项, v2 9 项, 建议补 变声器 / 录屏 / 位置信息 (反诈强信号)
- 设计哲学: v2 "功能×风险" 二维正交更优, 0605_2 把"诈骗/赌博/涉黄/反催收"做成 L1 是历史包袱, 不要倒退
- v2 在 AI伪造/走私换汇/撸口子指南/代还套现 等新型欺诈上比 0605_2 更前瞻

**建议优先级**:
- P0: 补 risk_type = 诈骗 / 传销 / 跑分
- P1: 补 借贷 L2 + 工具 L2 细分
- P2: 引入 quality_tag 平行字段
- P3: 出双向映射, 互相回灌打标结果

**备注**:
- v2 体系整体设计胜出, 但风险标签集合需要扩充
- 0605_2 体量(154k app)远大于 v2 当前批次, 是宝贵的离线对账参考

---

### v3 打标脚本搭建 (基于 v2 + 0605_2 体系补充)

**任务**: 保留 run_label_v2.py, 新建 v3, 把对比文档识别出来的 P0+P1+P2 优化点全部落地.

**脚本**: `run_label_v3.py` (基于 v2 复制改造, v2 原文件保留)

**v3 变更**:
- [P0] RISK_TYPES 20 → 23, 新增 **诈骗 / 传销 / 跑分**
- [P1] 借贷 L2 6 → 10, 加 网络小贷 / 持牌消金 / 租赁分期 / 投资理财类
- [P1] 工具 L2 9 → 12, 加 变声器 / 录屏录音 / 位置信息
- [P1] 健康运动 L2 2 → 3, 拆出 严重疾病
- [P2] 新增 **quality_tag** 字段 (14 项画像), 与 risk_type 平行, 非互斥
- LLM tool schema 增 quality_tag enum 约束
- 缓存 schema 增 quality_tag 列 (新 sqlite 文件, 不污染 v2)
- 规则前置 RULE_LABELS/RULE_PATTERNS 全部改成 4 元组 (l1, l2, risk, qual)
- validate_label 增 quality_tag 校验; l1=未知 时 quality_tag 强制 = "无"
- Excel 增 "优质画像分布" + "画像命中明细" 两个 sheet
- 默认输出前缀 v2 → v3, 缓存独立 (`applist_label_cache_applist_tag_v3.sqlite`)
- 默认批次目录 `tagging_tmp/` → `tagging_tmp_v3/`
- FEW_SHOT_TEXT 增 ~15 条 v3 新风险/新 L2/quality_tag 示例
- SYSTEM_PROMPT 增 quality_tag 判定规则段, 强调"默认无, 强映射才填"

**校验**:
- 语法 OK; APP_L1=23, L2_MAP=23 keys, ALL_L2=87, RISK_TYPES=23, QUALITY_TAGS=14
- RULE_LABELS 43 条全部 4 元组, 长度无异常

**备注**:
- v2 缓存与 v3 缓存独立, 互不影响
- 跑 v3: `python run_label_v3.py` (默认全量 applist_tag.csv) 或 `python run_label_v3.py sample_200.csv` (自动加 _v3 后缀)
- v3 仍保持 v2 的设计哲学 (功能×风险二维正交), quality_tag 是**新增的第三平行维度**, 非破坏性扩展

---

## 2026-06-08

### 补主流 app 标签库 + 重跑三表合并

**任务**: 修复 `applist_tag_merged_v3` 缺主流 app (微信/支付宝/淘宝/抖音等) 的问题, 避免下游特征 LEFT JOIN 大面积 NULL.

**脚本/工具**:
- 新增 `mainstream_apps_v3.py` — 手工维护 Top 主流 app pkg→v3 标签字典 (277 条)
- 修改 `merge_applist_v3.py` — 新增 `process_mainstream()` + `overlay_mainstream()`, 优先级 mainstream > v2 > 0605

**输出**:
- `applist_tag_mainstream.csv` (277 行, v3 schema, confidence=0.99)
- `applist_tag_merged_v3.csv` 重生成: 234235 → **234320** 行

**关键数据**:
- mainstream 覆盖 v2/0605 重复 pkg: **192** 个 (微信/淘宝等以前被山寨壳包占位的, 现强制修正)
- mainstream 独有新 pkg: **85** 个 (例如未在两份外部源里出现的主流变体)
- 最终 source 分布: 0605_2=154333, v2_0522=79710, mainstream=277
- 抽检验证: WeChat/Alipay/Taobao/JD/Meituan/Douyin 全部正确归到 mainstream 源, L1/L2 标签符合预期

**备注**:
- Excel 落地失败 (`applist_tag_merged_v3.xlsx` 被打开占用), CSV 已写; 关闭文件后重跑即可补 xlsx
- mainstream 字典覆盖 17 个 L1 大类 (社交/电商/出行/金融/游戏/工具/系统应用等), 新增 app 时直接在 `mainstream_apps_v3.py` MAINSTREAM 列表加行

---

### 爬取小米应用市场 (4922 unique pkg)

**任务**: 拉一份常用 app 名单 (目标 1000+, 用户原需求) 作为后续 applist 标签库的补充数据源, 提升主流 app 覆盖.

**脚本/工具**:
- `crawl_xiaomi_market.py` — 走小米官方 `app.mi.com/categotyAllListApi` JSON 接口, 28 个 categoryId × pageSize 100 × 最多 10 页, sleep 0.5s, UA 伪装
- 探测过 wandoujia / app.mi.com / sj.qq.com / huawei / coolapk, 只有小米接口直接给干净 JSON (其它都是 SPA / 需 login / 需 headless)
- 加 `--remap-only` 子命令, 改 MI_L1_TO_V3 后从 raw json 重跑映射, 不必再爬

**输出**:
- `xiaomi_market_raw.json` — 原始 record 数组 (含 level1/2CategoryName, ratingScore, publisherName 等)
- `applist_tag_xiaomi.csv` — v3 schema, 4922 行, confidence=0.75

**关键数据**:
- 28 个 categoryId, 前 14 个非游戏类各拉满 300 条; 游戏类 cid 重叠多, 去重后实有 4922 unique pkg
- L1 分布: 游戏 2523, 阅读资讯 599, 健康运动 599, 生活服务 600, 教育学习 318, 其他 8 类各 300
- 与 mainstream (277) 重叠 67 个 (主流 app 已覆盖); 与 merged_v3 (234320) 重叠 2765 个; **xiaomi 带来 brand-new pkg 2157 个**
- 抽检知名 pkg (淘宝/美团/抖音/快手/网易云/王者荣耀等) L1 全部正确; 微信/支付宝等不在小米分类 Top 列表里 (但已被 mainstream 覆盖, 无影响)

**备注**:
- 小米 L2 字面值大多不在 v3 词表 (例如"美食"/"音乐"/"短视频"), 目前 v3 L2 用该 L1 第一个合法值兜底, **L1 准但 L2 偏粗**; 后续若需更细 L2, 可针对 L1='视频影音' 拆 短视频/长视频/音乐 等 sub-rule
- xiaomi 上架 app 已过审, risk_type 全部 "无", 合理 (符合实际, 不是 mapping 失败)
- 是否接入 `merge_applist_v3.py` 作为第四源待用户决策: 接入会修正 2765 个已有 pkg 的标签 (xiaomi L1 比 0605 LLM 标签更准), 但 confidence 0.75 < mainstream 0.99 > v2 0.8 ≈ 0605 0.7, 建议优先级排 mainstream > xiaomi > v2 > 0605

---

### xiaomi 标签源接入 merge_applist_v3

**任务**: 将 `applist_tag_xiaomi.csv` (4922 行) 并入 `applist_tag_merged_v3.csv`, 提升 unique pkg 覆盖.

**脚本/工具**: 修改 `merge_applist_v3.py` 新增 `process_xiaomi()` + `overlay_xiaomi()`.

**接入策略**: xiaomi **仅补新 pkg, 不覆盖现有标签** (保守路线)
- 理由: xiaomi 上架 app 全是 risk_type='无', 直接 override 会冲掉 v2/0605 精修过的赌博/诈骗/反催收等风险标签
- 重叠的 2765 个 pkg 维持原 source 标签不动 (v2/0605/mainstream)
- 优先级链: `mainstream(全覆盖) > v2+0605(原合并逻辑) > xiaomi(仅补新)`

**输出**:
- `applist_tag_merged_v3.csv` 重生成: 234320 → **236477 行** (+2157)

**关键数据**:
- source 分布: 0605_2=154333, v2_0522=79710, xiaomi_market=2157, mainstream=277
- xiaomi 与现有重叠 2765 个 (跳过, 保留现 label)
- xiaomi 独有新 pkg 2157 个 (全部进入)

**备注**:
- 若后续发现 0605 LLM 在某些 L1 上系统性偏差 (如 121/123 系列), 可考虑升级 overlay_xiaomi 为"对 source=0605_2 的行用 xiaomi L1 覆盖, 保留 risk_type/quality_tag", 当前先稳为主
- xlsx 落地失败仍是文件被打开占用问题, CSV 已最新

---

## 2026-06-10

### 规则挖掘工具 rule_miner v0.1.0

**任务**: 从样本中挖掘高 lift 的反欺诈规则池（决策树森林 + 多维评估 + 灵活 filter）

**脚本/工具**: 新建 Python 包 `规则挖掘/rule_miner/`（12 个模块）+ TDD 全套测试 + 设计文档/实施计划

**输出**:
- `规则挖掘/rule_miner/` — config / preprocess / rule_extractor / miner / evaluator / filter / dedup / cache / result / exporter / api（共 11 个核心模块 + __init__）
- `规则挖掘/tests/` — 47 个单元/e2e 测试，全绿
- `规则挖掘/examples/demo.py` — 5000 行样本完整演示
- `规则挖掘/specs/2026-06-09-rule-mining-design.md` — 设计文档
- `规则挖掘/plans/2026-06-09-rule-mining-plan.md` — 14 步实施计划

**关键数据**:
- 1000 行样本 e2e：~55s
- API：`mine_rules(df, inputx, y, primary_key, dt=, cust_group=, filter_query=, ...)`
- 支持 `cust_group=None`（全局模式）与命名客群两种工作流
- pandas query DSL + QueryBuilder 链式 API
- Excel 多 sheet 输出（配置参数 / 客群分布 / 规则汇总 / 全局有效 / 各客群有效 / 跨客群矩阵 / 按月稳定性）
- pickle + sha256 缓存（同 (df, config) 二次跑直接走缓存）

**备注**:
- pandas 3.0.2 已知坑：`freq='6H'` 改 `'6h'`；`df.replace([list], scalar)` 触发 IndexError，改用 `mask(isin(...))` 绕过
- 中途 Subagent 派发碰 Cloudflare 524 超时，改为顺序实现
- code-reviewer 找出 3 个 critical（group_map 键类型 / n_jobs 未透传 / primary_key 死参数），已提交修复

---

## 2026-06-10

### 清理 applist CSV 的 app_name（为 StarRocks Stream Load 准备）

**任务**: 把 `applist_tag_merged_v3.csv` 的 `app_name` 列里所有逗号/空格/Tab/全角空格/零宽字符替换为 `-`，避免 Stream Load 解析字段错位。
**脚本/工具**: `clean_app_name.py`（pandas）
**输出**:
- `applist_tag_merged_v3_clean.csv`（UTF-8，无 BOM，236477 × 9）
- `applist_tag_merged_v3_clean.sample.csv`（前 20 条改写示例，UTF-8 BOM 方便 Excel 看）

**关键数据**:
- 总行数 236,477
- app_name 被改写 12,952 行（5.5%）
- 清理后 app_name 空/全分隔符 6 行（需人工核查）
- 清理后 app_name 残留逗号/空格 0 行
- `reason` 列原本有 470 行含逗号（被引号包裹，标准 CSV 行为，pandas 正常解析）

**备注**:
- 用 `re.sub(r'[\s,，​-\u200F⁠]+', '-', s)` 一次覆盖半角逗号、全角逗号、各种空白和零宽字符
- Windows GBK 终端 print 含 `‍` 的样本会 UnicodeEncodeError，改成把示例写文件
- 后续 Stream Load 用这个 clean 版本即可

---

## 2026-06-29

### 封装 skill：sample-feature-join-sql（样本表 × 特征宽表 关联聚合 SQL 生成）

**任务**: 把“样本表关联线上特征宽表、保留样本全字段 group by、对每个特征取 max() 去重重命名为同名”这套反复出现的逻辑标准化为可复用 skill，后续相似取数直接调。

**产物** (`C:\Users\d02206\.claude\skills\sample-feature-join-sql\`):
- `SKILL.md` — 触发条件 / 工作流 / 配置速查表 / 常见坑
- `gen_feature_join.py` — 通用生成器（配置驱动，逻辑不动，改 config 即可）
- `example_config.py` — 配置模板，复制即用

**相比上次一次性脚本的提升**:
- 关联键/样本字段/特征表/筛选规则全抽成 config，新任务不碰代码
- 关联键支持联合键 `[(s1,f1),(s2,f2)]`
- 筛选可选可组合：时间窗上限 + include 白名单 + exclude 黑名单；删 filters 即取全量
- 新增 `column_file` 与真实表列取交集，堵 unknown column 风险
- 多 target 批量产出（贷前/贷中一次跑完）

**验证（按 writing-skills 的 TDD 流程）**:
- 自验：全量 1806 列 / 过滤 470 / 20 列三种模式均生成结构正确 SQL
- 派全新 subagent 仅凭 skill 文件做陌生场景（apply_no=flow_no、≤7天、screenshot/bind_card）→ 命中 20 特征，SELECT/LEFT JOIN/GROUP BY 与关联键全对（GREEN 通过）
- 按 subagent 暴露的盲点补文档：输出路径 = out_dir + out 拼接；无窗口标志位需 nowindow_keep_regex 显式保留

**备注**:
- 控制台中文乱码 + `.bashrc` BOM 噪声是环境显示问题，不影响生成结果
- 调用方式：说“用 sample-feature-join-sql 关联 XX 样本和 XX 特征表”，或复制 example_config.py 改完跑 `python gen_feature_join.py 你的config.py`

## 2026-07-02

### 开源声纹相似度比对 demo

**任务**: 用开源模型做录音声纹比对，支持 1:1 判同人 + 1:N 声纹库检索，服务代理黑产/S4声音比对异常标签场景
**脚本/工具**: SpeechBrain ECAPA-TDNN (spkrec-ecapa-voxceleb)
**输出**: `声纹对比/voiceprint_compare.py`、`声纹对比/requirements.txt`
**关键数据**: 192维声纹向量，L2归一化后余弦相似度；默认阈值0.30(VoxCeleb经验值，需用业务数据标定)
**备注**: 三子命令 verify/enroll/search；音频自动转单声道+重采样16kHz；电话录音8kHz窄带需另标定阈值，必要时换中文电话场景模型(3D-Speaker/WeSpeaker)。尚未在真实数据上测试。

### 声纹比对 demo 真实录音实测 + 阈值标定尝试

**任务**: 用 5 段真实 m4a 录音跑声纹相似度矩阵，验证 demo 可用性并尝试标定判同人阈值
**脚本/工具**: 新增 `声纹对比/convert_to_wav.py`(m4a→16k单声道wav)、`声纹对比/eval_matrix.py`(N×N相似度矩阵+按真实标签算区分度)；模型 ECAPA-TDNN
**输出**: `声纹对比/convert_to_wav.py`、`声纹对比/eval_matrix.py`、`声纹对比/wav_16k/`
**关键数据**: 真实标签 A={1,3}、B={2,4}(1_1为1的复制)。同人对 1vs3=0.312、2vs4=0.477；异人对最高 1vs4=0.285。同人最低(0.312)与异人最高(0.285)间隔仅 0.027，阈值0.30下4段真实录音全分类正确，但间隔过窄不稳；A某同人分0.312偏低(疑录音过短/信道差)
**备注**: 环境踩坑连环——(1)默认源torch含CUDA达2.5GB下载卡死，改CPU版124MB；(2)torch2.12在Win报WinError1114,需装VS2022 VC++运行库(旧版14.28不够);(3)torchaudio2.11默认后端需torchcodec,改用soundfile读wav;(4)huggingface_hub1.21与speechbrain1.1不兼容,降级到0.36;(5)HF被墙,走HF_ENDPOINT=hf-mirror.com;(6)Win建符号链接需管理员权限,改LocalStrategy.COPY。结论:工程链路已通,但当前样本无法可靠标定阈值,需每人3~5段≥10秒不同录音;电话窄带建议换中文模型

### 声纹对比工具整理 + 使用文档

**任务**: 整理声纹对比历史记录，生成完整使用 md 文档
**输出**: `声纹对比/README.md`
**关键数据**: 汇总能力清单(verify/enroll/search/eval_matrix/convert)、环境准备(CPU torch/VC++运行库/HF镜像)、使用步骤、阈值标定说明、2026-07-02 实测记录(含相似度矩阵表)、8项常见坑速查表
**备注**: 文档把之前分散在两条日志里的踩坑与实测数据固化下来，便于复现和交接

## 2026-07-09

### 催收录音声纹对比分析(4通电话,查换号作案)

**任务**: 对 0709 文件夹 4 通催收电话录音做声纹对比,判断不同通话中的客户是否同一人(识别换号/黑产代理)
**脚本/工具**: 新增 `声纹对比/split_channels.py`(双声道拆分+限长截取);复用 eval_matrix.py(新增 --wav-dir);convert_to_wav.py 通用化(支持指定目录+mp3等格式)
**输出**: `声纹对比/0709/声纹分析报告.md`、`声纹对比/0709/channels/`(8个拆分声道wav)、`声纹对比/split_channels.py`
**关键数据**: 4通均双声道分离(左右相关≈0)含坐席+客户;4通同工号N00000020170。8×8矩阵聚类出两簇——簇A(坐席):0417_L↔0511_L=0.924等(0.80~0.92);簇B(疑似同一客户):0417_R↔0511_R=0.709/0408_L↔0417_R=0.666/0408_L↔0511_R=0.635。核心发现:0408/0417/0511三通疑似同一客户用3个不同号码(914787018349/152******43/155******70),符合换号作案特征。0228独立/证据弱
**备注**: (1)a段25分钟整段编码内存爆(需5.5GB),改分声道+截60秒;(2)脚本自动同人标签失效(L/R是双方两人,非同人),改人工聚类判读;(3)结论是线索非定论——簇B仅0.63~0.71(ECAPA英文模型+8kHz窄带拉低),同人异人分数重叠0.751,未做说话人分离。建议:人工听音复核/换中文模型(3D-Speaker/WeSpeaker)/加diarization/业务侧查号码关联客户号

### 声纹分析交叉验证(VAD去静音 + CAM++中文模型)

**任务**: 对上一步初步结论做多模型交叉验证,提升换号嫌疑置信度
**脚本/工具**: 新增 `声纹对比/vad_trim.py`(纯numpy能量VAD去静音,离线代替pyannote)、`声纹对比/eval_campp_zh.py`(3D-Speaker CAM++中文模型 via ModelScope);eval_matrix.py 加 --wav-dir
**输出**: 更新 `声纹对比/0709/声纹分析报告.md`(增补五之二交叉验证章节)、`vad_trim.py`、`eval_campp_zh.py`、`0709/channels/vad/`
**关键数据**: 三方法对比客户簇B最强对 0417_R↔0511_R: ECAPA原始0.709→ECAPA+VAD0.650→CAM++中文0.805(跨过0.8高置信线),另两对CAM++下0.665~0.682。坐席簇A三法稳定0.785~0.918。两簇结构三个独立方法完全一致。结论升级为"三方法一致确认,置信度中高",仅缺人工听音复核
**备注**: (1)pyannote模型gated+HF被墙,改能量VAD离线绕开;(2)ModelScope(阿里)国内直连不受墙,但py3.14装modelscope后连环缺依赖addict/datasets/einops等,逐个补齐;(3)VAD版分数略降(能量法留高能噪声+数据变少)但结构不变,反而印证聚类稳定;(4)CAM++如预期把中文窄带客户簇顶过0.8。处置建议:人工听音+业务侧查3号码是否关联不同客户号→命中S1代理号码关联标签

## 2026-07-10

### 声纹分析语音转文字验证(FunASR)

**任务**: 用户不便听录音,改用语音转文字定坐席/客户角色,并挖掘话术中的代理黑产信号
**脚本/工具**: 新增 `声纹对比/transcribe.py`(FunASR Paraformer中文ASR+VAD+标点,走ModelScope);`声纹对比/_editdistance_stub/`(纯Python editdistance替身包)
**输出**: `声纹对比/0709/转录文本.md`(8声道全文)、更新 `0709/声纹分析报告.md`(增补五之三转录验证章节)、`transcribe.py`、`_editdistance_stub/`
**关键数据**: 转录内容100%印证声学聚类——6声道角色全吻合:簇A(坐席)=0408_R/0417_L/0511_L念"深圳融合/征信业管理条例/身份证后四位";簇B(客户)=0408_L/0417_R/0511_R诉求一致(深圳融合+征信代偿+要求消记录)。话术直接暴露黑产信号:①律师代理投诉(近S13)②要求删征信(核心诉求)③同一人声+多号码+模板化诉求(近S6/S7)。结论升级为声学+文本双证据链,角色反推软肋消除,仅剩业务侧查号码-客户号关联
**备注**: (1)editdistance是C扩展,py3.14无wheel+本地无编译器→做纯Python Levenshtein替身包(version=0.8.1)满足依赖后funasr正常装;(2)装funasr时huggingface_hub被升回1.x,后续再跑ECAPA需重新降级(转录走ModelScope不受影响);(3)最终定性:三号码关联不同客户号=实锤代理黑产命中S1,同一客户号=异常维权S11/S13

## 2026-07-14

### 客服黑灰产识别策略框架设计

**任务**: 为客服中心设计黑灰产识别策略框架,三场景调用(电话进线/外呼/在线客服),入参客户号+手机号,输出风险标签,1秒返回
**脚本/工具**: 无(策略设计文档)
**输出**: `客服黑灰产识别策略/策略框架设计.md`
**关键数据**: 分层架构(场景适配/决策/规则/数据);标签体系"{风险大类}-{命中原因}"(确认黑产/疑似黑产/异常维权/关注客户),映射现有dws_anti_fraud_agent_label_df的S1~S14;策略清单按7维度共30+条(号码/设备/APP/通讯录/通话记录/逾期/地理),含用户提的5条基础策略;实时性分三档:真实时(号段/设备指纹/黑名单)/准实时预聚合(一号多客户等计数类,读计数表+增量更新)/离线T+1(通讯录团伙/窝点/声纹)
**备注**: (1)关键修正——用户明确特征需实时计算,推翻初版"全部离线T+1"设计,改为"预聚合计数+实时增量"兼顾1秒约束;(2)双主键结果表(rt_risk_label_by_cust/by_phone),手机号→客户号映射离线固化避免实时join;(3)待办:标签字典定稿(触发口径+映射S1~S14+等级)、结果表DDL、离线写入SQL、各阈值N标定、数据接入覆盖率确认(通讯录/通话/applist受采集权限限制)

### 确认反欺诈线上规则是否用到待下线特征变量

**任务**: 对比待下线特征清单与反欺诈线上规则,确认有无被使用的特征(下线前排查影响)
**脚本/工具**: 新增 `线上策略管理/check_offline_features.py`;数据源 `反欺诈策略文档.xlsx`(最新规则20260713 sheet的规则条件_中英文列,352条非空规则) + `待下线特征变量确认.xlsx`(两个sheet)
**输出**: `线上策略管理/待下线特征命中确认结果.xlsx`(命中明细x2 + 汇总)
**关键数据**: 严格匹配后确认5个待下线特征被线上规则使用,共14条规则:cust_age(7条,含年龄拒绝/疑似学生拒绝等硬拒绝)、apply_channel(3条)、mobile_hit_risk_relation_mobile(2条)、channel_code(1条)、dk_fail_AccountBad_cnt_90day(1条)。两份清单去重各3077特征(副本原3274含197重复),交集2705/各有372独有
**备注**: (1)匹配逻辑关键——线上特征名是"英文名_中文描述"拼接,待下线是纯英文名,用带边界正则匹配;(2)初版宽匹配误报2个假阳性(regist_channel/pdl_app_cnt实为更长的regist_channel_chinese/pdl_app_cnt_PDL且不在清单),严格匹配(英文名后须紧跟_中文或运算符)剔除;(3)建议:5个特征下线前push规则维护方做替代,尤其cust_age涉及硬拒绝规则

## 2026-07-24

### 声纹项目 P1:CAM++ 黑产声纹库 + 1:N 检索 + 0709 三通独立复核

**任务**: 补齐声纹 P1 核心交付——(1)把 1:N 检索从 ECAPA 升级到 CAM++;(2)建黑产声纹库;(3)用全新自动管线(diarize→CAM++)独立复核 0709"同一客户换 3 号"结论
**脚本/工具**: 新增 `声纹对比/voiceprint_campp.py`(CAM++ 声纹库,子命令 verify/enroll/search/info,走 FunASR AutoModel 取 192 维 spk_embedding);复用 `声纹对比/diarize.py` 跑完 0417/0511
**输出**: `声纹对比/voiceprint_campp.py`、`声纹对比/black_db.pkl`(黑产库种子,3 条客户声纹)、`声纹对比/0709/diar_out/` 下 0417+0511 的 _diar.json/_对话.md/_spk{0,1}.wav
**耗时**: 约 1.5h(CPU 上 0511 分离+大段 embedding 较慢,均后台跑)
**关键数据**: 6 段(3 通×2 人)CAM++ 全量矩阵——**客户 vs 客户跨通 0.584/0.652/0.657**(成簇,均>0.5 阈值),**坐席 vs 坐席跨通 0.788/0.818/0.926**(实为同一催收坐席,新发现),客户 vs 坐席跨角色仅 0.219~0.434(干净异人基线)。结论"三通同一客户换号作案"由独立自动管线复核成立,与此前手动声道分离结论一致
**备注**: (1)再次确认关键坑——modelscope.pipelines 在 py3.14 仍段错误(退出码139),CAM++ embedding 必须走 FunASR AutoModel(model='cam++'),实测正常产出 spk_embedding (1,192) float32;(2)客户段自相似(0.58~0.66)低于坐席段(0.79~0.93),合理:客户 3 个不同号码/终端/信道变化大,坐席同一话务中心同设备;(3)阈值 0.50 为电话场景临时经验值,仍需按交接 task3 用可标注数据标定电话/高清两套阈值;(4)每次 CLI 调用重载模型约 60s,批量任务应在单进程内一次加载(脚本已做懒加载单例)

### 声纹 P1:0228 补跑 + 1:N 检索实证,换号作案扩到 4 号

**任务**: 跑完 0709 案第 4 通 0228(25分钟,第 4 个号码 135******78),用 black_db 做 1:N 检索判断是否同一换号客户,顺带实证 1:N 检索管线在库外真实录音上的效果
**脚本/工具**: diarize.py(分离 0228) + voiceprint_campp.py 的 embed/search 逻辑
**输出**: `0709/diar_out/` 下 0228 的 _diar.json(441句)/_对话.md/_spk{0,1}.wav;`black_db.pkl` 扩到 4 条(新增 0709case1_客户_0228)
**关键数据**: 0228 两段各自 vs black_db(0709三段客户):**spk0 命中**(0.607/0.596/0.577,均值0.593,与三通客户互相 0.58~0.66 同量级),spk1 未命中(0.392/0.341/0.284,坐席基线)。→ 第 4 个号码也是同一反催收黑产客户,案件从 3 号扩到 4 号;文本诉求("三笔被记成代偿金额,要求查处理")与前三通一致,声学+文本双印证。同时证明 1:N 管线:库外新录音进来能正确命中同人、排除坐席
**备注**: (1)0228 diarize 在 CPU 上约 40+ 分钟,spk 段 17/21MB,embedding 提取也慢,均后台跑;(2)角色不靠猜——把两个说话人段都丢进 1:N,让声纹自己决定谁匹配客户簇,比读对话稿猜角色更稳

## 2026-07-28

### 声纹项目:说话人分离改用双声道天然分离,消除模糊边界

**任务**: 现有分离有模糊边界、同一时间出现两人声音;录音底层是双轨(一方一声道),优化分离
**脚本/工具**: 改造 `声纹对比/diarize.py`(仅此一个文件);实测源文件确认双轨特征
**输出**: `声纹对比/diarize.py`(新增 `_is_dual_track`/`_extract_channel`/`_diarize_dual_track`/`_diarize_mixed`,`_export_per_speaker` 支持按声道切片)
**耗时**: 约 1h(含探索、实测声道特征、验证 1 通样例)
**关键数据**: 实测源为 stereo 8000Hz,左右声道相关系数≈0,92% 发声时间是单方独占(左独占59%/右独占33%/真实重叠仅9%)→ 信号底层已天然分好。旧流程 `data.mean(axis=1)` 混单轨再 CAM++ 聚类,等于把已分好的信号揉碎再猜,模糊边界即由此产生。新方案:双轨时左=说话人0/右=说话人1,各声道独立转录后按时间戳归并;非双轨自动回退 CAM++。样例(20260529-145252 一通)验证:34句,坐席话术全部稳定归 spk0(20句/48.4s)、客户诉求全部归 spk1(14句/29.9s)零错配,真实抢话正确呈现为两条时间重叠句;输出格式(_diar.json/_spkN.wav/_对话.md)不变,下游 analyze_0727.py 零改动
**备注**: (1)关键坑——不带 spk_model 的纯转录模型不输出 sentence_info(拿不到句级时间戳),所以双轨模式仍用带 cam++ 的模型,只是忽略其聚类 spk、把说话人强制设为声道号;(2)双轨模式 spk 音频从各自声道独立 wav 切片(非混音),避免切进对方串音,提纯声纹供后续比对;(3)新增 `--force-mixed` 可强制走旧聚类逻辑;(4)按用户要求仅改代码+验证 1 通,已有 0709/0727 批次未重跑(需要时可批量重跑覆盖)

### 声纹项目:用双轨方案重跑 0709 全部 4 通录音

**任务**: 按新的双声道天然分离方案重跑 0709 案 4 通录音,覆盖旧的 CAM++ 聚类结果
**脚本/工具**: `声纹对比/diarize.py`(双轨模式);单进程循环调用,模型只加载一次(避免每通重载 60s)
**输出**: 覆盖 `声纹对比/0709/diar_out/` 下 4 通的 _diar.json/_spk{0,1}.wav/_对话.md
**耗时**: 约 15 分钟(4 通含 0228 长录音,单进程复用模型;比老日志"0228 单通 40+ 分钟"快很多)
**关键数据**: 4 通检测全部 dual_track=True,均干净分成 2 个说话人。0228(24分钟)453句(spk0 915s/spk1 772s)、0408 41句(spk0 90.8s/spk1 73.7s)、0417 46句(spk0 90s/spk1 60.5s)、0511 215句(spk0 323s/spk1 280s)。抽查 0408 对话稿:坐席("深圳银河的"+身份核验+引导话术)归 spk1、客户(征信被追偿诉求)归 spk0,角色零错配,真实抢话正确呈现为时间重叠的并行句
**备注**: (1)说话人编号规则变为 spk0=左声道、spk1=右声道(固定),与旧 CAM++ 聚类的编号无必然对应关系——若后续要复用 0709 的 embedding 缓存需重新提取;(2)0727 批次本次未重跑,如需一致口径可同样跑 `python diarize.py <录音> --out-dir 0727/diar_out`


## 2026-07-28

### 0728 批次声纹比对(10 客户号 x 2 段)

**任务**: 判断每个手机号的两段录音是否同一人(换号/代打检测)
**脚本/工具**: 声纹对比/0728/compare_0728.py (拆左右声道 -> CAM++ 192维 -> 同号 seg1{L,R}x seg2{L,R} 2x2 交叉余弦, 取最高分判定)
**输出**: 声纹对比/0728/0728_声纹比对结果.md; 中间件与 emb 缓存在 0728/work/
**关键数据**: 10/10 判同一人; 跨段最高相似度 0.734~0.932(阈值 0.50); 最高声道对不固定(s1R-s2R/s1L-s2L/s1R-s2L 皆有),故不预设声道靠矩阵反推
**备注**: 8k 双声道电话录音,一方一声道,拆声道后近纯净单人,规避串音。多号客户声道跨段相似度也偏高(如 136******93 s1L-s2R=0.587),提示两段坐席与客户可能都同人;阈值 0.50 为临时经验值,待标注标定


## 2026-07-28

### 0728 声纹方案扩展: 角色识别 + 异人对/阈值标定

**任务**: 在同号比对基础上, ①识别每通录音的坐席/客户声道 ②构造异人对标定 8k 判同阈值
**脚本/工具**: 0728/run_diarize.py(批量diarize转写) + 0728/role_id.py(话术判角色) + 0728/calibrate.py(EER标定); 复用 diarize.py/voiceprint_campp.py
**输出**: 0728/diar_out/(20段转写+40声道wav)、0728/角色识别结果.md、0728/roles.json、0728/阈值标定结果.md
**关键数据**:
  - 角色识别: 20段, 14段高/中置信, 6段话术接近需核对; 人工抽验(153******53(1)/177******17两段/186******58(1))全部判对; 坐席声道在同号两段间会翻转, 靠转写判角色不预设声道
  - 阈值标定: 同人190对/异人590对, 但EER高达48.9%、两分布均值均0.449完全重叠
  - **重要结论**: 坐席并非同一人(坐席两两相似度均值0.449/最小0.192), 这10通由多个不同坐席拨打, 本批不含任何已知同人对, 不具备阈值标定条件, 已在报告中明确不给误导性阈值
  - 唯一可靠产出: 异人对分布可信, 8k下不同人相似度也可高达0.7~0.9(95分位0.709), 线上判同阈值须高于异人95分位
**备注**:
  - 探索期证据B(跨通复现度)在8k上不可靠(相似度地板高), 已降级为参考列, 改以话术密度为主+先开口兜底
  - 要真正标定阈值需补数据: 首选同一客户多通录音(贴合换号检测); 或多坐席按簇内配对
  - 副产物信号: 多坐席现象本身可用于坐席换人/多坐席协作/窝点分析


## 2026-07-29

### 声纹系统上线版: 组件收敛 + 固化管线 + 建库 + 实时核验

**任务**: 把探索期脚本固化成可上线可复用系统(固化提取管线+离线建库+实时核验+画像预留)
**脚本/工具**: 新建 common/(embedding,audio_io,vad,diarize,role_id,calibrate,vpdb,cluster,denoise,extract) + pipelines/(build_customer_db,build_black_db,verify_realtime) + acoustic/profile(预留); 复用 CAM++/FunASR 路线
**输出**: 声纹对比/common/*, 声纹对比/pipelines/*, data/customer_db.pkl(10客户号/19模板), data/black_db.pkl(9条/2actor), 两份建库报告
**关键数据**:
  - 阶段A组件收敛: common 复现 0728 标定 EER=10.0%/阈值0.725/同人0.801/异人0.520, 与重构前逐位一致
  - 阶段B固化管线 extract_customer_embedding: 提的向量 vs 基线余弦 1.0000
  - 阶段C建库+主簇聚类(连接阈值0.725): 8个客户号同号两通聚成主簇(ok); 181******21两通0.545<阈值->2簇undecided; 153******53段1角色低置信隔离->单通undecided。冷启动本人vs代接逻辑成立
  - 阶段D实时核验(1:1+1:N三段决策带0.634/0.751): 库内客户验本人=本人(1.0命中); 换号验=非本人告警(0.518); undecided客户=证据不足(不硬判); 黑产1:N无误报
**备注**:
  - 硬约束遵守: Python3.14禁用modelscope.pipelines(段错误), 全走funasr.AutoModel; CPU-only; faiss未装用pickle+矩阵运算
  - 库schema扩展: 身份单元=客户号/actor_id, 支持一人多号/多模板/本人vs代接; search_by_identity按身份max-pooling
  - 降噪(阶段E)默认OFF留可开关骨架, 学术证据表明独立降噪可能损害声纹, 需装clearvoice后A/B验证(EER对比)才纳入, 尚未做
  - 兼容: 现有voiceprint_campp/diarize CLI保留, 实现下沉common; 旧脚本不受破坏


## 2026-07-29

### 降噪 A/B 实验(阶段E): FRCRN 降噪不纳入

**任务**: 验证 FRCRN 降噪对 8k 电话客户声纹判同是否有正收益, 决定是否纳入固化管线
**脚本/工具**: common/denoise.py(接入ClearVoice FRCRN_SE_16K) + 0728/denoise_ab.py(两阶段进程隔离)
**输出**: 0728/降噪AB实验结果.md(结论文档); denoise.py 保持 ENABLED=False
**关键数据/结论**: **不纳入**。未能产出EER对比 —— FRCRN在真实客户声道上无法稳定运行:
  - clearvoice依赖numpy<2.0/soundfile==0.12.1, 与环境(numpy2.4/py3.14)冲突; --no-deps+补yamlargparse/pydub后可import
  - 合成音频冒烟测试通过; 但真实客户声道: FRCRN+CAM++同进程段错误(139), 进程隔离后单跑FRCRN对10s+真实音频仍超时/崩溃(124/139)
  - 根因: clearvoice内部数据路径在numpy2.0+/CPU上原生不兼容
**备注**:
  - 印证方案§七预判(降噪有环境风险须先验证)+ 学术证据(独立降噪可能损害声纹)
  - 主系统(提取/建库/核验)不依赖降噪, 全部不受影响, 均已验证通过
  - 重启降噪需: 独立GPU环境 + numpy<2隔离依赖, 且仍须过A/B正收益判据
  - 至此上线版声纹系统 阶段A-E 全部收尾: 组件收敛/固化管线/建库/实时核验 已上线可用, 降噪明确排除


## 2026-08-13

### 搭建客服策略命中率监控看板(观远BI)

**任务**: 用数据集「反欺诈客服策略监控」搭建策略监控看板,体现各条策略在日/周/月粒度的具体命中率 + 趋势,发布到 风险运营部/反欺诈策略室/客服实时策略命中率监控 目录
**脚本/工具**: guanvis skill(DSL) + guancli;源文件 客服策略监控看板/(6 card + 3 selector + page.js)
**输出**: 线上页面 p851469e01d55d0f39a8136f「客服实时策略命中率监控」
**关键数据/设计**:
  - 参考「反欺诈规则命中率」报表模式,弃用大盘 KPI 大数字,改为 策略×时间粒度 的命中率矩阵 + 趋势
  - Tab 分 日/周/月 三粒度;每粒度内:上=命中率透视表(行 strategy_name×target_risk_tag,列 period_label,值 命中率=SUM(hit_cnt)/SUM(total_cnt)),下=命中率趋势 MULTI_LINE(x=period_start_date,按 strategy_name 分多条线)
  - 每卡带 period_type IN [D/W/M] 卡级过滤,避免三粒度混算重复计数
  - 全局筛选器: 分析口径(客户/订单默认客户)、样本范围(全部/投诉默认投诉)、策略(多选下拉)
  - 数据维值确认: period_type=D/W/M,dimension_type=CUSTOMER/ORDER,sample_type=COMPLAINT/ALL,strategy 共 6 条具体 + 1 条「全部策略(按标签优先级重算)」整体行
**备注**:
  - 趋势多序列: BASIC_LINE 不支持 column 分色,改用 MULTI_LINE + addColumn(strategy_name) 才过校验
  - 覆盖旧 KPI 版失败: --allow-overwrite 触发的「覆盖前备份导出」任务在本 BI 版本连续失败(疑似版本不支持,类同 execute-sql),且 guancli 无删页命令;改用全新 page ID 发布绕过。旧 KPI 版页面(h1f37fb014b22778679a1d44)仍在同目录,需在 BI 界面手动删除
  - move page 报 1012「页面已在目标目录中」为无害冗余步骤,setParentDir 已放对位置

### 客服策略监控看板 v2 迭代(观远BI)

**任务**: 三项改动 —— ①新增整体调用量趋势(客户数/订单数) ②切片器名改中文 ③把「全部策略」整体口径从各策略区拆出
**脚本/工具**: guanvis skill;源文件 客服策略监控看板/(7 card + 3 selector + page.js)
**输出**: 新线上页面 n0d4c064138f268fa377e7a4「客服实时策略命中率监控」(v1 的 p851469... 需手动删)
**关键数据/设计**:
  - 结构重排为两区:①整体总览区(区标题+调用量趋势卡,口径固定 IN[全部策略]) ②分策略区(区标题+日/周/月 Tab)
  - 分策略区 6 卡全部加 strategy_name NOT_IN[全部策略],矩阵/趋势只留 6 条具体策略
  - 调用量趋势卡: CASE WHEN 按 dimension_type 拆两条线(调用客户数/调用订单数=SUM(CASE WHEN dimension_type='CUSTOMER'/'ORDER' THEN total_cnt END)),因此该卡不随「分析口径」切片器过滤
  - 切片器名改中文(分析口径/样本范围/策略);分析口径+策略只 linkTo(0..5) 联动分策略卡,不动整体调用量卡(否则拆线被砍);样本范围 linkToAll
  - 区标题用 createAreaTitle(...).addAreaTitle() 放根布局(不能进 tab panel)
**备注**:
  - **切片器按钮值中文未解决**:selector 绑数据集原始字段,按钮显示的就是原始值(CUSTOMER/ORDER/ALL/COMPLAINT)。绑中文映射计算字段会导致按该字段过滤、匹配不上原值→筛选失效。干净做法须在数据集/ETL 加一列中文映射(如 dimension_type_cn),再把切片器绑到该列。本次只改了切片器"名字"为中文,按钮值待数据集加映射列后再处理
  - Duplicate field '调用订单数' 警告为误报(fdId 赋值前触发,实际两指标 fdId 不同),同前次「目标输出命中率」误报
  - 覆盖发布备份导出仍失败,继续用全新 ID 发布绕过

### 客服策略监控看板 · T+1 剔除「今天」残缺数据(方案确认)

**任务**: 看板是 T+1,今天数据未入库,日粒度「今天」列/点残缺,须剔除
**脚本/工具**: guancli ds preview 排查 + guanvis 时间宏 API 核查;暂未改看板文件
**输出**: 方案敲定,待数据侧加列后一次性发布;经验已沉淀进《观远BI看板制作指南.md》第四节
**关键数据/结论**:
  - 排查确认: is_complete_period 标记「日历周期是否走完」,非「数据是否入库」。日粒度它恒为 1(连今天 08-13 也是,total 23008 vs 昨天 62727),靠它剔不掉今天;只有进行中周/月为 0
  - 卡级过滤只支持固定值,写不了「< 今天」;TIME_MACRO 时间宏能做相对日期但只匹配日期字段,透视表列绑字符串 period_label 匹配不上
  - **定案**: 数据侧加自愈判断列 is_data_ready = IF(period_start_date < CURRENT_DATE, 1, 0)(BI 计算字段活算,历史自愈),各卡加 .addFilter(is_data_ready EQ 1);或 ETL 直接不落当天残缺日行
  - 进行中周/月: 用户选择保留展示(数据只到昨日、本就不含今天),后续在卡标题标注「进行中」
**备注**:
  - 反面教材已记录: 静态写死当天行=0 会因历史不重算而永远为 0,必须活算或跑批重刷
  - 待办: ①数据集加 is_data_ready 列 ②加列后重跑 guanvis init 重生成 schema → 7 卡加 is_data_ready EQ 1 过滤 → 换新页面 ID 发布 ③切片器按钮值中文映射列仍待加 ④手动删旧页 h1f37fb014b22778679a1d44、p851469e01d55d0f39a8136f

## 2026-08-14

### 搭建埋点采集率监控看板(观远BI)

**任务**: 用数据集「埋点采集率监控」搭建采集率监控看板,体现各数据类型在日/月粒度的采集率矩阵+趋势;切片器字段名改中文
**脚本/工具**: guanvis skill(DSL) + guancli;源文件 埋点采集监控看板/(4 card + 3 selector + page.js)
**输出**: 线上页面 me79cdef70723fee4f702897「埋点采集率监控」,目录 反欺诈策略室(j38c92ded50ee4df68807d6f)
**关键数据/设计**:
  - 数据集 o991df71b6efe40f9a915a56;14 字段。维值: period_type=day/month(无周),scenario=贷前/贷中,data_type=LBS/通讯录/通话记录/APPList(4类),new_old=全部/新户/老户,operation_sys=android/ios/other,channel_code 单值 A01,eligible_scope 单值 A01_APP_ALL_OS
  - **建模铁律**: 应采数 sample_count 在 4 个 data_type 上是重复的(同格四行都=91992,仅 collected_sample_count 不同),采集率必须按 data_type 分组算,绝不跨 data_type 汇总(否则分母×4)。故 data_type 固定作矩阵行维度/趋势分线维度
  - new_old 口径按场景不同: 贷前只有"全部",贷中为"新户/老户",互不重叠可安全分组
  - Tab 分 日/月 两档;每档 上=采集率矩阵(行 data_type×new_old,列 period_label,值 采集率=SUM(collected)/SUM(sample)),下=采集率趋势 MULTI_LINE(x=period_start,按 data_type 分线)
  - 全局切片器: 场景/系统/新老客,linkToAll
  - 字段名中文: 用 f(..., {alias:"中文"}) 把透视表表头/轴标题改中文(数据类型/新老客/日期/月份)
**备注**:
  - 切片器"名字"用中文(场景/系统/新老客);但 operation_sys 按钮值 android/ios/other 是数据集原始值改不了(同客服看板老坑),period_type 的 day/month 用 Tab 标签"日/月"承载不外露
  - 数据到 7 月下旬(日粒度无 T+1 今天残缺问题);月粒度含进行中 2026-08
  - guanvis init 生成的文件夹默认落在 CWD(仓库根),cd|grep 子shell 里 cd 不生效,发现后 mv 回 反欺诈/ 下
  - move page 报 1012「页面已在目标目录中」无害,setParentDir 已放对位置
  - 校验一次通过,无 error/warning;发布 8 资源全部成功

---

## 2026-08-14

### 客服实时策略命中率监控 v2（克隆+新增命中数卡）

**任务**: 在原「客服实时策略命中率监控」看板基础上，新增①整体命中订单数/用户数 ②BY规则（分策略）命中订单数/用户数（命中率的绝对分子）。原看板是 Malloy 直连卡，guancli 只读无法写卡，故用 guanvis DSL 完整重建为 v2 版本发布，不覆盖原看板。
**脚本/工具**: guanvis（init/preview/publish）、guancli（ds preview/page get）
**输出**: `kf_strategy_v2/`（schema.js + 9 card_*.js + 3 selector_*.js + page.js）；线上 Page ID `w6d4440631ad8ea81e392c24`（名「客服实时策略命中率监控 v2」，风险运营部目录 tc1fa3fa74a6a4379ba9faed）
**关键数据**: 12 张卡（3 筛选器 + 7 克隆图表卡 + 2 新增命中数透视表）+ 1 页，发布 13 资源全部成功
**备注**:
  - 数据集 d3cdc33d56120485e9c52cc2（STARROCKS，27 字段）；新卡命中数=hit_cnt 按 dimension_type 条件求和拆 ORDER/CUSTOMER，period_type=D 逐日；整体卡 strategy_name=umbrella，BY规则卡 NE umbrella
  - 坑：同卡两个 CASE WHEN calcField 因 fdId 为空触发「Duplicate field in zone metric」警告（判重键=fdId+alias+aggrType）→ 给每个 calcField 显式 alias 区分即解，payload 两个指标列均保留
  - move page 报 1012「页面已在目标目录中」无害，setParentDir 已放对位置
  - 已知沿用原设计怪癖：策略筛选器联动的命中率卡（1-6）被钉死 umbrella 口径，选具体策略会清空这些卡——与原看板一致，未改

### 客服实时策略命中率监控 v2（精简改造·按用户反馈迭代）

**任务**: 按反馈精简 v2：①切片器真正生效（分析口径/样本范围联动透视表，口径不写死）②修分策略命中率卡的 umbrella-写死 bug（原选子策略为空）③透视表时间列从左到右降序 ④删掉过度设计的两张命中数卡，改为在整体总览加一张「调用数/命中数/整体命中率」透视表。
**脚本/工具**: guanvis（preview/publish）、guancli（ds preview/page get）
**输出**: `kf_strategy_v2/`（11 card/selector + page.js）；新线上 Page ID `oe02cff9acf02121ba4f466d`（原 v2 页 w6d4... 作废，见备注）
**关键数据**: 11 卡（3 筛选器 + 7 命中率图表卡 + 1 新整体概览卡）+ 1 页，发布 12 资源全部成功
**备注**:
  - bug 根因：命中率透视卡(02-04)+趋势卡(05-07) 全部 `strategy_name EQ umbrella` 写死 → 选子策略必空。统一改 `NE umbrella`（只留 6 条真实策略），策略切片器在此底线上再收窄；透视卡补 `period_label DESC`（三粒度 label 均可字典序=时间序：D=2026-07-16 / W=2026-07-20 周一 / M=2025-09）；趋势线图保持时间升序便于读趋势
  - 新整体概览卡：SUM(total_cnt)=调用数、SUM(hit_cnt)=命中数、SUM(hit)/SUM(total)=整体命中率；strategy_name=umbrella 去重口径、period_type=D 逐日、日期 DESC；dimension_type/sample_type 不写死，交切片器
  - 切片器联动重排（卡 index：0 趋势/1-3 命中率透视/4-6 趋势线/7 新概览）：分析口径→1-7；样本范围→0-7；策略→仅 1-6（卡0/7 是 umbrella 整体口径不联动）。原 selector linkTo(8) 已越界，清除
  - **覆盖备份坑**：`publish --allow-overwrite` 覆盖原 v2 页时，CLI 覆盖前的「导出原资源包备份」异步任务连续两次失败（BI 侧问题）导致 upload 中止。改用新 Page ID 发布绕过覆盖检查（新页不触发备份）→ 成功
  - 遗留：旧 v2 页 `w6d4440631ad8ea81e392c24` 及其两张旧卡（n9c6.../dc9d...）成为孤儿；guancli 只读无删除命令，需在 BI 界面手动删除

---

## 2026-08-17

### 埋点采集率监控看板（宽表重做版）

**任务**: 数据源按此前的数据集优化建议由长表改为宽表（data_type 由维度改为每类各一列已采数）后，原看板全部 SQL 报错。按新宽表结构重做看板，保持与原版一致的格式（Tab 日/月 + 采集率矩阵 + 采集率趋势 + 3 切片器）。
**脚本/工具**: guanvis（init --force / preview / publish）、guancli（card get 回读）
**输出**: `埋点采集监控看板/`（schema.js 重新 init + 4 card + 3 selector + page.js）；新线上 Page ID `ee9d0513f6b98d632689c775`（名「埋点采集率监控」，反欺诈策略室目录 j38c92ded50ee4df68807d6f）
**关键数据**: 7 卡（3 筛选器 + 2 采集率矩阵 + 2 采集率趋势）+ 1 页，发布 8 资源全部成功
**备注**:
  - 新宽表 15 字段：base_sample_count 为 LBS/通讯录/通话 三类共用应采分母；APPList 用独立 applist_sample_count（安卓端口径，ios/other 行为 0）；data_type/eligible_scope/sample_count/collected_sample_count/collection_rate 全部删除
  - 4 个采集率 calcField（aggregation, percentage(2)）：LBS=SUM(lbs_collected)/SUM(base)、通讯录=SUM(contact_collected)/SUM(base)、通话=SUM(call_collected)/SUM(base)、APPList=SUM(applist_collected)/SUM(applist_sample)
  - 矩阵：行 new_old(新老客)、列 period_label(日期/月份)、指标 4 类采集率；趋势 MULTI_LINE：x=period_start，4 类采集率各一条线（不再用 data_type 分线）
  - **多 calcField 判重坑（同 v2 命中数卡）**：同卡 4 个 calcField 因 fdId 为空触发「Duplicate field in zone metric」警告；回读 card get 确认服务端 4 个指标+行列维度均在，警告仅为本地判重键（fdId 空）误报，payload 未合并，可忽略
  - 当前数据源 period_type 仅 "day"（月粒度暂无数据），月 Tab 保留但空；日粒度最新到昨天，无 T+1 今天残缺问题
  - operation_sys 宽表新增 "unknown" 档；切片器按钮值仍为原始英文（改中文需 ETL 映射列，同客服看板老坑）
  - 遗留：旧长表页 `me79cdef70723fee4f702897` 成孤儿，需在 BI 界面手动删除（guancli 只读无删页命令）

## 2026-08-19

### 客服实时策略命中率监控 v3 —— 新增各策略命中数透视表

**任务**: 用户反馈 v2 分策略部分缺「各策略命中数」统计，需放在「各策略命中率」卡片下方
**脚本/工具**: guanvis skill；工程 `kf_strategy_v3/`（从 v2 复制批量换 ID）
**输出**: 线上 Page `p21b4eb1b23ad4f49648f1dd`（客服实时策略命中率监控 v3），目录：反欺诈策略室 / 客服实时策略命中率监控
**关键数据**:
  - 新增 3 张命中数透视卡 card_09/10/11（日/周/月），结构同命中率表：行=strategy_name×target_risk_tag，列=period_label，指标=SUM(hit_cnt) 整数格式，period_label 降序
  - Tab 各面板布局改为「命中率透视(8) → 命中数透视(8) → 命中率趋势线(7)」
  - 3 个切片器（分析口径/样本范围/策略）均 linkTo 新增卡 index 8/9/10
  - 发布策略：应用户要求新建 v3（全新 Page/Card/Selector ID），保留 v2 用于回滚
  - 共 15 资源（1 page + 14 card）全部导入成功
**备注**:
  - 发布末尾报 move 500「页面已经在目标目录中」，无害——page 已在正确目录，忽略即可
  - 复用 v2 待优化项未动（月趋势 month() 跨年、单选切片器无固定默认、Card2 计数 ,.2f、无日期筛选器），本次仅按用户诉求加命中数表


## 2026-09-02

### app打标模块清理 + 未覆盖applist v3 打标（进行中）

**任务**: 用最新 v3 打标脚本对新投放的「未覆盖应用·下载人数≥5」applist 打标；并清理 app打标模块废弃文件
**脚本/工具**: `run_label_v3.py`（v3：l1/l2/risk_type + quality_tag 四维，sonnet-4-6 + tool_use + 规则前置）
**输入**: `app打标/APPlist打标周期任务_未覆盖应用_下载人数5及以上_20260902_v01.csv`（22113 unique 包）
**输出**: `applist_未覆盖_5plus_20260902_v3.csv` / `.xlsx` + 缓存 `applist_label_cache_applist_未覆盖_5plus_20260902_v3.sqlite`（打标进行中，完成后补关键数据）
**关键数据**:
  - v3 首次实跑（此前仅语法校验）；12 条 smoke 验证 tool_use 结构化输出正常
  - 规则前置命中 231（1.0%），实际送 LLM 21882 包
**清理（标准力度，用户确认；模块文件全部 untracked，删除不可经 git 恢复）**:
  - 删 `缓存备份/`（4 个 v2 cache bak，49M）、全部 `__pycache__`
  - 删 v2 中间产物：`tagging_tmp/`（1887 批，16M）、`applist_tag_0522*.csv/.xlsx`、`applist_label_cache_applist_tag_0522_v2.sqlite`（13M）
  - 删 0605 外部导入中间件：`applist_tag_0605_2.csv/_clean/_dirty`
  - 删小米/应用宝爬取件：`crawl_xiaomi_market.py`、`xiaomi_market_raw.json`、`applist_tag_xiaomi.csv`、`xiaomi_spotcheck.csv`、`mi_l1_audit.txt`、`yyb_next_data.json`
  - 共释放 ~130MB
**保留**: 原始 `applist_tag.csv`、生产件 `applist_tag_merged_v3.csv/.xlsx/_clean.csv`（喂 StarRocks `dfs_applist_tag_merged_v3`，被 applist_features.sql 消费）、`run_label_v2/v3.py`、`merge_applist_v3.py`、`mainstream_apps_v3.py`、`clean_*.py`、docs、`人工标注/`、`脚本_审计/`
**备注**:
  - 未做目录重组（脚本硬编码 BASE=反欺诈根目录且互相按根目录相对名引用，迁移风险高，用户选保持现状）
  - 输出前缀不能含 `/`（否则 cache sqlite 指向不存在子目录报错），故输出落在反欺诈根目录，与历史一致

**打标完成 (2026-09-02 收尾)**:
- 全量耗时 ~62min (3718s); 最终 22113 app, 覆盖率 **99.99%**, 仅 2 个无法解析 (com.ch.hyly / com.shengxun.buke)
- risk_type 分布: 无 16108(72.8%) / 色情 1978 / 赌博 858 / 小额现金贷 474 / 网赚刷量 423 / 翻墙VPN 347 / 黑灰产工具 259 / 仿冒山寨 238 / 撸口子指南162 / 改机软件150 / 反催收105 / 诈骗80 / 远程控制48 ...; 高风险命中共 5240 个
- **发现并修复严重 bug**: 代理(llmapi.lovbrowser.com)偶发把 tool_use 的 `labels` 参数二次编码成 JSON **字符串** (而非数组), 老校验 `isinstance(labels,list)` 恒 False → 整批误判 "LLM未返回"; temp=0 下 3 次重试结果一致 → 全批丢失. 首轮全量因此 452 app 未打标.
  - 修复: `_call_with_retry` 在校验前对 str 型 input/labels 先 `json.loads` (run_label_v2.py & v3.py 同步改)
  - 修复后补跑 (同前缀复用缓存): 452 → 60 → 9 → 2, 逐步用 BATCH_SIZE=30/3/1 绕开确定性 malformed JSON
- 剩余 2 个是模型确定性输出坏 JSON (line9 col20 处未转义引号), batch=1 仍无法恢复, 占比 0.009%, 放弃
