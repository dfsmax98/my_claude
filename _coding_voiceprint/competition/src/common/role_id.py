# -*- coding: utf-8 -*-
"""
角色识别 —— 抽自 0728/role_id.py 的 kw_score / load_diar, 融合逻辑抽成 decide_role。

判定双轨录音里哪个声道是坐席、哪个是客户:
  证据A(主): 转写坐席话术密度(每千字加权命中)
  证据C(兜底): 谁先开口(坐席通常先报家门)
  证据B(跨通复现度)在 8k 上不可靠, 已降级为参考, 不在本模块判定。
"""
import json
import io

# 坐席专属话术关键词。只保留能体现坐席身份或服务动作的短语，
# 不使用“平台、欠款、还款、征信”等双方都会说的业务主题词。
KW = {
    "坐席身份": (["很高兴为您服务", "客服这边", "我是客服", "客户服务中心", "工号"], 5.0),
    "身份核验": (["请问您来电", "来电号码", "注册号码", "注册手机号码", "预留号码",
               "请问是本人吗", "请问您本人", "核实一下您的", "确认一下您的"], 4.0),
    "服务动作": (["帮您查询", "为您查询", "帮您反馈", "为您反馈", "帮您申请",
               "为您申请", "帮您记录", "为您记录", "帮您处理", "为您处理",
               "帮您加急", "为您加急", "工作人员联系您"], 3.0),
    "坐席礼貌": (["请问有什么可以帮", "有什么可以帮您", "麻烦您稍等", "请您稍等"], 2.0),
}
SPK_TAG = {0: "L", 1: "R"}   # 双轨: speaker0=左, speaker1=右

HIGH_MIN_EVIDENCE = 5.0
MEDIUM_MIN_EVIDENCE = 3.0
HIGH_MIN_RATIO = 1.8
MEDIUM_MIN_RATIO = 1.35
HIGH_MIN_SCORE_MARGIN = 10.0
MEDIUM_MIN_SCORE_MARGIN = 5.0
FIRST_SPEECH_MIN_GAP = 0.3


def kw_score(text):
    """坐席话术加权命中密度(每千字)。返回 (加权分, 命中明细)。"""
    n = max(len(text), 1)
    total = 0.0
    detail = {}
    for cat, (words, w) in KW.items():
        hits = sum(text.count(word) for word in words)
        detail[cat] = hits
        total += hits * w
    return total / n * 1000, detail


def kw_evidence(text):
    """返回坐席话术密度、命中明细、加权证据和字符数。"""
    score, detail = kw_score(text)
    weighted_hits = sum(detail[category] * weight
                        for category, (_, weight) in KW.items())
    return score, detail, weighted_hits, max(len(text), 1)


def load_diar(jpath):
    """读 diar json, 返回 {speaker: {'text':拼接文本, 'dur':总时长, 'first':最早start}}。"""
    with io.open(jpath, encoding="utf-8") as f:
        segs = json.load(f)
    agg = {}
    for s in segs:
        spk = s["speaker"]
        a = agg.setdefault(spk, {"text": "", "dur": 0.0, "first": 1e9})
        a["text"] += s.get("text", "")
        a["dur"] += s["end"] - s["start"]
        a["first"] = min(a["first"], s["start"])
    return agg


def decide_role(agg):
    """由 load_diar 的聚合结果判定坐席/客户声道。

    输入 agg: {speaker: {'text','dur','first'}}, 需含 speaker 0 和 1。
    返回 {'agent_ch','customer_ch','confidence','ka','kb'}。
      confidence: 高/中/中(话术接近,先开口佐证)/低(话术接近,需人工核对)
    只有坐席专属话术证据达到门槛时才允许高/中置信；先开口只作中置信佐证。
    """
    if 0 not in agg or 1 not in agg:
        return {"agent_ch": None, "customer_ch": None, "confidence": "缺一方",
                "ka": 0.0, "kb": 0.0}

    ka, _, evidence_a, _ = kw_evidence(agg[0]["text"])
    kb, _, evidence_b, _ = kw_evidence(agg[1]["text"])
    return decide_role_from_scores(
        ka, kb, agg[0].get("first"), agg[1].get("first"),
        evidence_a=evidence_a, evidence_b=evidence_b,
    )


def decide_role_from_scores(ka, kb, first_a, first_b,
                            evidence_a=None, evidence_b=None):
    """使用坐席专属话术证据和有效首次发声时间判断角色。"""
    a_by_kw = 0 if ka >= kb else 1
    hi, lo = max(ka, kb), min(ka, kb)
    ratio = hi / lo if lo > 1e-6 else (999.0 if hi > 1e-6 else 1.0)
    margin = hi - lo
    evidence = [evidence_a, evidence_b]
    if evidence_a is None or evidence_b is None:
        # 兼容只传密度分的旧调用；生产路径始终传真实加权命中。
        evidence = [ka, kb]
    hi_evidence = max(evidence)

    first_valid = (
        first_a is not None and first_b is not None
        and abs(float(first_a) - float(first_b)) >= FIRST_SPEECH_MIN_GAP
    )
    a_by_first = None
    if first_valid:
        a_by_first = 0 if float(first_a) < float(first_b) else 1

    if (hi_evidence >= HIGH_MIN_EVIDENCE
            and ratio >= HIGH_MIN_RATIO
            and margin >= HIGH_MIN_SCORE_MARGIN):
        agent_spk, conf = a_by_kw, "高"
    elif (hi_evidence >= MEDIUM_MIN_EVIDENCE
          and ratio >= MEDIUM_MIN_RATIO
          and margin >= MEDIUM_MIN_SCORE_MARGIN):
        agent_spk, conf = a_by_kw, "中"
    else:
        agent_spk = a_by_kw
        if (hi_evidence >= MEDIUM_MIN_EVIDENCE
                and a_by_first is not None
                and a_by_kw == a_by_first):
            conf = "中(话术接近,先开口佐证)"
        elif hi_evidence < MEDIUM_MIN_EVIDENCE:
            conf = "低(坐席话术证据不足,需人工核对)"
        else:
            conf = "低(话术接近,需人工核对)"

    return {"agent_ch": SPK_TAG[agent_spk], "customer_ch": SPK_TAG[1 - agent_spk],
            "confidence": conf, "ka": round(ka, 2), "kb": round(kb, 2),
            "evidence_a": round(float(evidence[0]), 3),
            "evidence_b": round(float(evidence[1]), 3),
            "score_ratio": round(float(ratio), 3),
            "score_margin": round(float(margin), 3),
            "first_speech_used": conf == "中(话术接近,先开口佐证)"}
