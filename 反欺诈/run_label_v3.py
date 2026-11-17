# -*- coding: utf-8 -*-
"""
App 反欺诈打标 v3 (基于 v2 + 0605_2 外部体系补充)

v3 相对 v2 的核心变更 (来自 对比_v2_vs_0605_2.md):
  [P0 风险盲区]
  - RISK_TYPES 20 → 23, 新增:
    * 诈骗     (0605_2 有 L1 122 诈骗 1099 + risk_tag 31 诈骗 1313, v2 全部漏)
    * 传销     (0605_2 L1 126 传销 208, v2 漏)
    * 跑分     (0605_2 L1 134 跑分 11, 量小但策略红线)

  [P1 L2 细分]
  - 借贷软件 L2: 6 → 10, 新增 网络小贷 / 持牌消金 / 租赁手机 / 投资理财类
  - 工具 L2: 9 → 12, 新增 变声器 / 录屏 / 位置信息 (反诈强信号)
  - 健康运动 L2: 2 → 3, 拆出 严重疾病 (对应 0605_2 120_2)

  [P2 画像维度]
  - 新增 quality_tag 字段, 与 risk_type 平行 (非互斥), 14 项画像
  - LLM 输出 schema 增加 quality_tag enum 约束
  - 缓存 schema 增加 quality_tag 列
  - Excel 增加 "优质画像分布" sheet

  [其他]
  - 默认输出前缀 v2 → v3 (缓存独立, 不污染 v2 历史结果)
  - validate_label 同步校验 quality_tag, 不在白名单的强制 = "无"
  - 规则前置: 银行/系统应用 自动填 quality_tag = "无"
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
BATCH_DIR = BASE / "tagging_tmp_v3"

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
    # 借贷 L2 扩充 (v2 6 项 → v3 10 项)
    "借贷软件": [
        "小额现金贷", "网络小贷", "持牌消金", "银行信贷",
        "消费分期", "信用卡管理", "助贷导流", "贷款超市",
        "租赁分期", "投资理财类",
    ],
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
    "健康运动": ["运动健身", "健康医疗", "严重疾病"],
    "旅游": ["旅游软件"],
    # 工具 L2 扩充 (v2 9 项 → v3 12 项)
    "工具": [
        "系统工具", "安全清理", "文件管理", "输入法", "浏览器",
        "网络工具", "改机工具", "多开分身", "接码工具",
        "变声器", "录屏录音", "位置信息",
    ],
    "区块链加密": ["交易所", "钱包", "挖矿"],
    "色情成人": ["色情视频", "色情直播", "约炮社交"],
    "棋牌赌博": ["真钱棋牌", "体育博彩", "彩票"],
    "其他": ["其他"],
    "未知": ["未知"],
}

# RISK_TYPES 扩充 (v2 20 → v3 23, 新增 诈骗/传销/跑分)
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
    # v3 新增 (来自 0605_2 体系)
    "诈骗", "传销", "跑分",
    # 兜底
    "其他高风险",
    "未知",  # 仅当 l1=未知 时使用; validate_label 会强制对齐
]

# v3 新增: 优质画像 quality_tag, 与 risk_type 平行 (非互斥)
# 选自 0605_2 quality_tag 28 项中策略侧 ROI 最高的 14 项
QUALITY_TAGS = [
    "无",
    "优质客群",       # 0605_2 04 优质 (841)
    "有车",           # 0605_2 22 有车 (432)
    "网约车司机",     # 0605_2 25 网约车司机 + L2 123_6
    "货车司机",       # 0605_2 L2 123_3
    "医生",           # 0605_2 09 医生 (131)
    "律师",           # 0605_2 10 律师 (46)
    "教师",           # 0605_2 11 教师 (37)
    "公务员事业单位", # 0605_2 07 公务员及事业单位 (47)
    "企业员工",       # 0605_2 03 企业员工 (67)
    "学生",           # 0605_2 18 学生 (29)
    "销售",           # 0605_2 34 销售 + L2 123_7
    "个体工商户",     # 0605_2 01 个体工商户 (91) + L2 123_10
    "蓝领工人",       # 0605_2 19 工人 (28) + L2 133_2
]

# 扁平化 L2 全集, 用于 tool_use enum 约束
ALL_L2 = sorted({l2 for l2s in L2_MAP.values() for l2 in l2s})

TAXONOMY_TEXT = (
    "## 一级标签 app_l1（只能从中选）:\n"
    + " / ".join(APP_L1) + "\n\n"
    + "## 二级标签 app_l2（按 l1 归口，只能从对应集合中选）:\n"
    + "\n".join(f"- {l1}: {' / '.join(l2s)}" for l1, l2s in L2_MAP.items())
    + f"\n\n## 风险类型 risk_type（{len(RISK_TYPES)} 项，只能从中选）:\n"
    + " / ".join(RISK_TYPES)
    + f"\n\n## 优质画像 quality_tag（{len(QUALITY_TAGS)} 项，只能从中选；与 risk_type 平行）:\n"
    + " / ".join(QUALITY_TAGS)
)

# ==================== 规则前置 ====================
# 精确包名: (l1, l2, risk_type, quality_tag)
RULE_LABELS = {
    # 腾讯
    "com.tencent.mm": ("社交通讯", "即时通讯", "无", "无"),
    "com.tencent.mobileqq": ("社交通讯", "即时通讯", "无", "无"),
    "com.tencent.wework": ("办公软件", "协作OA", "无", "企业员工"),
    "com.tencent.qqmusic": ("视频影音", "音乐音频", "无", "无"),
    "com.tencent.qqlive": ("视频影音", "长视频", "无", "无"),
    "com.tencent.mtt": ("工具", "浏览器", "无", "无"),
    # 阿里
    "com.eg.android.AlipayGphone": ("金融理财", "支付钱包", "无", "无"),
    "com.taobao.taobao": ("电商购物", "综合电商", "无", "无"),
    "com.tmall.wireless": ("电商购物", "综合电商", "无", "无"),
    "com.alibaba.android.rimet": ("办公软件", "协作OA", "无", "企业员工"),  # 钉钉
    "com.taobao.idlefish": ("电商购物", "二手电商", "无", "无"),
    # 字节
    "com.ss.android.ugc.aweme": ("视频影音", "短视频", "无", "无"),
    "com.ss.android.ugc.aweme.lite": ("视频影音", "短视频", "无", "无"),
    "com.ss.android.article.news": ("阅读资讯", "新闻", "无", "无"),
    "com.ss.android.article.lite": ("阅读资讯", "新闻", "无", "无"),
    "com.ss.android.lark": ("办公软件", "协作OA", "无", "企业员工"),  # 飞书
    # 美团 / 京东 / 拼多多
    "com.sankuai.meituan": ("生活服务", "外卖", "无", "无"),
    "com.dianping.v1": ("生活服务", "本地生活", "无", "无"),
    "com.jingdong.app.mall": ("电商购物", "综合电商", "无", "无"),
    "com.xunmeng.pinduoduo": ("电商购物", "拼团", "无", "无"),
    # 出行 / 地图 — 网约车类填 quality_tag = 网约车司机 不合适 (普通乘客也装),
    # 真正区分车主端要靠包名 .driver 后缀; 这里乘客端默认 无
    "com.sdu.didi.psnger": ("出行交通", "网约车", "无", "无"),
    "com.sdu.didi.gsui": ("出行交通", "网约车", "无", "网约车司机"),  # 滴滴司机端
    "com.autonavi.minimap": ("出行交通", "地图导航", "无", "无"),
    "com.baidu.BaiduMap": ("出行交通", "地图导航", "无", "无"),
    "com.MobileTicket": ("出行交通", "火车机票", "无", "无"),
    # 百度 / 网易
    "com.baidu.searchbox": ("阅读资讯", "新闻", "无", "无"),
    "com.netease.cloudmusic": ("视频影音", "音乐音频", "无", "无"),
    "com.netease.newsreader.activity": ("阅读资讯", "新闻", "无", "无"),
    # 视频
    "com.qiyi.video": ("视频影音", "长视频", "无", "无"),
    "com.youku.phone": ("视频影音", "长视频", "无", "无"),
    "tv.danmaku.bili": ("视频影音", "长视频", "无", "无"),
    "com.smile.gifmaker": ("视频影音", "短视频", "无", "无"),
    "com.kuaishou.nebula": ("视频影音", "短视频", "无", "无"),
    # 音乐
    "cn.kuwo.player": ("视频影音", "音乐音频", "无", "无"),
    "cn.kugou.android": ("视频影音", "音乐音频", "无", "无"),
    # 持牌借贷 / 金融
    "com.dxmpay.wallet": ("借贷软件", "助贷导流", "无", "无"),
    "com.jd.jrapp": ("借贷软件", "助贷导流", "无", "无"),
    # 浏览器
    "com.UCMobile": ("工具", "浏览器", "无", "无"),
    "com.android.chrome": ("工具", "浏览器", "无", "无"),
    "com.android.browser": ("工具", "浏览器", "无", "无"),
    # 输入法
    "com.sohu.inputmethod.sogou": ("工具", "输入法", "无", "无"),
    "com.baidu.input": ("工具", "输入法", "无", "无"),
    "com.iflytek.inputmethod": ("工具", "输入法", "无", "无"),
}

# 正则前缀: (l1, l2, risk_type, quality_tag)
RULE_PATTERNS = [
    (re.compile(r"^com\.android\."), ("系统应用", "系统组件", "无", "无")),
    (re.compile(r"^com\.google\.android\."), ("系统应用", "系统组件", "无", "无")),
    (re.compile(r"^android(\.|$)"), ("系统应用", "系统组件", "无", "无")),
    (re.compile(r"^com\.miui\.|^com\.xiaomi\."), ("系统应用", "厂商应用", "无", "无")),
    (re.compile(r"^com\.huawei\.|^com\.hihonor\."), ("系统应用", "厂商应用", "无", "无")),
    (re.compile(r"^com\.oppo\.|^com\.coloros\.|^com\.heytap\."), ("系统应用", "厂商应用", "无", "无")),
    (re.compile(r"^com\.vivo\.|^com\.bbk\.|^com\.iqoo\."), ("系统应用", "厂商应用", "无", "无")),
    (re.compile(r"^com\.meizu\."), ("系统应用", "厂商应用", "无", "无")),
    (re.compile(r"^com\.icbc(\.|$)"), ("银行", "银行APP", "无", "无")),
    (re.compile(r"^com\.chinamworld\."), ("银行", "银行APP", "无", "无")),
    (re.compile(r"^com\.cmbchina\."), ("银行", "银行APP", "无", "无")),
    (re.compile(r"^com\.ccb\."), ("银行", "银行APP", "无", "无")),
    (re.compile(r"^com\.cebbank\."), ("银行", "银行APP", "无", "无")),
    (re.compile(r"^com\.boc\."), ("银行", "银行APP", "无", "无")),
    (re.compile(r"^com\.abchina\."), ("银行", "银行APP", "无", "无")),
    (re.compile(r"^com\.psbc\."), ("银行", "银行APP", "无", "无")),
    (re.compile(r"^com\.bocom\."), ("银行", "银行APP", "无", "无")),
]

FEW_SHOT_TEXT = """## 边界示例（重要参考, v3 含 quality_tag）

