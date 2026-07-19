"""Feature C Evaluation — Recall@K on held-out CheXpert + wound pairs.

Evaluates the trained linear projector W on held-out image-text pairs.

Usage:
    from app.services.feature_c_eval import evaluate_projector, run_qualitative_panel
    eval_report = evaluate_projector(W, test_images, test_texts)
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


def evaluate_projector(
    W: np.ndarray,
    image_embeddings: np.ndarray,
    text_embeddings: np.ndarray,
    k_values: List[int] = [1, 5, 10],
) -> Dict[str, Any]:
    """Evaluate the linear projector on held-out pairs.

    Args:
        W: (1024, 512) trained weight matrix.
        image_embeddings: (N, 512) NV-CLIP image embeddings.
        text_embeddings: (N, 1024) BGE-M3 text embeddings.
        k_values: K values for Recall@K.

    Returns:
        Evaluation report dict.
    """
    N = image_embeddings.shape[0]
    assert N == text_embeddings.shape[0], "Mismatched pair count"

    # Project images to text space
    projected = image_embeddings @ W.T  # (N, 1024)

    # Normalize
    proj_norm = projected / (np.linalg.norm(projected, axis=1, keepdims=True) + 1e-10)
    txt_norm = text_embeddings / (np.linalg.norm(text_embeddings, axis=1, keepdims=True) + 1e-10)

    # Similarity matrix
    sim = proj_norm @ txt_norm.T  # (N, N)

    # Compute Recall@K
    results = {}
    for k in k_values:
        hits = 0
        for i in range(N):
            # Top-k excluding self
            top_k = np.argsort(-sim[i])[:k + 1]
            if i in top_k[:k]:
                hits += 1
        recall = hits / N
        results[f"recall_at_{k}"] = round(recall, 4)

    # Also compute text-to-image recall
    for k in k_values:
        hits = 0
        for i in range(N):
            top_k = np.argsort(-sim[:, i])[:k + 1]
            if i in top_k[:k]:
                hits += 1
        recall = hits / N
        results[f"recall_at_{k}_t2i"] = round(recall, 4)

    # Mean Reciprocal Rank
    mrr = 0
    for i in range(N):
        rank = np.where(np.argsort(-sim[i]) == i)[0][0] + 1
        mrr += 1.0 / rank
    results["mrr"] = round(mrr / N, 4)

    # Median rank
    ranks = [np.where(np.argsort(-sim[i]) == i)[0][0] + 1 for i in range(N)]
    results["median_rank"] = int(np.median(ranks))

    logger.info(
        "Feature C eval: R@1=%.4f R@5=%.4f R@10=%.4f MRR=%.4f MedianRank=%d",
        results.get("recall_at_1", 0), results.get("recall_at_5", 0),
        results.get("recall_at_10", 0), results["mrr"], results["median_rank"],
    )

    return {
        "metrics": results,
        "num_pairs": N,
        "projector_shape": W.shape,
    }


def run_qualitative_panel(
    W: np.ndarray,
    image_embeddings: np.ndarray,
    text_embeddings: np.ndarray,
    clinical_cases: List[Dict[str, Any]],
    panel_size: int = 3,
) -> Dict[str, Any]:
    """Run a qualitative clinical panel evaluation.

    This simulates the 20-case qualitative panel mentioned in UpdatedIdea.md.
    In production, this would be replaced by actual clinician ratings.

    Args:
        W: Trained projector.
        image_embeddings: Test image embeddings.
        text_embeddings: Test text embeddings.
        clinical_cases: List of case descriptions for panelists.
        panel_size: Number of simulated panelists.

    Returns:
        Qualitative evaluation report.
    """
    projected = image_embeddings @ W.T
    proj_norm = projected / (np.linalg.norm(projected, axis=1, keepdims=True) + 1e-10)
    txt_norm = text_embeddings / (np.linalg.norm(text_embeddings, axis=1, keepdims=True) + 1e-10)
    sim = proj_norm @ txt_norm.T

    panel_ratings = []
    for _ in range(panel_size):
        for i, case in enumerate(clinical_cases[:min(20, len(clinical_cases))]):
            # Simulated clinician rating based on similarity
            rank = np.where(np.argsort(-sim[i]) == i)[0][0] + 1
            if rank == 1:
                rating = 5
            elif rank <= 3:
                rating = 4
            elif rank <= 5:
                rating = 3
            elif rank <= 10:
                rating = 2
            else:
                rating = 1

            panel_ratings.append({
                "case_id": i,
                "case_description": case.get("description", f"Case {i}"),
                "similarity_rank": int(rank),
                "clinical_relevance": rating,
            })

    # Aggregate
    ratings = [r["clinical_relevance"] for r in panel_ratings]
    mean_rating = np.mean(ratings)
    top_box = np.sum(np.array(ratings) >= 4) / len(ratings) * 100

    return {
        "panel_size": panel_size,
        "cases_evaluated": min(20, len(clinical_cases)),
        "mean_clinical_relevance": round(float(mean_rating), 2),
        "top_box_percentage": round(float(top_box), 1),
        "ratings_by_rank": {},
        "note": "Simulated qualitative panel — replace with real clinician ratings for paper",
    }