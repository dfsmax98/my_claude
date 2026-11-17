# -*- coding: utf-8 -*-
"""生成脱敏资产摘要和本地私有文件明细。"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_AUDIO = PROJECT_ROOT / "data" / "raw" / "kesu_1000"
MODELS = PROJECT_ROOT / "models"
MANIFEST_DIR = PROJECT_ROOT / "data" / "manifests"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(root: Path, suffixes: set[str] | None = None) -> list[dict]:
    rows = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if suffixes is not None and path.suffix.lower() not in suffixes:
            continue
        rows.append(
            {
                "relative_path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return rows


def aggregate_sha256(rows: list[dict]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(f"{row['sha256']} {row['bytes']}\n".encode("ascii"))
    return digest.hexdigest()


def main() -> None:
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    audio_rows = inventory(
        RAW_AUDIO, {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".wma"}
    )
    model_rows = inventory(MODELS)

    private_path = MANIFEST_DIR / "kesu_1000_private.csv"
    with private_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["relative_path", "bytes", "sha256"])
        writer.writeheader()
        writer.writerows(audio_rows)

    model_manifest = MANIFEST_DIR / "model_assets.json"
    model_manifest.write_text(
        json.dumps({"files": model_rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summary = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "raw_audio": {
            "file_count": len(audio_rows),
            "total_bytes": sum(row["bytes"] for row in audio_rows),
            "aggregate_sha256": aggregate_sha256(audio_rows),
            "private_manifest": private_path.name,
        },
        "models": {
            "file_count": len(model_rows),
            "total_bytes": sum(row["bytes"] for row in model_rows),
            "aggregate_sha256": aggregate_sha256(model_rows),
            "manifest": model_manifest.name,
        },
    }
    (MANIFEST_DIR / "asset_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
