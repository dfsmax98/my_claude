# -*- coding: utf-8 -*-
"""
按 v3 标签体系合并两份 applist 标签表.

输入:
  - applist_tag_0522_v2.csv          (内部 LLM v2.0 打标, ~79k unique pkg)
  - applist_tag_0605_2_clean.csv     (外部清洗后标签, ~154k unique pkg)

输出:
  - applist_tag_merged_v3.csv        统一到 v3 schema 的合并表
  - applist_tag_merged_v3.xlsx       含分布 sheet
  - merge_audit_unknown_*.csv        映射失败/兜底走 "其他" 的样本, 供人工校验

合并策略:
  1. 0522_v2 行: v2.0 → v3 词表迁移 (山寨低质/伪冒仿冒 → 仿冒山寨; 隐私窃取 → 其他高风险)
     v2 没有 quality_tag 维度, 默认 "无"
  2. 0605_2 行: 用 L1+L2 code 映射到 v3 (l1, l2); risk_tag 映射 risk_type; quality_tag code 映射 v3 quality_tag
  3. 重复 app_package 的合并:
       - 优先 v2 的 (l1, l2, risk_type) (v2 是为反欺诈策略定制, 风险粒度更对)
       - quality_tag: v2 没有, 用 0605_2 的兜底
       - source = "both"
"""
import re
import pandas as pd
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent))
from run_label_v3 import APP_L1, L2_MAP, RISK_TYPES, QUALITY_TAGS, validate_label

BASE = Path(r"d:\my_claude\反欺诈")
SRC_MAINSTREAM = BASE / "applist_tag_mainstream.csv"   # 手工维护主流 app, 优先级最高
SRC_XIAOMI     = BASE / "applist_tag_xiaomi.csv"       # 小米市场爬取, 仅补新 pkg, 不覆盖
SRC_V2 = BASE / "applist_tag_0522_v2.csv"
SRC_0605 = BASE / "applist_tag_0605_2_clean.csv"
OUT_CSV  = BASE / "applist_tag_merged_v3.csv"
OUT_XLSX = BASE / "applist_tag_merged_v3.xlsx"

# ==================== v2.0 → v3 词表迁移 ====================
V2_RISK_MIGRATE = {
    "山寨低质": "仿冒山寨",
    "伪冒仿冒": "仿冒山寨",
    "隐私窃取": "其他高风险",
}
V2_L1_MIGRATE = {
    "短视频": "视频影音",  # 旧版偶尔造的词
}
V2_L2_MIGRATE = {
    # v2.0 没有 v3 新增 L2, 不需要前向映射
}

# ==================== 0605_2 → v3 映射 ====================
# 0605_2 L1 code → v3 (l1_default, hint_risk_type)
# hint_risk_type: 该 L1 强烈隐含的 risk_type, 没有更细 L2 信号时用; "" 表示无暗示
L1_MAP = {
    "101": ("办公软件", ""),
    "102": ("游戏", ""),
    "103": ("棋牌赌博", "赌博"),
    "104": ("出行交通", ""),
    "105": ("社交通讯", ""),
    "106": ("工具", ""),
    "107": ("阅读资讯", ""),
    "108": ("教育学习", ""),
    "109": ("视频影音", ""),
    "110": ("电商购物", ""),
    "111": ("生活服务", ""),
    "112": ("健康运动", ""),
    "113": ("政务", ""),
    "114": ("金融理财", ""),
    "115": ("其他", ""),
    "116": ("银行", ""),
    "117": ("色情成人", "色情"),
    "118": ("生活服务", "投诉平台"),
    "119": ("其他", "仿冒山寨"),       # 伪冒, 没功能信息
    "120": ("健康运动", ""),
    "121": ("教育学习", ""),
    "122": ("其他", "诈骗"),           # 诈骗, 没功能信息
    "123": ("生活服务", ""),           # 职业类, 真正信息走 quality
    "124": ("生活服务", ""),
    "125": ("其他", "网赚刷量"),
    "126": ("其他", "传销"),
    "127": ("借贷软件", ""),
    "128": ("社交通讯", ""),
    "129": ("棋牌赌博", "赌博"),
    "130": ("其他", "反催收"),
    "131": ("工具", "改机软件"),
    "132": ("金融理财", ""),
    "133": ("生活服务", ""),
    "134": ("其他", "跑分"),
    "999": ("其他", ""),
}

