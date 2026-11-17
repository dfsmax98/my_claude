# -*- coding: utf-8 -*-
"""麦克风采集:持续产出固定大小的 float32 PCM 块。

sounddevice 回调把音频塞进队列;主循环按顺序取。
除音频块外,队列里还可以插入"标记"对象(开始/结束录音),
保证"结束"一定排在它之前录到的所有音频之后处理,不丢尾音。
"""
import queue
import numpy as np
import sounddevice as sd
from config import config


class MicCapture:
    def __init__(self, blocksize):
        self.sample_rate = config.ASR_SAMPLE_RATE
        self.blocksize = blocksize            # 每块采样点数
        self._q = queue.Queue()
        self._stream = None

    def _callback(self, indata, frames, time_info, status):
        if status:
            # 溢出等告警,PoC 阶段打印即可
            print(f"[音频] {status}")
        # indata: float32, shape=(frames, 1) -> 压成一维
        self._q.put(indata[:, 0].copy())

    def put_marker(self, marker):
        """往音频队列插入一个标记(按时间顺序和音频块一起被处理)。"""
        self._q.put(marker)

    def __enter__(self):
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.blocksize,
            callback=self._callback,
        )
        self._stream.start()
        return self

    def __exit__(self, *exc):
        if self._stream:
            self._stream.stop()
            self._stream.close()

    def chunks(self):
        """生成器:持续产出音频块(np.ndarray)或标记对象。"""
        while True:
            yield self._q.get()

    @staticmethod
    def rms(chunk: np.ndarray) -> float:
        """计算一块音频的均方根能量(0~1),用于静音判定。"""
        if chunk.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))
