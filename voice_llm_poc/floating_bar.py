# -*- coding: utf-8 -*-
"""屏幕下方浮窗状态提示(对标 Typeless 的 floating bar)。

状态:
  listening  录音中 —— 动态音量条(随麦克风音量跳动)
  thinking   处理中 —— “思考中”+ 跳动圆点
  retry      没听清 —— 短暂提示“没听清,请再说一遍”后消失
  hidden     空闲   —— 浮窗隐藏

用 tkinter 实现(零依赖),在独立线程跑自己的事件循环;
通过 pipeline.add_event_listener(bar.on_event) 接收事件。
"""
import time
import threading
import random


class FloatingBar:
    def __init__(self):
        self._state = "hidden"      # hidden | listening | thinking | retry
        self._level = 0.0           # 0~1 显示音量
        self._retry_msg = ""
        self._hide_at = 0.0         # retry 自动消失时间
        self._bar_h = [0.1] * 7     # 音量条当前高度(平滑用)
        self._root = None
        self._thread = None

    # ---------- 对接 pipeline 事件 ----------
    def on_event(self, evt):
        t = evt.get("type")
        if t == "status":
            s = evt.get("status")
            if s == "recording":
                self._state = "listening"
            elif s == "busy":
                self._state = "thinking"
            elif s == "idle":
                if self._state != "retry":
                    self._state = "hidden"
        elif t == "level":
            # pipeline 已按分贝归一化到 0~1
            self._level = float(evt.get("level", 0.0))
        elif t in ("retry", "notice"):
            self._retry_msg = evt.get("reason") or "没听清,请再说一遍"
            self._state = "retry"
            self._hide_at = time.time() + 2.2
        elif t in ("result", "empty"):
            # 出稿完成后由随后的 idle 收尾;这里不动
            pass

    # ---------- 启动 ----------
    def start(self):
        self._thread = threading.Thread(target=self._tk_main, daemon=True)
        self._thread.start()

    def _tk_main(self):
        try:
            import tkinter as tk
        except Exception as e:
            print(f"[浮窗] tkinter 不可用,跳过浮窗:{e}")
            return
        root = tk.Tk()
        self._root = root
        root.overrideredirect(True)          # 无边框
        root.attributes("-topmost", True)    # 置顶
        try:
            root.attributes("-alpha", 0.93)
        except Exception:
            pass
        W, H = 230, 58
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        x = (sw - W) // 2
        y = sh - 130
        root.geometry(f"{W}x{H}+{x}+{y}")
        self._canvas = tk.Canvas(root, width=W, height=H, highlightthickness=0, bg="#12141a")
        self._canvas.pack(fill="both", expand=True)
        self._W, self._H = W, H
        root.withdraw()
        self._visible = False
        self._render()
        root.mainloop()

    # ---------- 渲染循环(~30fps)----------
    def _render(self):
        import tkinter as tk
        root, c = self._root, self._canvas
        state = self._state

        # retry 到点自动隐藏
        if state == "retry" and time.time() >= self._hide_at:
            self._state = state = "hidden"

        # 显隐
        want_visible = state != "hidden"
        if want_visible and not self._visible:
            root.deiconify(); root.attributes("-topmost", True); self._visible = True
        elif not want_visible and self._visible:
            root.withdraw(); self._visible = False

        if self._visible:
            c.delete("all")
            W, H = self._W, self._H
            # 圆角底板
            self._round_rect(c, 2, 2, W - 2, H - 2, 16, fill="#1b1f29", outline="#2a2f3a")
            if state == "listening":
                self._draw_bars(c, W, H)
            elif state == "thinking":
                self._draw_thinking(c, W, H)
            elif state == "retry":
                self._draw_text(c, W, H, "🔇  " + self._retry_msg, "#f59e0b")

        root.after(33, self._render)

    def _draw_bars(self, c, W, H):
        n = len(self._bar_h)
        cx, cy = W // 2, H // 2
        gap, bw = 7, 5
        total = n * bw + (n - 1) * gap
        x0 = cx - total // 2
        for i in range(n):
            # 目标高度:中间高两头低 + 音量 + 随机活跃度
            center_bias = 1.0 - abs(i - (n - 1) / 2) / (n / 1.6)
            target = 0.12 + self._level * center_bias * (0.7 + 0.6 * random.random())
            target = min(1.0, target)
            # 平滑
            self._bar_h[i] += (target - self._bar_h[i]) * 0.35
            bh = int(self._bar_h[i] * (H - 22))
            bh = max(4, bh)
            x = x0 + i * (bw + gap)
            color = "#4f8cff" if self._level > 0.05 else "#3a4254"
            c.create_rectangle(x, cy - bh // 2, x + bw, cy + bh // 2,
                               fill=color, outline="", width=0)

    def _draw_thinking(self, c, W, H):
        c.create_text(W // 2 - 18, H // 2, text="思考中", fill="#e6e8ec",
                      font=("Microsoft YaHei", 12, "bold"))
        # 三个跳动圆点
        phase = int(time.time() * 3) % 3
        for i in range(3):
            x = W // 2 + 24 + i * 11
            r = 4 if i == phase else 2
            col = "#f59e0b" if i == phase else "#5a6373"
            c.create_oval(x - r, H // 2 - r, x + r, H // 2 + r, fill=col, outline="")

    def _draw_text(self, c, W, H, text, color):
        c.create_text(W // 2, H // 2, text=text, fill=color,
                      font=("Microsoft YaHei", 11, "bold"))

    @staticmethod
    def _round_rect(c, x1, y1, x2, y2, r, **kw):
        pts = [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r, x2,y2-r, x2,y2, x2-r,y2,
               x1+r,y2, x1,y2, x1,y2-r, x1,y1+r, x1,y1]
        c.create_polygon(pts, smooth=True, **kw)
