# 比赛项目工作日志

## [2026-08-22] 工作记录

### 任务: 从原声纹项目复制并整理比赛工程

- 建立`src/tests/configs/models/data/docs/reports/scripts/_temp`职责目录。
- 复制985条原始录音、角色模型、PLDA模型、ModelScope运行时模型、代码、测试和Markdown文档，原文件保持不变。
- 修改比赛代码路径，使其只读取`competition/`内资产。
- 生成脱敏资产摘要和文件级模型SHA-256清单。
- 66项单元测试全部通过。
- PLDA端到端回放复现原冻结指标。

### 注意

- 原始录音和embedding为敏感数据，不进入普通Git。
- 运行时模型约2.2 GiB，不进入普通Git。
- 后续比赛代码变更只在`competition/`内进行，不回写原`声纹对比/`本体。

## [2026-08-22] 工作记录

### 任务: 整理本地已有资产结构

- **耗时**: 约5分钟
- **涉及文件**:
  - `docs/本地资产结构.md`（创建）
  - `docs/README.md`（修改）
  - `README.md`（修改）
  - `WORKLOG.md`（修改）
- **关键产出**:
  - 完成1,308个本地文件、约3.48 GiB资产的目录级盘点。
  - 明确代码、数据、模型、文档、报告和临时产物的职责与Git边界。
  - 登记核心模型、985条录音、处理数据和完整性清单的复现入口。
- **Skill调用**: 无匹配Skill，使用本地文件与Git盘点。
- **待办/注意**: 当前改动尚未提交；原始录音、embedding和私有清单继续仅在本地保留。

## [2026-08-22] 工作记录

### 任务: 规划声纹识别平台

- **耗时**: 约10分钟
- **涉及文件**:
  - `docs/ai会话记录.md`（追加用户输入）
  - `WORKLOG.md`（追加记录）
- **关键产出**:
  - 完成现有分轨、ASR角色识别、embedding、客户/黑产建库、实时核验、N:N聚类和Web看板的能力映射。
  - 确定本地单机首版的平台分层、异步处理状态、双路核验决策、数据边界与分阶段验收方案。
  - 识别旧实时余弦阈值、PLDA训练角色版本、并发pickle写入和N:N效果不足等上线阻断项。
- **Skill调用**: 无匹配Skill，基于现有声纹代码与冻结评估产物规划。
- **待办/注意**: 本轮仅完成方案设计，未修改业务代码；实施前需确认本地单机首版及可信首录入库口径。

## [2026-08-22] 工作记录

### 任务: 复制万条录音批次辅助embedding

- **耗时**: 约8分钟
- **涉及文件**:
  - `data/processed/auxiliary_recent_voiceprints_10k_role_text_v2/`（复制5个本地敏感数据文件）
  - `data/manifests/auxiliary_voiceprints_10k_role_text_v2.json`（创建脱敏清单）
  - `configs/project.json`（登记辅助数据源）
  - `docs/辅助声纹数据源说明.md`（创建）
  - `README.md`、`docs/README.md`、`docs/本地资产结构.md`、`data/processed/README.md`（修改）
- **关键产出**:
  - 从10,000条录音源批次复制8,301条正式客户embedding，覆盖6,932个身份。
  - 聚合NPZ与8,301个源分片逐条一致，复制文件与源文件SHA-256全部一致。
  - 明确辅助源仅用于身份隔离后的PLDA、AS-Norm和质量模型候选，不直接进入正式客户库或黑产库。
- **Skill调用**: 无匹配Skill，使用本地资产校验和项目现有清单规范。
- **待办/注意**: 辅助embedding和角色数值结果为敏感数据，继续仅在本地保存；实际训练前必须排除评估和测试身份。

## [2026-08-22] 工作记录

### 任务: 按计划实现本地声纹识别平台

- **耗时**: 约35分钟
- **涉及文件**:
  - `configs/platform.json`、`configs/project.json`（创建/修改）
  - `models/backend/customer_plda_v2_current_role/`（创建当前角色PLDA后端）
  - `src/voiceprint_platform/`（创建平台服务层）
  - `src/web/app.py`、`src/web/static/`、`src/web/README.md`（升级HTTP服务与操作前端）
  - `src/pipelines/evaluate_customer_plda_quality.py`（兼容当前角色辅助源和最小身份通数）
  - `tests/unit/test_voiceprint_platform.py`、`tests/unit/test_evaluate_customer_plda_quality.py`（创建/修改）
  - `docs/声纹识别平台说明.md`、`docs/reports/plda_current_role_v2_20260822/`（创建）
  - `README.md`、`tests/README.md`、`models/README.md`、`docs/README.md`、`docs/本地资产结构.md`（修改）
  - `data/manifests/asset_summary.json`、`data/manifests/model_assets.json`（刷新）
