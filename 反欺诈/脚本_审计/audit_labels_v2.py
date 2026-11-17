# -*- coding: utf-8 -*-
"""审计 v2：收敛规则，剔除明显误报，输出真正需要复审的可疑标签"""
import sys, sqlite3, re
import pandas as pd
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

BASE = Path(r"d:\my_claude\反欺诈")
CACHE = BASE / "applist_label_cache_applist_tag_0522_v2.sqlite"

# 收敛后的可疑关键词：name 命中且 risk='无' 才视为可疑
# 每项: (label, 命中关键词, 排除关键词)
SUSPECT_RULES = [
    ("赌博",
     ["牛牛","炸金花","扎金花","德州","百家乐","老虎机","真金棋牌","真人棋牌",
      "棋牌室","棋牌大厅","真钱","彩票","竞彩","捕鱼","百人","龙虎斗","21点","21點"],
     ["计算器","教学","教程","学","新闻"]),
    ("色情",
     ["约炮","约会同城","撩妹","撩汉","裸聊","果聊","成人","深夜直播","小姐姐","御姐",
      "靓妹","骚","开车","荷尔蒙","暧昧","秒撩","美女直播","附近的女","附近秒聊"],
     []),
    ("小额现金贷",
     ["秒下款","急用钱","小额借款","闪贷","快速贷款","极速贷","秒贷","闪借","闪到账",
      "极速到账","秒到账","小额下款","贷款超市","贷款大全","贷款管家"],
     ["计算","计算器","房贷","车贷","保险"]),
    ("翻墙VPN",
     ["翻墙","科学上网","Shadowsocks","SSR","V2Ray","机场加速","外网加速","翻墙加速"],
     []),
    ("加速器(疑似翻墙)",
     ["游戏加速","网络加速器","上网加速器","网游加速器"],
     ["充电","内存","清理","厂商","企业","令牌","公司","集团","内部","校园","高校","政务"]),
    ("网赚刷量",
     ["走路赚","看视频赚","试玩赚","刷视频赚","拉新赚","转发赚","阅读赚","签到赚",
      "悬赏任务","任务赚钱","赚钱app","抢红包","步步赚","看广告赚"],
     ["游戏"]),
    ("区块链",
     ["挖矿","加密货币","BTC","ETH","NFT","DeFi","Token","数字货币","区块链"],
     []),
    ("改机软件",
     ["改机","虚拟定位","定位修改","修改定位","Root权限","root权限","多开分身","app多开","应用多开"],
     ["模拟器","计算器","导航"]),
    ("黑灰产工具",
     ["接码","虚拟号","按键精灵","抓包","逆向","群控","云控","自动脚本","脚本精灵"],
     []),
]

# 风险与一级标签一致性
EXPECTED_L1 = {
    "赌博": "棋牌赌博",
    "色情": "色情成人",
    "区块链": "区块链加密",
}

def main():
    conn = sqlite3.connect(str(CACHE))
    df = pd.read_sql(
        "SELECT app_package,app_l1,app_l2,risk_type,confidence,reason FROM label_cache",
        conn,
    )
    conn.close()
    src = pd.read_csv(BASE / "applist_tag_0522.csv").drop_duplicates("app_package")
    df = df.merge(src, on="app_package", how="left")
    df["app_name"] = df["app_name"].fillna("")

    safe = df[df["risk_type"] == "无"].copy()
    issues = []

    for label, kws, excludes in SUSPECT_RULES:
        if not kws:
            continue
        pat = "|".join(map(re.escape, kws))
        mask = safe["app_name"].str.contains(pat, regex=True, na=False)
        if excludes:
            exp = "|".join(map(re.escape, excludes))
            mask &= ~safe["app_name"].str.contains(exp, regex=True, na=False)
        suspects = safe[mask]
        if len(suspects) > 0:
            issues.append((f"risk=无 但疑似 {label}", len(suspects), suspects))

    # 风险 vs l1 不一致
    for rt, l1 in EXPECTED_L1.items():
        mis = df[(df["risk_type"] == rt) & (df["app_l1"] != l1)]
        if len(mis) > 0:
            issues.append((f"风险一致性: risk={rt} 但 app_l1!={l1}",
                           len(mis), mis))

    # 改机软件 app_l2 不一致
    mis = df[(df["risk_type"] == "改机软件")
             & (~df["app_l2"].isin(["改机工具", "多开分身"]))]
    if len(mis) > 0:
        issues.append((f"风险一致性: risk=改机软件 但 app_l2 不规范",
                       len(mis), mis))

    print(f"{'='*60}")
    print(f"可疑标签审计 v2  (cache 总数 {len(df)})")
    print(f"{'='*60}\n")
    total = 0
    for desc, n, _ in issues:
        print(f"  [{n:>5}]  {desc}")
        total += n
    print(f"\n  合计可疑条目（含重复）: {total}")

    out = BASE / "tagging_tmp" / "audit_suspects_v2.xlsx"
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        # 汇总
        summary = pd.DataFrame(
            [(d, n) for d, n, _ in issues], columns=["类型", "数量"]
        )
        summary.to_excel(w, sheet_name="汇总", index=False)
        for desc, n, sub in issues:
            name = re.sub(r"[<>:/\\|?*\"]", "_", desc)[:31]
            cols = ["app_name","app_package","app_l1","app_l2",
                    "risk_type","confidence","reason"]
            sub[cols].to_excel(w, sheet_name=name, index=False)
    print(f"\n明细输出: {out}")

    # 给出复审建议：哪些类别需要走 LLM 复审
    print("\n建议:")
    for desc, n, _ in issues:
        if "一致性" in desc:
            print(f"  - {desc} [{n}] → 直接按规则修正 app_l1/app_l2")
        else:
            print(f"  - {desc} [{n}] → 走 LLM 复审")

if __name__ == "__main__":
    main()
