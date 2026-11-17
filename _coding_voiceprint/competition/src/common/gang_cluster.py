# -*- coding: utf-8 -*-
"""跨客户声纹图聚类与带真值评估。"""
from collections import Counter
import warnings

import numpy as np


def cosine_matrix(embeddings):
    vectors = np.asarray(embeddings, dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    vectors = vectors / np.maximum(norms, 1e-12)
    return vectors @ vectors.T


def mutual_knn_edges(matrix, threshold, topk):
    """返回达到阈值且互为Top-K的无向边列表。"""
    matrix = np.asarray(matrix, dtype=np.float32)
    count = len(matrix)
    if count < 2:
        return []
    work = matrix.copy()
    np.fill_diagonal(work, -np.inf)
    k = min(max(int(topk), 1), count - 1)
    neighbors = np.argpartition(-work, kth=k - 1, axis=1)[:, :k]
    neighbor_sets = [set(row.tolist()) for row in neighbors]
    edges = []
    for left in range(count):
        for right in neighbor_sets[left]:
            if right <= left or left not in neighbor_sets[right]:
                continue
            score = float(matrix[left, right])
            if score >= threshold:
                edges.append((left, right, score))
    return edges


def connected_components(count, edges):
    adjacency = [[] for _ in range(count)]
    for left, right, _ in edges:
        adjacency[left].append(right)
        adjacency[right].append(left)
    seen = np.zeros(count, dtype=bool)
    components = []
    for start in range(count):
        if seen[start]:
            continue
        stack = [start]
        seen[start] = True
        component = []
        while stack:
            node = stack.pop()
            component.append(node)
            for neighbor in adjacency[node]:
                if not seen[neighbor]:
                    seen[neighbor] = True
                    stack.append(neighbor)
        components.append(sorted(component))
    return components


def cluster_embeddings(embeddings, threshold, topk, min_cluster_size=3):
    matrix = cosine_matrix(embeddings)
    edges = mutual_knn_edges(matrix, threshold, topk)
    components = connected_components(len(matrix), edges)
    clusters = [component for component in components
                if len(component) >= min_cluster_size]
    return {"matrix": matrix, "edges": edges, "clusters": clusters,
            "components": components}


def _predicted_labels(count, clusters):
    labels = [f"singleton_{index}" for index in range(count)]
    for cluster_index, cluster in enumerate(clusters):
        for node in cluster:
            labels[node] = f"cluster_{cluster_index}"
    return np.asarray(labels)


def evaluate_clusters(true_labels, clusters, gang_prefix="gang_"):
    from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

    true_labels = np.asarray(true_labels).astype(str)
    count = len(true_labels)
    predicted = _predicted_labels(count, clusters)
    row, col = np.triu_indices(count, k=1)
    true_same = true_labels[row] == true_labels[col]
    pred_same = predicted[row] == predicted[col]
    true_positive = int((true_same & pred_same).sum())
    false_positive = int((~true_same & pred_same).sum())
    false_negative = int((true_same & ~pred_same).sum())
    precision = (true_positive / (true_positive + false_positive)
                 if true_positive + false_positive else 1.0)
    recall = (true_positive / (true_positive + false_negative)
              if true_positive + false_negative else 1.0)
    f1 = (2 * precision * recall / (precision + recall)
          if precision + recall else 0.0)

    total_cluster_nodes = sum(len(cluster) for cluster in clusters)
    weighted_purity = 1.0
    false_clusters = 0
    max_cluster_size = 0
    if total_cluster_nodes:
        purity_sum = 0
        for cluster in clusters:
            labels = Counter(true_labels[cluster].tolist())
            dominant = labels.most_common(1)[0][1]
            purity = dominant / len(cluster)
            purity_sum += dominant
            max_cluster_size = max(max_cluster_size, len(cluster))
            dominant_label = labels.most_common(1)[0][0]
            if purity < 0.8 or not dominant_label.startswith(gang_prefix):
                false_clusters += 1
        weighted_purity = purity_sum / total_cluster_nodes

    gangs = sorted({label for label in true_labels if label.startswith(gang_prefix)})
    detected = 0
    fragmented = 0
    for gang in gangs:
        members = set(np.flatnonzero(true_labels == gang).tolist())
        overlaps = []
        for cluster in clusters:
            overlap = len(members & set(cluster))
            if overlap:
                purity = overlap / len(cluster)
                coverage = overlap / len(members)
                overlaps.append((coverage, purity))
        if any(coverage >= 0.8 and purity >= 0.8
               for coverage, purity in overlaps):
            detected += 1
        if len(overlaps) > 1:
            fragmented += 1

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message="The number of unique classes is greater than 50%")
        ari = adjusted_rand_score(true_labels, predicted)
        nmi = normalized_mutual_info_score(true_labels, predicted)

    return {
        "pair_precision": float(precision),
        "pair_recall": float(recall),
        "pair_f1": float(f1),
        "true_positive_pairs": true_positive,
        "false_positive_pairs": false_positive,
        "false_negative_pairs": false_negative,
        "cluster_count": len(clusters),
        "clustered_nodes": total_cluster_nodes,
        "weighted_purity": float(weighted_purity),
        "gang_count": len(gangs),
        "gang_detected": detected,
        "gang_detection_recall": float(detected / len(gangs)) if gangs else 1.0,
        "fragmented_gangs": fragmented,
        "false_clusters": false_clusters,
        "max_cluster_size": max_cluster_size,
        "ari": float(ari),
        "nmi": float(nmi),
    }