- **关键产出**:
  - 完成双轨上传、双轨ASR、当前角色识别、客户embedding、质量评分、PLDA 1:1、黑产1:N和组合标签闭环。
  - 完成客户首录审核、本人通过后模板增量、黑产入库审核、24小时ASR清理和每日N:N影子任务。
  - 当前角色PLDA challenger使用821条、234个至少3通身份训练；全覆盖EER 8.69%，质量分流60.04%覆盖时EER 6.59%。
  - 历史黑产库自动导入20个身份、21条模板；本地服务运行于 `http://127.0.0.1:8767`。
- **测试验证**:
  - 73项单元测试全部通过，Python和JavaScript语法检查通过。
  - HTTP健康、总览、模型、multipart上传和任务查询通过。
  - 119.62秒真实双轨MP3端到端处理通过，冷启动约62.3秒，正确返回`待建库`且黑产未误命中。
  - 桌面与移动视口截图已检查，桌面布局正常，移动导航和横向约束已修正。
  - 已清理测试生成的5个 `__pycache__` 目录。
- **Skill调用**: 无匹配Skill，复用现有声纹模型与流程实现。
- **待办/注意**: 当前仅适合受控本机环境；生产前仍需统一鉴权、存储加密、独立业务真值阈值标定和数据库/向量库部署审批。

## [2026-08-22] 工作记录

### 🎯 任务: 双录音客户代表声纹筛选并导入客户声纹库
- **耗时**: 约20分钟
- **涉及文件**:
  - src/pipelines/select_representative_customer_voiceprints.py (创建)
  - 	ests/unit/test_select_representative_customer_voiceprints.py (创建)
  - src/voiceprint_platform/__init__.py (修改为惰性导入)
  - data/processed/customer_voiceprint_selected_472_20260822/ (生成本地敏感筛选产物)
  - data/processed/platform/platform_state.json (导入客户库状态)
  - data/processed/platform/vectors/customer/ (写入客户模板向量)
- **关键产出**:
  - 从971条候选录音中识别499个客户，其中472个客户恰好有两条录音。
  - 按 .65*质量分 + 0.25*有效语音时长 + 0.10*ASR字数 为每个双录音客户选择1条代表声纹。
  - 向平台客户声纹库导入472个客户、472条录音记录、472条active模板，模板和客户记录均保留 customer_key/cust_no。
  - 生成 selected_customer_voiceprints.csv、selected_customer_voiceprints.npz、import_summary.json 和中文导入报告。
- **Skill调用**: 无
- **测试验证**:
  - python -m pytest tests/unit/test_select_representative_customer_voiceprints.py -q 通过。
  - 校验平台状态: 472条选中模板均为active，缺失客户主键0条，缺失向量文件0条。
- **待办/注意**:
  - 产物包含客户主键和声纹embedding，继续仅在本地 data/processed/ 保存，不进入普通Git。

## [2026-08-22] 工作记录

### 🎯 任务: 临时文件整理
- **耗时**: 约1分钟
- **涉及文件**:
  - src/common/__pycache__/ (清理)
  - src/pipelines/__pycache__/ (清理)
  - src/voiceprint_platform/__pycache__/ (清理)
  - 	ests/unit/__pycache__/ (清理)
- **关键产出**:
  - 清理测试运行产生的Python缓存目录，未移动或删除业务数据。
- **Skill调用**: 无
- **待办/注意**: 无

## [2026-08-22] 工作记录

### 🎯 任务: 检查客户声纹库前端刷新问题
- **耗时**: 约15分钟
- **涉及文件**:
  - src/web/static/index.html (修改)
  - src/web/static/app.js (修改)
  - docs/ai会话记录.md (追加用户输入)
- **关键产出**:
  - 确认磁盘平台状态库包含472个客户、473条客户模板，其中472条为本次导入active模板。
  - 确认 http://127.0.0.1:8768/api/v1/overview 返回客户数472、active客户模板472。
  - 修正前端客户声纹库列表，仅显示哈希平台ID的问题；现列表展示客户主键、平台ID、状态、模板数和更新时间。
  - 客户详情弹窗补充客户主键和原始录音ID。
- **Skill调用**: 无
- **待办/注意**:
  - 8765端口当前不是新版平台接口；新版可访问地址为 http://127.0.0.1:8768。

## [2026-08-22] 工作记录

### 🎯 任务: 模拟新录音导入比对流程
- **耗时**: 约20分钟
- **涉及文件**:
  - src/voiceprint_platform/service.py (修改)
  - 	ests/unit/test_voiceprint_platform.py (修改)
  - data/processed/platform/platform_state.json (模拟上传与状态修补)
  - data/processed/platform/vectors/customer/ (新增实时核验通过模板向量)
  - docs/ai会话记录.md (追加用户输入)
