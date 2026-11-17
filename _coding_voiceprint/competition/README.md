# 反欺诈声纹识别比赛工程

> 基于FunASR文本角色识别、CAM++声纹embedding、外部AS-norm、PLDA和embedding质量评分的完整离线工程。

## 当前基线

1000样本测试实际包含985通录音。使用`role-text-v1-20260820`重跑后，客户侧正式评估集为971通、499个身份。

| 后端 | 覆盖率 | EER | Top-1 |
|------|---:|---:|---:|
| CAM++裸余弦 | 100% | 11.65% | 59.22% |
| 外部AS-norm `K=50` | 100% | 10.38% | 61.44% |
| PLDA | 100% | 7.42% | 76.06% |
| PLDA + 质量分流 | 60.04% | 5.64% | 80.00% |

以上结果是冻结样本上的离线基线。PLDA、AS-norm和余弦阈值不能混用，比赛提交前需按赛题验证集重新标定。

## 目录职责

| 目录 | 内容 | Git策略 |
|------|------|------|
| `src/common/` | 音频IO、角色模型、CAM++、VAD、声纹库和聚类公共组件 | 跟踪 |
| `src/pipelines/` | 数据处理、评估、PLDA、黑产库和全量库流程 | 跟踪 |
| `src/web/` | 本地功能看板 | 跟踪 |
| `tests/` | 单元测试与集成测试 | 跟踪 |
| `configs/` | 项目路径和冻结版本 | 跟踪 |
| `models/role/` | 文本角色模型与模型卡 | Git LFS |
| `models/backend/` | PLDA、质量模型与cohort快照 | Git LFS |
| `models/runtime/` | ModelScope和可选降噪模型 | 本地保留，忽略 |
| `data/raw/` | 原始录音副本 | 本地保留，忽略 |
| `data/processed/` | embedding、矩阵和声纹库 | 本地保留，忽略 |
| `data/manifests/` | 脱敏资产摘要和本地私有明细 | 摘要跟踪，私有明细忽略 |
| `docs/` | 总文档、方案、交接和评估报告 | 跟踪 |
| `reports/` | 可重新生成的实验结果 | 忽略 |
| `_temp/` | 临时音频、缓存和日志 | 忽略 |

当前辅助源位于 `data/processed/auxiliary_recent_voiceprints_10k_role_text_v2/`，包含当前角色模型从10,000条源录音中筛选出的8,301条客户embedding，覆盖6,932个身份。

## 环境

推荐使用现有声纹运行环境：

```powershell
cd competition
. .\scripts\set_env.ps1
python --version
```

安装最小依赖：

```powershell
pip install -r requirements.txt
```

## 常用命令

运行单元测试：

```powershell
. .\scripts\set_env.ps1
python -m unittest discover -s tests\unit -p "test_*.py"
```

重跑985通角色识别和客户矩阵：

```powershell
. .\scripts\set_env.ps1
python src\pipelines\classify_roles_adaptive.py `
  data\raw\kesu_1000 `
  --embedding-path data\processed\kesu_1000_channel_embeddings.npz `
  --output-dir reports\kesu_role_refresh
```

重跑PLDA与质量优化：

```powershell
. .\scripts\set_env.ps1
python src\pipelines\evaluate_customer_plda_quality.py `
  --matrix data\processed\kesu_1000_customer_matrix.npz `
  --roles data\processed\kesu_1000_adaptive_roles.json `
  --plda-train data\processed\plda_training_customer_embeddings.npz `
  --cohort-dir models\backend\customer_plda_v1\external_cohort_snapshot.npz `
  --output-dir reports\plda_quality
```

启动本地平台：

```powershell
. .\scripts\set_env.ps1
$env:VOICEPRINT_ADMIN_PASSWORD="本地管理员密码"
python src\web\app.py --port 8766
```

平台支持录音上传、双轨ASR、角色识别、客户1:1、黑产1:N、两类声纹库、N:N影子聚类和人工复核。首次启动会从已审核黑产声纹库导入20个身份、21条模板。
首次启动会创建管理员账号 `d02206`，管理员密码必须通过 `VOICEPRINT_ADMIN_PASSWORD` 或 `VOICEPRINT_ADMIN_PASSWORD_HASH` 注入；仓库不保存固定默认密码或密码哈希。

## 文档入口

- `docs/本地资产结构.md`：本地资产盘点、数据分级、完整性清单和Git边界。
- `docs/辅助声纹数据源说明.md`：万条录音批次辅助embedding的数据口径和使用限制。
- `docs/声纹识别平台说明.md`：本地平台运行、接口、决策和验收说明。
- `docs/project/声纹项目总文档.md`：完整项目说明和通用优化模板。
- `docs/project/上线版说明.md`：离线建库和实时核验设计。
- `docs/project/声纹方案设计.md`：业务与技术方案。
- `docs/reports/`：1000样本、角色模型、PLDA和功能测试报告。

## 安全约束

- 原始录音、客户标识和embedding均按敏感数据管理。
- 正式报告不得持久化ASR全文或明文客户身份。
- 黑产库自动命中前必须使用独立非黑查询集标定1:N FAR。
- 训练、验证和测试按身份隔离，不能仅按录音文件隔离。
