# -*- coding: utf-8 -*-
"""网页前端服务:FastAPI + WebSocket。

后台跑完整语音服务(全局热键/ASR/LLM/注入),浏览器开一个页面实时查看:
状态灯、实时转写、成稿结果、历史记录、当前配置。

运行:python main.py --web   然后浏览器打开 http://127.0.0.1:8900
"""
import os
import json
import asyncio
import threading
from collections import deque

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from config import config

HERE = os.path.dirname(os.path.abspath(__file__))
HOST = os.environ.get("WEB_HOST", "127.0.0.1")
PORT = int(os.environ.get("WEB_PORT", "8900"))

app = FastAPI(title="语音助手")

_clients = set()
_loop = None
_pipeline = None
_history = deque(maxlen=50)   # 最近记录,新连接时补发


# ---------- 事件广播(从 pipeline 线程 -> asyncio 循环 -> 所有浏览器)----------
def emit(evt):
    if _loop is None:
        return
    try:
        _loop.call_soon_threadsafe(_schedule_broadcast, evt)
    except RuntimeError:
        pass

def _schedule_broadcast(evt):
    if evt.get("type") in ("original", "result"):
        _history.append(evt)
    asyncio.ensure_future(_broadcast(evt))

async def _broadcast(evt):
    msg = json.dumps(evt, ensure_ascii=False)
    dead = []
    for ws in list(_clients):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for d in dead:
        _clients.discard(d)


# ---------- 生命周期 ----------
@app.on_event("startup")
async def _startup():
    global _loop
    _loop = asyncio.get_running_loop()
    # 在后台线程创建 pipeline(含模型加载,首次可能下载),避免阻塞网页启动
    threading.Thread(target=_boot_pipeline, daemon=True).start()
    print(f"\n网页已就绪:http://{HOST}:{PORT}  (语音模型在后台加载中,UI 可先打开)\n")


def _boot_pipeline():
    global _pipeline
    from pipeline import DictationPipeline
    _pipeline = DictationPipeline(use_llm=True)
    _pipeline.add_event_listener(emit)
    _pipeline.start()


@app.get("/api/config")
async def get_config():
    return {
        "model": config.LLM_MODEL,
        "base_url": config.LLM_BASE_URL,
        "translate_target": config.TRANSLATE_TARGET,
        "hotkeys": {
            "dictate": config.HOTKEY_DICTATE,
            "translate": config.HOTKEY_TRANSLATE,
            "ask": config.HOTKEY_ASK,
        },
        "output_mode": config.OUTPUT_MODE,
    }


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _clients.add(ws)
    # 补发最近历史,让新打开的页面不空白
    try:
        for evt in list(_history):
            await ws.send_text(json.dumps(evt, ensure_ascii=False))
        while True:
            await ws.receive_text()   # 目前前端只收不发,保持连接
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        _clients.discard(ws)


@app.get("/", response_class=HTMLResponse)
async def index():
    with open(os.path.join(HERE, "static", "index.html"), "r", encoding="utf-8") as f:
        return f.read()


def run_web():
    import uvicorn
    import webbrowser
    # 延迟打开浏览器
    threading.Timer(1.5, lambda: webbrowser.open(f"http://{HOST}:{PORT}")).start()
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
