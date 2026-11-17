#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
样本表 × 线上特征宽表 关联聚合 SQL 生成器（通用 / 配置驱动）
=====================================================================
一句话：给定「样本表 + 特征宽表 + 关联键 + 特征字典」，生成
        “保留样本全字段 group by，对每个特征取 max() 去重并重命名为同名”
        的关联聚合 SQL（默认 StarRocks 语法）。

复用方式：复制一份 config（dict），改 5 个字段即可，无需改本文件逻辑。
    python gen_feature_join.py my_config.py

config 文件需定义一个名为 CONFIG 的 dict（结构见 example_config.py）。
若不传参，则运行内置 DEMO_CONFIG（仅打印，不写文件）。

筛选是“可选”的：
  - 不配 filters     → 取字典全量特征
  - 配 window_max_days→ 只留时间窗 ≤N 天（含小时级、无窗口标志位）
  - 配 include_regex → 只留命中白名单的特征（异常行为筛选等）
  - 配 column_files  → 与真实表列取交集，避免 unknown column
"""
import re
import os
import sys
import importlib.util


# ----------------------------- 特征字典加载 -----------------------------
def load_features(dict_path, name_col=0, sep="\t", header_values=("特征明细",)):
    """从字典文件读特征名。默认：制表符分隔、第一列是特征名。
    自动跳过表头、空行、脏行（非 [A-Za-z_] 开头或含非法字符）、重复。"""
    feats, seen = [], set()
    with open(dict_path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.rstrip("\n")
            if not ln.strip():
                continue
            name = ln.split(sep)[name_col].strip()
            if not name or name in header_values:
                continue
            if not re.match(r"^[A-Za-z][A-Za-z0-9_]+$", name):
                continue
            if name in seen:
                continue
            seen.add(name)
            feats.append(name)
    return feats


def load_columns(col_file):
    """读取一张表的真实列名清单（每行一个列名，或制表符首列）。"""
    cols = set()
    with open(col_file, "r", encoding="utf-8") as f:
        for ln in f:
            c = ln.strip().split("\t")[0].strip()
            if c:
                cols.add(c.lower())
    return cols


# ----------------------------- 特征筛选 -----------------------------
def make_window_filter(window_max_days, keep_hours=True, keep_nowindow_regex=None):
    """返回一个 (name)->bool 的时间窗过滤器。
    window_max_days: 保留 ≤N 天的窗口；None 表示不按窗口过滤。
    无窗口后缀的特征：仅当命中 keep_nowindow_regex 才保留。"""
    day_re = re.compile(r"_(\d+)d$")
    hour_re = re.compile(r"_(\d+)h$")
    other_win = re.compile(r"_(\d+m|\d+y|today)$")  # 月/年/today 视为带窗口
    nowin_res = [re.compile(p) for p in (keep_nowindow_regex or [])]

    def f(name):
        if window_max_days is None:
            return True
        md = day_re.search(name)
        if md:
            return int(md.group(1)) <= window_max_days
        mh = hour_re.search(name)
        if mh:
            return keep_hours
        if other_win.search(name):
            # 月(1m=30d 视情况)、年、today：默认 today 保留、月年剔除
            return name.endswith("_today")
        # 无窗口后缀
        return any(r.search(name) for r in nowin_res)

    return f


def make_regex_filter(include_regex):
    """返回命中任一正则即保留的过滤器；include_regex 为空则全部保留。"""
    res = [re.compile(p) for p in (include_regex or [])]
    if not res:
        return lambda name: True
    return lambda name: any(r.search(name) for r in res)


def select_features(feats, filters):
    """按 filters 组合筛选。filters 为 None 取全量。"""
    if not filters:
        return list(feats)
    win_f = make_window_filter(
        filters.get("window_max_days"),
        keep_hours=filters.get("keep_hours", True),
        keep_nowindow_regex=filters.get("nowindow_keep_regex"),
    )
    rgx_f = make_regex_filter(filters.get("include_regex"))
    excl = [re.compile(p) for p in filters.get("exclude_regex", [])]
    out = []
    for n in feats:
        if not win_f(n):
            continue
        if not rgx_f(n):
            continue
        if any(r.search(n) for r in excl):
            continue
        out.append(n)
    return out


# ----------------------------- SQL 生成 -----------------------------
def build_sql(target, feats, agg="max", dialect="starrocks"):
    """target: 单个目标配置 dict。feats: 最终特征列表。"""
    s_cols = ",\n    ".join(f"s.{c}" for c in target["sample_cols"])
    gby = ", ".join(f"s.{c}" for c in target["sample_cols"])
    feat_lines = ",\n    ".join(f"{agg}(f.{c}) AS {c}" for c in feats)
    join_on = " AND ".join(
        f"s.{sk} = f.{fk}" for sk, fk in target["join_keys"]
    )
    where = ""
    if target.get("sample_where"):
        where = f"\nWHERE {target['sample_where']}"
    title = target.get("name", "")
    body = f"""-- =====================================================================
-- {title} 样本 × 特征宽表 关联聚合（{dialect}）
-- 样本表：{target['sample_table']}（保留全部字段）
-- 特征表：{target['feat_table']}
-- 关联键：{join_on}
-- 特征数：{len(feats)}；聚合：group by 样本全字段，对每个特征取 {agg}()
-- =====================================================================
SELECT
    {s_cols},
    {feat_lines}
FROM {target['sample_table']} s
LEFT JOIN {target['feat_table']} f
    ON {join_on}{where}
GROUP BY {gby}
;
"""
    return body


# ----------------------------- 主流程 -----------------------------
def run(config, write=True):
    feats = load_features(
        config["dict_path"],
        name_col=config.get("dict_name_col", 0),
        sep=config.get("dict_sep", "\t"),
    )
    kept = select_features(feats, config.get("filters"))
    print(f"字典特征(清洗后): {len(feats)} | 筛选后: {len(kept)}")

    results = {}
    for target in config["targets"]:
        cols = kept
        # 可选：与真实表列取交集
        cf = target.get("column_file")
        if cf and os.path.exists(cf):
            real = load_columns(cf)
            before = len(cols)
            cols = [c for c in cols if c.lower() in real]
            print(f"[{target.get('name','')}] 列交集: {before} -> {len(cols)} "
                  f"(丢弃 {before-len(cols)} 个不存在的列)")
        sql = build_sql(target, cols,
                        agg=config.get("agg", "max"),
                        dialect=config.get("dialect", "starrocks"))
        results[target.get("name", target["out"])] = sql
        if write:
            out_path = os.path.join(config.get("out_dir", "."), target["out"])
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(sql)
            print(f"[{target.get('name','')}] -> {target['out']} ({len(cols)} 特征)")

    if write and config.get("dump_feature_list"):
        lp = os.path.join(config.get("out_dir", "."), config["dump_feature_list"])
        with open(lp, "w", encoding="utf-8") as f:
            f.write("\n".join(kept))
        print(f"命中特征清单 -> {config['dump_feature_list']}")
    return results


def load_config(path):
    spec = importlib.util.spec_from_file_location("uc", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.CONFIG


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cfg = load_config(sys.argv[1])
        run(cfg, write=True)
    else:
        print("用法: python gen_feature_join.py <config.py>")
        print("config 需定义 CONFIG dict，结构见 example_config.py")