- **关键产出**:
  - 使用客户 170002923156 的另一条录音 170002923156_2.mp3 模拟前端上传核验。
  - 任务 job_cc281ce28a6644c39b67ba6f 完成，结果 erify_154326a2f18b4b16874d2858。
  - 角色识别为客户右声道，质量分0.789839，客户1:1状态verified，黑产1:N状态clear，无风险标签。
  - 核验通过后该客户active模板从1条增加到2条；新增模板和原导入模板均保留 customer_key/cust_no。
  - 停止重复写同一状态库的8767旧服务，仅保留8768新版平台服务。
- **Skill调用**: 无
- **测试验证**:
  - D:\asrvenv\Scripts\python.exe -m unittest tests.unit.test_voiceprint_platform.VoiceprintPlatformTest.test_first_recording_requires_review_then_verified_call_updates_template 通过。
  - D:\asrvenv\Scripts\python.exe tests\unit\test_select_representative_customer_voiceprints.py 通过。
- **待办/注意**:
  - 当前前端地址为 http://127.0.0.1:8768；本次模拟会使客户模板总数从472增至473。

## [2026-08-22] 工作记录

### 🎯 任务: 抽取第二个客户模拟新录音1:1比对
- **耗时**: 约10分钟
- **涉及文件**:
  - docs/ai会话记录.md (追加用户输入)
  - data/processed/platform/platform_state.json (新增模拟核验任务与待复核记录)
  - data/processed/platform/uploads/、data/processed/platform/artifacts/、data/processed/platform/vectors/query/ (新增本次模拟运行产物)
- **关键产出**:
  - 使用客户 170100079854 的另一条录音 170100079854_1.mp3 模拟上传核验。
  - 任务 job_decba6e5a9394c52a9aed7f5 完成，结果 erify_8ea858b85dfd4477a0b86cb1。
  - 角色识别为客户右声道，客户1:1分数9.726304，命中模板 cust_tpl_selected_6606a059c76a66276bdb。
  - 质量分0.696960，低于阈值0.731500，因此结果状态为review，标签为待复核，未自动新增active模板。
  - 黑产1:N状态clear。
- **Skill调用**: 无
- **待办/注意**:
  - 本次测试使平台任务数增加到3，录音记录增加到475，待复核数增加到2；客户模板数未增加。

## [2026-08-22] 工作记录

### 🎯 任务: AS-Norm 与 PLDA 测试版效果评估
- **耗时**: 约15分钟
- **涉及文件**:
  - src/pipelines/evaluate_asnorm_plda_ab_test.py (创建)
  - eports/asnorm_plda_ab_test_20260822/ (生成离线测试报告与分数矩阵)
  - docs/ai会话记录.md (追加用户输入)
- **关键产出**:
  - 在971条评估embedding、499个客户、472个同人pair、470463个异人pair上完成对比。
  - 裸余弦EER 11.65%，外部AS-Norm(k=50) EER 10.38%，PLDA EER 8.69%。
  - PLDA+AS-Norm等权融合EER 8.47%，测试集内最佳权重(PLDA=0.6)融合EER 8.26%。
  - 输出 metrics.csv、summary.json、score_matrices.npz 和 AS-Norm与PLDA测试版评估报告.md。
- **Skill调用**: 无
- **待办/注意**:
  - 本次为离线测试版本，未修改平台配置、实时阈值、模型文件或依赖；测试集内最优融合权重偏乐观，不能直接上线。

## [2026-08-22] 工作记录

### 🎯 任务: 声纹平台功能、代码与前端UI综合评估
- **耗时**: 约20分钟
- **涉及文件**:
  - src/voiceprint_platform/service.py (审查)
  - src/voiceprint_platform/store.py (审查)
  - src/voiceprint_platform/backend.py (审查)
  - src/voiceprint_platform/processing.py (审查)
  - src/voiceprint_platform/clustering.py (审查)
  - src/web/app.py (审查)
  - src/web/static/app.js (审查)
  - src/web/static/styles.css (审查)
  - _temp/ui_check.js (创建临时UI检查脚本)
  - _temp/ui_check_20260822/ (生成UI检查截图与结果)
  - docs/ai会话记录.md (已追加用户输入)
- **关键产出**:
  - 确认平台服务 http://127.0.0.1:8768 正常，客户库472个客户、473条有效客户模板、2条待复核任务可通过API刷新。
  - 完成桌面、平板、移动端UI截图检查，确认主要页面可渲染，客户库可展示472行，客户详情弹窗可打开。
  - 发现复核流转缺口: verification类型复核通过/拒绝仅更新复核任务状态，不会推进核验结果或模板状态。
  - 发现移动端/平板导航可用性问题: 平板显示内部英文data-view，手机仅保留前四个入口。
  - 清理测试产生的__pycache__目录。
