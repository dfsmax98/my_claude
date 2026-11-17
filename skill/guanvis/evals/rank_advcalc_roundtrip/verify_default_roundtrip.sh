#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
EVAL_DIR="$ROOT_DIR/evals/rank_advcalc_roundtrip"
OUT_DIR="$EVAL_DIR/.roundtrip"

mkdir -p "$OUT_DIR"

cd "$ROOT_DIR"

export GUANCLI_PROFILE=default

go run ./cmd/guanvis preview "$EVAL_DIR" > "$OUT_DIR/preview_payload.json"
go run ./cmd/guanvis publish "$EVAL_DIR" > "$OUT_DIR/publish.log"

guancli card get r3f01a02b03c04d05e06f07a --profile default --raw > "$OUT_DIR/raw_range.json"
guancli card get r4f01a02b03c04d05e06f08a --profile default --raw > "$OUT_DIR/raw_topn.json"
guancli card preview r3f01a02b03c04d05e06f07a --profile default --limit 50 -f json > "$OUT_DIR/preview_range.json"
guancli card preview r4f01a02b03c04d05e06f08a --profile default --limit 50 -f json > "$OUT_DIR/preview_topn.json"

python3 - "$OUT_DIR" <<'PY'
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])

cases = [
    {
        "kind": "range",
        "raw": out / "raw_range.json",
        "preview": out / "preview_range.json",
        "expected": {
            "按列RANK降序": {
                "calDimension": "COLUMN",
                "rankType": "RANK",
                "sorting": "desc",
                "tfdId": "",
                "topN": {"topType": "ALL", "count": 10, "calculationType": "COUNT"},
            },
            "按行DENSE升序": {
                "calDimension": "ROW",
                "rankType": "DENSE_RANK",
                "sorting": "asc",
                "tfdId": "",
                "topN": {"topType": "ALL", "count": 10, "calculationType": "COUNT"},
            },
            "地区组内ROW_NUMBER降序": {
                "calDimension": "FIELD",
                "rankType": "ROW_NUMBER",
                "sorting": "desc",
                "tfdId": "xe01f39825ccc428eaf67911",
                "topN": {"topType": "ALL", "count": 10, "calculationType": "COUNT"},
            },
            "类别维度项RANK升序": {
                "calDimension": "DIMENSION_ITEM",
                "rankType": "RANK",
                "sorting": "asc",
                "tfdId": "cece9879e99f545449909a82",
                "topN": {"topType": "ALL", "count": 10, "calculationType": "COUNT"},
            },
        },
    },
    {
        "kind": "topn",
        "raw": out / "raw_topn.json",
        "preview": out / "preview_topn.json",
        "expected": {
            "Top3适用小计": {
                "calDimension": "COLUMN",
                "rankType": "RANK",
                "sorting": "desc",
                "tfdId": "",
                "topN": {"topType": "CUSTOM_NUMBER", "count": 3, "calculationType": "COUNT", "applyToSubtotal": True},
            },
            "Top5不适用小计": {
                "calDimension": "DIMENSION_ITEM",
                "rankType": "DENSE_RANK",
                "sorting": "desc",
                "tfdId": "xe01f39825ccc428eaf67911",
                "topN": {"topType": "CUSTOM_NUMBER", "count": 5, "calculationType": "COUNT", "applyToSubtotal": False},
            },
        },
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

    for alias, expected in case["expected"].items():
        metric = by_alias.get(alias)
        if metric is None:
            raise SystemExit(f"{case['kind']}: missing metric alias {alias}")
        if "formula" in metric:
            raise SystemExit(f"{case['kind']}: {alias} degraded to formula")
        adv_calc = metric.get("advCalc")
        if not adv_calc:
            raise SystemExit(f"{case['kind']}: {alias} missing advCalc")
        if adv_calc.get("advType") != "RANK":
            raise SystemExit(f"{case['kind']}: {alias} advType is not RANK")
        adv_value = adv_calc.get("advValue") or {}
        if adv_value.get("advType") != "RANK":
            raise SystemExit(f"{case['kind']}: {alias} advValue.advType is not RANK")
        for key in ("calDimension", "rankType", "sorting", "tfdId"):
            if adv_value.get(key, "") != expected[key]:
                raise SystemExit(f"{case['kind']}: {alias} {key}={adv_value.get(key)!r}, want {expected[key]!r}")
        top_n = adv_value.get("topN") or {}
        for key, want in expected["topN"].items():
            if top_n.get(key) != want:
                raise SystemExit(f"{case['kind']}: {alias} topN.{key}={top_n.get(key)!r}, want {want!r}")
        if not any(isinstance(row, dict) and row.get(alias) not in ("", None) for row in rows):
            raise SystemExit(f"{case['kind']}: {alias} has no non-empty preview value")
        card_summary["aliases"][alias] = adv_value

    summary["cards"].append(card_summary)

(out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2))
PY
