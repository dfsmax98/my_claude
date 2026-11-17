# -*- coding: utf-8 -*-
"""FunASR 流式识别封装(CPU)。

对外提供:
    engine = ASREngine()
    text_piece = engine.feed(pcm_chunk, is_final=False)  # 喂一块音频,返回新增识别文本
    engine.reset()                                        # 一句话结束后重置缓存

首次运行会自动下载模型(paraformer-zh-streaming,约几百 MB),之后走本地缓存。
"""
import os
import threading
import numpy as np
from config import config

# 流式分块参数(paraformer-zh-streaming 官方推荐)
# chunk_size = [0, 10, 5] 代表 600ms 的处理块
CHUNK_SIZE = [0, 10, 5]
ENCODER_LOOK_BACK = 4
DECODER_LOOK_BACK = 1
# 每次送入模型的采样点数:chunk_size[1] * 960(16k 下 = 9600 = 600ms)
CHUNK_STRIDE = CHUNK_SIZE[1] * 960


class ASREngine:
    def __init__(self):
        self.sample_rate = config.ASR_SAMPLE_RATE
        self.chunk_stride = CHUNK_STRIDE
        self._cache = {}
        self._model = None
        # 模型和流式缓存都不是线程安全的:同一时刻只允许一个调用
        self._lock = threading.Lock()
        self._load_model()

    def _load_model(self):
        try:
            from funasr import AutoModel
        except ImportError as e:
            raise ImportError(
                "未安装 funasr。请先 pip install -r requirements.txt\n"
                "(torch 用 CPU 版:pip install torch torchaudio --index-url "
                "https://download.pytorch.org/whl/cpu)"
            ) from e
        ncpu = max(1, (os.cpu_count() or 4) - 1)   # 留一个核给音频采集/界面
        print(f"[ASR] 加载模型 {config.ASR_MODEL} (device={config.ASR_DEVICE}, 线程={ncpu}) ...")
        self._model = AutoModel(model=config.ASR_MODEL, device=config.ASR_DEVICE,
                                disable_update=True, disable_pbar=True, disable_log=True,
                                ncpu=ncpu)
        print("[ASR] 模型就绪")

    def feed(self, pcm_chunk: np.ndarray, is_final: bool = False) -> str:
        """喂一块 float32 PCM(单声道,16k),返回这一块新识别出的文本(可能为空)。"""
        with self._lock:
            res = self._model.generate(
                input=pcm_chunk,
                cache=self._cache,
                is_final=is_final,
                chunk_size=CHUNK_SIZE,
                encoder_chunk_look_back=ENCODER_LOOK_BACK,
                decoder_chunk_look_back=DECODER_LOOK_BACK,
                disable_pbar=True,
            )
        if res and len(res) > 0:
            return res[0].get("text", "")
        return ""

    def reset(self):
        """一句话结束后清空流式缓存,准备下一句。"""
        with self._lock:
            self._cache = {}
