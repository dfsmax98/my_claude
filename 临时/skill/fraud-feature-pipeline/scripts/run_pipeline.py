#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
反欺诈特征挖掘 Pipeline —— 确定性步骤串联器 (Step3→4→5)。

本脚本只负责"确定性"的三步, 由 agent 在完成 Step1(查字典)/Step2(查表+脑暴+写YAML)后调用:
  Step3 建表   : strategy-mining 生成 4 表 SQL(labeled/recent7d × preloan/inloan) 并执行
  Step4 评估   : feature_eval 对 labeled 表算 IV/KS/PSI/lift(分月+分客群) → Excel
  Step5 策略   : strategy-analysis 决策树挖单/多变量策略; y影响取labeled表, 拒绝率取recent7d表

创造性的 Step2(特征设计/写 YAML)由 agent 完成, 不在本脚本内。

用法:
  python run_pipeline.py --config <特征配置.yaml> --stage preloan \
      --steps build,eval,analyze [--dry-run] [--output-dir ./pipeline_out]

  --steps 可只跑部分: 如 --steps eval,analyze (表已建好时)
  --dry-run: 只生成 SQL 不执行建表
"""
import argparse
import os
import sys

# 定位 skill 根目录, 挂载各子 skill 与公共 lib
SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for p in [os.path.join(SKILL_ROOT, "lib"),
          os.path.join(SKILL_ROOT, "strategy-mining", "scripts"),
          os.path.join(SKILL_ROOT, "strategy-mining", "lib"),
          os.path.join(SKILL_ROOT, "strategy-analysis")]:
    if p not in sys.path:
        sys.path.insert(0, p)

# .env 自动加载(凭证)
try:
    from env_loader import load_env
    load_env(os.path.join(SKILL_ROOT, "lib"))
except Exception:
    pass


def log(msg):
    print("[pipeline] " + msg, flush=True)


def step_build(config, stage, output_dir, dry_run):
    """Step3: 生成 4 表 SQL 并(可选)执行建表。"""
    import generate_feature_sql as gen

    cfg = gen.load_config(config)
    sql_dir = os.path.join(output_dir, "sql")
    os.makedirs(sql_dir, exist_ok=True)

    stages = [stage] if stage else ["preloan", "inloan"]
    modes = gen.normalize_modes(cfg, ["labeled", "recent7d"])
    has_composite = any(f.get("type") == "composite" for f in cfg["features"])

    generated = []
    for st in stages:
        for mode in modes:
            for ds in cfg["data_sources"]:
                sql = gen.generate_single_source_sql(cfg, st, ds["name"], mode)
                if sql:
                    fp = os.path.join(sql_dir, gen.build_sql_filename(cfg, st, ds["name"], mode))
                    open(fp, "w", encoding="utf-8").write(sql)
                    generated.append(fp)
            if has_composite:
                csql = gen.generate_composite_sql(cfg, st, mode)
                if csql:
                    fp = os.path.join(sql_dir, gen.build_sql_filename(cfg, st, "composite", mode))
                    open(fp, "w", encoding="utf-8").write(csql)
                    generated.append(fp)
    log(f"Step3 生成 {len(generated)} 个 SQL 文件 -> {sql_dir}")

    if dry_run:
        log("dry-run: 跳过建表执行")
        return {"sql_files": generated, "executed": False}

    # 执行建表(需 DB 凭证, 走 db_connector)
    from db_connector import get_connection
    conn, cur = get_connection()
    for fp in generated:
        sql = open(fp, encoding="utf-8").read()
        for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
            cur.execute(stmt)
        log(f"  已执行: {os.path.basename(fp)}")
    conn.commit(); cur.close(); conn.close()
    return {"sql_files": generated, "executed": True}


def _load_table(table):
    """用 db_connector 把表读成 DataFrame。"""
    import pandas as pd
    from db_connector import get_connection
    conn, cur = get_connection()
    cur.execute(f"SELECT * FROM {table}")
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    cur.close(); conn.close()
    return pd.DataFrame(rows, columns=cols)


def step_eval(labeled_table, scene, features, output_dir):
    """Step4: feature_eval 对 labeled 表算指标 → Excel。"""
    import feature_eval as fe
    df = _load_table(labeled_table)
    dt_col = "close_datetime" if scene == "preloan" else "create_datetime"
    group_cols = ["cust_group_dq"] if scene == "preloan" else ["cust_group_dz", "new_old"]
    feats = features or [c for c in df.columns
                         if c.startswith(("f_", "contact_", "immediate_", "smy_", "bs_", "app_"))]
    out = os.path.join(output_dir, f"feature_eval_{scene}.xlsx")
    r = fe.evaluate_features(df, feats, y_list=["fpd_k30"], dt_col=dt_col,
                             dt_cut="month", group_cols=group_cols, output_path=out,
                             bin_method="tree")
    log(f"Step4 特征评估报告 -> {out}")
    return r


def step_analyze(labeled_table, recent7d_table, scene, output_dir):
    """Step5: 策略分析。y影响取 labeled 表, 拒绝率影响取 recent7d 表。"""
    from src.analyzer import StrategyAnalyzer
    sc = "dq" if scene == "preloan" else "dz"
    analyzer = StrategyAnalyzer(scene=sc)
    p1, s1, res1 = analyzer.run_step1(labeled_table,
                                      output_path=os.path.join(output_dir, f"strategy_{sc}_step1.xlsx"))
    p2, s2 = analyzer.run_step2(recent7d_table, step1_strategies=res1["strategies"],
                                output_path=os.path.join(output_dir, f"strategy_{sc}_step2.xlsx"))
    log(f"Step5 策略报告 -> {p1} / {p2}")
    return {"step1": p1, "step2": p2, "summary1": s1, "summary2": s2}


def main():
    ap = argparse.ArgumentParser(description="反欺诈特征挖掘 pipeline 串联器")
    ap.add_argument("--config", help="strategy-mining 特征配置 YAML(build 步骤需要)")
    ap.add_argument("--stage", choices=["preloan", "inloan"], default="preloan")
    ap.add_argument("--steps", default="build,eval,analyze", help="逗号分隔: build,eval,analyze")
    ap.add_argument("--labeled-table", help="labeled(有fpd_k30表现)表名, eval/analyze 需要")
    ap.add_argument("--recent7d-table", help="recent7d(近7天)表名, analyze 需要")
    ap.add_argument("--features", nargs="*", help="指定评估/挖掘的特征(默认自动识别)")
    ap.add_argument("--output-dir", default="./pipeline_out")
    ap.add_argument("--dry-run", action="store_true", help="build 只生成 SQL 不执行")
    args = ap.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    steps = [s.strip() for s in args.steps.split(",") if s.strip()]

    if "build" in steps:
        if not args.config:
            ap.error("build 步骤需要 --config")
        step_build(args.config, args.stage, args.output_dir, args.dry_run)

    if "eval" in steps:
        if not args.labeled_table:
            ap.error("eval 步骤需要 --labeled-table")
        step_eval(args.labeled_table, args.stage, args.features, args.output_dir)

    if "analyze" in steps:
        if not (args.labeled_table and args.recent7d_table):
            ap.error("analyze 步骤需要 --labeled-table 和 --recent7d-table")
        step_analyze(args.labeled_table, args.recent7d_table, args.stage, args.output_dir)

    log("完成. 产物目录: " + os.path.abspath(args.output_dir))


if __name__ == "__main__":
    main()