格式: app_name → l1 / l2 / risk_type / quality_tag

# 借贷类细分
- 招联金融   → 借贷软件 / 持牌消金 / 无 / 无
- 中邮消费金融 → 借贷软件 / 持牌消金 / 无 / 无
- 360 借条   → 借贷软件 / 网络小贷 / 无 / 无
- 维信卡卡贷 → 借贷软件 / 小额现金贷 / 小额现金贷 / 无
- 贷款管家   → 借贷软件 / 贷款超市 / 小额现金贷 / 无
- 小赢卡贷   → 借贷软件 / 助贷导流 / 无 / 无
- 省呗       → 借贷软件 / 消费分期 / 无 / 无
- 租机宝     → 借贷软件 / 租赁分期 / 小额现金贷 / 无
- 智能还款管家 / 卡帮管家 → 借贷软件 / 信用卡管理 / 代还套现 / 无

# 工具新增 L2
- 旋风加速器     → 工具 / 网络工具 / 翻墙VPN / 无
- 录屏大师       → 工具 / 录屏录音 / 无 / 无
- 隐秘录音       → 工具 / 录屏录音 / 黑灰产工具 / 无
- 万能变声器     → 工具 / 变声器 / 黑灰产工具 / 无 （配合诈骗高发, 默认高风险）
- 虚拟定位 / 任我行 → 工具 / 位置信息 / 改机软件 / 无
- 应用多开/平行空间 → 工具 / 多开分身 / 改机软件 / 无
- 易开发(改机) → 工具 / 改机工具 / 改机软件 / 无
- 雷电模拟器   → 游戏 / 模拟器 / 无 / 无

