# -*- coding: utf-8 -*-
"""按规则修正 l1/l2 与 risk_type 不一致的标签"""
import sys, sqlite3, pandas as pd
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

BASE = Path(r"d:\my_claude\反欺诈")
CACHE = BASE / "applist_label_cache_applist_tag_0522_v2.sqlite"

# risk_type → (默认 app_l1, 默认 app_l2)
RISK_TO_L1L2 = {
    "色情": ("色情成人", "约炮社交"),  # 因绝大多数是约炮/陌生人，二级看具体
    "赌博": ("棋牌赌博", "真钱棋牌"),
    "区块链": ("区块链加密", "钱包"),
    "改机软件": ("工具", "改机工具"),
}

def main():
    conn = sqlite3.connect(str(CACHE))
    fixed = 0

    # 色情：l1!=色情成人 → 改成色情成人 + 选 l2
    cur = conn.execute("""
        UPDATE label_cache
           SET app_l1='色情成人',
               app_l2=CASE
                 WHEN app_l2 LIKE '%直播%' THEN '色情直播'
                 WHEN app_l2 LIKE '%视频%' OR app_l1='视频影音' THEN '色情视频'
                 WHEN app_l2 LIKE '%社交%' OR app_l1='社交通讯' THEN '约炮社交'
                 ELSE '色情视频'
               END,
               reason=reason || ' [审计修正l1→色情成人]'
         WHERE risk_type='色情' AND app_l1!='色情成人'
    """)
    fixed += cur.rowcount
    print(f"色情 l1 修正: {cur.rowcount}")

    # 赌博 (用 Python 因为需要 app_name 拿到 hint)
    df = pd.read_sql("SELECT app_package,app_l1,app_l2,risk_type,reason FROM label_cache WHERE risk_type='赌博' AND app_l1!='棋牌赌博'", conn)
    src = pd.read_csv(BASE/"applist_tag_0522.csv").drop_duplicates("app_package")
    df = df.merge(src, on="app_package", how="left")
    df["app_name"] = df["app_name"].fillna("")
    def gdr(r):
        n = r.app_name or ""
        if "彩票" in n: return "彩票"
        if "博彩" in n or "竞彩" in n: return "体育博彩"
        return "真钱棋牌"
    upd = [(gdr(r), r.reason+" [审计修正l1→棋牌赌博]", r.app_package) for r in df.itertuples()]
    conn.executemany(
        "UPDATE label_cache SET app_l1='棋牌赌博', app_l2=?, reason=? WHERE app_package=?", upd)
    print(f"赌博 l1 修正: {len(upd)}")
    fixed += len(upd)

    # 区块链
    cur = conn.execute("""
        UPDATE label_cache
           SET app_l1='区块链加密',
               app_l2=CASE
                 WHEN app_l2 LIKE '%钱包%' THEN '钱包'
                 WHEN app_l2 LIKE '%交易%' THEN '交易所'
                 ELSE '钱包'
               END,
               reason=reason || ' [审计修正l1→区块链加密]'
         WHERE risk_type='区块链' AND app_l1!='区块链加密'
    """)
    print(f"区块链 l1 修正: {cur.rowcount}")
    fixed += cur.rowcount

    # 改机软件 l2 不规范 → 系统工具改为改机工具
    cur = conn.execute("""
        UPDATE label_cache
           SET app_l1='工具', app_l2='改机工具',
               reason=reason || ' [审计修正l2→改机工具]'
         WHERE risk_type='改机软件'
           AND app_l2 NOT IN ('改机工具','多开分身')
    """)
    print(f"改机软件 l2 修正: {cur.rowcount}")
    fixed += cur.rowcount

    conn.commit()
    conn.close()
    print(f"\n总修正: {fixed} 条")

if __name__ == "__main__":
    main()