- **Skill调用**: 无
- **测试验证**:
  - node --check src/web/static/app.js 通过。
  - D:\asrvenv\Scripts\python.exe -m compileall -q src 通过。
  - D:\asrvenv\Scripts\python.exe -m unittest discover -s tests\unit -p "test_*.py" 通过，74个测试OK。
- **待办/注意**:
  - 本次仅做评估审查，未修改平台业务实现；UI截图保存在 _temp/ui_check_20260822/。

## [2026-08-22] 工作记录

### 🎯 任务: N:N团伙检测功能测试
- **耗时**: 约8分钟
- **涉及文件**:
  - docs/ai会话记录.md (追加用户输入)
  - data/processed/platform/platform_state.json (新增一次N:N影子聚类运行记录)
  - src/voiceprint_platform/clustering.py (审查)
  - src/common/gang_cluster.py (审查)
  - configs/platform.json (读取配置)
- **关键产出**:
  - 调用 http://127.0.0.1:8768/api/v1/cluster-runs 完成一次真实库N:N影子聚类。
  - 本次运行ID: cluster_run_0c45563f1b4946ae97b78eb2。
  - 覆盖客户数472，互为Top-K且达到阈值的连边数2，候选团伙簇0个。
  - 配置阈值为0.925，topk=2，min_cluster_size=3，shadow_only=true。
  - 未新增团伙复核任务，待复核数保持2。
- **Skill调用**: 无
- **测试验证**:
  - D:\asrvenv\Scripts\python.exe -m unittest tests.unit.test_voiceprint_platform.VoiceprintPlatformTest.test_cluster_run_is_shadow_only 通过。
  - 清理测试产生的__pycache__目录。
- **待办/注意**:
  - 当前真实库只出现两条高相似连边，不满足三人及以上连通分量，因此不构成团伙候选。

## [2026-08-22] 工作记录

### 🎯 任务: 团伙簇算法说明
- **耗时**: 约3分钟
- **涉及文件**:
  - docs/ai会话记录.md (追加用户输入)
  - src/voiceprint_platform/clustering.py (读取)
  - src/common/gang_cluster.py (读取)
  - configs/platform.json (读取)
- **关键产出**:
  - 梳理当前N:N团伙簇算法: 客户有效模板聚合为质心、余弦相似矩阵、互为Top-K边、阈值过滤、连通分量成簇。
  - 确认当前配置 threshold=0.925、topk=2、min_cluster_size=3、shadow_only=true。
- **Skill调用**: 无
- **待办/注意**: 无

## [2026-08-22] 工作记录

### 🎯 任务: 各模型阈值优化空间评估
- **耗时**: 约10分钟
- **涉及文件**:
  - docs/ai会话记录.md (追加用户输入)
  - configs/platform.json (读取)
  - models/role/role_text_v1_20260820/role_text_model.joblib (读取阈值元信息)
  - reports/plda_current_role_min3_20260822/plda_quality_summary.json (读取)
  - reports/plda_current_role_min3_20260822/plda_quality_metrics.csv (读取)
  - reports/asnorm_plda_ab_test_20260822/summary.json (读取)
  - reports/voiceprint_function_test_20260810/black_metrics.json (读取)
  - reports/voiceprint_function_test_20260810/gang_metrics.json (读取)
  - reports/voiceprint_function_test_20260810/gang_parameter_sweep.csv (读取)
- **关键产出**:
  - 质量阈值当前取0.7314997896756941，对应约60%覆盖率和PLDA EER 6.59%；若提升自动通过率可评估0.6967562114017541附近的80%覆盖率点。
  - PLDA当前优于裸余弦和AS-Norm；PLDA+AS-Norm融合离线EER最低但需冻结集验证。
  - 黑产1:N阈值0.9036450386047364误报低但召回偏低，存在按业务召回目标下调阈值空间。
  - 团伙N:N阈值0.925为高精度低召回策略，适合影子调查；若要多捞线索可测试0.90或0.875但误报会明显增加。
  - 角色模型阈值: abstain_threshold=0.8175754，quality_rule为min_chars=20、min_speech_seconds=5.0。
- **Skill调用**: 无
- **待办/注意**:
  - 本次仅评估阈值优化空间，未修改平台配置或模型文件。

## [2026-08-22] 工作记录

### 🎯 任务: 整理声纹平台详细说明文档
- **耗时**: 约12分钟
- **涉及文件**:
  - docs/ai会话记录.md (追加用户输入)
  - docs/声纹平台详细说明.md (创建)
  - docs/README.md (追加文档入口)
  - docs/声纹识别平台说明.md (读取参考)
  - README.md (读取参考)
  - src/web/README.md (读取参考)
