#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Feature SQL Generator v25 - split sample cohorts for faster evaluation."""
import argparse
import os
import re
import yaml


DEFAULT_DERIVATION_MODES = {
    "labeled": {
        "suffix": "labeled",
        "description": "samples with fpd_k30 labels for IV/Lift evaluation",
        "filters": ["s.{label_field} >= 0"],
    },
    "recent7d": {
        "suffix": "recent7d",
        "description": "recent 7-day samples for pass-rate impact validation",
        "filters": ["s.{time_field} >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)"],
    },
    "full": {
        "suffix": "",
        "description": "legacy full sample cohort",
        "filters": [],
    },
}

def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def clean_cond(s):
    if not s: return "1=1"
    s = s.strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    return s

def get_stage_value(mapping, stage, key=None, default=None):
    """Read stage-aware config while keeping older configs compatible."""
    value = mapping.get(key, default) if key else mapping
    if isinstance(value, dict):
        return value.get(stage, default)
    return value if value is not None else default

def get_sample_table(sample, stage):
    table_cfg = sample.get("table")
    if isinstance(table_cfg, dict):
        return table_cfg.get(stage)
    return sample.get(stage)

def qualify_condition(condition, alias, fields):
    clean = clean_cond(condition)
    qualified = clean
    for field in sorted(fields or [], key=len, reverse=True):
        pattern = r"(?<![\w.])" + re.escape(field) + r"(?![\w])"
        qualified = re.sub(pattern, alias + "." + field, qualified)
    return qualified

# 允许的聚合函数白名单(StarRocks/Hive 通用)。未知 agg 直接报错, 避免拼出非法 SQL。
ALLOWED_AGGS = {
    "COUNT", "COUNT_DISTINCT", "SUM", "AVG", "MAX", "MIN",
    "STDDEV", "STDDEV_POP", "VARIANCE", "VAR_POP",
}

def validate_agg(agg, feat_name):
    """校验聚合函数在白名单内, 否则抛出明确错误(如伪函数 DATEDIFF_MAX)。"""
    if agg is None:
        raise ValueError(
            "特征 '{f}' 缺少 agg/agg_func 字段".format(f=feat_name))
    if agg.upper() not in ALLOWED_AGGS:
        raise ValueError(
            "特征 '{f}' 使用了不支持的聚合函数 '{a}'。".format(f=feat_name, a=agg)
            + " 允许的函数: " + ", ".join(sorted(ALLOWED_AGGS)) + "。"
            + " 若需'最近行为距今天数'等派生逻辑, 请改用 composite 特征(type: composite)"
            + " 配合 MAX(...) 基础特征, 在 logic 里用 DATEDIFF 表达。")
    return agg.upper()

def parse_window_days(window):
    value = str(window or "365d").strip().lower()
    if value.endswith("d"):
        return int(value[:-1])
    if value.endswith("y"):
        return int(value[:-1]) * 365
    return int(value)

def normalize_modes(cfg, requested_modes=None):
    mode_cfg = cfg.get("derivation_modes")
    modes = requested_modes if requested_modes else mode_cfg
    if not modes:
        modes = ["labeled", "recent7d"]
    if isinstance(modes, str):
        modes = [modes]

    normalized = []
    for mode in modes:
        if isinstance(mode, str):
            if mode not in DEFAULT_DERIVATION_MODES:
                raise ValueError("Unknown derivation mode: " + mode)
            item = DEFAULT_DERIVATION_MODES[mode].copy()
            item["name"] = mode
        elif isinstance(mode, dict):
            name = mode.get("name")
            if not name:
                raise ValueError("derivation_modes item must include name")
            item = DEFAULT_DERIVATION_MODES.get(name, {}).copy()
            item.update(mode)
            item["name"] = name
            item.setdefault("suffix", name)
            item.setdefault("filters", [])
        else:
            raise ValueError("Invalid derivation mode config: " + repr(mode))
        normalized.append(item)
    return normalized

def build_sample_filters(sample, stage, mode):
    s_time = sample["time_field"][stage]
    label_field = sample.get("label_field", "fpd_k30")
    filters = ["s." + s_time + " IS NOT NULL"]
    for raw in mode.get("filters", []):
        filters.append(raw.format(time_field=s_time, label_field=label_field))
    return filters