# v3 新增 risk_type
- 投资理财课堂(承诺保本高息) → 借贷软件 / 投资理财类 / 诈骗 / 无
- 假冒公检法App → 工具 / 系统工具 / 诈骗 / 无
- 山海经资本盘 → 其他 / 其他 / 传销 / 无
- 微商XX星球   → 其他 / 其他 / 传销 / 无
- USDT 跑分平台 → 其他 / 其他 / 跑分 / 无
- 数币代收任务 → 其他 / 其他 / 跑分 / 无

# 其他既有规则
- 黑猫投诉 → 生活服务 / 投诉维权 / 投诉平台 / 无
- Pi Network → 区块链加密 / 挖矿 / 区块链 / 无
- 趣步/走路赚钱 → 其他 / 其他 / 网赚刷量 / 无
- 向日葵远程控制 / AnyDesk → 工具 / 系统工具 / 远程控制 / 无
- FaceMagic / Reface / AI换脸 → 摄影美化 / 拍照修图 / AI伪造 / 无
- USDT 快兑 / 数字货币 OTC → 区块链加密 / 钱包 / 走私换汇 / 无
- 撸口子大全 / 网贷口子论坛 → 阅读资讯 / 新闻 / 撸口子指南 / 无
- 仿微信图标 "WeXin" / 山寨清理大师 → 工具 / 系统工具 / 仿冒山寨 / 无

