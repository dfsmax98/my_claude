# Git初版提交清单

> 本清单记录声纹平台初版进入Git的文件范围、数据边界和验证方式。

## 1. 提交范围

### 1.1 核心代码

| 路径 | 内容 | Git策略 |
|------|------|------|
| `src/common/` | 音频处理、ASR角色特征、CAM++ embedding、VAD、聚类等公共组件 | 跟踪 |
| `src/pipelines/` | 角色模型、客户库、黑产库、PLDA、AS-Norm、N:N评估和批处理流程 | 跟踪 |
| `src/voiceprint_platform/` | 单机声纹平台服务、状态库、后端打分和聚类调度 | 跟踪 |
| `src/web/` | 本地HTTP服务和前端静态页面 | 跟踪 |
| `scripts/` | 环境设置、测试和资产清单脚本 | 跟踪 |
| `tests/` | 单元测试、集成测试目录和测试说明 | 跟踪 |

### 1.2 配置和模型

| 路径 | 内容 | Git策略 |
|------|------|------|
| `configs/platform.json` | 平台模型版本、阈值、权限默认值和保留期配置 | 跟踪 |
| `configs/project.json` | 项目配置 | 跟踪 |
| `models/role/` | 文本角色模型和模型卡 | Git LFS跟踪 |
| `models/backend/` | PLDA、质量模型和cohort快照 | Git LFS跟踪 |
| `models/runtime/` | ModelScope运行时模型说明 | 仅跟踪README，模型文件本地保留 |

### 1.3 前端界面

| 路径 | 内容 | Git策略 |
|------|------|------|
| `src/web/app.py` | 本地Web API、鉴权、文件接口和静态资源服务 | 跟踪 |
| `src/web/static/index.html` | 平台页面结构 | 跟踪 |
| `src/web/static/app.js` | 登录、总览、录音处理、库详情、权限、版本和监控交互 | 跟踪 |
| `src/web/static/styles.css` | 响应式布局和平台UI样式 | 跟踪 |
| `src/web/README.md` | 前端运行说明 | 跟踪 |

## 2. 数据边界

### 2.1 可提交数据

| 路径 | 内容 | 说明 |
|------|------|------|
| `data/manifests/asset_summary.json` | 本地资产脱敏汇总 | 不含原始录音 |
| `data/manifests/auxiliary_voiceprints_10k_role_text_v2.json` | 万条辅助声纹脱敏清单 | 不含客户明细和embedding |
| `data/manifests/model_assets.json` | 模型资产清单 | 用于本地校验 |
| `data/processed/platform/platform_state.json` | 平台状态库 | 用于赛事方测试复现，包含账号哈希、客户库索引、核验记录和审计状态 |
| `data/processed/platform/vectors/` | 平台embedding向量 | 用于客户库、黑产库和query向量复现 |
| `_temp/voiceprint_sample_pack_20260822_1629/` | 回归测试样本包 | 包含10通已建库客户另一通、2通黑产录音和10通未建库录音 |
| `data/raw/kesu_1000/README.md` | 原始录音目录说明 | 仅说明，不提交录音 |
| `data/processed/README.md` | 处理数据目录说明 | 仅说明 |
| `reports/README.md` | 可再生成报告目录说明 | 仅说明，不提交运行报告产物 |

### 2.2 本地保留数据

| 路径 | 原因 |
|------|------|
| `data/raw/kesu_1000/*.mp3` | 原始录音，敏感数据 |
| `data/processed/platform/uploads/` | 平台上传录音 |
| `data/processed/platform/artifacts/` | ASR、分轨WAV和处理产物 |
| `data/processed/**/*.npz`、`data/processed/**/*.pkl` | embedding、矩阵和声纹库 |
| `data/manifests/*_private.csv` | 私有文件级明细 |
| `_temp/` | 临时样本包、日志、截图和调试脚本 |
| `reports/` | 可重新生成的实验输出 |
| `models/runtime/` | 大型本地运行时模型 |

例外：`_temp/voiceprint_sample_pack_20260822_1629/` 按赛事方测试交付要求进入Git，其余 `_temp/` 内容继续忽略。

## 3. 安全处理

- 仓库不提交固定默认管理员密码或密码哈希。
- 首次启动平台时，需要通过 `VOICEPRINT_ADMIN_PASSWORD` 或 `VOICEPRINT_ADMIN_PASSWORD_HASH` 注入管理员密码。
- `docs/ai会话记录.md` 中涉及密码的用户输入已脱敏。
- `.gitignore` 已排除原始录音、平台状态库、embedding、私有清单、临时文件和运行报告。
- `.gitattributes` 已将小型可发布模型纳入Git LFS策略。

## 4. 初版验证命令

```powershell
cd D:\数据智能部\d02206\codex\competition
D:\asrvenv\Scripts\python.exe -m compileall -q src
D:\asrvenv\Scripts\python.exe -m unittest discover -s tests\unit -p "test_*.py"
```

## 5. 启动方式

```powershell
cd D:\数据智能部\d02206\codex\competition
. .\scripts\set_env.ps1
$env:VOICEPRINT_ADMIN_PASSWORD="本地管理员密码"
python src\web\app.py --host 127.0.0.1 --port 8768
```

已有本地平台状态库不进入Git；若本机已存在 `data/processed/platform/platform_state.json`，平台会继续使用已有账号和状态。
