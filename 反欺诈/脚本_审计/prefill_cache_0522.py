# -*- coding: utf-8 -*-
"""将 applist_tag_v2.csv 的已有结果预填入 applist_tag_0522_v2 的 SQLite 缓存"""
import sqlite3
from pathlib import Path
import pandas as pd

BASE     = Path(r"d:\my_claude\反欺诈")
cache_db = BASE / "applist_label_cache_applist_tag_0522_v2.sqlite"

# 建表（与 run_label_v2.py 相同结构）
conn = sqlite3.connect(str(cache_db))
conn.execute("""
    CREATE TABLE IF NOT EXISTS label_cache (
        app_package TEXT PRIMARY KEY,
        app_l1 TEXT, app_l2 TEXT, risk_type TEXT,
        confidence REAL, reason TEXT, updated_at TEXT
    )
""")
conn.commit()

# 从 v2 结果写入缓存
v2 = pd.read_csv(BASE / "applist_tag_v2.csv", encoding="utf-8-sig")
v2.columns = ["app_Name", "app_package", "app_l1", "app_l2", "risk_type", "confidence", "reason"]
v2 = v2.dropna(subset=["app_package"])

rows = v2[["app_package", "app_l1", "app_l2", "risk_type", "confidence", "reason"]].to_dict("records")
conn.executemany(
    """INSERT OR REPLACE INTO label_cache
       (app_package,app_l1,app_l2,risk_type,confidence,reason,updated_at)
       VALUES (?,?,?,?,?,?,datetime('now'))""",
    [(r["app_package"], r["app_l1"], r["app_l2"], r["risk_type"],
      r["confidence"], r["reason"]) for r in rows],
)
conn.commit()

count = conn.execute("SELECT COUNT(*) FROM label_cache").fetchone()[0]
print(f"缓存预填完成：{count} 条")
conn.close()