# quality_tag 命中示例 (画像维度, 与 risk_type 独立)
- 滴滴司机端     → 出行交通 / 网约车 / 无 / 网约车司机
- 货拉拉司机端   → 出行交通 / 网约车 / 无 / 货车司机
- 法宝/律师在线  → 生活服务 / 本地生活 / 无 / 律师
- 丁香医生(医生端) → 健康运动 / 健康医疗 / 无 / 医生
- 学习强国       → 政务 / 政务服务 / 无 / 公务员事业单位
- 钉钉/企业微信  → 办公软件 / 协作OA / 无 / 企业员工
- 中国教育考试网 → 教育学习 / 题库 / 无 / 教师
- 学习通 / 超星 → 教育学习 / 在线课程 / 无 / 学生
- 收钱吧/拉卡拉商户 → 金融理财 / 支付钱包 / 无 / 个体工商户
- 汽车之家(车主)  → 出行交通 / 地图导航 / 无 / 有车
- 鲁班长(蓝领招工) → 生活服务 / 招聘 / 无 / 蓝领工人
- 销售易/纷享销客 → 办公软件 / 协作OA / 无 / 销售

# 名称是纯乱码且包名也纯随机 → 未知 / 未知 / 未知 / 无 / confidence ≤ 0.3
"""

SYSTEM_PROMPT = f"""你是互联网金融反欺诈领域的资深分析师，负责对用户手机安装的 app 进行打标。
你的判断会被用于贷前反欺诈策略，需要兼顾召回与准确。

{TAXONOMY_TEXT}

## 关键判定规则（严格执行）

