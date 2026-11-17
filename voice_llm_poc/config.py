# -*- coding: utf-8 -*-
"""配置加载:优先读 .env 文件,其次读系统环境变量,最后用默认值。

不依赖 python-dotenv 也能工作(内置简易解析)。
"""
import os

def _load_dotenv():
    """把同目录 .env 读进 os.environ(不覆盖已存在的系统变量)。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)

_load_dotenv()

def _get(key, default=None):
    return os.environ.get(key, default)

class Config:
    # LLM
    LLM_BASE_URL = _get("LLM_BASE_URL", "https://llmapi.lovbrowser.com").rstrip("/")
    LLM_API_KEY  = _get("LLM_API_KEY", "")
    # 默认用不带"思考"的快模型:实测 haiku 2~6s,推理类 flash 模型 15~30s
    LLM_MODEL    = _get("LLM_MODEL", "claude-haiku-4-5-20251001")
    LLM_CHAT_PATH = _get("LLM_CHAT_PATH", "/v1/chat/completions")
    LLM_TIMEOUT  = float(_get("LLM_TIMEOUT", "30"))
    LLM_MAX_TOKENS = int(_get("LLM_MAX_TOKENS", "1024"))

    # LLM 任务模式:format=听写润色(Typeless 原生)  fraud=反欺诈研判(本地化扩展)
    LLM_TASK = _get("LLM_TASK", "format")

    # ASR
    ASR_MODEL       = _get("ASR_MODEL", "paraformer-zh-streaming")
    ASR_SAMPLE_RATE = int(_get("ASR_SAMPLE_RATE", "16000"))
    ASR_DEVICE      = _get("ASR_DEVICE", "cpu")

    # 端点检测 / 有效语音判定
    # 绝对下限(RMS);实际阈值 = max(下限, 环境底噪 × VAD_NOISE_RATIO),自动适配不同麦克风
    VAD_SILENCE_RMS = float(_get("VAD_SILENCE_RMS", "0.004"))
    VAD_NOISE_RATIO = float(_get("VAD_NOISE_RATIO", "3.0"))
    VAD_SILENCE_MS  = int(_get("VAD_SILENCE_MS", "800"))

    # ===== 浮窗(屏幕下方状态提示)=====
    SHOW_FLOATING_BAR = _get("SHOW_FLOATING_BAR", "true").lower() in ("1", "true", "yes", "on")

    # ASR 识别语言(当前模型以中文为主;预留)
    LANG = _get("LANG", "zh")

    # ===== 三大模块的触发热键(各一个,toggle:按一下开始,再按一下出稿)=====
    HOTKEY_DICTATE   = _get("HOTKEY_DICTATE", "<ctrl>+<alt>+d")    # 1.口述转写
    HOTKEY_TRANSLATE = _get("HOTKEY_TRANSLATE", "<ctrl>+<alt>+t")  # 2.翻译
    HOTKEY_ASK       = _get("HOTKEY_ASK", "<ctrl>+<alt>+a")        # 3.问答/选中改写(按选中与否自动切换)
    # 翻译目标语言
    TRANSLATE_TARGET = _get("TRANSLATE_TARGET", "英语")

    # 结果输出方式:type=敲到光标处  print=只打印(调试用)
    OUTPUT_MODE = _get("OUTPUT_MODE", "type")
    # 注入方式:paste=剪贴板+Ctrl+V(中文推荐)  key=逐字模拟键入
    INJECT_METHOD = _get("INJECT_METHOD", "paste")

    @classmethod
    def check_llm(cls):
        """返回 (ok, message)。"""
        if not cls.LLM_API_KEY or cls.LLM_API_KEY.startswith("在这里填"):
            return False, "LLM_API_KEY 未配置,请复制 .env.example 为 .env 并填入 key"
        return True, "ok"


config = Config()
