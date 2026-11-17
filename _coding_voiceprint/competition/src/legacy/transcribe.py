# -*- coding: utf-8 -*-
"""
中文语音转录: 用 FunASR Paraformer (阿里达摩院, 走 ModelScope 国内源) 把声道 wav 转成文字。
配 VAD + 标点模型, 输出带标点的中文文本。

用途: 把电话录音每个声道转文字, 通过话术内容判断谁是坐席(念催收话术)、谁是客户,
      并直接从文本发现代理黑产信号(模板化投诉/胁迫施压/异常诉求等)。

用法:
  MODELSCOPE_CACHE=./ms_cache python transcribe.py --wav-dir 0709/channels
  输出: 屏幕打印 + 写入 <wav-dir>/../转录文本.md
"""
import argparse
import glob
import os

MODEL = "paraformer-zh"       # 中文 Paraformer, 从 ModelScope 拉
VAD_MODEL = "fsmn-vad"        # 语音端点检测
PUNC_MODEL = "ct-punc"        # 标点恢复

_MODEL = None


def get_model():
    global _MODEL
    if _MODEL is None:
        from funasr import AutoModel
        # hub="ms" 强制走 ModelScope(阿里, 国内直连), 不走被墙的 HuggingFace
        _MODEL = AutoModel(model=MODEL, vad_model=VAD_MODEL,
                           punc_model=PUNC_MODEL, hub="ms", disable_update=True)
    return _MODEL


def transcribe(path):
    model = get_model()
    res = model.generate(input=path, batch_size_s=300)
    # res 是 list[dict], 取 text
    if res and isinstance(res, list) and "text" in res[0]:
        return res[0]["text"].strip()
    return ""


def call_of(name):
    """从别名取通话标识: 20260408_914787018349_L -> 20260408_914787018349"""
    parts = name.rsplit("_", 1)
    return parts[0] if len(parts) == 2 and parts[1] in ("L", "R") else name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav-dir", default="0709/channels")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.wav_dir, "*.wav")))
    if not files:
        print(f"{args.wav_dir} 下没有 wav")
        return

    out_path = args.out or os.path.join(os.path.dirname(args.wav_dir.rstrip("/\\")),
                                        "转录文本.md")

    results = {}
    for f in files:
        name = os.path.splitext(os.path.basename(f))[0]
        print(f"转录中: {name} ...")
        try:
            text = transcribe(f)
        except Exception as e:
            text = f"[转录失败: {e}]"
        results[name] = text
        print(f"  -> {text[:80]}{'...' if len(text) > 80 else ''}\n")

    # 按通话分组(L/R 配对)输出
    calls = {}
    for name, text in results.items():
        calls.setdefault(call_of(name), {})[name[-1]] = (name, text)

    lines = ["# 催收录音转录文本\n",
             "> 由 FunASR Paraformer(中文)转录; 每通话含左(L)/右(R)两声道\n"]
    for call, chans in sorted(calls.items()):
        lines.append(f"\n## 通话 {call}\n")
        for ch in ("L", "R"):
            if ch in chans:
                nm, tx = chans[ch]
                lines.append(f"### 声道 {ch} ({nm})\n\n{tx or '(无有效语音)'}\n")

    with open(out_path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(lines))
    print(f"\n全部完成, 转录文本已写入: {out_path}")


if __name__ == "__main__":
    main()
