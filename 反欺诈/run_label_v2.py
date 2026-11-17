# -*- coding: utf-8 -*-
"""
App 反欺诈打标 v2 (claude-sonnet-4-6 + tool_use 结构化输出 + 规则前置)

用法:
    # 默认跑全量 applist_tag.csv
    python run_label_v2.py
    # 或指定输入和输出前缀
    python run_label_v2.py sample_200.csv sample_200_v2new

输出:
    <prefix>.csv  +  <prefix>.xlsx (多 sheet)
    缓存独立到 applist_label_cache_<prefix>.sqlite

v2.1 变更:
  - 模型名 claude-opus-4-6 → claude-sonnet-4-6 (前者不存在; sonnet 性价比够)
  - 输出走 tool_use, 不再正则解析 JSON
  - 落库前做 l1/l2/risk_type 白名单校验
  - 规则前置: 已知大厂 app / 系统应用直接命中, 不耗 LLM
  - 系统提示词加 few-shot 边界示例
  - max_tokens 4096 → 8192, 长包名不再被截断
  - 重试区分 429 / 其他, 429 读 retry-after

v2.2 变更 (标签体系优化):
  - L1/L2 严格按功能划分, 风险信号全部上到 risk_type (上游不区分黑产工具 L1)
  - RISK_TYPES: 17 → 20 项
    + 新增: 远程控制 / 代还套现 / 撸口子指南 / AI伪造 / 走私换汇
    + 合并: 山寨低质 + 伪冒仿冒 → 仿冒山寨
    + 删除: 隐私窃取 (LLM 仅凭包名/app_name 标不出, 真要用走黑名单)
    + 约束: "未知" 仅当 l1=未知 时使用, 在 validate_label 强制对齐

v2.3 变更 (稳定性加固):
  - temperature=0, 同一输入跨次结果尽量一致
  - app_l2 加 enum 约束 (扁平化 L2_MAP 全集), LLM 不能再造词
  - "LLM未返回" 的失败结果不写缓存, 下次自动重试
  - SYSTEM_PROMPT 显式禁止造词, 必须在给定枚举里挑
"""
import os
import re
import sys
import json
import time
import sqlite3
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic
import pandas as pd

BASE = Path(r"d:\my_claude\反欺诈")
BATCH_DIR = BASE / "tagging_tmp"

MODEL = "claude-sonnet-4-6"
BATCH_SIZE = 30
MAX_WORKERS = 6
MAX_RETRIES = 3
MAX_TOKENS = 8192

# ==================== 标签体系 ====================
APP_L1 = [
    "系统应用", "办公软件", "借贷软件", "金融理财", "银行", "政务",
    "社交通讯", "电商购物", "生活服务", "出行交通", "视频影音",
    "阅读资讯", "游戏", "教育学习", "摄影美化", "健康运动", "旅游",
    "工具", "区块链加密", "色情成人", "棋牌赌博", "其他", "未知",
]
L2_MAP = {
    "系统应用": ["系统组件", "桌面启动", "厂商应用"],
    "办公软件": ["文档处理", "协作OA", "邮箱", "会议视频", "翻译"],
    "借贷软件": ["小额现金贷", "银行信贷", "消费分期", "信用卡管理", "助贷导流", "贷款超市"],
    "金融理财": ["基金股票", "保险理财", "记账", "外汇", "支付钱包"],
    "银行": ["银行APP"],
    "政务": ["政务服务"],
    "社交通讯": ["即时通讯", "陌生人社交", "出海社交", "匿名IM", "社区论坛", "婚恋"],
    "电商购物": ["综合电商", "垂直电商", "二手电商", "海淘特卖", "拼团"],
    "生活服务": ["外卖", "本地生活", "招聘", "家政维修", "投诉维权"],
    "出行交通": ["网约车", "公共交通", "地图导航", "火车机票"],
    "视频影音": ["短视频", "长视频", "直播", "影视点播", "音乐音频"],
    "阅读资讯": ["新闻", "小说", "漫画"],
    "游戏": ["手游", "模拟器"],
    "教育学习": ["在线课程", "K12", "语言学习", "题库"],
    "摄影美化": ["拍照修图"],
    "健康运动": ["运动健身", "健康医疗"],
    "旅游": ["旅游软件"],
    "工具": ["系统工具", "安全清理", "文件管理", "输入法", "浏览器",
            "网络工具", "改机工具", "多开分身", "接码工具"],
    "区块链加密": ["交易所", "钱包", "挖矿"],
    "色情成人": ["色情视频", "色情直播", "约炮社交"],
    "棋牌赌博": ["真钱棋牌", "体育博彩", "彩票"],
    "其他": ["其他"],
    "未知": ["未知"],
}
RISK_TYPES = [
    "无",
    # 借贷/催收/征信 产业链
    "小额现金贷", "反催收", "征信修复", "代还套现", "撸口子指南",
    # 投诉/赌博/色情/VPN/区块链
    "投诉平台", "赌博", "区块链", "色情", "翻墙VPN",
    # 强欺诈意图新型工具
    "远程控制", "AI伪造", "走私换汇",
    # 应用质量/黑产工具
    "仿冒山寨", "改机软件", "黑灰产工具", "网赚刷量",
    # 兜底
    "其他高风险",
    "未知",  # 仅当 l1=未知 时使用; validate_label 会强制对齐
]

