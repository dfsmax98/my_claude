# -*- coding: utf-8 -*-
"""反向审计：被标为高风险但可能实则无风险的 app"""
import sys, sqlite3, re
import pandas as pd
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

BASE = Path(r"d:\my_claude\反欺诈")
CACHE = BASE / "applist_label_cache_applist_tag_0522_v2.sqlite"

# 知名正规品牌词（命中通常说明是正规 app，不应标高风险）
REGULAR_KEYWORDS = [
    # 银行
    "工商银行","建设银行","农业银行","中国银行","交通银行","招商银行","浦发银行",
    "民生银行","兴业银行","光大银行","平安银行","中信银行","华夏银行","邮政储蓄","邮储",
    "广发银行","北京银行","上海银行","南京银行","宁波银行","江苏银行",
    # 互联网持牌金融
    "支付宝","微信","花呗","借呗","京东金条","美团金融","度小满","招联金融","马上消费",
    "微粒贷","蚂蚁财富","陆金所","平安普惠",
    # 大厂
    "华为","小米","OPPO","vivo","荣耀","三星","苹果","Apple",
    "百度","腾讯","阿里","京东","美团","滴滴","字节","抖音","快手","微博",
    "新浪","搜狐","网易","知乎","B站","哔哩哔哩",
    # 政府/官方
    "政务","公安","税务","社保","公积金","12306","国家","政府",
    # 知名教育/办公
    "钉钉","飞书","企业微信","WPS","金山","Microsoft","Office","学习强国",
]

# 风险类型 → 高风险列表
HIGH_RISK = ["小额现金贷","赌博","色情","翻墙VPN","山寨低质","伪冒仿冒",
             "改机软件","黑灰产工具","网赚刷量","隐私窃取","其他高风险",
             "区块链","反催收","征信修复","投诉平台"]

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

    print(f"{'='*60}")
    print(f"反向审计：高风险但可能误标")
    print(f"{'='*60}")
    print(f"高风险总数: {df['risk_type'].isin(HIGH_RISK).sum()}\n")

    issues = []

    # 规则 1: 高风险但名称含正规品牌词
    pat = "|".join(map(re.escape, REGULAR_KEYWORDS))
    high = df[df["risk_type"].isin(HIGH_RISK)]
    mask = high["app_name"].str.contains(pat, regex=True, na=False, case=False)
    sub = high[mask]
    if len(sub) > 0:
        issues.append(("高风险但含正规品牌词", sub))

    # 规则 2: 高风险 + confidence 极低
    sub = high[high["confidence"] < 0.4]
    if len(sub) > 0:
        issues.append(("高风险但 confidence<0.4", sub))

    # 规则 3: risk=山寨低质 + 包名是 com.xxx.xxx 但名字含中文常用词
    sub = high[(high["risk_type"]=="山寨低质")
               & (high["app_name"].str.contains(
                   "计算器|银行|商城|超市|医院|学校|学院|公司|集团|科技|股份|有限",
                   regex=True, na=False))]
    if len(sub) > 0:
        issues.append(("山寨低质但名字像正规机构", sub))

    # 规则 4: risk=改机软件 但名字含"模拟"游戏类
    sub = high[(high["risk_type"]=="改机软件")
               & (high["app_name"].str.contains("模拟器|计算器|导航", regex=True, na=False))]
    if len(sub) > 0:
        issues.append(("改机软件但名字像游戏/工具", sub))

    # 规则 5: risk=赌博 但名字含"教学/教程/学习"
    sub = high[(high["risk_type"]=="赌博")
               & (high["app_name"].str.contains("教学|教程|学习|训练", regex=True, na=False))]
    if len(sub) > 0:
        issues.append(("赌博但名字像教学", sub))

    # 规则 6: risk=色情 但是常规社交品牌
    sub = high[(high["risk_type"]=="色情")
               & (high["app_name"].str.contains(
                   "陌陌|探探|Soul|Tinder|Bumble|QQ|微信", regex=True, na=False))]
    if len(sub) > 0:
        issues.append(("色情但是常规社交品牌", sub))

    # 规则 7: risk=网赚 但名字含"游戏"
    sub = high[(high["risk_type"]=="网赚刷量")
               & (high["app_name"].str.contains("游戏|手游", regex=True, na=False))]
    if len(sub) > 0:
        issues.append(("网赚刷量但是游戏", sub))

    # 规则 8: risk=翻墙VPN 但名字含"企业/校园/政务/内部"
    sub = high[(high["risk_type"]=="翻墙VPN")
               & (high["app_name"].str.contains(
                   "企业|校园|高校|学校|政务|内部|公司|集团|令牌", regex=True, na=False))]
    if len(sub) > 0:
        issues.append(("翻墙VPN但是企业/校园VPN", sub))

    print("各类可疑数量：")
    total = 0
    for desc, sub in issues:
        print(f"  [{len(sub):>4}]  {desc}")
        total += len(sub)
    print(f"\n合计: {total}\n")

    out = BASE / "tagging_tmp" / "audit_overlabeled.xlsx"
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        summary = pd.DataFrame([(d, len(s)) for d, s in issues], columns=["类型","数量"])
        summary.to_excel(w, sheet_name="汇总", index=False)
        for desc, sub in issues:
            name = re.sub(r"[<>:/\\|?*\"]", "_", desc)[:31]
            cols = ["app_name","app_package","app_l1","app_l2","risk_type","confidence","reason"]
            sub[cols].to_excel(w, sheet_name=name, index=False)
    print(f"明细输出: {out}")

if __name__ == "__main__":
    main()