# 0605_2 L2 完整 code → v3 (l2_override, risk_type_override)
# 没列的, 用 L1_MAP 默认 + 根据 L1 推 l2[0]
L2_MAP_0605 = {
    # 101 办公商务
    "101_1": ("文档处理", ""),
    "101_2": ("文档处理", ""),
    "101_3": ("系统工具", "远程控制"),  # 远程操作
    "101_4": ("文档处理", ""),
    "101_5": ("文档处理", ""),
    "101_6": ("邮箱", ""),
    "101_99": ("文档处理", ""),
    # 102 游戏
    "102_1": ("手游", ""),
    # 103 博彩游戏
    "103_1": ("真钱棋牌", "赌博"),
    "103_2": ("彩票", "赌博"),
    "103_3": ("真钱棋牌", "赌博"),
    # 104 旅游出行
    "104_1": ("旅游软件", ""),  # 出境
    "104_2": ("地图导航", ""),
    "104_3": ("公共交通", ""),
    "104_4": ("公共交通", ""),  # 共享单车
    "104_5": ("旅游软件", ""),  # 住宿
    "104_6": ("火车机票", ""),
    "104_7": ("旅游软件", ""),
    "104_8": ("旅游软件", ""),
    "104_9": ("网约车", ""),
    "104_10": ("地图导航", ""),  # 汽车周边
    "104_11": ("地图导航", ""),
    "104_12": ("地图导航", ""),
    "104_13": ("地图导航", ""),
    "104_14": ("地图导航", ""),
    "104_15": ("地图导航", ""),
    "104_99": ("公共交通", ""),
    # 105 通讯社交
    "105_1": ("陌生人社交", ""),  # 异性社交
    "105_2": ("即时通讯", ""),
    "105_3": ("社区论坛", ""),
    "105_99": ("即时通讯", ""),
    # 106 系统工具
    "106_1": ("网络工具", ""),
    "106_2": ("安全清理", ""),
    "106_3": ("变声器", ""),
    "106_4": ("网络工具", "翻墙VPN"),
    "106_5": ("浏览器", ""),
    "106_6": ("录屏录音", ""),
    "106_7": ("录屏录音", ""),
    "106_8": ("系统工具", ""),
    "106_9": ("系统工具", ""),
    "106_10": ("系统工具", ""),
    "106_11": ("输入法", ""),
    "106_12": ("系统工具", ""),
    "106_13": ("位置信息", ""),
    "106_14": ("文件管理", ""),
    "106_15": ("安全清理", ""),
    "106_16": ("__l1_系统应用__", ""),  # 系统自带 → l1 转 系统应用
    "106_17": ("系统工具", ""),
    "106_18": ("系统工具", ""),
    "106_19": ("系统工具", ""),
    "106_20": ("系统工具", ""),
    "106_99": ("系统工具", ""),
    # 107 新闻阅读
    "107_1": ("漫画", ""),
    "107_2": ("小说", ""),
    "107_3": ("小说", ""),
    "107_4": ("小说", ""),
    "107_5": ("新闻", ""),
    "107_99": ("新闻", ""),
    # 108 教育
    "108_1": ("语言学习", ""),
    "108_2": ("题库", ""),
    "108_99": ("在线课程", ""),
    # 109 影音
    "109_1": ("短视频", ""),
    "109_2": ("__l1_摄影美化__", ""),  # 摄影图像
    "109_3": ("影视点播", ""),
    "109_4": ("直播", ""),
    "109_99": ("长视频", ""),
    # 110 购物
    "110_1": ("二手电商", ""),
    "110_2": ("综合电商", ""),
    "110_3": ("海淘特卖", ""),
    "110_4": ("综合电商", ""),
    "110_5": ("垂直电商", ""),  # 医药
    "110_6": ("综合电商", ""),
    "110_99": ("综合电商", ""),
    # 111 生活休闲
    "111_1": ("本地生活", ""),  # 房产
    "111_2": ("本地生活", ""),
    "111_3": ("__l1_金融理财__", ""),  # 理财记账
    "111_4": ("外卖", ""),
    "111_5": ("家政维修", ""),
    "111_6": ("本地生活", ""),
    "111_7": ("本地生活", ""),
    "111_8": ("本地生活", ""),
    "111_9": ("本地生活", ""),
    "111_10": ("本地生活", ""),
    "111_99": ("本地生活", ""),
    # 112 运动健康
    "112_1": ("运动健身", ""),
    # 113 政务
    "113_1": ("政务服务", ""),  # 反诈
    "113_2": ("政务服务", ""),
    "113_3": ("政务服务", ""),
    "113_4": ("政务服务", ""),
    "113_5": ("政务服务", ""),
    "113_6": ("政务服务", ""),
    "113_7": ("政务服务", ""),
    "113_8": ("政务服务", ""),
    "113_9": ("政务服务", ""),
    "113_99": ("政务服务", ""),
    # 114 支付
    "114_1": ("支付钱包", ""),
    "114_99": ("支付钱包", ""),
    # 115 公益
    "115_1": ("其他", ""),
    # 116 银行
    "116_1": ("银行APP", ""),
    "116_2": ("银行APP", ""),
    "116_3": ("__l1_借贷软件__信用卡管理__", ""),  # 信用卡 → 借贷软件/信用卡管理
    "116_99": ("银行APP", ""),
    # 117 涉黄
    "117_1": ("色情视频", "色情"),
    # 118 投诉
    "118_1": ("投诉维权", "投诉平台"),
    # 119 伪冒
    "119_1": ("其他", "仿冒山寨"),
    # 120 医疗
    "120_1": ("健康医疗", ""),
    "120_2": ("严重疾病", ""),
    "120_3": ("健康医疗", ""),
    "120_4": ("健康医疗", ""),
    "120_99": ("健康医疗", ""),
    # 121 育儿
    "121_1": ("K12", ""),
    "121_2": ("K12", ""),
    "121_3": ("K12", ""),
    # 122 诈骗
    "122_1": ("即时通讯", "诈骗"),  # 聊天社交+诈骗
    "122_2": ("系统工具", "诈骗"),  # 远程操作+诈骗
    "122_3": ("其他", "诈骗"),
    "122_4": ("其他", "诈骗"),
    # 123 职业 (l2 用 生活服务的 本地生活/招聘, quality_tag 真正信号靠 quality_tag code)
    "123_1": ("本地生活", ""),
    "123_2": ("本地生活", ""),  # 房产中介
    "123_3": ("本地生活", ""),
    "123_4": ("本地生活", ""),
    "123_5": ("本地生活", ""),
    "123_6": ("本地生活", ""),
    "123_7": ("本地生活", ""),
    "123_8": ("本地生活", ""),
    "123_9": ("本地生活", ""),
    "123_10": ("本地生活", ""),
    "123_11": ("本地生活", ""),
    "123_12": ("本地生活", ""),
    "123_13": ("本地生活", ""),
    "123_99": ("本地生活", ""),
    # 124 中介
    "124_1": ("本地生活", ""),
    # 125 赚钱
    "125_1": ("其他", "网赚刷量"),
    "125_2": ("其他", "网赚刷量"),
    "125_99": ("其他", "网赚刷量"),
    # 126 传销
    "126_1": ("其他", "传销"),
    "126_2": ("其他", "传销"),
    # 127 贷款 (核心 — 用 v3 新增 L2)
    "127_1": ("贷款超市", ""),
    "127_2": ("小额现金贷", "小额现金贷"),
    "127_3": ("持牌消金", ""),
    "127_4": ("贷款超市", ""),
    "127_5": ("投资理财类", ""),
    "127_6": ("网络小贷", ""),
    "127_7": ("银行信贷", ""),
    "127_8": ("助贷导流", ""),
    "127_9": ("租赁分期", ""),
    "127_10": ("租赁分期", ""),
    "127_11": ("助贷导流", ""),
    "127_12": ("银行信贷", ""),
    "127_13": ("信用卡管理", ""),
    "127_14": ("消费分期", ""),
    "127_99": ("贷款超市", ""),
    # 128 境外
    "128_1": ("出海社交", ""),
    "128_2": ("网约车", ""),
    "128_99": ("出海社交", ""),
    # 129 赌博
    "129_1": ("真钱棋牌", "赌博"),
    "129_2": ("真钱棋牌", "赌博"),
    "129_3": ("真钱棋牌", "赌博"),
    # 130 反催收
    "130_1": ("其他", "反催收"),
    # 131 改机
    "131_1": ("多开分身", "改机软件"),
    "131_2": ("改机工具", "改机软件"),
    "131_3": ("多开分身", "改机软件"),
    "131_99": ("改机工具", "改机软件"),
    # 132 高风险投资
    "132_1": ("__l1_区块链加密__交易所__", ""),
    "132_2": ("基金股票", ""),
    "132_3": ("基金股票", ""),
    "132_4": ("保险理财", ""),
    "132_5": ("基金股票", ""),
    "132_6": ("外汇", ""),
    "132_99": ("基金股票", ""),
    # 133 工作招聘
    "133_1": ("招聘", ""),
    "133_2": ("招聘", ""),
    "133_3": ("招聘", ""),
    "133_4": ("招聘", ""),
    # 134 跑分
    "134_1": ("其他", "跑分"),
    "134_2": ("其他", "跑分"),
    # 999
    "999_99": ("其他", ""),
}

