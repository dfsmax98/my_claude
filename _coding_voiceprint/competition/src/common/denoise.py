# -*- coding: utf-8 -*-
"""
降噪封装(可开关)—— ClearVoice FRCRN_SE_16K。

⚠ A/B 实验结论(2026-07-29): 保持 ENABLED=False, 降噪不纳入固化管线。
原因(实测):
  1. clearvoice 依赖 numpy<2.0/soundfile==0.12.1, 与本环境(numpy2.4/py3.14)冲突;
     --no-deps 装本体 + 补 yamlargparse/pydub 后可 import(冒烟测试合成音频能过)。
  2. 但处理【真实客户声道】时: 同进程与 CAM++ 共存 -> 段错误(139);
     单独跑也在 CPU 上对 10s+ 真实音频超时/崩溃(退出124/139)。
  3. 结论: FRCRN/clearvoice 在当前 Py3.14 + numpy2.4 + torch-CPU 环境不可用。
     符合方案 §七预判(降噪有环境风险, 且学术证据本就提示降噪可能损害声纹)。
后续若要重启降噪: 需独立 GPU 环境 + 匹配的 numpy<2 依赖, 且仍须过 A/B 正收益判据。

学术证据: 独立语音增强会扭曲说话人信息, 可能损害声纹识别。故降噪默认关闭。
模型: ClearVoice FRCRN_SE_16K(16k 单通道时域, 独立 pip 包不走 pipelines)。
"""
import os
import tempfile

import numpy as np

# 全局开关: A/B 验证有正收益前保持 False
ENABLED = False

_DENOISER = None


def is_enabled():
    return ENABLED


def _get_denoiser():
    global _DENOISER
    if _DENOISER is None:
        from clearvoice import ClearVoice
        _DENOISER = ClearVoice(task="speech_enhancement",
                               model_names=["FRCRN_SE_16K"])
    return _DENOISER


def apply(signal, sr, force=False):
    """对单声道 16k 信号降噪。ENABLED=False 且非 force 时原样返回。

    signal: 1D float32 ndarray; 返回同形状归一化 ndarray。
    force: A/B 验证时绕过全局开关强制降噪。
    """
    if not ENABLED and not force:
        return signal

    import soundfile as sf
    cv = _get_denoiser()
    # FRCRN 是 16k 模型; 客户声道已是 16k, 若 sr!=16000 需上采样(此处约定 16k)
    with tempfile.TemporaryDirectory() as td:
        tin = os.path.join(td, "in.wav")
        sf.write(tin, np.asarray(signal, dtype=np.float32), sr)
        out = cv(input_path=tin, online_write=False)

    arr = np.asarray(out, dtype=np.float32).reshape(-1)  # (1,N) -> (N,)
    peak = np.max(np.abs(arr))                            # FRCRN 输出未归一化
    if peak > 0:
        arr = arr / peak * 0.95
    return arr