**总原则 (一定要遵守)**:
- app_l1 / app_l2 只描述应用**功能类别**, 所有风险信号一律落到 risk_type.
  同一个 l1/l2 下可以是 risk_type=无 也可以是高风险, 由应用本身性质决定.
- **quality_tag 是与 risk_type 平行的画像维度**, 描述该 app 的典型用户群.
  与 risk_type 不互斥: 既可能 risk_type=无 + quality_tag=医生, 也可能 risk_type=网赚刷量 + quality_tag=无.
  绝大多数 app 应给 quality_tag=无, 仅当能强映射到职业/客群时才填.
- **四个字段 (app_l1 / app_l2 / risk_type / quality_tag) 必须严格从给定枚举里选,
  不允许自创新词、近义词、组合词**. 即使没有完全匹配, 也要选最接近的合法枚举值, 而不是造新词.
- 同样的输入 (app_name + app_package) 在不同次调用中应给出**完全一致**的结果.

### risk_type 判定 (按优先级)
1. **破解版 / 仿冒大厂图标** → risk_type=仿冒山寨
2. **多开/分身** → l1=工具, l2=多开分身, risk_type=改机软件
3. **改机/虚拟定位/Root** → l1=工具, l2=改机工具 或 位置信息, risk_type=改机软件
4. **接码/虚拟号** → l1=工具, l2=接码工具, risk_type=黑灰产工具
5. **自动化脚本/按键精灵/抓包/逆向/隐秘录音** → risk_type=黑灰产工具
6. **投诉平台** → l1=生活服务, l2=投诉维权, risk_type=投诉平台
7. **持牌借贷**（招联 / 微粒贷 / 京东金条 / 借呗 / 花呗 等） → risk_type=无, l2 按持牌消金/网络小贷/助贷导流 细分
8. **无资质借贷 / 砍头息 / 贷超** → risk_type=小额现金贷
9. **加密货币** → l1=区块链加密, risk_type=区块链
10. **赌博 / 棋牌真钱 / 彩票** → l1=棋牌赌博, risk_type=赌博
11. **色情 / 涉黄 / 约炮** → l1=色情成人, risk_type=色情
12. **VPN / 加速器 / 代理** → l1=工具, l2=网络工具, risk_type=翻墙VPN
13. **反催收 / 债务优化 / 上岸** → risk_type=反催收
14. **征信修复 / 铲单** → risk_type=征信修复
15. **走路赚钱 / 看视频赚钱 / 任务悬赏** → risk_type=网赚刷量
16. **远程控制类**（TeamViewer / 向日葵 / AnyDesk / AirDroid / 蒲公英） → risk_type=远程控制 (电诈高发, 正规也判高风险)
17. **代还 / 套现**（信用卡代还 / 智能还款 / 花呗套现 / 备用金套现） → risk_type=代还套现
18. **撸口子论坛 / 网贷口子大全 / 多头借贷指南** → risk_type=撸口子指南
19. **AI 换脸 / Deepfake / AI 变声 / 虚拟身份生成** → risk_type=AI伪造
20. **USDT / 数字货币 OTC / 外汇黑市 / 跨境换汇** → risk_type=走私换汇
21. **诈骗类**(假冒公检法/虚假投资/杀猪盘/虚假理财/承诺保本高息) → **risk_type=诈骗**  (v3 新增)
22. **传销类**(资金盘/拉人头/动态收益/微商XX星球/民族大业) → **risk_type=传销**  (v3 新增)
23. **跑分类**(USDT跑分/银行卡跑分/数币代收任务) → **risk_type=跑分**  (v3 新增)
24. **risk_type=未知 仅当 l1=未知 时使用**; l1 有合法值但风险不确定时, 用 "其他高风险"（确实可疑）或 "无"（确实正常）