# 扁平化 L2 全集, 用于 tool_use enum 约束 (per-l1 合法性在 validate_label 再校验)
ALL_L2 = sorted({l2 for l2s in L2_MAP.values() for l2 in l2s})

TAXONOMY_TEXT = (
    "## 一级标签 app_l1（只能从中选）:\n"
    + " / ".join(APP_L1) + "\n\n"
    + "## 二级标签 app_l2（按 l1 归口，只能从对应集合中选）:\n"
    + "\n".join(f"- {l1}: {' / '.join(l2s)}" for l1, l2s in L2_MAP.items())
    + "\n\n## 风险类型 risk_type（20 项，只能从中选）:\n"
    + " / ".join(RISK_TYPES)
)

# ==================== 规则前置 ====================
# 精确包名匹配; 命中后不调 LLM, 置信度 1.0
RULE_LABELS = {
    # 腾讯
    "com.tencent.mm": ("社交通讯", "即时通讯", "无"),
    "com.tencent.mobileqq": ("社交通讯", "即时通讯", "无"),
    "com.tencent.wework": ("办公软件", "协作OA", "无"),
    "com.tencent.qqmusic": ("视频影音", "音乐音频", "无"),
    "com.tencent.qqlive": ("视频影音", "长视频", "无"),
    "com.tencent.mtt": ("工具", "浏览器", "无"),
    # 阿里
    "com.eg.android.AlipayGphone": ("金融理财", "支付钱包", "无"),
    "com.taobao.taobao": ("电商购物", "综合电商", "无"),
    "com.tmall.wireless": ("电商购物", "综合电商", "无"),
    "com.alibaba.android.rimet": ("办公软件", "协作OA", "无"),  # 钉钉
    "com.taobao.idlefish": ("电商购物", "二手电商", "无"),       # 闲鱼
    # 字节
    "com.ss.android.ugc.aweme": ("视频影音", "短视频", "无"),
    "com.ss.android.ugc.aweme.lite": ("视频影音", "短视频", "无"),
    "com.ss.android.article.news": ("阅读资讯", "新闻", "无"),
    "com.ss.android.article.lite": ("阅读资讯", "新闻", "无"),
    "com.ss.android.lark": ("办公软件", "协作OA", "无"),  # 飞书
    # 美团 / 大众点评 / 京东 / 拼多多
    "com.sankuai.meituan": ("生活服务", "外卖", "无"),
    "com.dianping.v1": ("生活服务", "本地生活", "无"),
    "com.jingdong.app.mall": ("电商购物", "综合电商", "无"),
    "com.xunmeng.pinduoduo": ("电商购物", "拼团", "无"),
    # 出行 / 地图
    "com.sdu.didi.psnger": ("出行交通", "网约车", "无"),
    "com.autonavi.minimap": ("出行交通", "地图导航", "无"),
    "com.baidu.BaiduMap": ("出行交通", "地图导航", "无"),
    "com.MobileTicket": ("出行交通", "火车机票", "无"),
    # 百度 / 网易
    "com.baidu.searchbox": ("阅读资讯", "新闻", "无"),
    "com.netease.cloudmusic": ("视频影音", "音乐音频", "无"),
    "com.netease.newsreader.activity": ("阅读资讯", "新闻", "无"),
    # 视频
    "com.qiyi.video": ("视频影音", "长视频", "无"),
    "com.youku.phone": ("视频影音", "长视频", "无"),
    "tv.danmaku.bili": ("视频影音", "长视频", "无"),
    "com.smile.gifmaker": ("视频影音", "短视频", "无"),  # 快手
    "com.kuaishou.nebula": ("视频影音", "短视频", "无"),  # 快手极速版
    # 音乐
    "cn.kuwo.player": ("视频影音", "音乐音频", "无"),
    "cn.kugou.android": ("视频影音", "音乐音频", "无"),
    # 持牌借贷 / 金融
    "com.dxmpay.wallet": ("借贷软件", "助贷导流", "无"),   # 度小满
    "com.jd.jrapp": ("借贷软件", "助贷导流", "无"),        # 京东金融
    # 浏览器
    "com.UCMobile": ("工具", "浏览器", "无"),
    "com.android.chrome": ("工具", "浏览器", "无"),
    "com.android.browser": ("工具", "浏览器", "无"),
    # 输入法
    "com.sohu.inputmethod.sogou": ("工具", "输入法", "无"),
    "com.baidu.input": ("工具", "输入法", "无"),
    "com.iflytek.inputmethod": ("工具", "输入法", "无"),
}

