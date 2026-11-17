# -*- coding: utf-8 -*-
"""准备 v2 客户声纹后端优化输入。

从新角色模型客户 embedding 生成评估矩阵，并从外部正式库按身份隔离切分
PLDA 训练集和 AS-norm cohort。该脚本只生成版本化实验输入，不覆盖原始库。
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np


MODULE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_V2_EMBEDDINGS = (
    MODULE_ROOT / "data" / "recent_voiceprints_10k_role_text_v2"
    / "customer_embeddings_v2.npz"
)
DEFAULT_COHORT_BATCHES = (
    MODULE_ROOT / "data" / "full_customer_voiceprint_library_20250101_v1"
    / "embedding_batches"
)
DEFAULT_OUTPUT = (
    MODULE_ROOT / "reports" / "recent_voiceprints_nxn_v2"
    / "backend_optimization" / "plda_quality" / "inputs"
)


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def atomic_save_npz(path: Path, **arrays: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.stem + ".tmp.npz")
    np.savez_compressed(temp, **arrays)
    os.replace(temp, path)


def normalize_rows(values: np.ndarray) -> np.ndarray:
    vectors = np.asarray(values, dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.maximum(norms, 1e-12)


def load_external_records(batch_dir: Path, excluded_eval_identities: set[str]) -> tuple[list[dict], dict]:
    records = []
    role_versions = Counter()
    overlap_removed = 0
    formal_total = 0
    for path in sorted(batch_dir.glob("*.npz")):
        data = np.load(path, allow_pickle=False)
        for metadata_text, embedding in zip(data["metadata"].astype(str), data["embeddings"]):
            metadata = json.loads(metadata_text)
            if not metadata.get("formal_index_eligible"):
                continue
            formal_total += 1
            identity = str(metadata["identity_sha256"])
            if identity in excluded_eval_identities:
                overlap_removed += 1
                continue
            role_versions[str(metadata.get("role_model_version") or "unknown")] += 1
            records.append(
                {
                    "identity": identity,
                    "embedding": np.asarray(embedding, dtype=np.float32),
                    "source": str(path.name),
                }
            )
    stats = {
        "source_batch_count": len(list(batch_dir.glob("*.npz"))),
        "formal_total": formal_total,
        "overlap_removed": overlap_removed,
        "role_model_versions": dict(role_versions),
    }
    return records, stats


def split_external_records(
    records: list[dict],
    max_plda_records_per_identity: int,
) -> tuple[list[dict], list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        grouped[record["identity"]].append(record)

    plda_train = []
    cohort = []
    for identity in sorted(grouped):
        group = grouped[identity]
        if len(group) >= 2:
            plda_train.extend(group[:max_plda_records_per_identity])
        else:
            cohort.extend(group)
    return plda_train, cohort


def run(args: argparse.Namespace) -> dict:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    v2_data = np.load(Path(args.v2_embeddings), allow_pickle=False)
    recording_ids = v2_data["recording_ids"].astype(str)
    identities = v2_data["identity_sha256"].astype(str)
    embeddings = normalize_rows(v2_data["embeddings"])
    eval_identity_set = set(identities.tolist())

    matrix_path = output_dir / "customer_embeddings_v2_matrix.npz"
    atomic_save_npz(
        matrix_path,
        recording_ids=recording_ids,
        identities=identities,
        embeddings=embeddings.astype(np.float32),
    )

    external_records, external_stats = load_external_records(
        Path(args.cohort_batches), eval_identity_set
    )
    plda_records, cohort_records = split_external_records(
        external_records, args.max_plda_records_per_identity
    )

    plda_path = output_dir / "external_plda_train_identity_disjoint.npz"
    atomic_save_npz(
        plda_path,
        embeddings=normalize_rows(np.asarray([row["embedding"] for row in plda_records])),
        identity_sha256=np.asarray([row["identity"] for row in plda_records]),
        needs_review=np.zeros(len(plda_records), dtype=bool),
    )

    cohort_path = output_dir / "external_asnorm_cohort_identity_disjoint.npz"
    atomic_save_npz(
        cohort_path,
        embeddings=normalize_rows(np.asarray([row["embedding"] for row in cohort_records])),
        identities=np.asarray([row["identity"] for row in cohort_records]),
        role_model_versions_json=np.asarray(
            [json.dumps(external_stats["role_model_versions"], ensure_ascii=False)]
        ),
        overlap_removed=np.asarray([external_stats["overlap_removed"]], dtype=np.int32),
    )

    plda_identities = [row["identity"] for row in plda_records]
    cohort_identities = [row["identity"] for row in cohort_records]
    summary = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "inputs": {
            "v2_embeddings": str(Path(args.v2_embeddings)),
            "cohort_batches": str(Path(args.cohort_batches)),
        },
        "outputs": {
            "matrix": str(matrix_path),
            "plda_train": str(plda_path),
            "asnorm_cohort": str(cohort_path),
        },
        "evaluation": {
            "record_count": int(len(recording_ids)),
            "identity_count": int(len(eval_identity_set)),
        },
        "external_source": external_stats,
        "plda_training": {
            "record_count": int(len(plda_records)),
            "identity_count": int(len(set(plda_identities))),
            "identity_record_distribution": dict(Counter(Counter(plda_identities).values())),
        },
        "asnorm_cohort": {
            "record_count": int(len(cohort_records)),
            "identity_count": int(len(set(cohort_identities))),
        },
        "identity_overlap_checks": {
            "eval_vs_plda": len(eval_identity_set & set(plda_identities)),
            "eval_vs_cohort": len(eval_identity_set & set(cohort_identities)),
            "plda_vs_cohort": len(set(plda_identities) & set(cohort_identities)),
        },
        "note": "PLDA 训练集和 AS-norm cohort 均来自外部正式库，并按身份与 v2 评估集隔离；PLDA 训练身份也从 cohort 中剔除。",
    }
    atomic_write_json(output_dir / "backend_input_summary.json", summary)
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="准备 v2 声纹后端优化输入")
    parser.add_argument("--v2-embeddings", default=str(DEFAULT_V2_EMBEDDINGS))
    parser.add_argument("--cohort-batches", default=str(DEFAULT_COHORT_BATCHES))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--max-plda-records-per-identity", type=int, default=20)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    summary = run(parse_args(argv))
    print(
        "DONE "
        f"MATRIX_RECORDS={summary['evaluation']['record_count']} "
        f"PLDA_RECORDS={summary['plda_training']['record_count']} "
        f"COHORT_RECORDS={summary['asnorm_cohort']['record_count']}"
    )


if __name__ == "__main__":
    main()
