# 反欺诈声纹识别比赛项目

> 本仓库用于沉淀反欺诈声纹识别比赛代码、配置、模型清单、数据清单和实验文档。比赛项目与原工作区中的 `声纹对比/` 本体完全隔离，原项目文件保持不变。

## 项目入口

比赛项目位于 [`competition/`](competition/README.md)，目录按职责拆分：

```text
competition/
├── src/          # 角色识别、embedding、后端优化、建库与检索代码
├── tests/        # 单元测试和集成测试
├── configs/      # 路径、模型版本和实验配置
├── models/       # 角色模型、PLDA模型和本地运行时模型
├── data/         # 原始录音、处理后数据和资产清单
├── docs/         # 项目文档与历史评估报告
├── reports/      # 可重新生成的实验输出
├── scripts/      # 环境、清单和测试脚本
└── _temp/        # 临时文件，不进入版本控制
```

## 数据与模型

- `competition/data/raw/kesu_1000/`：985条双声道MP3录音副本，约1.08 GiB。
- `competition/models/runtime/modelscope/`：FunASR、VAD、标点和CAM++本地模型副本，约2.07 GiB。
- `competition/models/role/`：当前文本角色模型。
- `competition/models/backend/`：PLDA和embedding质量模型。
- 大体积录音、运行时模型、敏感embedding和运行报告默认不进入普通Git，只提交脱敏清单和说明文档。

## 快速开始

```powershell
cd competition
. .\scripts\set_env.ps1
python -m unittest discover -s tests\unit -p "test_*.py"
```

详细运行方式、模型口径和比赛基线见 [`competition/README.md`](competition/README.md)。

## 隔离原则

- 比赛代码只读取 `competition/` 下的配置、数据、模型和输出目录。
- 原 `声纹对比/` 作为历史项目本体保留，不纳入本仓库比赛提交。
- 原始录音和生物特征向量属于敏感数据，上传前必须确认比赛平台的数据合规要求。
- 所有阈值均需在独立验证集重新标定，不跨余弦、AS-norm和PLDA分数空间复用。