def get_output_table(cfg, stage, source_name, mode):
    base_table = cfg.get("output_table_" + stage, cfg["output_table"] + "_" + stage)
    suffix = mode.get("suffix", mode["name"])
    parts = [base_table]
    if suffix:
        parts.append(suffix)
    parts.append(source_name)
    return "_".join(parts)

def generate_single_source_sql(cfg, stage, source_name, mode=None):
    """Generate SQL for a single data source only"""
    sample = cfg["sample_table"]
    s_table = get_sample_table(sample, stage)
    s_time = sample["time_field"][stage]
    s_keys = sample["primary_keys"][stage]
    mode = mode or DEFAULT_DERIVATION_MODES["full"].copy()
    mode.setdefault("name", "full")
    
    target_cfg = sample.get("target_fields", {})
    if isinstance(target_cfg, dict):
        target_fields = target_cfg.get(stage, [])
    else:
        target_fields = target_cfg if isinstance(target_cfg, list) else []
    
    other_cfg = sample.get("other_groupby_fields", {})
    if isinstance(other_cfg, dict):
        other_fields = other_cfg.get(stage, [])
    else:
        other_fields = other_cfg if isinstance(other_cfg, list) else []
    
    out_table = get_output_table(cfg, stage, source_name, mode)
    groupby_fields = s_keys + [s_time] + target_fields + other_fields
    
    # Find the data source config
    ds = next((d for d in cfg["data_sources"] if d["name"] == source_name), None)
    if not ds:
        return None
    
    alias = ds["name"]
    tf = ds["time_field"]
    join_field = ds.get("join_field", get_stage_value(ds.get("join_key", {}), stage))
    ds_fields = ds.get("select_fields", [])
    
    # Build JOIN with time window in ON clause
    on_conditions = [
        "s.{jf} = {alias}.{jf}".format(jf=join_field, alias=alias),
        "{alias}.{tf} < s.{s_time}".format(alias=alias, tf=tf, s_time=s_time)
    ]
    if ds.get("partition_field"):
        on_conditions.append("{alias}.{pf} >= '20250101'".format(alias=alias, pf=ds["partition_field"]))
    
    for flt in ds.get("filters", []):
        on_conditions.append(qualify_condition(flt, alias, ds_fields))
    
    join_clause = "LEFT JOIN {table} {alias}\n    ON ".format(table=ds["table"], alias=alias) + "\n    AND ".join(on_conditions)
    
    # SELECT: groupby + features from this source only
    select_fields = ["s." + k for k in groupby_fields]
    
    for feat in cfg["features"]:
        if feat.get("type") == "composite" or feat["source"] != source_name:
            continue
        
        window_days = parse_window_days(feat.get("window", feat.get("time_window", "365d")))
        feat_tf = feat.get("time_field", tf)
        field = feat.get("field", feat.get("agg_field"))
        agg = validate_agg(feat.get("agg", feat.get("agg_func")), feat["name"])

        # 若特征自带独立 time_field, JOIN 的上界(tf < s.time)可能不覆盖它,
        # 需在 CASE 里补上界, 防止未来信息穿越。
        need_upper = feat_tf != tf
        time_cond = "{alias}.{tf} >= DATE_SUB(s.{s_time}, INTERVAL {days} DAY)".format(
            alias=alias, tf=feat_tf, s_time=s_time, days=window_days)
        if need_upper:
            time_cond = "(" + time_cond + ") AND ({alias}.{tf} < s.{s_time})".format(
                alias=alias, tf=feat_tf, s_time=s_time)
        qualified_field = "{alias}.{field}".format(alias=alias, field=field)

        feat_cond = feat.get("condition")
        if feat_cond:
            cond = "(" + time_cond + ") AND (" + qualify_condition(feat_cond, alias, ds_fields) + ")"
        else:
            cond = time_cond

        if agg == "COUNT_DISTINCT":
            expr = "COUNT(DISTINCT CASE WHEN " + cond + " THEN " + qualified_field + " END)"
        elif agg == "COUNT":
            expr = "COUNT(CASE WHEN " + cond + " THEN " + qualified_field + " END)"
        else:
            expr = agg + "(CASE WHEN " + cond + " THEN " + qualified_field + " END)"
        select_fields.append(expr + " AS " + feat["name"])
    
    where_clause = "\n  AND ".join(build_sample_filters(sample, stage, mode))
    
    sql = """-- purpose: {purpose}
-- sample_stage: {stage}
-- derivation_mode: {mode_name}
CREATE TABLE IF NOT EXISTS {out} AS
SELECT {selects}
FROM {s_table} s
{join}
WHERE {where}
GROUP BY {groupby};""".format(
        purpose=mode.get("description", mode["name"]),
        stage=stage,
        mode_name=mode["name"],
        out=out_table,
        selects=', '.join(chr(10)+'    '+f for f in select_fields),
        s_table=s_table,
        join=join_clause,
        where=where_clause,
        groupby=', '.join("s."+k for k in groupby_fields)
    )
    return sql

