"""客户主模板的N:N影子聚类。"""
from __future__ import annotations

from collections import defaultdict

import numpy as np

from common.gang_cluster import cluster_embeddings


def customer_centroids(store) -> tuple[list[str], np.ndarray]:
    grouped = defaultdict(list)
    for template in store.list("customer_templates"):
        if template.get("status") != "active":
            continue
        grouped[template["customer_id"]].append(
            store.load_vector(template["vector_path"])
        )
    customer_ids = sorted(grouped)
    centroids = []
    for customer_id in customer_ids:
        centroid = np.mean(grouped[customer_id], axis=0)
        norm = float(np.linalg.norm(centroid))
        centroids.append(centroid / max(norm, 1e-12))
    if not centroids:
        return customer_ids, np.zeros((0, 192), dtype=np.float32)
    return customer_ids, np.asarray(centroids, dtype=np.float32)


def run_customer_clustering(store, config: dict) -> dict:
    customer_ids, vectors = customer_centroids(store)
    settings = config["gang_cluster"]
    if len(vectors) < int(settings["min_cluster_size"]):
        return {
            "customer_count": len(customer_ids),
            "edge_count": 0,
            "clusters": [],
            "threshold": float(settings["threshold"]),
            "topk": int(settings["topk"]),
            "shadow_only": bool(settings["shadow_only"]),
        }
    result = cluster_embeddings(
        vectors,
        float(settings["threshold"]),
        int(settings["topk"]),
        int(settings["min_cluster_size"]),
    )
    clusters = [
        {
            "cluster_id": f"cluster_{index + 1:04d}",
            "member_count": len(indices),
            "customer_ids": [customer_ids[item] for item in indices],
            "status": "pending_review",
        }
        for index, indices in enumerate(result["clusters"])
    ]
    return {
        "customer_count": len(customer_ids),
        "edge_count": len(result["edges"]),
        "clusters": clusters,
        "threshold": float(settings["threshold"]),
        "topk": int(settings["topk"]),
        "shadow_only": bool(settings["shadow_only"]),
    }
