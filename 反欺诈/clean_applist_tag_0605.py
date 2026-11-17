# -*- coding: utf-8 -*-
"""
清洗外部 applist 打标数据 applist_tag_0605_2.csv.

输入:  applist_tag_0605_2.csv
输出:
  - applist_tag_0605_2_clean.csv     主清洗表
  - applist_tag_0605_2_dirty.csv     CSV 解析错位的脏行 (供 audit)
  - applist_tag_0605_2_taxonomy.md   提取出来的 L1/L2/risk 编码字典

清洗规则:
  1. 隔离 CSV 错位行 (markcategories 不是 3 位数字)
  2. 去重 app_package_name (保留第一条)
  3. L2 描述统一: 127_6/127_7/127_14 统一带 "贷款_" 前缀
  4. risk code 补零成 2 位 (4→04, 9→09 …), 解决"04 优质 / 4 优质"重复
  5. risk_label 拆 risk_tag + quality_tag 两列
     - risk_tag  = 风险类 (负面/赌博/诈骗/涉黄/刷单/网搜诈骗/赚钱)
     - quality_tag = 优质画像类 (优质/医生/律师/职业/有车/客群等)
"""
import re
import pandas as pd
from pathlib import Path

BASE = Path(r"d:\my_claude\反欺诈")
SRC = BASE / "applist_tag_0605_2.csv"
OUT_CLEAN = BASE / "applist_tag_0605_2_clean.csv"
OUT_DIRTY = BASE / "applist_tag_0605_2_dirty.csv"
OUT_TAXO  = BASE / "applist_tag_0605_2_taxonomy.md"

# L2 描述统一映射 (左 = 旧, 右 = 统一后)
L2_DESC_FIX = {
    ("127_6",  "网络小贷"): "贷款_网络小贷",
    ("127_7",  "银行类"):   "贷款_银行类",
    ("127_14", "分期平台"): "贷款_分期平台",
}

# 风险类 risk code (补零后); 其余 code 归 quality_tag
RISK_CODES = {"27", "29", "30", "31", "32", "33", "35"}
# 27 负面 / 29 刷单 / 30 涉黄 / 31 诈骗 / 32 赌博 / 33 赚钱 / 35 网搜诈骗

def pad_code(c):
    """补零成 2 位; 非数字原样."""
    c = str(c).strip()
    if c.isdigit():
        return c.zfill(2)
    return c

def split_risk_quality(row):
    """拆 risk_label 为 risk_tag + quality_tag (都用 desc 拼)."""
    rl = row["risk_label"]
    rd = row["risk_label_desc"]
    if pd.isna(rl) or pd.isna(rd):
        return pd.Series([None, None, None, None])
    codes = [pad_code(c) for c in str(rl).split("|")]
    descs = str(rd).split("|")
    if len(codes) != len(descs):
        return pd.Series([None, None, None, None])
    risk_codes, risk_descs, qual_codes, qual_descs = [], [], [], []
    for c, d in zip(codes, descs):
        if c in RISK_CODES:
            risk_codes.append(c); risk_descs.append(d)
        else:
            qual_codes.append(c); qual_descs.append(d)
    return pd.Series([
        "|".join(risk_codes) if risk_codes else None,
        "|".join(risk_descs) if risk_descs else None,
        "|".join(qual_codes) if qual_codes else None,
        "|".join(qual_descs) if qual_descs else None,
    ])