# 0605_2 risk_tag code → v3 risk_type (覆盖 L1/L2 隐含的 risk_type)
RISK_TAG_MAP = {
    "27": "其他高风险",  # 负面
    "29": "网赚刷量",    # 刷单
    "30": "色情",        # 涉黄
    "31": "诈骗",        # 诈骗
    "32": "赌博",        # 赌博
    "33": "网赚刷量",    # 赚钱
    "35": "诈骗",        # 网搜诈骗
}

# 0605_2 quality_tag code → v3 quality_tag
QUAL_MAP = {
    "01": "个体工商户",
    "02": "无",            # 主播 (无对应)
    "03": "企业员工",
    "04": "优质客群",
    "05": "公务员事业单位",  # 两会代表
    "06": "企业员工",      # 企业福利
    "07": "公务员事业单位",
    "08": "公务员事业单位",  # 军人
    "09": "医生",
    "10": "律师",
    "11": "教师",
    "12": "蓝领工人",      # 有工会组织
    "13": "公务员事业单位",  # 警察
    "14": "优质客群",      # 飞行员
    "15": "蓝领工人",      # 保安
    "16": "个体工商户",    # 卖彩票
    "17": "蓝领工人",      # 厨师
    "18": "学生",
    "19": "蓝领工人",
    "20": "销售",          # 微商
    "21": "销售",          # 招聘者
    "22": "有车",
    "23": "蓝领工人",      # 海员
    "24": "销售",          # 电商
    "25": "网约车司机",
    "26": "个体工商户",    # 美容美发
    "28": "销售",          # 中介
    "34": "销售",
}

