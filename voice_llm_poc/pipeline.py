# -*- coding: utf-8 -*-
"""听写主链路(复刻 Typeless 原生,三模块三热键):

  热键1(口述)→ 录音 → 转写 → LLM 润色成稿  → 敲到光标处
  热键2(翻译)→ 录音 → 转写 → LLM 翻译译文  → 敲到光标处
  热键3(问答)→ 录音 → 转写 → 有选中:按指令改写选中 / 无选中:回答问题

线程模型(避免并发调用 ASR、避免丢尾音):
  - 麦克风回调线程:只往队列塞 100ms 的小音频块
  - 音频线程(唯一的 ASR 调用方):按顺序处理队列;"开始/结束"作为标记塞进同一队列,
    所以结束前录到的音频一定先处理完,再收尾
  - 命令线程:处理热键(热键回调本身立刻返回,不在键盘钩子里做重活)
  - 出稿线程:门控 + LLM + 注入
"""
import time
import queue
import threading
from collections import deque

import numpy as np
from config import config

_START = object()   # 队列标记:开始录音
_STOP = object()    # 队列标记:结束录音


class DictationPipeline:
    # 模块定义:名字 -> (热键, 中文标签)
    MODES = {
        "dictate":   (config.HOTKEY_DICTATE,   "口述"),
        "translate": (config.HOTKEY_TRANSLATE, "翻译"),
        "ask":       (config.HOTKEY_ASK,       "问答/改写"),
    }

    BLOCK = 1600          # 采集块:100ms(音量条刷新更顺滑)
    PREROLL_BLOCKS = 3    # 预录 300ms,防止吞掉第一个字

    def __init__(self, use_llm=True):
        from asr_engine import ASREngine, CHUNK_STRIDE
        self.asr = ASREngine()
        self.chunk_stride = CHUNK_STRIDE          # ASR 每次处理 600ms
        self.use_llm = use_llm
        self.output_mode = config.OUTPUT_MODE     # type | print

        self.llm = None
        if use_llm:
            from llm_client import LLMClient
            self.llm = LLMClient()

        # 始终创建注入器:问答模块要用它抓取选中文字(即使只打印)
        from text_injector import TextInjector
        self.injector = TextInjector()

        self._mic = None
        self._mic_ready = threading.Event()
        self._cmd_q = queue.Queue()
        self._recording = False
        self._busy = False
        self._active_mode = None
        self._selection = ""
        self._selection_ready = threading.Event()
        self._listener = None

        # 本句统计
        self._buffer = ""
        self._voiced_blocks = 0
        self._peak_rms = 0.0
        self._t_stop = 0.0

        # 自适应底噪(空闲时持续估计)
        self._noise_floor = 0.003

        self.on_status = None      # 可选回调 on_status(status, mode_label):给托盘更新图标
        self.on_event = None       # 可选单回调
        self.event_listeners = []  # on_event(dict) 监听器列表(网页/浮窗等)

    # ---------- 事件 ----------
    def add_event_listener(self, fn):
        self.event_listeners.append(fn)

    def _set_status(self, status, mode_label=None):
        if self.on_status:
            try:
                self.on_status(status, mode_label)
            except Exception:
                pass

    def _emit(self, evt):
        for fn in ([self.on_event] if self.on_event else []) + self.event_listeners:
            try:
                fn(evt)
            except Exception:
                pass

    # ---------- 启动 ----------
    def start(self):
        """非阻塞启动:浮窗 + 音频线程 + 命令线程 + 全局热键。"""
        from pynput import keyboard
        if config.SHOW_FLOATING_BAR:
            try:
                from floating_bar import FloatingBar
                self._bar = FloatingBar()
                self.add_event_listener(self._bar.on_event)
                self._bar.start()
            except Exception as e:
                print(f"[浮窗] 启动失败,忽略:{e}")
        if self.llm:
            threading.Thread(target=self.llm.warm_up, daemon=True).start()
        threading.Thread(target=self._audio_loop, daemon=True).start()
        threading.Thread(target=self._cmd_loop, daemon=True).start()
        hotkeys = {hk: (lambda m=mode: self._cmd_q.put(m))   # 回调立刻返回
                   for mode, (hk, _label) in self.MODES.items()}
        self._listener = keyboard.GlobalHotKeys(hotkeys)
        self._listener.start()
        self._set_status("idle")

    def stop(self):
        if self._listener:
            self._listener.stop()

    def run(self):
        """阻塞运行(控制台模式)。"""
        self._print_banner()
        self.start()
        self._listener.join()

    def _print_banner(self):
        print("=" * 60)
        print("  语音助手已就绪(复刻 Typeless),三个模块各一个热键:")
        for mode, (hk, label) in self.MODES.items():
            extra = f" → {config.TRANSLATE_TARGET}" if mode == "translate" else ""
            print(f"    [{label}]{extra:8s} {hk}")
        print("  * 问答/改写:选中文字时=按口述指令改写选中内容;未选中=口述问题求答")
        print("  用法:按热键开始说话,再按同一热键结束并出稿")
        print("  退出:在本窗口按 Ctrl+C")
        print("=" * 60)

    # ---------- 热键命令 ----------
    def _cmd_loop(self):
        while True:
            mode = self._cmd_q.get()
            try:
                self._toggle(mode)
            except Exception as e:
                print(f"[热键处理异常] {e}")

    def _toggle(self, mode):
        if self._busy:
            print("[忙] 上一句还在处理,稍等")
            return
        if not self._mic_ready.wait(timeout=5):
            print("[麦克风未就绪]")
            return
        if self._recording:
            # 结束:塞 STOP 标记,音频线程处理完之前的音频后收尾
            self._recording = False
            self._busy = True
            self._t_stop = time.time()
            label = self.MODES[self._active_mode][1]
            print(f"\n[●停止·{label}] 正在生成...")
            self._set_status("busy", label)
            self._emit({"type": "status", "status": "busy", "mode": label})
            self._mic.put_marker(_STOP)
        else:
            # 开始:先塞 START 标记立刻开录,选中文字在后台并行抓取
            self._active_mode = mode
            self._selection = ""
            self._selection_ready.clear()
            self._recording = True
            self._mic.put_marker(_START)
            label = self.MODES[mode][1]
            print(f"\n[○录音中·{label}] 请说话...")
            self._set_status("recording", label)
            self._emit({"type": "status", "status": "recording", "mode": label, "selection": ""})
            if mode == "ask":
                threading.Thread(target=self._grab_selection, daemon=True).start()
            else:
                self._selection_ready.set()

    def _grab_selection(self):
        try:
            sel = (self.injector.get_selected_text() or "").strip()
        except Exception as e:
            print(f"[抓取选中失败,按纯问答处理] {e}")
            sel = ""
        self._selection = sel
        self._selection_ready.set()
        if sel:
            preview = sel[:30].replace("\n", " ")
            print(f"\n[已选中 {len(sel)} 字:{preview}…] 口述内容将作为对它的指令")
            self._emit({"type": "status", "status": "recording", "mode": "改写选中", "selection": sel})
            self._set_status("recording", "改写选中")

    # ---------- 音频线程(唯一的 ASR 调用方)----------
    def _audio_loop(self):
        from audio_capture import MicCapture
        preroll = deque(maxlen=self.PREROLL_BLOCKS)
        pending = np.zeros(0, dtype=np.float32)
        in_utt = False
        with MicCapture(self.BLOCK) as mic:
            self._mic = mic
            self._mic_ready.set()
            for item in mic.chunks():
                if item is _START:
                    self.asr.reset()
                    self._buffer = ""
                    self._voiced_blocks = 0
                    self._peak_rms = 0.0
                    pending = np.concatenate(list(preroll)) if preroll else np.zeros(0, np.float32)
                    preroll.clear()
                    in_utt = True
                    continue
                if item is _STOP:
                    if in_utt:
                        t0 = time.time()
                        # 收尾:把剩余不足 600ms 的音频作为最后一块送入
                        tail = self.asr.feed(pending, is_final=True) if pending.size else \
                            self.asr.feed(np.zeros(self.chunk_stride, np.float32), is_final=True)
                        self._buffer += tail or ""
                        asr_tail_ms = (time.time() - t0) * 1000
                        text = self._buffer.strip()
                        stats = (self._voiced_blocks, self._peak_rms, self._noise_floor)
                        self.asr.reset()
                        pending = np.zeros(0, dtype=np.float32)
                        in_utt = False
                        threading.Thread(target=self._finalize, args=(text, stats, asr_tail_ms),
                                         daemon=True).start()
                    continue

                chunk = item
                rms = MicCapture.rms(chunk)
                if not in_utt:
                    # 空闲:持续估计环境底噪,并保留预录
                    self._noise_floor = 0.95 * self._noise_floor + 0.05 * rms
                    preroll.append(chunk)
                    continue

                # 录音中:音量(给浮窗/网页)+ 有效语音统计(给门控)
                self._emit({"type": "level", "level": round(self._display_level(rms), 3)})
                self._peak_rms = max(self._peak_rms, rms)
                if rms >= self._voice_threshold():
                    self._voiced_blocks += 1
                pending = np.concatenate([pending, chunk])
                while pending.size >= self.chunk_stride:
                    seg, pending = pending[:self.chunk_stride], pending[self.chunk_stride:]
                    piece = self.asr.feed(seg, is_final=False)
                    if piece:
                        self._buffer += piece
                        print(f"\r识别中: {self._buffer}", end="", flush=True)
                        self._emit({"type": "partial", "text": self._buffer})

    def _voice_threshold(self):
        """有效语音阈值:底噪的若干倍,且不低于绝对下限。"""
        return max(config.VAD_SILENCE_RMS, self._noise_floor * config.VAD_NOISE_RATIO)

    @staticmethod
    def _display_level(rms):
        """RMS 转 0~1 显示音量(按分贝映射,不同灵敏度的麦克风都能看到起伏)。"""
        db = 20 * np.log10(rms + 1e-9)
        return float(np.clip((db + 55) / 35, 0.0, 1.0))   # -55dB→0,-20dB→1

    # ---------- 出稿线程 ----------
    def _finalize(self, text, stats, asr_tail_ms):
        voiced_blocks, peak, floor = stats
        voiced_ms = voiced_blocks * self.BLOCK / config.ASR_SAMPLE_RATE * 1000
        try:
            print(f"\r[音频] 有效语音 {voiced_ms:.0f}ms 峰值RMS {peak:.4f} 底噪 {floor:.4f}" + " " * 10)
            if not text:
                # 完全没识别出内容:静默提示一下即可,不要求重说
                print("[没听到内容]")
                self._emit({"type": "notice", "reason": "没听到内容"})
                return
            print(f"[原文] {text}")
            # 问答模块:等后台抓选中完成(一般早已完成)
            self._selection_ready.wait(timeout=2)
            self._emit({"type": "original", "text": text,
                        "mode": self._active_mode, "selection": self._selection})
            t0 = time.time()
            result = self._handle(self._active_mode, text)
            llm_ms = (time.time() - t0) * 1000
            total_ms = (time.time() - self._t_stop) * 1000
            print(f"[耗时] 识别收尾 {asr_tail_ms:.0f}ms | LLM {llm_ms:.0f}ms | 松键到出稿 {total_ms:.0f}ms")
            self._output(result, {"asr_ms": round(asr_tail_ms), "llm_ms": round(llm_ms),
                                  "total_ms": round(total_ms)})
        except Exception as e:
            print(f"[出稿异常] {e}")
        finally:
            self._busy = False
            self._set_status("idle")
            self._emit({"type": "status", "status": "idle"})

    # ---------- 产出:按模块分派 LLM 任务 ----------
    def _handle(self, mode, text):
        if not self.use_llm:
            return text
        try:
            if mode == "dictate":
                return self.llm.format_text(text)
            if mode == "translate":
                return self.llm.translate_text(text, config.TRANSLATE_TARGET)
            if mode == "ask":
                if self._selection:
                    # 有选中文字:口述当指令,处理选中内容(结果替换选中)
                    return self.llm.rewrite_selection(self._selection, text)
                # 无选中:口述当问题
                return self.llm.answer_question(text)
            return text
        except Exception as e:
            print(f"[LLM 错误,退回原文] {e}")
            return text

    def _output(self, result, timing=None):
        print(f"[成稿] {result}")
        injected = False
        if self.output_mode == "type" and self.injector:
            self.injector.inject(result)
            print("[已敲入光标处]")
            injected = True
        print("-" * 60)
        self._emit({"type": "result", "text": result, "mode": self._active_mode,
                    "injected": injected, "timing": timing or {}})
