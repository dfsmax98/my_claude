# -*- coding: utf-8 -*-
"""lov-model 探测脚本：对 lovbrowser 网关逐档探测模型可用性。"""

import json
import os


def get_token():
    """从环境变量取 token，优先 ANTHROPIC_AUTH_TOKEN。"""
    tok = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY")
    if not tok:
        raise RuntimeError(
            "未找到 token：请设置环境变量 ANTHROPIC_AUTH_TOKEN（或 ANTHROPIC_API_KEY）"
        )
    return tok


def load_config(path):
    """读取并校验 models.json，补默认值。"""
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    if not cfg.get("base_url"):
        raise ValueError("models.json 缺少 base_url")
    if not cfg.get("auto_route"):
        raise ValueError("models.json 的 auto_route 不能为空")
    cfg.setdefault("timeout_seconds", 10)
    cfg.setdefault("manual_only", [])
    return cfg


def classify(status):
    """HTTP 状态码 -> 判定类别。"""
    if status == 200:
        return "ok"
    if status == 429:
        return "ratelimited"
    if status in (401, 403):
        return "auth_error"
    return "unavailable"


def _send(url, data, headers, timeout):
    """实际发送 HTTP POST，返回 (status, body_bytes)。"""
    import ssl
    import urllib.request
    import urllib.error
    req = urllib.request.Request(url, data=data, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    # 使用默认安全 TLS 上下文（校验证书与主机名）。Python 走 OpenSSL，
    # 不做 Windows schannel 的在线吊销检查，因此无需削弱校验。
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.status, resp.read()[:300]
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()[:300]


def probe_model(base_url, token, model, timeout):
    """对单个模型发 max_tokens:1 探测。返回 (category, status, detail)。"""
    url = base_url.rstrip("/") + "/v1/messages"
    data = json.dumps({
        "model": model,
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "hi"}],
    }).encode("utf-8")
    headers = {
        "content-type": "application/json",
        "anthropic-version": "2023-06-01",
        "x-api-key": token,
        "Authorization": "Bearer " + token,
        # 网关前置 Cloudflare 会按浏览器指纹拦截无 UA 的请求（error 1010），必须带 UA
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    }
    try:
        status, body = _send(url, data, headers, timeout)
    except Exception as exc:  # 网络错误/超时
        return "unavailable", None, str(exc)[:200]
    return classify(status), status, body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)


def run(config, token, only_model=None):
    """编排探测。返回 selected / results / stopped_reason。"""
    base = config["base_url"]
    timeout = config.get("timeout_seconds", 10)
    results = []
    if only_model is not None:
        cat, status, detail = probe_model(base, token, only_model, timeout)
        results.append((only_model, cat, status, detail))
        return {
            "selected": only_model if cat == "ok" else None,
            "results": results,
            "stopped_reason": "manual",
        }
    for model in config["auto_route"]:
        cat, status, detail = probe_model(base, token, model, timeout)
        results.append((model, cat, status, detail))
        if cat == "ok":
            return {"selected": model, "results": results, "stopped_reason": None}
        if cat == "auth_error":
            return {"selected": None, "results": results, "stopped_reason": "auth_error"}
    return {"selected": None, "results": results, "stopped_reason": "exhausted"}


def format_output(out):
    """把 run() 结果格式化为人读文本 + 机器可读尾行。"""
    icon = {"ok": "OK ", "ratelimited": "限流", "unavailable": "不可用", "auth_error": "鉴权失败"}
    lines = ["模型探测结果："]
    for model, cat, status, _ in out["results"]:
        st = status if status is not None else "-"
        lines.append("  [{}] {} (HTTP {})".format(icon.get(cat, cat), model, st))
    lines.append("")
    if out["selected"]:
        lines.append("推荐使用：{}".format(out["selected"]))
        lines.append("→ 请在会话内执行： /model {}".format(out["selected"]))
        lines.append("RECOMMEND: {}".format(out["selected"]))
    else:
        reason = out["stopped_reason"]
        if reason == "auth_error":
            lines.append("鉴权失败：换模型无用。请检查环境变量 ANTHROPIC_AUTH_TOKEN 的 token 是否有效。")
        else:
            lines.append("auto_route 全部不可用（{}）。可检查网关/网络，或手动探测：probe.py --model <name>".format(reason))
        lines.append("RECOMMEND: none ({})".format(reason))
    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="lov-model 探测与路由")
    parser.add_argument("--model", default=None, help="只探测指定模型（手动模式）")
    parser.add_argument("--config", default=None, help="models.json 路径")
    args = parser.parse_args()
    cfg_path = args.config or os.path.join(os.path.dirname(os.path.abspath(__file__)), "models.json")
    try:
        cfg = load_config(cfg_path)
        token = get_token()
    except (ValueError, RuntimeError, OSError) as exc:
        print("配置/凭证错误：{}".format(exc))
        print("RECOMMEND: none (config_error)")
        return 1
    out = run(cfg, token, only_model=args.model)
    print(format_output(out))
    return 0 if out["selected"] else 2


if __name__ == "__main__":
    import sys
    sys.exit(main())
