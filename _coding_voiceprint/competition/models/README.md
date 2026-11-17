# 模型目录

- `role/`：当前文本角色识别模型和模型卡。
- `backend/`：PLDA模型、embedding质量模型和冻结cohort快照。
- `runtime/modelscope/`：FunASR、FSMN-VAD、标点和CAM++本地运行时模型副本。
- `runtime/denoise/`：FRCRN降噪模型副本；当前生产链路默认禁用。

`runtime/`约2.2 GiB，默认不进入Git。角色模型和后端模型使用Git LFS规则管理。

当前本地平台使用 `backend/customer_plda_v2_current_role/`；`backend/customer_plda_v1/`保留用于原冻结基线复现。两套后端分数空间和阈值不得混用。
