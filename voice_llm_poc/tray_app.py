# -*- coding: utf-8 -*-
"""桌面托盘 UI(对标 Typeless 的常驻形态)。

托盘图标随状态变色:
    灰 = 空闲   红 = 录音中   橙 = 生成中
右键菜单:显示当前状态、三个模块的热键、打开配置、退出。

运行:python main.py --tray
"""
import os
import subprocess
import threading
from config import config

# 状态 -> 颜色
_COLORS = {
    "idle":      (120, 120, 130),
    "recording": (220, 60, 60),
    "busy":      (235, 170, 40),
}
_LABELS = {"idle": "空闲", "recording": "录音中", "busy": "生成中"}


def _make_icon(color):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 画一个简单的话筒:圆头 + 杆 + 底座
    d.ellipse([22, 10, 42, 40], fill=color)          # 话筒头
    d.rectangle([30, 38, 34, 50], fill=color)        # 杆
    d.rectangle([24, 50, 40, 54], fill=color)        # 底座
    return img


class TrayApp:
    def __init__(self):
        import pystray
        self.pystray = pystray
        self.pipeline = None          # 延迟创建(加载 ASR 模型较慢)
        self._status = "启动中(正在加载模型)…"
        self._status_key = "idle"
        self.icon = pystray.Icon(
            "voice_llm_poc",
            _make_icon(_COLORS["idle"]),
            "语音助手",
            menu=self._build_menu(),
        )

    def _build_menu(self):
        P = self.pystray
        M = P.MenuItem
        return P.Menu(
            M(lambda item: f"状态:{self._status}", None, enabled=False),
            P.Menu.SEPARATOR,
            M(f"口述      {config.HOTKEY_DICTATE}", None, enabled=False),
            M(f"翻译→{config.TRANSLATE_TARGET}  {config.HOTKEY_TRANSLATE}", None, enabled=False),
            M(f"问答/改写  {config.HOTKEY_ASK}", None, enabled=False),
            P.Menu.SEPARATOR,
            M("打开配置(.env)", self._open_env),
            M("退出", self._quit),
        )

    def _on_status(self, status, mode_label=None):
        self._status_key = status
        label = _LABELS.get(status, status)
        if mode_label:
            label += f"·{mode_label}"
        self._status = label
        try:
            self.icon.icon = _make_icon(_COLORS.get(status, _COLORS["idle"]))
            self.icon.title = f"语音助手 - {label}"
            self.icon.update_menu()
        except Exception:
            pass

    def _open_env(self, icon, item):
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        try:
            os.startfile(env_path)            # Windows
        except Exception:
            subprocess.Popen(["notepad", env_path])

    def _quit(self, icon, item):
        if self.pipeline:
            self.pipeline.stop()
        icon.stop()

    def _boot_pipeline(self):
        """后台加载模型并启动链路,避免托盘启动被阻塞。"""
        from pipeline import DictationPipeline
        self.pipeline = DictationPipeline(use_llm=True)
        self.pipeline.on_status = self._on_status
        self.pipeline.start()

    def run(self):
        # 托盘先亮起来,模型在后台加载
        threading.Thread(target=self._boot_pipeline, daemon=True).start()
        self.icon.run()


def run_tray():
    TrayApp().run()