# 123 职业 L2 → quality_tag 兜底 (当 quality_tag 字段为空但走的是职业 L1 时使用)
PROF_L2_QUAL = {
    "123_2": "销售",          # 房产中介
    "123_3": "货车司机",
    "123_4": "蓝领工人",      # 快递
    "123_5": "蓝领工人",      # 骑手
    "123_6": "网约车司机",
    "123_7": "销售",
    "123_8": "个体工商户",
    "123_9": "个体工商户",
    "123_10": "个体工商户",
    "123_11": "个体工商户",
    "123_12": "优质客群",
    "123_13": "无",
}

# ==================== 处理 v2 表 ====================
def process_v2(df):
    print(f"[v2] 原始 {len(df)} 行")
    df = df.drop_duplicates("app_package", keep="first").copy()
    print(f"[v2] 去重 unique pkg {len(df)}")

    # 词表迁移
    df["risk_type"] = df["risk_type"].map(lambda x: V2_RISK_MIGRATE.get(x, x))
    df["app_l1"] = df["app_l1"].map(lambda x: V2_L1_MIGRATE.get(x, x))
    df["quality_tag"] = "无"
    df["source"] = "v2_0522"

    # validate (会 fallback 非法值)
    records = []
    for _, r in df.iterrows():
        rec = {
            "app_package": r["app_package"],
            "app_name": r.get("app_name", ""),
            "app_l1": r["app_l1"],
            "app_l2": r["app_l2"],
            "risk_type": r["risk_type"],
            "quality_tag": r["quality_tag"],
            "confidence": r.get("confidence", 0.8),
            "reason": r.get("reason", ""),
            "source": "v2_0522",
        }
        validate_label(rec)
        records.append(rec)
    return pd.DataFrame(records)