def _order_composites(composites):
    """按 logic 中互相引用的依赖做拓扑排序, 确保被依赖的 composite 先算。"""
    names = {c["name"] for c in composites}
    ordered, placed = [], set()
    remaining = list(composites)
    # 最多迭代 N 轮(N=特征数), 避免循环依赖时死循环
    for _ in range(len(remaining) + 1):
        progressed = False
        still = []
        for c in remaining:
            logic = c.get("logic", "")
            deps = {n for n in names if n != c["name"] and re.search(r"(?<![\w])" + re.escape(n) + r"(?![\w])", logic)}
            if deps <= placed:
                ordered.append(c); placed.add(c["name"]); progressed = True
            else:
                still.append(c)
        remaining = still
        if not remaining:
            break
        if not progressed:
            # 存在循环依赖或引用了未定义 composite, 按原序追加剩余, 交由数据库报错
            ordered.extend(remaining)
            break
    return ordered

def generate_composite_sql(cfg, stage, mode=None):
    """生成合并层 SQL: JOIN 各源表(single-source产出的表), 在外层计算 composite 特征。

    仅当配置里存在 composite 特征时才生成。composite 引用的基础特征来自各源表,
    通过样本主键 JOIN 后在外层用 CASE/算术表达式计算。
    """
    composites = [f for f in cfg["features"] if f.get("type") == "composite"]
    if not composites:
        return None

    sample = cfg["sample_table"]
    s_table = get_sample_table(sample, stage)
    s_keys = sample["primary_keys"][stage]
    mode = mode or DEFAULT_DERIVATION_MODES["full"].copy()
    mode.setdefault("name", "full")

    # 参与的数据源(有基础特征的源)
    source_names = []
    for f in cfg["features"]:
        if f.get("type") != "composite" and f.get("source") and f["source"] not in source_names:
            source_names.append(f["source"])
    if not source_names:
        return None

    # 各源表名 + JOIN(按主键)
    src_tables = {sn: get_output_table(cfg, stage, sn, mode) for sn in source_names}
    base_alias = "t_" + source_names[0]
    join_keys = s_keys
    from_parts = ["{tbl} {al}".format(tbl=src_tables[source_names[0]], al=base_alias)]
    for sn in source_names[1:]:
        al = "t_" + sn
        on = " AND ".join("{b}.{k} = {a}.{k}".format(b=base_alias, a=al, k=k) for k in join_keys)
        from_parts.append("FULL OUTER JOIN {tbl} {al} ON {on}".format(tbl=src_tables[sn], al=al, on=on))

    # 基础特征名 -> 所在源别名, 供 composite 引用时限定(避免歧义); 同时构造 COALESCE 主键
    feat_owner = {}
    for f in cfg["features"]:
        if f.get("type") != "composite" and f.get("source"):
            feat_owner[f["name"]] = "t_" + f["source"]

    # composite logic 里把基础特征名替换为 owner.特征名
    def qualify_logic(logic):
        out = logic
        for fname in sorted(feat_owner, key=len, reverse=True):
            out = re.sub(r"(?<![\w.])" + re.escape(fname) + r"(?![\w])",
                         feat_owner[fname] + "." + fname, out)
        return out

    ordered = _order_composites(composites)
    # 已算出的 composite 也可被后续 composite 引用 -> 用子查询逐层展开较复杂,
    # 这里改为: 前序 composite 直接内联其(已限定)表达式。
    composite_expr = {}
    select_exprs = []
    # 主键(跨表用 COALESCE 兜住 FULL OUTER JOIN 的 NULL)
    for k in join_keys:
        coalesce = "COALESCE(" + ", ".join("t_{s}.{k}".format(s=s, k=k) for s in source_names) + ")"
        select_exprs.append(coalesce + " AS " + k)
    # 透传基础特征
    for fname, owner in feat_owner.items():
        select_exprs.append("{o}.{f} AS {f}".format(o=owner, f=fname))
    # 逐个 composite: 先限定基础特征, 再内联前序 composite
    for c in ordered:
        expr = qualify_logic(c.get("logic", "NULL"))
        for prev_name, prev_expr in composite_expr.items():
            expr = re.sub(r"(?<![\w.])" + re.escape(prev_name) + r"(?![\w])",
                          "(" + prev_expr + ")", expr)
        composite_expr[c["name"]] = expr
        select_exprs.append(expr + " AS " + c["name"])

    out_table = get_output_table(cfg, stage, "composite", mode)
    sql = """-- purpose: {purpose} (composite merge layer)
-- sample_stage: {stage}
-- derivation_mode: {mode_name}
-- NOTE: 依赖各 single-source 表已先行生成: {srcs}
CREATE TABLE IF NOT EXISTS {out} AS
SELECT {selects}
FROM {frm};""".format(
        purpose=mode.get("description", mode["name"]),
        stage=stage,
        mode_name=mode["name"],
        srcs=", ".join(src_tables.values()),
        out=out_table,
        selects=", ".join(chr(10) + "    " + e for e in select_exprs),
        frm=(chr(10) + "  ").join(from_parts),
    )
    return sql

