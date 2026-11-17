# -*- coding: utf-8 -*-
"""
离线建客户声纹库。

流程:
  遍历录音目录 -> 每通 extract_customer_embedding(return_meta)
    -> 双轨失败/reject/低置信 隔离到"待复核"清单, 不入库
    -> ok 按客户号归组
  -> 每个客户号 cluster.cluster_identity 定主簇(本人) / aux(代接)
  -> 写 records + identities 聚合层 -> save_db -> 建库报告

身份单元 = 客户号(本批用手机号代替; 真实上线传业务客户号映射)。
断点续跑: emb 缓存 npz(key=name)。

用法:
  MODELSCOPE_CACHE=./ms_cache PYTHONIOENCODING=utf-8 \
    python pipelines/build_customer_db.py <录音目录> [--db data/customer_db.pkl]
"""
import os, sys, re, glob, io, json, argparse
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import numpy as np
from common import vpdb, cluster
from common.extract import extract_customer_embedding, NotDualTrackError


def cust_no_of(name):
    """从文件名提取客户号(本批=手机号11位)。"""
    m = re.search(r"1\d{10}", name)
    return m.group(0) if m else name


def seg_of(name):
    m = re.search(r"[（(](\d)[）)]", name)
    return m.group(1) if m else "1"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src_dir", help="录音目录")
    ap.add_argument(
        "--db",
        default=os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "processed", "customer_db.pkl"
        ),
    )
    ap.add_argument("--work", default=None, help="diarize 中间产物目录")
    args = ap.parse_args()

    work = args.work or os.path.join(args.src_dir, "_build_work")
    cache_path = os.path.join(work, "_emb_cache.npz")
    os.makedirs(work, exist_ok=True)

    files = sorted(glob.glob(os.path.join(args.src_dir, "*.mp3")) +
                   glob.glob(os.path.join(args.src_dir, "*.wav")))
    cache = {}
    if os.path.exists(cache_path):
        d = np.load(cache_path, allow_pickle=True)
        cache = {k: d[k] for k in d.files}

    by_cust = {}     # cust_no -> [(name, emb, meta)]
    review = []      # 待复核清单
    for i, f in enumerate(files, 1):
        name = os.path.splitext(os.path.basename(f))[0]
        try:
            if name in cache:
                emb = cache[name]
                meta = {"role_confidence": "缓存", "quality": "ok", "customer_ch": "?"}
            else:
                emb, meta = extract_customer_embedding(f, out_dir=work, return_meta=True)
        except NotDualTrackError as e:
            review.append((name, "非双轨")); print(f"[{i}/{len(files)}] 跳过 {name}: 非双轨"); continue
        except Exception as e:
            review.append((name, f"异常:{e}")); print(f"[{i}/{len(files)}] 失败 {name}: {e}"); continue

        if emb is None or meta.get("quality") == "reject":
            review.append((name, f"质检reject/{meta.get('role_confidence')}"))
            print(f"[{i}/{len(files)}] 隔离 {name}: reject"); continue
        if str(meta.get("role_confidence", "")).startswith("低"):
            review.append((name, f"角色低置信:{meta['role_confidence']}"))
            print(f"[{i}/{len(files)}] 隔离 {name}: 角色低置信"); continue

        cache[name] = emb
        by_cust.setdefault(cust_no_of(name), []).append((name, emb, meta))
        print(f"[{i}/{len(files)}] OK {name} 客户声道={meta.get('customer_ch')}")

    np.savez(cache_path, **cache)

    # ---- 建库: 每客户号聚类定主簇 ----
    db = {"model": "cam++", "schema_version": 2, "identities": {}, "records": []}
    report = build_records(db, by_cust)

    vpdb.save_db(db, args.db)
    write_report(args, db, by_cust, review, report)
    print(f"\n建库完成: {len(db['identities'])} 个客户号, {len(db['records'])} 条模板, "
          f"待复核 {len(review)} -> {args.db}")


def build_records(db, by_cust):
    """聚类 + 写 records/identities。返回 per-客户号报告行。"""
    report = []
    for cust, items in sorted(by_cust.items()):
        embs = [e for _, e, _ in items]
        cl = cluster.cluster_identity(embs)
        rec_ids = []
        primary_set = set(cl["primary"]) if cl["primary"] else set()
        for idx, (name, emb, meta) in enumerate(items):
            rid = f"{cust}::{name}::{seg_of(name)}"
            rec_ids.append(rid)
            db["records"].append({
                "id": rid, "emb": emb, "cust_no": cust,
                "phone": cust, "call_id": name, "seg": seg_of(name),
                "cluster": "primary" if idx in primary_set else "aux",
                "quality": meta.get("quality", "ok"),
                "role_confidence": meta.get("role_confidence"),
                "denoise": bool(meta.get("denoise_applied", False)),
                "source": name, "added": vpdb.now_ts(),
            })
        primary_ids = [rec_ids[k] for k in (cl["primary"] or [])]
        aux_ids = [[rec_ids[k] for k in grp] for grp in cl["aux"]]
        db["identities"][cust] = {
            "primary_cluster": primary_ids if cl["status"] == "ok" else "undecided",
            "aux_clusters": aux_ids,
            "phones": [cust], "n_calls": len(items),
            "n_voices": cl["n_voices"], "status": cl["status"],
        }
        report.append((cust, len(items), cl["n_clusters"], cl["status"],
                       len(primary_ids)))
    return report


def write_report(args, db, by_cust, review, report):
    L = ["# 客户声纹库 建库报告", "",
         f"客户号 {len(db['identities'])} 个, 模板 {len(db['records'])} 条, 待复核 {len(review)} 段", "",
         "## 每客户号", "",
         "| 客户号 | 通数 | 声音簇数 | 状态 | 主簇模板数 |", "|---|---|---|---|---|"]
    for cust, n, nc, status, np_ in report:
        L.append(f"| {cust} | {n} | {nc} | {status} | {np_} |")
    L += ["", "## 待复核清单(未入库)", ""]
    if review:
        for name, why in review:
            L.append(f"- {name}: {why}")
    else:
        L.append("(无)")
    out = os.path.join(os.path.dirname(args.db), "customer_db_报告.md")
    with io.open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


if __name__ == "__main__":
    main()