### quality_tag 判定 (默认填 "无", 只在强信号时命中)
- **网约车司机端**(滴滴/曹操/高德 等的司机端, 通常包名含 .driver/.gsui) → quality_tag=网约车司机
- **货车司机端**(货拉拉司机/满帮司机/运满满) → quality_tag=货车司机
- **司机端不能凭乘客端推断**: 普通滴滴乘客端 quality_tag=无
- **医疗专业端**(医生端/医脉通/丁香园 而非丁香医生患者端) → quality_tag=医生
- **法律专业端**(律所/律师在线/法宝/无讼) → quality_tag=律师
- **教师端**(校园管理/钉钉教师/教师资格考试) → quality_tag=教师
- **公务员事业单位**(学习强国/人民日报/各地党建/政务办公) → quality_tag=公务员事业单位
- **企业员工**(钉钉/企业微信/飞书/北森/销售易) → quality_tag=企业员工
- **学生**(学习通/超星/小猿搜题/高校学务系统) → quality_tag=学生
- **销售**(纷享销客/红圈营销/电销CRM) → quality_tag=销售
- **个体工商户**(收钱吧/拉卡拉商户/聚合支付商户) → quality_tag=个体工商户
- **蓝领招工**(鲁班长/优蓝网/工立方) → quality_tag=蓝领工人
- **车主**(汽车之家车主版/车主指南/车300/违章查询) → quality_tag=有车
- **优质客群** = 兜底高净值 (奢侈品/高端会员/私人银行/招行金葵花) 用得很少, 谨慎使用

### 推理与未知判定
**优先尝试合理推理，不要轻易标"未知"**:
- 中文名称即使包名乱码也通常足够判断
- 包名词根有信号: vpn/loan/cash/game/news/shop/sex/coin/wallet/clone/multi/jiema/driver 等
- 推断得到的标签 confidence ≤ 0.5; 高置信判断 confidence ≥ 0.8

**仅当以下情况标"未知"**(confidence ≤ 0.3):
- app 名称为乱码 / 纯数字 / 单字符, 且包名也是纯随机字符

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
                        "quality_tag": {
                            "type": "string",
                            "enum": QUALITY_TAGS,
                            "description": "用户画像; 与 risk_type 独立, 绝大多数填 '无'",
                        },
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "reason": {"type": "string", "maxLength": 40},
                    },
                    "required": [
                        "app_package", "app_l1", "app_l2",
                        "risk_type", "quality_tag", "confidence", "reason",
                    ],
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
            app_l1 TEXT, app_l2 TEXT, risk_type TEXT, quality_tag TEXT,
            confidence REAL, reason TEXT, updated_at TEXT
        )
    """)
    conn.commit()
    return conn

def get_cached(conn, pkgs):
    if not pkgs:
        return {}
    cols = ["app_package", "app_l1", "app_l2", "risk_type", "quality_tag", "confidence", "reason"]
    result = {}
    chunk_size = 500
    for i in range(0, len(pkgs), chunk_size):
        chunk = pkgs[i:i + chunk_size]
        placeholders = ",".join("?" * len(chunk))
        rows = conn.execute(
            f"SELECT app_package,app_l1,app_l2,risk_type,quality_tag,confidence,reason "
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
           (app_package,app_l1,app_l2,risk_type,quality_tag,confidence,reason,updated_at)
           VALUES (?,?,?,?,?,?,?,datetime('now'))""",
        [(r["app_package"], r["app_l1"], r["app_l2"], r["risk_type"],
          r.get("quality_tag", "无"), r["confidence"], r["reason"]) for r in results],
    )
    conn.commit()