# ==================== 处理 0605_2 表 ====================
def process_0605(df):
    print(f"[0605] 原始 {len(df)} 行")
    df = df.drop_duplicates("app_package_name", keep="first").copy()
    print(f"[0605] 去重 unique pkg {len(df)}")

    records = []
    unknown_l2 = []  # 收集 L2 code 没在映射表的样本

    for _, r in df.iterrows():
        l1_code = str(r["app_markcategories"]).strip()
        l2_code = str(r["app_marksubcategory"]).strip()
        risk_tag = str(r.get("risk_tag", "")).strip()
        qual_tag = str(r.get("quality_tag", "")).strip()

        # L1 默认值
        l1_default, hint_risk = L1_MAP.get(l1_code, ("其他", ""))
        v3_l1 = l1_default
        v3_risk = hint_risk
        v3_l2 = None

        # L2 映射 (含特殊 __l1_xxx__ 跳转)
        if l2_code in L2_MAP_0605:
            l2_target, override_risk = L2_MAP_0605[l2_code]
            if l2_target.startswith("__l1_"):
                # 形如 __l1_系统应用__ 或 __l1_借贷软件__信用卡管理__
                parts = l2_target.strip("_").split("_")
                # 解析: l1_<L1>[_<L2>]
                v3_l1 = parts[1]
                v3_l2 = parts[2] if len(parts) >= 3 else None
            else:
                v3_l2 = l2_target
            if override_risk:
                v3_risk = override_risk
        else:
            unknown_l2.append({"l1_code": l1_code, "l2_code": l2_code,
                               "app_name": r.get("app_name", ""), "app_package": r["app_package_name"]})

        # L2 兜底: 用该 L1 第一个合法 l2
        if v3_l2 is None:
            valid = L2_MAP.get(v3_l1, [])
            v3_l2 = valid[0] if valid else "未知"

        # risk_tag 优先级最高 (是 0605_2 的显式黑标)
        if risk_tag and risk_tag != "nan":
            # risk_tag 可能 pipe 分隔, 取第一个最严重
            for rc in risk_tag.split("|"):
                rc = rc.strip()
                if rc in RISK_TAG_MAP:
                    v3_risk = RISK_TAG_MAP[rc]
                    break

        if not v3_risk:
            v3_risk = "无"

        # quality_tag
        v3_qual = "无"
        if qual_tag and qual_tag != "nan":
            for qc in qual_tag.split("|"):
                qc = qc.strip()
                if qc in QUAL_MAP:
                    v3_qual = QUAL_MAP[qc]
                    break
        # 兜底: 职业 L1 但没显式 quality_tag, 用 L2 推
        if v3_qual == "无" and l1_code == "123" and l2_code in PROF_L2_QUAL:
            v3_qual = PROF_L2_QUAL[l2_code]

        reason = f"0605_2 {l1_code}/{l2_code}"
        rec = {
            "app_package": r["app_package_name"],
            "app_name": r.get("app_name", ""),
            "app_l1": v3_l1,
            "app_l2": v3_l2,
            "risk_type": v3_risk,
            "quality_tag": v3_qual,
            "confidence": 0.7,
            "reason": reason,
            "source": "0605_2",
        }
        validate_label(rec)
        records.append(rec)

    out = pd.DataFrame(records)
    print(f"[0605] 映射完成; L2 code 未命中映射表的样本 {len(unknown_l2)}")
    if unknown_l2:
        pd.DataFrame(unknown_l2).to_csv(
            BASE / "merge_audit_unknown_l2.csv", index=False, encoding="utf-8-sig")
    return out

# ==================== 处理 mainstream 表 (已是 v3 schema, 仅校验) ====================
def process_mainstream(df):
    print(f"[mainstream] 原始 {len(df)} 行")
    df = df.drop_duplicates("app_package", keep="first").copy()
    print(f"[mainstream] 去重 unique pkg {len(df)}")
    df["source"] = "mainstream"
    records = []
    for _, r in df.iterrows():
        rec = {
            "app_package": r["app_package"],
            "app_name": r.get("app_name", ""),
            "app_l1": r["app_l1"],
            "app_l2": r["app_l2"],
            "risk_type": r["risk_type"],
            "quality_tag": r["quality_tag"],
            "confidence": r.get("confidence", 0.99),
            "reason": r.get("reason", "mainstream手工标定"),
            "source": "mainstream",
        }
        validate_label(rec)
        records.append(rec)
    return pd.DataFrame(records)