# 正则前缀规则; 命中后置信度 0.9 (略低于精确匹配, 因为是模糊)
RULE_PATTERNS = [
    (re.compile(r"^com\.android\."), ("系统应用", "系统组件", "无")),
    (re.compile(r"^com\.google\.android\."), ("系统应用", "系统组件", "无")),
    (re.compile(r"^android(\.|$)"), ("系统应用", "系统组件", "无")),
    (re.compile(r"^com\.miui\.|^com\.xiaomi\."), ("系统应用", "厂商应用", "无")),
    (re.compile(r"^com\.huawei\.|^com\.hihonor\."), ("系统应用", "厂商应用", "无")),
    (re.compile(r"^com\.oppo\.|^com\.coloros\.|^com\.heytap\."), ("系统应用", "厂商应用", "无")),
    (re.compile(r"^com\.vivo\.|^com\.bbk\.|^com\.iqoo\."), ("系统应用", "厂商应用", "无")),
    (re.compile(r"^com\.meizu\."), ("系统应用", "厂商应用", "无")),
    (re.compile(r"^com\.icbc(\.|$)"), ("银行", "银行APP", "无")),
    (re.compile(r"^com\.chinamworld\."), ("银行", "银行APP", "无")),
    (re.compile(r"^com\.cmbchina\."), ("银行", "银行APP", "无")),
    (re.compile(r"^com\.ccb\."), ("银行", "银行APP", "无")),
    (re.compile(r"^com\.cebbank\."), ("银行", "银行APP", "无")),
    (re.compile(r"^com\.boc\."), ("银行", "银行APP", "无")),
    (re.compile(r"^com\.abchina\."), ("银行", "银行APP", "无")),
    (re.compile(r"^com\.psbc\."), ("银行", "银行APP", "无")),
    (re.compile(r"^com\.bocom\."), ("银行", "银行APP", "无")),
]