# ==================== 校验与规则匹配 ====================
def validate_label(r):
    """v3: 增加 quality_tag 校验.

    不变量:
    - l1 ∈ APP_L1, 否则全部 = "未知"
    - l2 ∈ L2_MAP[l1], 否则 fallback 到 valid_l2[0]
    - risk_type ∈ RISK_TYPES, 否则 = "其他高风险"
    - quality_tag ∈ QUALITY_TAGS, 否则 = "无"
    - l1 == "未知" ↔ risk_type == "未知", quality_tag 强制 = "无"
    """
    for k in ("app_l1", "app_l2", "risk_type"):
        r.setdefault(k, "未知")
    r.setdefault("quality_tag", "无")
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

    if r["quality_tag"] not in QUALITY_TAGS:
        r["quality_tag"] = "无"

    # l1↔risk_type 未知不变量
    if r["app_l1"] == "未知":
        r["risk_type"] = "未知"
        r["quality_tag"] = "无"
    elif r["risk_type"] == "未知":
        r["risk_type"] = "其他高风险"

    try:
        c = float(r["confidence"])
        r["confidence"] = max(0.0, min(1.0, c))
    except (ValueError, TypeError):
        r["confidence"] = 0.0
    r["reason"] = str(r["reason"])[:40]
    return r

def apply_rules(apps):
    """规则前置: v3 命中后返回 4 元组 (l1, l2, risk_type, quality_tag)."""
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
        if match and len(match) == 4:
            l1, l2, risk, qual = match
            hits.append({
                "app_package": pkg,
                "app_l1": l1, "app_l2": l2,
                "risk_type": risk, "quality_tag": qual,
                "confidence": conf, "reason": "规则命中",
            })
        else:
            remaining.append(a)
    return hits, remaining

# ==================== LLM 调用 (tool_use) ====================
def _call_with_retry(client, apps):
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
                temperature=0,
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
                "quality_tag": "无",
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

    def _dist(col):
        s = df[col].value_counts().rename_axis(col).reset_index(name="数量")
        s["占比"] = (s["数量"] / len(df) * 100).round(1).astype(str) + "%"
        return s

    summary = _dist("risk_type")
    l1_summary = _dist("app_l1")
    l2_summary = _dist("app_l2")
    quality_summary = _dist("quality_tag")

    high_risk_types = [r for r in RISK_TYPES if r not in ("无", "未知")]
    high_risk_df = df_sorted[df_sorted["risk_type"].isin(high_risk_types)]

    # v3 新增: 命中 quality_tag 的明细 (非"无")
    quality_hit_df = df_sorted[df_sorted["quality_tag"] != "无"]

    with pd.ExcelWriter(out_path, engine="openpyxl") as w:
        df_sorted.to_excel(w, sheet_name="全量结果", index=False)
        summary.to_excel(w, sheet_name="风险类型分布", index=False)
        l1_summary.to_excel(w, sheet_name="一级标签分布", index=False)
        l2_summary.to_excel(w, sheet_name="二级标签分布", index=False)
        quality_summary.to_excel(w, sheet_name="优质画像分布", index=False)
        high_risk_df.to_excel(w, sheet_name="高风险明细", index=False)
        quality_hit_df.to_excel(w, sheet_name="画像命中明细", index=False)
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
    risk_counts, l1_counts, qual_counts = {}, {}, {}
    for r in rows:
        risk_counts[r["risk_type"]] = risk_counts.get(r["risk_type"], 0) + 1
        l1_counts[r["app_l1"]] = l1_counts.get(r["app_l1"], 0) + 1
        q = r.get("quality_tag", "无")
        qual_counts[q] = qual_counts.get(q, 0) + 1

    lines = [f"===== 分布快照 batch {done}/{total}  样本 {n} ====="]
    lines.append("[risk_type]")
    for k, v in sorted(risk_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  {k:<12} {v:5d}  {v/n*100:5.1f}%")
    lines.append("[app_l1]")
    for k, v in sorted(l1_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  {k:<12} {v:5d}  {v/n*100:5.1f}%")
    lines.append("[quality_tag] (非'无')")
    for k, v in sorted(qual_counts.items(), key=lambda x: -x[1]):
        if k != "无":
            lines.append(f"  {k:<14} {v:5d}  {v/n*100:5.1f}%")
    lines.append("=" * 40)
    text = "\n".join(lines)

    BATCH_DIR.mkdir(parents=True, exist_ok=True)
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
        run(BASE / sys.argv[1], Path(sys.argv[1]).stem + "_v3")
    else:
        run(BASE / "applist_tag.csv", "applist_tag_v3")

if __name__ == "__main__":
    main()
