#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
EVAL_DIR="$ROOT_DIR/evals/comparative_mvp_roundtrip"
OUT_DIR="$EVAL_DIR/.roundtrip"

mkdir -p "$OUT_DIR"

cd "$ROOT_DIR"

go run ./cmd/guanvis preview "$EVAL_DIR" > "$OUT_DIR/preview_payload.json"
go run ./cmd/guanvis publish "$EVAL_DIR" > "$OUT_DIR/publish.log"

guancli card get p3bc51ab664e095ab2dff402 --profile default --raw > "$OUT_DIR/raw_normal.json"
guancli card get o360e50afb73bcc998353c13 --profile default --raw > "$OUT_DIR/raw_filter_based.json"
guancli card preview p3bc51ab664e095ab2dff402 --profile default --limit 50 -f json > "$OUT_DIR/preview_normal.json"
guancli card preview o360e50afb73bcc998353c13 --profile default --limit 50 -f json > "$OUT_DIR/preview_filter_based.json"

python3 - "$OUT_DIR" <<'PY'
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])

cases = [
    {
        "kind": "normal",
        "raw": out / "raw_normal.json",
        "preview": out / "preview_normal.json",
        "expected_aliases": [
            "月同比对比值",
            "季同比增长值",
            "年同比增长率",
            "上月末增长率",
            "上季度末增长值",
            "上年末对比值",
        ],
    },
    {
        "kind": "filter_based",
        "raw": out / "raw_filter_based.json",
        "preview": out / "preview_filter_based.json",
        "expected_aliases": [
            "日环比增长值",
            "周同比增长率",
            "默认年同比增长率",
            "年同比按周对比值",
            "自定义后移增长率",
        ],
    },
]

summary = {"cards": []}

for case in cases:
    raw_obj = json.loads(case["raw"].read_text())
    response = raw_obj.get("response") or raw_obj.get("data") or raw_obj
    zone_data = response["content"]["meta"]["chartMain"]["zoneData"]
    metrics = zone_data.get("metric", [])
    by_alias = {m.get("alias"): m for m in metrics if m.get("alias")}
    rows = json.loads(case["preview"].read_text())

    card_summary = {
        "kind": case["kind"],
        "cardId": response.get("cdId") or response.get("id"),
        "name": response.get("name"),
        "previewRows": len(rows),
        "aliases": {},
    }

    for alias in case["expected_aliases"]:
        metric = by_alias.get(alias)
        if metric is None:
            raise SystemExit(f"{case['kind']}: missing metric alias {alias}")
        if "formula" in metric:
            raise SystemExit(f"{case['kind']}: {alias} degraded to formula")
        adv_calc = metric.get("advCalc")
        if not adv_calc:
            raise SystemExit(f"{case['kind']}: {alias} missing advCalc")
        if adv_calc.get("advType") != "COMPARATIVE":
            raise SystemExit(f"{case['kind']}: {alias} advType is not COMPARATIVE")
        if not any(isinstance(row, dict) and row.get(alias) not in ("", None) for row in rows):
            raise SystemExit(f"{case['kind']}: {alias} has no non-empty preview value")
        card_summary["aliases"][alias] = adv_calc["advValue"]

    summary["cards"].append(card_summary)

(out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2))
PY