# ==================== 合并 ====================
def merge_two(v2_df, e_df):
    v2_pkg = set(v2_df["app_package"])
    e_pkg = set(e_df["app_package"])
    overlap = v2_pkg & e_pkg
    only_v2 = v2_pkg - e_pkg
    only_e = e_pkg - v2_pkg
    print(f"[merge] v2 only {len(only_v2)}, 0605 only {len(only_e)}, overlap {len(overlap)}")

    v2_idx = v2_df.set_index("app_package")
    e_idx = e_df.set_index("app_package")

    rows = []
    # only_v2
    for pkg in only_v2:
        r = v2_idx.loc[pkg].to_dict()
        r["app_package"] = pkg
        rows.append(r)
    # only_0605
    for pkg in only_e:
        r = e_idx.loc[pkg].to_dict()
        r["app_package"] = pkg
        rows.append(r)
    # overlap: 优先 v2, quality_tag 用 0605 兜底
    for pkg in overlap:
        v2_r = v2_idx.loc[pkg].to_dict()
        e_r = e_idx.loc[pkg].to_dict()
        merged = dict(v2_r)
        merged["app_package"] = pkg
        # 用 0605 补 quality_tag (v2 都是 "无")
        if merged.get("quality_tag", "无") == "无" and e_r.get("quality_tag", "无") != "无":
            merged["quality_tag"] = e_r["quality_tag"]
        # 用 0605 补 risk: 若 v2 是 "无" 而 0605 给了高风险, 也接受 (谨慎)
        # 仅当 0605 命中 显式 risk_tag (诈骗/赌博/色情/传销/跑分) 时覆盖
        if merged.get("risk_type") == "无" and e_r.get("risk_type") in (
            "诈骗", "传销", "跑分", "赌博", "色情", "代还套现"
        ):
            merged["risk_type"] = e_r["risk_type"]
            merged["reason"] = (merged.get("reason", "") + " +0605补risk")[:40]
        # 用 0605 补 app_name (若 v2 缺)
        if not str(merged.get("app_name", "")).strip() and e_r.get("app_name"):
            merged["app_name"] = e_r["app_name"]
        merged["source"] = "both"
        rows.append(merged)

    out = pd.DataFrame(rows)
    # 列顺序
    cols = ["app_package", "app_name", "app_l1", "app_l2", "risk_type",
            "quality_tag", "confidence", "reason", "source"]
    out = out[cols]
    return out

def process_xiaomi(df):
    """xiaomi 已是 v3 schema (crawl_xiaomi_market 已映射好), 仅校验."""
    print(f"[xiaomi] 原始 {len(df)} 行")
    df = df.drop_duplicates("app_package", keep="first").copy()
    print(f"[xiaomi] 去重 unique pkg {len(df)}")
    records = []
    for _, r in df.iterrows():
        rec = {
            "app_package": r["app_package"],
            "app_name": r.get("app_name", ""),
            "app_l1": r["app_l1"],
            "app_l2": r["app_l2"],
            "risk_type": r.get("risk_type", "无"),
            "quality_tag": r.get("quality_tag", "无"),
            "confidence": r.get("confidence", 0.75),
            "reason": r.get("reason", "xiaomi_market"),
            "source": "xiaomi_market",
        }
        validate_label(rec)
        records.append(rec)
    return pd.DataFrame(records)


def overlay_xiaomi(base_df, xm_df):
    """xiaomi 仅补新 pkg, 不覆盖现有 (避免冲掉 v2/0605 已经精修过的 risk_type/quality_tag).
    L1 准确度差异交给后续看效果再决定是否升级为 override.
    """
    base_pkgs = set(base_df["app_package"])
    xm_pkgs = set(xm_df["app_package"])
    new_only = xm_pkgs - base_pkgs
    skipped = xm_pkgs & base_pkgs
    print(f"[overlay_xm] xiaomi 新增 {len(new_only)} pkg; 与现有重叠 {len(skipped)} 个 (保留现有)")

    add_df = xm_df[xm_df["app_package"].isin(new_only)].copy()
    out = pd.concat([base_df, add_df], ignore_index=True)
    cols = ["app_package", "app_name", "app_l1", "app_l2", "risk_type",
            "quality_tag", "confidence", "reason", "source"]
    return out[cols]