- **关键产出**:
  - 新增约21KB中文详细说明文档，覆盖平台定位、当前运行状态、启动方式、业务流程、模型阈值、阈值优化空间、HTTP API、前端页面、数据存储、人工复核、验证结果、限制风险和后续优化建议。
  - 文档内容基于已核验代码、配置、报告和本地测试结果整理，未写入客户明细或录音路径。
  - 更新 docs/README.md 文档索引。
- **Skill调用**: 无
- **测试验证**:
  - 使用 Get-Content -Encoding UTF8 校验新文档可正常读取。
  - 使用 Select-String 检查标题结构。
- **待办/注意**:
  - 原简版 docs/声纹识别平台说明.md 未覆盖，后续如需可再同步当前8768端口和客户主键保留口径。

## [2026-08-22] 工作记录

### 🎯 任务: 梳理平台上线前工作清单
- **耗时**: 约3分钟
- **涉及文件**:
  - docs/ai会话记录.md (追加用户输入)
  - WORKLOG.md (追加本记录)
- **关键产出**:
  - 基于当前代码审查、功能测试、UI检查和阈值评估结果，梳理上线前P0/P1/P2工作项。
- **Skill调用**: 无
- **待办/注意**: 无

## [2026-08-22] 工作记录

### 🎯 任务: 平台治理、账号权限、复核策略与监控看板改造
- **耗时**: 约45分钟
- **涉及文件**:
  - docs/ai会话记录.md (追加用户输入，管理员口令已脱敏)
  - configs/platform.json (新增安全、治理、权限、版本公告配置)
  - src/voiceprint_platform/store.py (扩展状态schema和向量删除能力)
  - src/voiceprint_platform/backend.py (客户质量拒识状态、黑产1:N灰区下界)
  - src/voiceprint_platform/service.py (账号会话、权限、版本公告、监控、复核策略、模板滚动上限)
  - src/web/app.py (登录、权限校验、管理员接口、监控接口)
  - src/web/static/index.html (新增登录、账号管理、权限配置、版本公告、运行监控页面)
  - src/web/static/app.js (接入登录、权限、监控、账号、公告交互)
  - src/web/static/styles.css (新增登录和管理页面样式)
  - tests/unit/test_voiceprint_platform.py (更新复核口径并新增灰区复核/模板滚动测试)
  - docs/声纹平台详细说明.md (同步治理和复核新口径)
- **关键产出**:
  - 初版限定单实例运行，治理配置记录 single_instance=true。
  - 新增本地账号系统，默认管理员 d02206，配置中仅保存PBKDF2口令哈希。
  - 新增 admin/operator/viewer 三类角色和客户主键、录音、ASR、声纹元数据、账号、权限、公告、监控、N:N触发等权限项。
  - 新增账号管理页、权限配置页、版本公告页、运行监控页。
  - 人工复核调整为外部流转，仅保留 self_check_gray_zone 和 black_search_gray_zone 两类场景，不反向修改平台模板或核验结果。
  - 客户活动embedding模板上限默认3，超过后最早活动模板 rolled_out，并删除对应向量文件；录音和ASR文本暂时全量保留。
  - 黑产1:N新增灰区下界 review_below=0.8858376145362855，命中阈值仍为0.9036450386047364。
  - 重启 8768 本地服务并验证登录、总览、账号、权限、治理、公告和监控接口。
- **Skill调用**: 无
- **测试验证**:
  - node --check src/web/static/app.js 通过。
  - D:\asrvenv\Scripts\python.exe -m compileall -q src 通过。
  - D:\asrvenv\Scripts\python.exe -m unittest discover -s tests\unit -p "test_*.py" 通过，76个测试OK。
  - 未登录访问 /api/v1/overview 返回401；管理员登录后可访问总览、账号列表、权限、治理、公告和监控接口。
  - 清理测试产生的__pycache__目录。
- **待办/注意**:
  - 端到端真实音频回归测试按用户要求放到其他优化完成后执行。
  - 当前本地账号系统未接入统一认证、HTTPS、登录失败锁定和强密码策略。

## [2026-08-22] 工作记录

### 🎯 任务: 再检查平台功能可优化方向
- **耗时**: 约8分钟
- **涉及文件**:
  - docs/ai会话记录.md (追加用户输入)
  - WORKLOG.md (追加本记录)
- **关键产出**:
  - 登录后读取当前总览、治理配置、监控、版本公告、账号和复核队列数据。
  - 确认当前单实例服务正常，worker运行中，客户472个，活动客户模板473条，客户模板上限配置为3，版本公告1条，账号1个。
  - 识别2条旧规则遗留复核任务: verification 和 customer_enrollment，建议后续受控归档或迁移为历史记录。
  - 梳理平台功能下一步优化方向: 历史数据迁移、端到端回归、权限安全增强、监控告警、配置版本回退、存储生命周期、UI交互和算法灰度。
