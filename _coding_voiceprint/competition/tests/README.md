# 比赛工程测试指南

## 环境准备

```powershell
cd D:\数据智能部\d02206\codex\competition
. .\scripts\set_env.ps1
```

## 执行测试

```powershell
python -m unittest discover -s tests\unit -p "test_*.py" -v
```

当前共73项单元测试，包含角色识别、PLDA、质量模型、两类声纹库、N:N聚类、平台状态恢复、审核和Web聚合结果。

真实录音端到端测试应使用 `data/raw/` 中的授权样本，运行产物统一写入 `data/processed/platform/` 或 `_temp/`，不得提交Git。