def overlay_mainstream(base_df, main_df):
    """mainstream 优先级最高: 主流 pkg 直接覆盖 v2/0605 的结果."""
    main_pkgs = set(main_df["app_package"])
    base_pkgs = set(base_df["app_package"])
    overridden = main_pkgs & base_pkgs
    new_from_main = main_pkgs - base_pkgs
    print(f"[overlay] mainstream 覆盖 v2/0605 共 {len(overridden)} pkg; "
          f"mainstream 独有 {len(new_from_main)} pkg")

    # 去掉被 mainstream 覆盖的, 再拼上 mainstream
    base_keep = base_df[~base_df["app_package"].isin(main_pkgs)].copy()
    out = pd.concat([main_df, base_keep], ignore_index=True)
    cols = ["app_package", "app_name", "app_l1", "app_l2", "risk_type",
            "quality_tag", "confidence", "reason", "source"]
    return out[cols]

# ==================== Excel ====================
def export_excel(df, out_path):
    df = df.copy()
    df["_risk_order"] = df["risk_type"].apply(
        lambda x: RISK_TYPES.index(x) if x in RISK_TYPES else 99)
    df_sorted = df.sort_values(["_risk_order", "app_l1", "app_l2"]).drop(columns="_risk_order")

    def _dist(col):
        s = df[col].value_counts().rename_axis(col).reset_index(name="数量")
        s["占比"] = (s["数量"] / len(df) * 100).round(2).astype(str) + "%"
        return s

    risk = _dist("risk_type")
    l1 = _dist("app_l1")
    l2 = _dist("app_l2")
    qual = _dist("quality_tag")
    src = _dist("source")

    high_risk = [r for r in RISK_TYPES if r not in ("无", "未知")]
    high_df = df_sorted[df_sorted["risk_type"].isin(high_risk)]
    qual_df = df_sorted[df_sorted["quality_tag"] != "无"]

    with pd.ExcelWriter(out_path, engine="openpyxl") as w:
        df_sorted.head(100000).to_excel(w, sheet_name="全量结果_前10w", index=False)
        risk.to_excel(w, sheet_name="风险类型分布", index=False)
        l1.to_excel(w, sheet_name="一级标签分布", index=False)
        l2.to_excel(w, sheet_name="二级标签分布", index=False)
        qual.to_excel(w, sheet_name="优质画像分布", index=False)
        src.to_excel(w, sheet_name="来源分布", index=False)
        high_df.head(50000).to_excel(w, sheet_name="高风险明细_前5w", index=False)
        qual_df.head(50000).to_excel(w, sheet_name="画像命中明细_前5w", index=False)

# ==================== main ====================
def main():
    v2_raw = pd.read_csv(SRC_V2)
    e_raw = pd.read_csv(SRC_0605, dtype={"app_markcategories": str,
                                          "app_marksubcategory": str,
                                          "risk_label": str, "risk_tag": str,
                                          "quality_tag": str})
    main_raw = pd.read_csv(SRC_MAINSTREAM)
    xm_raw = pd.read_csv(SRC_XIAOMI)

    mainstream = process_mainstream(main_raw)
    xiaomi = process_xiaomi(xm_raw)
    v2 = process_v2(v2_raw)
    e = process_0605(e_raw)

    # 合并顺序: v2 + 0605 → 上面 overlay mainstream (全字段 win) → 再 overlay xiaomi (仅补新 pkg)
    v2_e = merge_two(v2, e)
    with_main = overlay_mainstream(v2_e, mainstream)
    merged = overlay_xiaomi(with_main, xiaomi)
    print(f"[OUT] 合并后 {len(merged)} 行")
    print("\n=== source 分布 ===")
    print(merged["source"].value_counts().to_string())
    print("\n=== risk_type 分布 ===")
    print(merged["risk_type"].value_counts().head(20).to_string())
    print("\n=== quality_tag 分布 (非'无') ===")
    print(merged[merged["quality_tag"] != "无"]["quality_tag"].value_counts().to_string())
    print("\n=== app_l1 分布 ===")
    print(merged["app_l1"].value_counts().to_string())

    merged.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    print(f"\n[OUT] {OUT_CSV.name}")
    export_excel(merged, OUT_XLSX)
    print(f"[OUT] {OUT_XLSX.name}")

if __name__ == "__main__":
    main()
