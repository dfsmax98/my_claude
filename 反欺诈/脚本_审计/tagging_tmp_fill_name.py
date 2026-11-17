# -*- coding: utf-8 -*-
"""回填 tagging_tmp/*.json 中缺失的 app_name（旧 bug 导致字段为空）"""
import json
from pathlib import Path
import pandas as pd

BASE = Path(r"d:\my_claude\反欺诈")
BATCH_DIR = BASE / "tagging_tmp"

df = pd.read_csv(BASE / "applist_tag_0522.csv")
name_map = dict(zip(df["app_package"], df["app_name"].fillna("")))
print(f"加载 {len(name_map)} 个 app_package -> app_name 映射")

files = sorted(BATCH_DIR.glob("applist_tag_0522_v2_*.json"))
print(f"待处理 {len(files)} 个批次文件")

n_files_changed = 0
n_records_filled = 0
for fp in files:
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  跳过 {fp.name}: {e}")
        continue

    changed = False
    for item in data:
        pkg = item.get("app_package", "")
        cur_name = item.get("app_name") or item.get("app_Name") or ""
        if not cur_name and pkg in name_map:
            new_name = name_map[pkg]
            if new_name:
                item.pop("app_Name", None)
                # 把 app_name 放到首位
                new_item = {"app_name": new_name}
                for k, v in item.items():
                    if k != "app_name":
                        new_item[k] = v
                item.clear()
                item.update(new_item)
                n_records_filled += 1
                changed = True
        elif "app_Name" in item and "app_name" not in item:
            # 只是统一字段名
            item["app_name"] = item.pop("app_Name")
            changed = True

    if changed:
        fp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        n_files_changed += 1

print(f"\n完成: 修改 {n_files_changed} 个文件，回填 {n_records_filled} 条 app_name")