FEW_SHOT_TEXT = """## 边界示例（重要参考）
- 小赢卡贷 → 借贷软件 / 助贷导流 / 无  （持牌但做导流）
- 省呗 → 借贷软件 / 消费分期 / 无
- 维信卡卡贷 → 借贷软件 / 小额现金贷 / 小额现金贷  （无资质现金贷）
- 贷款管家 → 借贷软件 / 贷款超市 / 小额现金贷
- 旋风加速器 → 工具 / 网络工具 / 翻墙VPN
- 雷电模拟器 → 游戏 / 模拟器 / 无
- 应用多开/平行空间 → 工具 / 多开分身 / 改机软件
- 黑猫投诉 → 生活服务 / 投诉维权 / 投诉平台
- 易开发(改机) → 工具 / 改机工具 / 改机软件
- Pi Network → 区块链加密 / 挖矿 / 区块链
- 趣步/走路赚钱 → 其他 / 其他 / 网赚刷量
- 向日葵远程控制 / AnyDesk → 工具 / 系统工具 / 远程控制
- 智能还款管家 / 卡帮管家 → 借贷软件 / 信用卡管理 / 代还套现
- 撸口子大全 / 网贷口子论坛 → 阅读资讯 / 新闻 / 撸口子指南
- FaceMagic / Reface / AI换脸 → 摄影美化 / 拍照修图 / AI伪造
- USDT 快兑 / 数字货币 OTC → 区块链加密 / 钱包 / 走私换汇
- 仿微信图标的"WeXin" / 山寨清理大师 → 工具 / 系统工具 / 仿冒山寨
- 名称是纯乱码且包名也纯随机 → 未知 / 未知 / 未知 / confidence ≤ 0.3
"""

SYSTEM_PROMPT = f"""你是互联网金融反欺诈领域的资深分析师，负责对用户手机安装的 app 进行打标。
你的判断会被用于贷前反欺诈策略，需要兼顾召回与准确。

{TAXONOMY_TEXT}

## 关键判定规则（严格执行）

**总原则 (一定要遵守)**:
- app_l1 / app_l2 只描述应用**功能类别**, 所有风险信号一律落到 risk_type.
  同一个 l1/l2 下可以是 risk_type=无 也可以是高风险, 由应用本身性质决定.
- **三个字段 (app_l1 / app_l2 / risk_type) 必须严格从给定枚举里选, 不允许自创新词、
  近义词、组合词**. 即使没有完全匹配, 也要选最接近的合法枚举值, 而不是造一个新词.
- 同样的输入 (app_name + app_package) 在不同次调用中应给出**完全一致**的结果,
  不要在边界 case 上随意切换标签.

1. **破解版 / 抄袭包装 / 仿冒大厂图标** → risk_type=仿冒山寨（合并原 山寨低质 + 伪冒仿冒）
2. **多开/分身** → app_l1=工具, app_l2=多开分身, risk_type=改机软件
3. **改机/虚拟定位/Root** → app_l1=工具, app_l2=改机工具, risk_type=改机软件
4. **接码/虚拟号** → app_l1=工具, app_l2=接码工具, risk_type=黑灰产工具
5. **自动化脚本/按键精灵/抓包/逆向** → risk_type=黑灰产工具
6. **黑灰产工具判定极严**: 仅限接码 / 自动化脚本 / 抓包逆向. 其他可疑应用归对应 risk_type
7. **投诉平台** → app_l1=生活服务, app_l2=投诉维权, risk_type=投诉平台
8. **持牌借贷**（招联 / 微粒贷 / 京东金条 / 借呗 / 花呗 等） → risk_type=无
9. **无资质借贷 / 砍头息 / 贷超** → risk_type=小额现金贷
10. **加密货币** → app_l1=区块链加密, risk_type=区块链
11. **赌博 / 棋牌真钱 / 彩票** → app_l1=棋牌赌博, risk_type=赌博
12. **色情 / 涉黄 / 约炮** → app_l1=色情成人, risk_type=色情
13. **VPN / 加速器 / 代理** → app_l1=工具, app_l2=网络工具, risk_type=翻墙VPN
14. **反催收 / 债务优化 / 上岸** → risk_type=反催收
15. **征信修复 / 铲单** → risk_type=征信修复
16. **走路赚钱 / 看视频赚钱 / 任务悬赏** → risk_type=网赚刷量
17. **远程控制类**（TeamViewer / 向日葵 / AnyDesk / AirDroid / 蒲公英 等） → risk_type=远程控制
    → 电诈高发, 凡是能让他人远程操作本机的, 哪怕是大厂正规产品也判高风险
18. **代还 / 套现**（信用卡代还 / 智能还款 / 花呗套现 / 备用金套现 等; 持牌银行卡管除外） → risk_type=代还套现
19. **撸口子论坛 / 网贷口子大全 / 多头借贷指南** → risk_type=撸口子指南
20. **AI 换脸 / Deepfake / AI 变声 / 虚拟身份生成** → risk_type=AI伪造
21. **USDT / 数字货币 OTC / 外汇黑市 / 跨境换汇** → risk_type=走私换汇
22. **risk_type=未知 仅当 l1=未知 时使用**;
    l1 有合法值但风险不确定时, 用 "其他高风险"（确实可疑）或 "无"（确实正常）

## 推理与未知判定
**优先尝试合理推理，不要轻易标"未知"**:
- 中文名称即使包名乱码也通常足够判断（"星空赚动"→网赚, "惠民花"→现金贷, "旋风加速器"→VPN）
- 包名词根有信号：vpn/loan/cash/game/news/shop/mall/sex/porn/coin/wallet/clone/multi/jiema 等
- 通过名称的中文语义、行业惯用词、营销话术做推断
- 推断得到的标签 **confidence ≤ 0.5**，让下游知道是推理结果
- 高置信判断（明确知名 app、包名规范且有强信号）confidence ≥ 0.8

**仅当以下情况标"未知"**（confidence ≤ 0.3）:
- app 名称为乱码 / 纯数字 / 单字符等完全无语义信息
- 且包名也是纯随机字符（无任何可识别词根）

{FEW_SHOT_TEXT}

## 输出
必须调用 submit_labels 工具, labels 数组顺序与输入一致, reason 限 20 字以内.
"""

