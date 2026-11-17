# -*- coding: utf-8 -*-
"""
黑产声纹库: 迁移现有 black_db.pkl 到新 schema + 支持后续 enroll。

迁移: 旧 records({id,emb,source,added,tag,case[,phone]}) 补齐:
  - actor_id: 黑产个体标识(同一代理多通聚一个)。本批按 case 分组
    (0709 案实证为同一换号客户 -> 一个 actor; 0727 案同理)。
  - phones: 关联号码列表(从 id/phone 提取)
  - reviewer/review_ts: 入库审核留痕(合规)
并补 identities 聚合层(按 actor_id)。

入库审核关卡: 仅 tag 含"确认/换号作案"且有 reviewer 的进主库(本批历史数据
默认视为已确认, reviewer 标 migrated)。

用法:
  python pipelines/build_black_db.py --src black_db.pkl --db data/black_db.pkl
"""
import os, sys, re, io, argparse
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from common import vpdb


def actor_of(rec):
    """黑产个体标识: 同一案件的换号作案聚为一个 actor。"""
    return f"actor_{rec.get('case','unknown')}"


def phones_of(rec):
    """从 id / phone 字段提取关联号码。"""
    ph = set()
    if rec.get("phone"):
        ph.add(str(rec["phone"]))
    for m in re.findall(r"1\d{10}", rec.get("id", "")):
        ph.add(m)
    return sorted(ph)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--src",
        default=os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "processed", "legacy_black_db.pkl"
        ),
    )
    ap.add_argument(
        "--db",
        default=os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "processed", "black_db.pkl"
        ),
    )
    args = ap.parse_args()

    old = vpdb.load_db(args.src)
    db = {"model": "cam++", "schema_version": 2, "identities": {}, "records": []}
    ts = vpdb.now_ts()

    by_actor = {}
    for r in old["records"]:
        actor = actor_of(r)
        phones = phones_of(r)
        nr = dict(r)
        nr["actor_id"] = actor
        nr["phones"] = phones
        nr.setdefault("tag", "确认黑产")
        nr["reviewer"] = r.get("reviewer", "migrated")
        nr["review_ts"] = r.get("review_ts", ts)
        db["records"].append(nr)
        a = by_actor.setdefault(actor, {"rec_ids": [], "phones": set(), "cases": set()})
        a["rec_ids"].append(nr["id"])
        a["phones"].update(phones)
        a["cases"].add(r.get("case", "?"))

    for actor, info in by_actor.items():
        db["identities"][actor] = {
            "rec_ids": info["rec_ids"],
            "phones": sorted(info["phones"]),
            "n_calls": len(info["rec_ids"]),
            "cases": sorted(info["cases"]),
        }

    vpdb.save_db(db, args.db)

    # 报告
    L = ["# 黑产声纹库 迁移报告", "",
         f"记录 {len(db['records'])} 条, 黑产个体(actor) {len(db['identities'])} 个", "",
         "| actor_id | 通数 | 关联号码 | 案件 |", "|---|---|---|---|"]
    for actor, info in sorted(db["identities"].items()):
        L.append(f"| {actor} | {info['n_calls']} | {','.join(info['phones']) or '-'} | {','.join(info['cases'])} |")
    with io.open(os.path.join(os.path.dirname(args.db), "black_db_报告.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"迁移完成: {len(db['records'])} 条 / {len(db['identities'])} 个 actor -> {args.db}")


if __name__ == "__main__":
    main()