- **Skill调用**: 无
- **测试验证**:
  - node --check src/web/static/app.js 通过。
  - D:\asrvenv\Scripts\python.exe -m unittest discover -s tests\unit -p "test_*.py" 通过，76个测试OK。
  - 清理测试产生的__pycache__目录。
- **待办/注意**:
  - 本次仅检查和给出优化方向，未修改平台业务实现或状态库数据。

## [2026-08-22] 工作记录

### 🎯 任务: 历史复核归档、权限矩阵测试和真实录音端到端回归
- **耗时**: 约18分钟
- **涉及文件**:
  - docs/ai会话记录.md (追加用户输入)
  - data/processed/platform/platform_state.json (复核归档、临时账号创建/停用、真实录音回归状态更新)
  - data/processed/platform/uploads/ (新增/复用真实录音上传文件)
  - data/processed/platform/artifacts/ (新增真实录音处理产物)
  - data/processed/platform/vectors/ (新增客户query与客户模板向量)
  - WORKLOG.md (追加本记录)
- **关键产出**:
  - 将2条旧规则遗留pending复核任务全部标记为approved，当前待复核数为0。
  - 创建临时operator/viewer账号完成权限测试矩阵，验证后已停用临时账号。
  - 权限矩阵验证全部通过: 未登录401、viewer客户主键脱敏且禁止音频/ASR/账号管理、operator可看客户主键和监控但不能管理账号、admin可管理账号和权限。
  - 真实录音回归1: 新客户 regression_new_20260822_155830 首次入库成功，质量accepted，黑产clear，新增1个客户和1条活动模板。
  - 真实录音回归2: 历史客户完成二次核验，1:1 verified，质量accepted，黑产clear，活动模板从2增至3。
  - 回归后平台总览: jobs=5、recordings=477、customers=473、active_customer_templates=475、pending_reviews=0。
- **Skill调用**: 无
- **测试验证**:
  - node --check src/web/static/app.js 通过。
  - D:\asrvenv\Scripts\python.exe -m unittest discover -s tests\unit -p "test_*.py" 通过，76个测试OK。
  - Unicode转义校验新入库标签为“首录建库”，终端乱码不影响平台JSON数据。
  - 清理测试产生的__pycache__目录。
- **待办/注意**:
  - 本次真实录音回归会保留新增客户、录音、ASR文本、处理产物和embedding状态，符合当前“录音/ASR暂时全量保存”的策略。

## [2026-08-22] 工作记录

### 🎯 任务: 核查回归测试录音是否已入库
- **耗时**: 约2分钟
- **涉及文件**:
  - docs/ai会话记录.md (追加用户输入)
  - WORKLOG.md (追加本记录)
- **关键产出**:
  - 确认 `data/raw/kesu_1000/170002923156_2.mp3` 的文件哈希此前已在平台出现。
  - 该录音先以客户 `170002923156` 入库，后续回归测试又以合成客户主键 `regression_new_20260822_155830` 重复入库。
  - 明确该场景不是严格意义上的“全新录音/全新人员”首录入库测试，只是用新客户主键模拟首录建库流程。
- **Skill调用**: 无
- **待办/注意**:
  - 如需严格验证新入库场景，应从10000通录音项目或其他原始音频池中重新选择平台未出现过哈希的录音。

## [2026-08-22] 工作记录

### 🎯 任务: 从客户声纹库剔除重复回归测试声纹
- **耗时**: 约8分钟
- **涉及文件**:
  - docs/ai会话记录.md (追加用户输入)
  - data/processed/platform/platform_state.json (停用目标客户模板、重算客户模板计数、追加审计事件)
  - data/processed/platform/vectors/customer/cust_tpl_fdbb4775e6884de8b696722e.npy (删除客户库模板向量)
  - _temp/platform_state_before_voiceprint_evict_20260822_161818.json (状态库备份)
  - WORKLOG.md (追加本记录)
- **关键产出**:
  - 将重复测试客户 `regression_new_20260822_155830` 对应模板 `cust_tpl_fdbb4775e6884de8b696722e` 从 `active` 改为 `disabled`。
  - 删除该模板的客户声纹库向量文件，并将模板 `vector_path` 置空。
  - 合成客户 `cust_41799c8aa1a2563c22e93aab` 活动模板数更新为0，状态更新为 `pending_enrollment`。
  - 平台活动客户模板数由475降为474，录音、ASR、核验记录和上传文件保留用于审计。