# ==================== 工具定义（结构化输出） ====================
LABEL_TOOL = {
    "name": "submit_labels",
    "description": "提交一批 app 的打标结果。labels 长度必须与输入一致，顺序对齐。",
    "input_schema": {
        "type": "object",
        "properties": {
            "labels": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "app_package": {"type": "string", "description": "原样回填的包名"},
                        "app_l1": {"type": "string", "enum": APP_L1},
                        "app_l2": {
                            "type": "string",
                            "enum": ALL_L2,
                            "description": "必须从对应 l1 的合法 l2 集合中选, 不能造新词",
                        },
                        "risk_type": {"type": "string", "enum": RISK_TYPES},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "reason": {"type": "string", "maxLength": 40},
                    },
                    "required": ["app_package", "app_l1", "app_l2", "risk_type", "confidence", "reason"],
                },
            }
        },
        "required": ["labels"],
    },
}

# ==================== 缓存 ====================
def init_cache(cache_db):
    conn = sqlite3.connect(str(cache_db), check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS label_cache (
            app_package TEXT PRIMARY KEY,
            app_l1 TEXT, app_l2 TEXT, risk_type TEXT,
            confidence REAL, reason TEXT, updated_at TEXT
        )
    """)
    conn.commit()
    return conn

def get_cached(conn, pkgs):
    if not pkgs:
        return {}
    cols = ["app_package", "app_l1", "app_l2", "risk_type", "confidence", "reason"]
    result = {}
    chunk_size = 500  # SQLite 变量上限约 999，保守取 500
    for i in range(0, len(pkgs), chunk_size):
        chunk = pkgs[i:i + chunk_size]
        placeholders = ",".join("?" * len(chunk))
        rows = conn.execute(
            f"SELECT app_package,app_l1,app_l2,risk_type,confidence,reason "
            f"FROM label_cache WHERE app_package IN ({placeholders})",
            chunk,
        ).fetchall()
        for r in rows:
            result[r[0]] = dict(zip(cols, r))
    return result

def save_cache(conn, results):
    if not results:
        return
    conn.executemany(
        """INSERT OR REPLACE INTO label_cache
           (app_package,app_l1,app_l2,risk_type,confidence,reason,updated_at)
           VALUES (?,?,?,?,?,?,datetime('now'))""",
        [(r["app_package"], r["app_l1"], r["app_l2"], r["risk_type"],
          r["confidence"], r["reason"]) for r in results],
    )
    conn.commit()

# ==================== 校验与规则匹配 ====================
def validate_label(r):
    """对单条标签做白名单兜底, 防止 LLM 造词污染下游策略.

    不变量:
    - l1 必须在 APP_L1; 否则强制全部 = "未知"
    - l2 必须在 L2_MAP[l1]; 否则 fallback 到该 l1 的首个合法 l2
    - risk_type 必须在 RISK_TYPES; 否则 = "其他高风险"
    - l1 == "未知" ↔ risk_type == "未知" (强制对齐, 消除歧义)
    """
    for k in ("app_l1", "app_l2", "risk_type"):
        r.setdefault(k, "未知")
    r.setdefault("reason", "")
    r.setdefault("confidence", 0.0)

    if r["app_l1"] not in APP_L1:
        r["app_l1"], r["app_l2"], r["risk_type"] = "未知", "未知", "未知"
    else:
        valid_l2 = L2_MAP.get(r["app_l1"], [])
        if r["app_l2"] not in valid_l2:
            r["app_l2"] = valid_l2[0] if valid_l2 else "未知"
        if r["risk_type"] not in RISK_TYPES:
            r["risk_type"] = "其他高风险"

    # l1↔risk_type 未知不变量
    if r["app_l1"] == "未知":
        r["risk_type"] = "未知"
    elif r["risk_type"] == "未知":
        # l1 已知但 LLM 给了 risk=未知, 降级到 "其他高风险" 让下游能识别
        r["risk_type"] = "其他高风险"

    try:
        c = float(r["confidence"])
        r["confidence"] = max(0.0, min(1.0, c))
    except (ValueError, TypeError):
        r["confidence"] = 0.0
    r["reason"] = str(r["reason"])[:40]
    return r

def apply_rules(apps):
    """规则前置: 已知大厂 / 系统应用直接命中, 不耗 LLM."""
    hits, remaining = [], []
    for a in apps:
        pkg = a["app_package"]
        match = RULE_LABELS.get(pkg)
        conf = 1.0
        if not match:
            for pat, lbl in RULE_PATTERNS:
                if pat.match(pkg):
                    match = lbl
                    conf = 0.9
                    break
        if match and len(match) == 3:
            l1, l2, risk = match
            hits.append({
                "app_package": pkg,
                "app_l1": l1, "app_l2": l2, "risk_type": risk,
                "confidence": conf, "reason": "规则命中",
            })
        else:
            remaining.append(a)
    return hits, remaining

# ==================== LLM 调用 (tool_use) ====================
def _call_with_retry(client, apps):
    """带分层重试的 LLM 调用; 返回 list[label_dict]."""
    user_msg = (
        f"请对以下 {len(apps)} 个 Android 应用打标。"
        f"务必调用 submit_labels 工具，labels 顺序与输入一致。\n\n"
        + json.dumps(apps, ensure_ascii=False)
    )
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                temperature=0,  # 打标要稳定, 同输入应给同结果
                system=[{
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }],
                tools=[LABEL_TOOL],
                tool_choice={"type": "tool", "name": "submit_labels"},
                messages=[{"role": "user", "content": user_msg}],
            )
            tool_block = next(
                (b for b in resp.content if getattr(b, "type", None) == "tool_use"),
                None,
            )
            if tool_block is None:
                raise ValueError("LLM did not return tool_use block")
            # 部分代理/模型会把 tool 参数二次编码成 JSON 字符串:
            # input 整体是 str, 或 input["labels"] 是 str. 先反序列化再校验,
            # 否则 isinstance(labels, list) 恒 False -> 整批误判 "LLM未返回".
            tool_input = tool_block.input
            if isinstance(tool_input, str):
                tool_input = json.loads(tool_input)
            labels = tool_input.get("labels", [])
            if isinstance(labels, str):
                labels = json.loads(labels)
            if not isinstance(labels, list) or not labels:
                raise ValueError("tool_use input missing labels array")
            return labels
        except anthropic.RateLimitError as e:
            last_err = e
            wait = 2 ** attempt
            try:
                ra = e.response.headers.get("retry-after")
                if ra:
                    wait = max(wait, int(float(ra)))
            except Exception:
                pass
            logging.warning("rate limited, sleep %ds (attempt %d)", wait, attempt + 1)
            time.sleep(wait)
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
            last_err = e
            logging.warning("api error attempt %d: %s", attempt + 1, e)
            time.sleep(2 ** attempt)
        except Exception as e:
            last_err = e
            logging.warning("parse/other error attempt %d: %s", attempt + 1, e)
            time.sleep(1)
    raise RuntimeError(f"label_batch failed after {MAX_RETRIES} retries: {last_err}")

def label_batch(client, apps, batch_idx=None, batch_prefix="batch"):
    try:
        raw = _call_with_retry(client, apps)
    except Exception as e:
        logging.error("batch %s 最终失败: %s", batch_idx, e)
        raw = []

    # 校验 + 补齐缺失
    by_pkg = {}
    for r in raw:
        if not isinstance(r, dict) or "app_package" not in r:
            continue
        by_pkg[r["app_package"]] = validate_label(r)

    results = []
    for a in apps:
        pkg = a["app_package"]
        if pkg in by_pkg:
            results.append(by_pkg[pkg])
        else:
            results.append({
                "app_package": pkg,
                "app_l1": "未知", "app_l2": "未知", "risk_type": "未知",
                "confidence": 0.0, "reason": "LLM未返回",
            })

    if batch_idx is not None:
        BATCH_DIR.mkdir(parents=True, exist_ok=True)
        name_map = {a["app_package"]: a.get("app_name", "") for a in apps}
        enriched = [
            {"app_name": name_map.get(r["app_package"], ""), **r}
            for r in results
        ]
        out_file = BATCH_DIR / f"{batch_prefix}_{batch_idx:03d}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(enriched, f, ensure_ascii=False, indent=2)
    return results

# ==================== Excel ====================
def export_excel(df: pd.DataFrame, out_path: Path):
    df = df.copy()
    df["_risk_order"] = df["risk_type"].apply(
        lambda x: RISK_TYPES.index(x) if x in RISK_TYPES else 99
    )
    df_sorted = df.sort_values(["_risk_order", "app_l1", "app_l2"]).drop(columns="_risk_order")

    summary = (df["risk_type"].value_counts()
               .rename_axis("risk_type").reset_index(name="数量"))
    summary["占比"] = (summary["数量"] / len(df) * 100).round(1).astype(str) + "%"

    l1_summary = (df["app_l1"].value_counts()
                  .rename_axis("app_l1").reset_index(name="数量"))
    l1_summary["占比"] = (l1_summary["数量"] / len(df) * 100).round(1).astype(str) + "%"

    l2_summary = (df["app_l2"].value_counts()
                  .rename_axis("app_l2").reset_index(name="数量"))
    l2_summary["占比"] = (l2_summary["数量"] / len(df) * 100).round(1).astype(str) + "%"

    high_risk_types = [r for r in RISK_TYPES if r not in ("无", "未知")]
    high_risk_df = df_sorted[df_sorted["risk_type"].isin(high_risk_types)]

    with pd.ExcelWriter(out_path, engine="openpyxl") as w:
        df_sorted.to_excel(w, sheet_name="全量结果", index=False)
        summary.to_excel(w, sheet_name="风险类型分布", index=False)
        l1_summary.to_excel(w, sheet_name="一级标签分布", index=False)
        l2_summary.to_excel(w, sheet_name="二级标签分布", index=False)
        high_risk_df.to_excel(w, sheet_name="高风险明细", index=False)
        for rt in high_risk_types:
            sub = df_sorted[df_sorted["risk_type"] == rt]
            if len(sub) > 0:
                sub.to_excel(w, sheet_name=rt[:31], index=False)

# ==================== 主流程 ====================
def chunked(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def dump_distribution(cached_all, done, total, prefix="batch"):
    rows = list(cached_all.values())
    n = len(rows)
    if n == 0:
        return
    risk_counts = {}
    l1_counts = {}
    for r in rows:
        risk_counts[r["risk_type"]] = risk_counts.get(r["risk_type"], 0) + 1
        l1_counts[r["app_l1"]] = l1_counts.get(r["app_l1"], 0) + 1

    lines = [f"===== 分布快照 batch {done}/{total}  样本 {n} ====="]
    lines.append("[risk_type]")
    for k, v in sorted(risk_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  {k:<12} {v:5d}  {v/n*100:5.1f}%")
    lines.append("[app_l1]")
    for k, v in sorted(l1_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  {k:<12} {v:5d}  {v/n*100:5.1f}%")
    lines.append("=" * 40)
    text = "\n".join(lines)

    snap_file = BATCH_DIR / f"_snapshot_{prefix}_{done:03d}.txt"
    snap_file.write_text(text, encoding="utf-8")
    for ln in lines:
        logging.info(ln)

def run(input_csv: Path, output_prefix: str):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    out_csv  = BASE / f"{output_prefix}.csv"
    out_xlsx = BASE / f"{output_prefix}.xlsx"
    cache_db = BASE / f"applist_label_cache_{output_prefix}.sqlite"

    df = pd.read_csv(input_csv)
    logging.info("读取 %s, 共 %d 行", input_csv.name, len(df))

    conn = init_cache(cache_db)
    all_pkgs = df["app_package"].dropna().unique().tolist()
    cached = get_cached(conn, all_pkgs)
    todo_pkgs = [p for p in all_pkgs if p not in cached]
    logging.info("unique 包名 %d, 已缓存 %d, 待打标 %d",
                 len(all_pkgs), len(cached), len(todo_pkgs))

    todo_apps = (df[df["app_package"].isin(todo_pkgs)]
                 .drop_duplicates("app_package")
                 [["app_name", "app_package"]]
                 .fillna("")
                 .to_dict("records"))

    # 规则前置: 大厂 / 系统应用直接命中, 不调 LLM
    rule_hits, todo_apps = apply_rules(todo_apps)
    if rule_hits:
        save_cache(conn, rule_hits)
        total_before = len(rule_hits) + len(todo_apps)
        logging.info("规则前置命中 %d (占 %.1f%%), 实际送 LLM %d",
                     len(rule_hits), len(rule_hits) / max(total_before, 1) * 100,
                     len(todo_apps))

    client = anthropic.Anthropic()
    t0 = time.time()
    if todo_apps:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = {ex.submit(label_batch, client, b, i, output_prefix): i
                       for i, b in enumerate(chunked(todo_apps, BATCH_SIZE), 1)}
            total = len(futures)
            done = 0
            for f in as_completed(futures):
                res = f.result()
                # 失败兜底结果 (reason="LLM未返回"/"LLM调用失败") 不写缓存,
                # 留待下次跑时自动重试; 否则会被永久缓存成 "未知"
                ok_res = [r for r in res
                          if r.get("reason") not in ("LLM未返回", "LLM调用失败")]
                save_cache(conn, ok_res)
                done += 1
                if done % 10 == 0 or done == total:
                    elapsed = time.time() - t0
                    eta = elapsed / done * (total - done) if done > 0 else 0
                    logging.info("进度 %d/%d (%.0f%%)  已用 %.0fs  ETA %.0fs",
                                 done, total, done / total * 100, elapsed, eta)
                if done % 50 == 0 or done == total:
                    cur_all = get_cached(conn, all_pkgs)
                    dump_distribution(cur_all, done, total, output_prefix)

    logging.info("LLM 调用完成, 耗时 %.1fs", time.time() - t0)

    cached_all = get_cached(conn, all_pkgs)
    label_df = pd.DataFrame(cached_all.values())
    out = df.merge(label_df, on="app_package", how="left")
    out.to_csv(out_csv, index=False, encoding="utf-8-sig")
    export_excel(out, out_xlsx)
    logging.info("写出 %s / %s", out_csv.name, out_xlsx.name)

def main():
    if len(sys.argv) >= 3:
        run(BASE / sys.argv[1], sys.argv[2])
    elif len(sys.argv) == 2:
        run(BASE / sys.argv[1], Path(sys.argv[1]).stem + "_v2")
    else:
        run(BASE / "applist_tag.csv", "applist_tag_v2")

if __name__ == "__main__":
    main()