def main():
    df = pd.read_csv(SRC, encoding="utf-8-sig", dtype=str)
    n0 = len(df)

    # 1. 隔离脏行
    valid_l1 = df["app_markcategories"].apply(
        lambda x: bool(re.fullmatch(r"\d{3}", str(x).strip())) if pd.notna(x) else False
    )
    dirty = df[~valid_l1].copy()
    clean = df[valid_l1].copy()
    print(f"[1] 原始 {n0}, 脏行 {len(dirty)} → 隔离, 干净 {len(clean)}")

    # 2. 去重 app_package_name
    n_before = len(clean)
    clean = clean.drop_duplicates(subset=["app_package_name"], keep="first")
    print(f"[2] 去重重复包名: {n_before} → {len(clean)} (去 {n_before - len(clean)})")

    # 3. L2 描述统一
    for (code, old_desc), new_desc in L2_DESC_FIX.items():
        mask = (clean["app_marksubcategory"] == code) & (clean["app_marksubcategory_desc"] == old_desc)
        n = mask.sum()
        clean.loc[mask, "app_marksubcategory_desc"] = new_desc
        print(f"[3] L2 {code}: {old_desc!r} → {new_desc!r} ({n} 行)")

    # 4. risk_label code 补零 + 5. 拆分 risk_tag / quality_tag
    risk_qual = clean.apply(split_risk_quality, axis=1)
    risk_qual.columns = ["risk_tag", "risk_tag_desc", "quality_tag", "quality_tag_desc"]
    clean = pd.concat([clean, risk_qual], axis=1)

    # 同时把原始 risk_label code 也补零回填一份, 方便对账
    def pad_pipe(s):
        if pd.isna(s): return s
        return "|".join(pad_code(c) for c in str(s).split("|"))
    clean["risk_label"] = clean["risk_label"].apply(pad_pipe)

    n_risk = clean["risk_tag"].notna().sum()
    n_qual = clean["quality_tag"].notna().sum()
    print(f"[4-5] 拆分完成: 含风险标签 {n_risk} ({n_risk/len(clean)*100:.1f}%), "
          f"含优质画像 {n_qual} ({n_qual/len(clean)*100:.1f}%)")

    # 输出
    clean.to_csv(OUT_CLEAN, index=False, encoding="utf-8-sig")
    dirty.to_csv(OUT_DIRTY, index=False, encoding="utf-8-sig")
    print(f"[OUT] {OUT_CLEAN.name} ({len(clean)} 行)")
    print(f"[OUT] {OUT_DIRTY.name} ({len(dirty)} 行)")

    # 6. 导出 taxonomy 字典
    write_taxonomy(clean)
    print(f"[OUT] {OUT_TAXO.name}")

def write_taxonomy(clean):
    """从清洗后数据反推 L1/L2/risk/quality 编码字典并写成 markdown."""
    lines = ["# applist_tag_0605_2 标签字典", ""]
    lines.append(f"> 来源: {SRC.name}, 清洗时间提取")
    lines.append("")

    # L1
    lines.append("## L1 (app_markcategories)")
    lines.append("")
    lines.append("| code | desc | 数量 |")
    lines.append("|:-:|---|---:|")
    l1 = clean.groupby(["app_markcategories", "app_markcategories_desc"]).size().reset_index(name="cnt").sort_values(["app_markcategories"])
    for _, r in l1.iterrows():
        lines.append(f"| {r['app_markcategories']} | {r['app_markcategories_desc']} | {r['cnt']} |")
    lines.append("")

    # L2
    lines.append("## L2 (app_marksubcategory)")
    lines.append("")
    lines.append("| code | desc | 数量 |")
    lines.append("|:-:|---|---:|")
    l2 = clean.groupby(["app_marksubcategory", "app_marksubcategory_desc"]).size().reset_index(name="cnt").sort_values(["app_marksubcategory"])
    for _, r in l2.iterrows():
        lines.append(f"| {r['app_marksubcategory']} | {r['app_marksubcategory_desc']} | {r['cnt']} |")
    lines.append("")

    # risk + quality
    sub = clean[clean["risk_label"].notna()].copy()
    pairs = []
    for _, r in sub.iterrows():
        codes = str(r["risk_label"]).split("|")
        descs = str(r["risk_label_desc"]).split("|")
        for c, d in zip(codes, descs):
            pairs.append((c, d))
    pdf = pd.DataFrame(pairs, columns=["code", "desc"])
    pcnt = pdf.groupby(["code", "desc"]).size().reset_index(name="cnt").sort_values(["code"])

    lines.append("## risk_label (拆 pipe 后, 补零)")
    lines.append("")
    lines.append("**风险类** (拆到 `risk_tag` 列):")
    lines.append("")
    lines.append("| code | desc | 数量 |")
    lines.append("|:-:|---|---:|")
    for _, r in pcnt[pcnt["code"].isin(RISK_CODES)].iterrows():
        lines.append(f"| {r['code']} | {r['desc']} | {r['cnt']} |")
    lines.append("")
    lines.append("**优质画像类** (拆到 `quality_tag` 列):")
    lines.append("")
    lines.append("| code | desc | 数量 |")
    lines.append("|:-:|---|---:|")
    for _, r in pcnt[~pcnt["code"].isin(RISK_CODES)].iterrows():
        lines.append(f"| {r['code']} | {r['desc']} | {r['cnt']} |")
    lines.append("")

    OUT_TAXO.write_text("\n".join(lines), encoding="utf-8")

if __name__ == "__main__":
    main()