- **Skill调用**: 无
- **测试验证**:
  - `http://127.0.0.1:8768/api/health` 返回 `status=ok`。
  - 目标模板状态为 `disabled`，`vector_path=null`，向量文件不存在。
  - 本地服务已恢复运行，PID为76760。
- **待办/注意**:
  - 本次未删除真实客户 `170002923156` 的历史声纹模板。

## [2026-08-22] 工作记录

### 🎯 任务: 核查客户170002923156第三条声纹来源
- **耗时**: 约3分钟
- **涉及文件**:
  - docs/ai会话记录.md (追加用户输入)
  - data/processed/platform/platform_state.json (只读核查)
  - WORKLOG.md (追加本记录)
- **关键产出**:
  - 客户 `170002923156` 当前有3条活动客户模板。
  - 第3条模板为 `cust_tpl_3b062efd238a410f914e3a4e`，来源录音为 `rec_9b5a8be2ca0a4467b06f531c`。
  - 该录音上传哈希为 `0061f80b3aa823cc79f6a99379c47f5c61005a94be4aa4a259e6a367e12e95aa`，对应原始文件 `data/raw/kesu_1000/170002923156_1.mp3`。
  - 该第3条模板来自端到端历史客户回归测试，和客户第1条代表声纹导入的来源字段 `170002923156_1` 重复。
- **Skill调用**: 无
- **测试验证**:
  - 对 `data/raw/kesu_1000/170002923156_1.mp3` 计算SHA256，和第3条录音记录哈希一致。
- **待办/注意**:
  - 第3条不是来自10000通录音项目，而是来自 `kesu_1000` 原始录音目录。

## [2026-08-22] 工作记录

### 🎯 任务: 准备端到端回归录音样本包
- **耗时**: 约18分钟
- **涉及文件**:
  - docs/ai会话记录.md (追加用户输入)
  - _temp/prepare_voiceprint_sample_pack.py (创建临时样本准备脚本)
  - _temp/voiceprint_sample_pack_20260822_1629/ (生成测试录音样本包)
  - _temp/voiceprint_sample_pack_20260822_1629/sample_manifest.csv (生成样本质量清单)
  - _temp/voiceprint_sample_pack_20260822_1629/sample_manifest.json (生成样本质量清单)
  - _temp/voiceprint_sample_pack_20260822_1629/README.md (生成样本包说明)
  - WORKLOG.md (追加本记录)
- **关键产出**:
  - 准备10通已建库客户的另一通录音，均为当前平台活动客户且仅1条活动模板，备用录音质量分达标。
  - 准备2通已确认黑产声纹库来源录音，角色识别高置信且客户侧有效语音充足。
  - 准备10通未建库录音，来自本机可见的10000原始音频目录，排除平台已出现音频哈希，并通过当前平台质量模型。
  - 样本清单记录录音来源、准备路径、质量分、有效客户语音时长、ASR字数、声道、总时长、SHA-256和筛选依据。
- **Skill调用**: 无
- **测试验证**:
  - 样本包数量校验通过: 已建库客户另一通10条、黑产录音2条、未建库录音10条。
  - 22个准备文件均存在，准备文件SHA-256与清单一致。
- **待办/注意**:
  - 当前 `role_text_v2` 万条辅助目录不含原始音频；本次未建库样本使用 `声纹对比/data/recent_voiceprints_10k_20260819/audio/` 中的10000原始mp3。
  - 本次仅准备文件和清单，没有导入平台、没有新增声纹模板。

## [2026-08-22] 工作记录

### 🎯 任务: 整理声纹平台初版并提交Git
- **耗时**: 约25分钟
- **涉及文件**:
  - `.gitignore` (新增Git边界规则)
  - `.gitattributes` (新增文本和Git LFS规则)
  - `README.md` (更新仓库入口说明)
  - `competition/` (暂存声纹比赛平台核心代码、前端、配置、模型卡、LFS模型、脱敏清单、测试和文档)
  - `competition/docs/Git初版提交清单.md` (新增初版提交范围说明)
  - `competition/configs/platform.json` (移除固定管理员密码哈希)
  - `competition/src/voiceprint_platform/config.py` (支持管理员密码环境变量注入)
  - `competition/src/voiceprint_platform/service.py` (首次启动缺少管理员密码时拒绝初始化)
  - `competition/tests/unit/test_voiceprint_platform.py` (补充测试配置管理员密码哈希)
  - `WORKLOG.md` (清理NUL字符并追加本记录)
- **关键产出**:
  - 明确Git只提交代码、前端、配置、文档、脱敏资产清单和小型可发布模型。
  - 原始录音、平台状态库、embedding、私有清单、运行报告、临时样本包和大型运行时模型保持本地保留并被忽略。
  - 管理员默认密码不进入Git，首次启动通过 `VOICEPRINT_ADMIN_PASSWORD` 或 `VOICEPRINT_ADMIN_PASSWORD_HASH` 注入。
  - 小型模型文件按 `.gitattributes` 进入Git LFS。