def generate_dict(cfg):
    rows = ["feature_name,feature_desc,feature_type,time_window,source_table"]
    for feat in cfg["features"]:
        ftype = "composite" if feat.get("type")=="composite" else "int"
        window = feat.get("window", "-")
        source = feat.get("source", "-")
        rows.append(feat["name"] + "," + feat["desc"] + "," + ftype + "," + window + "," + source)
    return chr(10).join(rows)

def build_sql_filename(cfg, stage, source_name, mode):
    suffix = mode.get("suffix", mode["name"])
    if suffix:
        return cfg["feature_group"] + "_" + stage + "_" + suffix + "_" + source_name + ".sql"
    return cfg["feature_group"] + "_" + stage + "_" + source_name + ".sql"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", default="assets")
    parser.add_argument("--stages", nargs="*", default=["preloan", "inloan"])
    parser.add_argument("--modes", nargs="*", default=None,
                        help="Derivation modes: labeled, recent7d, full or custom names from config")
    parser.add_argument("--single-source", action="store_true", help="Generate separate SQL per data source")
    args = parser.parse_args()
    
    cfg = load_config(args.config)
    dictionary = generate_dict(cfg)
    modes = normalize_modes(cfg, args.modes)
    
    os.makedirs(args.output, exist_ok=True)
    
    has_composite = any(f.get("type") == "composite" for f in cfg["features"])

    for stage in args.stages:
        # 默认即按 single-source 逐源生成(StarRocks 兼容); --single-source 保留向后兼容
        for mode in modes:
            for ds in cfg["data_sources"]:
                sql = generate_single_source_sql(cfg, stage, ds["name"], mode)
                if sql:
                    sql_path = os.path.join(args.output, build_sql_filename(cfg, stage, ds["name"], mode))
                    with open(sql_path, "w", encoding="utf-8") as f:
                        f.write(sql)
                    print("Generated: " + sql_path)
            # composite 合并层: JOIN 各源表后在外层计算复合特征
            if has_composite:
                csql = generate_composite_sql(cfg, stage, mode)
                if csql:
                    cpath = os.path.join(args.output, build_sql_filename(cfg, stage, "composite", mode))
                    with open(cpath, "w", encoding="utf-8") as f:
                        f.write(csql)
                    print("Generated: " + cpath + "  (composite merge layer)")
    
    dict_path = os.path.join(args.output, cfg["feature_group"] + "_dictionary.csv")
    with open(dict_path, "w", encoding="utf-8-sig") as f:
        f.write(dictionary)
    print("Generated: " + dict_path)
    print("Done! Generated for stages: " + ", ".join(args.stages))
    print("Derivation modes: " + ", ".join(m["name"] for m in modes))

if __name__ == "__main__":
    main()
