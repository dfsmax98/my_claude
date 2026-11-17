# -*- coding: utf-8 -*-
"""文本注入 + 选中文字抓取(对标 Typeless 的 input-helper / SelectedText)。

注入两种方式:
- paste:写入剪贴板,再模拟 Ctrl+V 粘贴 —— 对中文/Emoji 最稳,推荐。
- key  :用 pynput 逐字模拟键入 —— 对中文常失败(受输入法影响),仅备用。

抓选中:模拟 Ctrl+C。关键点是**等用户松开触发热键的 Ctrl/Alt**之后再发,
否则系统收到的是 Ctrl+Alt+C,不是复制。
"""
import sys
import time
from config import config

_SENTINEL = "__voice_llm_no_selection__"   # 不能含 \x00:Windows 剪贴板会在 \x00 处截断

# Windows 虚拟键码:Shift / Ctrl / Alt / 左右 Win
_VK_MODIFIERS = (0x10, 0x11, 0x12, 0x5B, 0x5C)


def _modifiers_down():
    """查询物理修饰键是否仍被按着(仅 Windows;其他平台返回 False)。"""
    if sys.platform != "win32":
        return False
    import ctypes
    gaks = ctypes.windll.user32.GetAsyncKeyState
    return any(gaks(vk) & 0x8000 for vk in _VK_MODIFIERS)


class TextInjector:
    def __init__(self):
        self.method = config.INJECT_METHOD
        from pynput.keyboard import Controller
        import pyperclip
        self._kb = Controller()
        self._clip = pyperclip

    # ---------- 修饰键处理 ----------
    def _wait_modifiers_released(self, timeout=0.8):
        """等用户松开 Ctrl/Alt/Shift/Win;超时则模拟松开,保证后续组合键干净。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not _modifiers_down():
                return
            time.sleep(0.02)
        from pynput.keyboard import Key
        for k in (Key.alt_l, Key.alt_r, Key.ctrl_l, Key.ctrl_r,
                  Key.shift_l, Key.shift_r, Key.cmd_l, Key.cmd_r):
            try:
                self._kb.release(k)
            except Exception:
                pass
        time.sleep(0.05)

    def _ctrl_combo(self, ch):
        from pynput.keyboard import Key
        with self._kb.pressed(Key.ctrl):
            self._kb.press(ch)
            self._kb.release(ch)

    def _clip_get(self):
        try:
            return self._clip.paste()
        except Exception:
            return None

    def _clip_set(self, text):
        try:
            self._clip.copy(text)
        except Exception:
            pass

    # ---------- 注入 ----------
    def inject(self, text):
        if not text:
            return
        self._wait_modifiers_released()
        if self.method == "paste":
            self._inject_paste(text)
        else:
            self._kb.type(text)

    def _inject_paste(self, text):
        old = self._clip_get()           # 备份原剪贴板,粘贴后还原
        self._clip_set(text)
        time.sleep(0.05)
        self._ctrl_combo("v")
        time.sleep(0.15)                 # 给目标应用时间读取剪贴板
        if old is not None:
            self._clip_set(old)

    # ---------- 抓取当前选中文字 ----------
    def get_selected_text(self, wait=0.5):
        """模拟 Ctrl+C 抓当前选中文本;抓完还原剪贴板。无选中返回空串。

        已知局限:少数编辑器(如 VS Code)在没有选中时按 Ctrl+C 会复制整行。
        """
        self._wait_modifiers_released()
        old = self._clip_get()
        self._clip_set(_SENTINEL)
        time.sleep(0.03)
        self._ctrl_combo("c")
        # 轮询等剪贴板被目标应用更新
        sel = ""
        deadline = time.time() + wait
        while time.time() < deadline:
            time.sleep(0.03)
            cur = self._clip_get()
            if cur is not None and cur != _SENTINEL:
                sel = cur
                break
        if old is not None:
            self._clip_set(old)
        return sel
