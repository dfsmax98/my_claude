# -*- coding: utf-8 -*-
"""可插拔 LLM 客户端:OpenAI 兼容的 /v1/chat/completions 接口。

默认打你们的网关 https://llmapi.lovbrowser.com,鉴权走 Bearer <api-key>。
如果网关返回结构有差异,只需改 _parse_response。
"""
import json
import re
import time
import requests
from config import config
from prompts import (
    FORMAT_SYSTEM_PROMPT, build_format_prompt,
    TRANSLATE_SYSTEM_PROMPT, build_translate_prompt,
    ASK_SYSTEM_PROMPT, build_ask_prompt,
    REWRITE_SYSTEM_PROMPT, build_rewrite_prompt,
    FRAUD_SYSTEM_PROMPT, build_fraud_prompt,
)

# 网关前有 Cloudflare,会按浏览器指纹拦截/限速非浏览器 UA,这里伪装成 Chrome
_BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")


class LLMClient:
    def __init__(self):
        self.base_url = config.LLM_BASE_URL
        self.url = config.LLM_BASE_URL + config.LLM_CHAT_PATH
        self.model = config.LLM_MODEL
        self.timeout = config.LLM_TIMEOUT
        self.headers = {
            "Authorization": f"Bearer {config.LLM_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": _BROWSER_UA,
        }
        # 复用 TCP/TLS 连接,省掉每次请求的握手
        self.session = requests.Session()

    def warm_up(self):
        """启动时预先建立到网关的连接(失败无所谓)。"""
        try:
            self.session.head(self.base_url, headers={"User-Agent": _BROWSER_UA}, timeout=5)
        except Exception:
            pass

    def _post(self, payload):
        """发一次请求;超时/断连自动重试一次(网关偶发抖动)。"""
        for attempt in (1, 2):
            try:
                resp = self.session.post(self.url, headers=self.headers,
                                         data=json.dumps(payload), timeout=self.timeout)
                resp.raise_for_status()
                return resp
            except (requests.ReadTimeout, requests.ConnectTimeout, requests.ConnectionError):
                if attempt == 2:
                    raise
                time.sleep(0.5)
                print("[LLM] 请求超时/断连,重试一次…")

    def chat(self, messages, temperature=0.2):
        """底层聊天调用,返回助手文本。"""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": config.LLM_MAX_TOKENS,
            "stream": False,
        }
        resp = self._post(payload)
        return self._parse_response(resp.json())

    @staticmethod
    def _parse_response(data):
        # OpenAI 兼容结构
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            # 兜底:有些网关直接返回 content / text
            for k in ("content", "text", "data"):
                if isinstance(data.get(k), str):
                    return data[k]
            raise ValueError(f"无法解析 LLM 响应: {json.dumps(data, ensure_ascii=False)[:300]}")

    # ---------- Typeless 原生:听写润色 ----------
    def format_text(self, transcript, app_context=""):
        """把 ASR 原始文本整理成干净书面文本,返回字符串。"""
        messages = [
            {"role": "system", "content": FORMAT_SYSTEM_PROMPT},
            {"role": "user", "content": build_format_prompt(transcript, app_context)},
        ]
        return self.chat(messages, temperature=0.2).strip()

    # ---------- Typeless 原生:翻译 ----------
    def translate_text(self, transcript, target):
        """把口述内容翻译成 target 语言,返回译文。"""
        messages = [
            {"role": "system", "content": TRANSLATE_SYSTEM_PROMPT.format(target=target)},
            {"role": "user", "content": build_translate_prompt(transcript, target)},
        ]
        return self.chat(messages, temperature=0.3).strip()

    # ---------- Typeless 原生:问问题 ----------
    def answer_question(self, transcript):
        """把口述当作问题,返回 AI 回答。"""
        messages = [
            {"role": "system", "content": ASK_SYSTEM_PROMPT},
            {"role": "user", "content": build_ask_prompt(transcript)},
        ]
        return self.chat(messages, temperature=0.4).strip()

    # ---------- Typeless 原生:针对选中文字改写/提问 ----------
    def rewrite_selection(self, selected_text, instruction):
        """按语音指令处理选中文字,返回结果(用于替换选中内容)。"""
        messages = [
            {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
            {"role": "user", "content": build_rewrite_prompt(selected_text, instruction)},
        ]
        return self.chat(messages, temperature=0.3).strip()

    # ---------- 扩展:反欺诈研判 ----------
    def analyze_fraud(self, transcript, context=""):
        messages = [
            {"role": "system", "content": FRAUD_SYSTEM_PROMPT},
            {"role": "user", "content": build_fraud_prompt(transcript, context)},
        ]
        raw = self.chat(messages)
        return self._extract_json(raw)

    @staticmethod
    def _extract_json(text):
        """从模型输出里抠出 JSON(容忍 ```json 包裹或前后多余文字)。"""
        text = text.strip()
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            text = text[start:end + 1]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"risk_level": "unknown", "raw": text}


if __name__ == "__main__":
    # 快速自测:python llm_client.py
    ok, msg = config.check_llm()
    if not ok:
        print("[配置错误]", msg)
    else:
        client = LLMClient()
        demo = "嗯那个就是说我们明天上午十点开个会然后对一下这个季度的那个数据啊对就这样"
        print("ASR原文:", demo)
        print("润色后 :", client.format_text(demo))
