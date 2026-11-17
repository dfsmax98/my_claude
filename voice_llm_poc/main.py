# -*- coding: utf-8 -*-
"""入口 —— 复刻 Typeless 原生(三模块三热键)。

模块:
  口述  = 转写 + 润色成稿
  翻译  = 转写 + 翻译成目标语言
  问答  = 转写 + AI 回答

用法:
  python main.py                      # 启动:三个热键各管一个模块,结果敲到光标处
  python main.py --no-llm             # 不调 LLM,直接敲原始转写(验证 ASR)
  python main.py --print             # 结果只打印,不敲入(调试)
  python main.py --dictate "..."     # 文本测:口述润色
  python main.py --translate "..."   # 文本测:翻译
  python main.py --ask "..."         # 文本测:问答
  python main.py --fraud "..."       # 文本测:反欺诈研判(扩展)
  python main.py --check             # 检查配置与依赖
"""
import argparse
from config import config


def cmd_check():
    print("=== 配置检查 ===")
    print(f"LLM_BASE_URL : {config.LLM_BASE_URL}")
    print(f"LLM_MODEL    : {config.LLM_MODEL}")
    ok, msg = config.check_llm()
    print(f"LLM_API_KEY  : {'已配置' if ok else '缺失 -> ' + msg}")
    print(f"ASR_MODEL    : {config.ASR_MODEL} (device={config.ASR_DEVICE})")
    print(f"热键 口述    : {config.HOTKEY_DICTATE}")
    print(f"热键 翻译    : {config.HOTKEY_TRANSLATE}  → {config.TRANSLATE_TARGET}")
    print(f"热键 问答    : {config.HOTKEY_ASK}")
    print(f"输出         : {config.OUTPUT_MODE}({config.INJECT_METHOD})")
    for mod in ("funasr", "sounddevice", "numpy", "requests", "torch", "pynput", "pyperclip"):
        try:
            __import__(mod)
            print(f"依赖 {mod:12s}: OK")
        except ImportError:
            print(f"依赖 {mod:12s}: 未安装")


def _need_llm():
    ok, msg = config.check_llm()
    if not ok:
        print("[配置错误]", msg)
    return ok


def cmd_dictate(text):
    if not _need_llm():
        return
    from llm_client import LLMClient
    print(f"ASR原文: {text}")
    print(f"润色后 : {LLMClient().format_text(text)}")


def cmd_translate(text):
    if not _need_llm():
        return
    from llm_client import LLMClient
    print(f"ASR原文: {text}")
    print(f"译文({config.TRANSLATE_TARGET}): {LLMClient().translate_text(text, config.TRANSLATE_TARGET)}")


def cmd_ask(text):
    if not _need_llm():
        return
    from llm_client import LLMClient
    print(f"提问: {text}")
    print(f"回答: {LLMClient().answer_question(text)}")


def cmd_fraud(text):
    import json
    if not _need_llm():
        return
    from llm_client import LLMClient
    print(f"输入: {text}")
    print("研判:", json.dumps(LLMClient().analyze_fraud(text), ensure_ascii=False, indent=2))


def cmd_run(use_llm, print_only):
    if print_only:
        config.OUTPUT_MODE = "print"
    if use_llm and not _need_llm():
        print("可先用 --no-llm 只测转写,或 --dictate/--translate/--ask 测 LLM。")
        return
    from pipeline import DictationPipeline
    DictationPipeline(use_llm=use_llm).run()


def main():
    p = argparse.ArgumentParser(description="语音助手 PoC:口述/翻译/问答 三模块(复刻 Typeless)")
    p.add_argument("--tray", action="store_true", help="以桌面托盘图标常驻运行")
    p.add_argument("--web", action="store_true", help="启动网页前端(浏览器仪表盘,推荐)")
    p.add_argument("--no-llm", action="store_true", help="不调 LLM,直接敲原始转写")
    p.add_argument("--print", dest="print_only", action="store_true", help="结果只打印不敲入")
    p.add_argument("--dictate", type=str, help="文本测:口述润色")
    p.add_argument("--translate", type=str, help="文本测:翻译")
    p.add_argument("--ask", type=str, help="文本测:问答")
    p.add_argument("--fraud", type=str, help="文本测:反欺诈研判")
    p.add_argument("--check", action="store_true", help="检查配置与依赖")
    args = p.parse_args()

    if args.check:
        cmd_check()
    elif args.dictate:
        cmd_dictate(args.dictate)
    elif args.translate:
        cmd_translate(args.translate)
    elif args.ask:
        cmd_ask(args.ask)
    elif args.fraud:
        cmd_fraud(args.fraud)
    elif args.tray:
        if not _need_llm():
            return
        from tray_app import run_tray
        run_tray()
    elif args.web:
        if not _need_llm():
            return
        from web_server import run_web
        run_web()
    else:
        cmd_run(use_llm=not args.no_llm, print_only=args.print_only)


if __name__ == "__main__":
    main()