- **Skill调用**: 无
- **测试验证**:
  - `node --check src/web/static/app.js` 通过。
  - `D:\asrvenv\Scripts\python.exe -m compileall -q src` 通过。
  - `D:\asrvenv\Scripts\python.exe -m unittest discover -s tests\unit -p "test_*.py"` 通过，76个测试OK。
  - 敏感扫描未命中明文管理员密码或旧固定密码哈希。
  - 暂存清单未包含原始录音、平台状态库、样本包或私有清单。
- **待办/注意**:
  - 已生成本地Git提交，但远程推送被CODING拒绝，原因是当前deploy key没有push权限。
  - 需更换具备写权限的SSH key或HTTPS凭据后重新执行 `git push origin master`，推送后再确认Git LFS对象可正常下载。

## [2026-08-22] 工作记录

### 🎯 任务: 创建赛事方operator测试账号并更新平台说明
- **耗时**: 约8分钟
- **涉及文件**:
  - `data/processed/platform/platform_state.json` (新增本地测试账号，仅本地保留，不进入Git)
  - `_temp/platform_state_before_contest_operator_20260822_1651.json` (状态库备份)
  - `docs/ai会话记录.md` (追加用户输入)
  - `docs/声纹识别平台说明.md` (更新登录与测试账号说明)
  - `WORKLOG.md` (追加本记录)
- **关键产出**:
  - 创建赛事方测试账号 `contest_operator`，角色为 `operator`，状态为 `active`。
  - 密码仅设置到平台状态库的PBKDF2哈希中，未写入Markdown文档、Git仓库或工作日志。
  - 文档中补充管理员账号、赛事方测试账号、operator权限范围和相关登录接口。
- **Skill调用**: 无
- **测试验证**:
  - 平台服务 `http://127.0.0.1:8768/api/health` 正常。
  - `contest_operator` 登录成功。
  - `operator` 可访问 `/api/v1/overview`。
  - `operator` 访问 `/api/v1/admin/users` 返回403，符合权限预期。
- **待办/注意**:
  - 该账号保存在本地平台状态库中；状态库不进入Git。若赛事方使用全新环境，需要由管理员在账号管理页创建同名operator账号或导入状态库。

## [2026-08-22] 工作记录

### 🎯 任务: 梳理声纹平台可绑定Agent能力方向
- **耗时**: 约3分钟
- **涉及文件**:
  - docs/ai会话记录.md (追加用户输入)
  - WORKLOG.md (追加本记录)
- **关键产出**:
  - 梳理声纹平台适合绑定Agent的功能点，包括录音质检、入库建议、灰区复核辅助、黑产命中解释、N:N团伙簇研判、阈值监控、运行巡检、版本公告和回归测试编排。
  - 明确不建议由Agent直接自动执行的高风险动作，如删除模板、修改阈值、开放多进程写入和绕过人工审批。
- **Skill调用**: 无
- **待办/注意**:
  - 如后续落地，需要按只读建议优先、写操作需管理员确认的原则设计Agent权限。

## [2026-08-22] 工作记录

### 🎯 任务: 上传平台状态库、embedding向量和临时样本包
- **耗时**: 约8分钟
- **涉及文件**:
  - `.gitignore` (放开平台状态库、平台向量和指定临时样本包)
  - `.gitattributes` (指定样本包mp3使用Git LFS)
  - `data/processed/platform/platform_state.json` (纳入Git)
  - `data/processed/platform/vectors/` (纳入Git)
  - `_temp/voiceprint_sample_pack_20260822_1629/` (纳入Git)
  - `docs/Git初版提交清单.md` (更新提交范围说明)
  - `docs/声纹识别平台说明.md` (更新平台交付数据说明)
  - `docs/ai会话记录.md` (追加用户输入)
  - `WORKLOG.md` (追加本记录)
- **关键产出**:
  - 按交付要求补充平台状态库、客户库/黑产库/query embedding向量。
  - 临时样本包中22通录音及清单纳入Git，覆盖10通已建库客户另一通、2通黑产录音和10通未建库录音。
  - 平台上传录音、ASR正文、声道WAV、运行报告、全量原始录音和其他临时调试文件继续排除。
- **Skill调用**: 无
- **测试验证**:
  - 样本包文件统计通过: 22个mp3、1个csv、1个json、1个README。
  - 敏感扫描未在文档范围命中明文测试密码或管理员密码。
- **待办/注意**:
  - 状态库包含账号密码哈希和平台运行索引，属于按本次要求上传的可复现状态数据。
