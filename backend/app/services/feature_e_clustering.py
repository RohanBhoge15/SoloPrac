"""Feature E — Trajectory Clustering for Proactive Risk Alerts.

Approach:
1. Trajectory embedding: mean-pool medical_text vectors of last N versions +
   delta-vitals over sliding window
2. Clustering: HDBSCAN over patient population → cohort labels
3. Anomaly detection: Mahalanobis distance > d_thresh from cluster centroid → alert

This module holds the algorithm + a synthetic-data evaluation harness (used for
the IEEE paper's offline precision/recall on injected deteriorations). The live
production path — running this over real patients, persisting alerts, and
pushing them to the doctor dashboard over WebSocket — lives in
`app.services.risk_scan` and runs on an arq cron schedule.

Usage:
    # Offline evaluation (synthetic):
    from app.services.feature_e_clustering import run_full_evaluation
    report = run_full_evaluation(num_patients=100, inject_deteriorations=10)

    # Live scan (real data): see app.services.risk_scan.scan_doctor
"""

from __future__ import annotations

import json
import math
import logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

logger = logging.getLogger(__name__)


# ─── Trajectory Embedding ──────────────────────────────────

def compute_trajectory_embeddings(
    patient_vectors: Dict[str, List[np.ndarray]],  # patient_id → list of medical_text vectors
    vitals_history: Dict[str, List[Dict[str, float]]],  # patient_id → list of vitals dicts
    window_size: int = 5,
) -> np.ndarray:
    """Compute trajectory embeddings for a patient cohort.

    For each patient:
    1. Mean-pool the last `window_size` medical_text vectors
    2. Compute delta-vitals over sliding windows
    3. Concatenate to form a single trajectory embedding

    Args:
        patient_vectors: Map of patient_id → list of 768d medical_text vectors
                         (ordered by time, newest last)
        vitals_history: Map of patient_id → list of vitals dicts
                        Each dict: {"bp_systolic": ..., "bp_diastolic": ...,
                                    "heart_rate": ..., "weight": ...}
        window_size: Number of recent versions to consider.

    Returns:
        (N, D) numpy array where N = number of patients, D = trajectory dim
    """
    patient_ids = list(patient_vectors.keys())
    embeddings = []

    for pid in patient_ids:
        vecs = patient_vectors[pid]
        vitals = vitals_history.get(pid, [])

        if not vecs:
            embeddings.append(np.zeros(768 + 8))  # padded dim
            continue

        # 1. Mean-pool vectors
        recent_vecs = vecs[-window_size:] if len(vecs) >= window_size else vecs
        pooled = np.mean(recent_vecs, axis=0)  # (768,)

        # 2. Delta vitals over sliding windows
        delta_features = []
        if len(vitals) >= 2:
            recent_vitals = vitals[-window_size:] if len(vitals) >= window_size else vitals
            # Compute deltas between consecutive visits
            for j in range(1, len(recent_vitals)):
                prev = recent_vitals[j - 1]
                curr = recent_vitals[j]
                for key in ["bp_systolic", "bp_diastolic", "heart_rate", "weight"]:
                    p_val = prev.get(key, 0)
                    c_val = curr.get(key, 0)
                    delta_features.append(c_val - p_val)

            # Also add std dev as variability feature
            for key in ["bp_systolic", "bp_diastolic", "heart_rate", "weight"]:
                vals = [v.get(key, 0) for v in recent_vitals]
                delta_features.append(np.std(vals))
        else:
            delta_features = [0.0] * 8  # 4 deltas + 4 stds = 8

        delta_arr = np.array(delta_features, dtype=np.float32)
        embedding = np.concatenate([pooled, delta_arr])
        embeddings.append(embedding)

    return np.array(embeddings, dtype=np.float32)


# ─── HDBSCAN Clustering (NumPy implementation) ────────────

class HDBSCANClusterer:
    """Simplified HDBSCAN-like clustering using pairwise distance.

    In production, this would use the hdbscan package. Here we implement
    a simplified version using mutual reachability and hierarchical
    clustering for the paper simulation.
    """

    def __init__(self, min_cluster_size: int = 3, min_samples: int = 2):
        self.min_cluster_size = min_cluster_size
        self.min_samples = min_samples
        self.labels_: Optional[np.ndarray] = None
        self.cluster_centroids_: Optional[np.ndarray] = None
        self._data: Optional[np.ndarray] = None

    def fit(self, X: np.ndarray) -> np.ndarray:
        """Fit HDBSCAN clustering.

        Uses k-distance based noise detection + connected components
        for clustering.

        Args:
            X: (N, D) trajectory embeddings.

        Returns:
            Cluster labels (-1 = noise).
        """
        N = X.shape[0]
        self._data = X

        if N < self.min_cluster_size:
            self.labels_ = np.full(N, -1)
            self.cluster_centroids_ = np.empty((0, X.shape[1]))
            return self.labels_

        # Compute pairwise distances
        X_norm = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-10)
        dist = 1.0 - X_norm @ X_norm.T  # cosine distance

        # Compute k-distance (distance to kth nearest neighbor)
        sorted_dist = np.sort(dist, axis=1)
        k_dist = sorted_dist[:, min(self.min_samples, N - 1)]

        # Core distance threshold: median k-distance
        threshold = np.median(k_dist) * 1.5

        # Build connectivity graph (mutual reachability)
        # Core points have k-distance ≤ threshold
        core_mask = k_dist <= threshold
        core_indices = np.where(core_mask)[0]

        if len(core_indices) < self.min_cluster_size:
            self.labels_ = np.full(N, -1)
            self.cluster_centroids_ = np.empty((0, X.shape[1]))
            return self.labels_

        # Connected components among core points
        core_dist = dist[np.ix_(core_indices, core_indices)]
        connectivity = core_dist <= threshold

        # Label connected components
        labels = self._connected_components(connectivity)

        # Map back to full dataset
        self.labels_ = np.full(N, -1)
        for i, core_idx in enumerate(core_indices):
            self.labels_[core_idx] = labels[i]

        # Filter small clusters
        unique_labels = np.unique(self.labels_)
        for lbl in unique_labels:
            if lbl == -1:
                continue
            cluster_size = np.sum(self.labels_ == lbl)
            if cluster_size < self.min_cluster_size:
                self.labels_[self.labels_ == lbl] = -1

        # Compute centroids
        unique_labels = np.unique(self.labels_)
        unique_labels = unique_labels[unique_labels != -1]
        centroids = []
        for lbl in unique_labels:
            mask = self.labels_ == lbl
            centroids.append(np.mean(X[mask], axis=0))
        self.cluster_centroids_ = np.array(centroids) if centroids else np.empty((0, X.shape[1]))

        n_clusters = len(unique_labels)
        n_noise = np.sum(self.labels_ == -1)
        logger.info("HDBSCAN: %d clusters, %d noise points (%.1f%%)",
                     n_clusters, n_noise, n_noise / N * 100 if N > 0 else 0)

        return self.labels_

    def _connected_components(self, adj_matrix: np.ndarray) -> np.ndarray:
        """Label connected components in a binary adjacency matrix."""
        N = adj_matrix.shape[0]
        labels = np.full(N, -1)
        current_label = 0

        for i in range(N):
            if labels[i] != -1:
                continue
            # BFS
            queue = [i]
            labels[i] = current_label
            while queue:
                node = queue.pop(0)
                neighbors = np.where(adj_matrix[node])[0]
                for nb in neighbors:
                    if labels[nb] == -1:
                        labels[nb] = current_label
                        queue.append(nb)
            current_label += 1

        return labels

    def anomaly_score(
        self,
        point: np.ndarray,
        cluster_label: int,
    ) -> float:
        """Compute Mahalanobis-like anomaly score.

        Args:
            point: (D,) trajectory embedding to evaluate.
            cluster_label: Assigned cluster label.

        Returns:
            Distance score (higher = more anomalous).
        """
        if self._data is None or self.cluster_centroids_ is None:
            return 1.0

        if cluster_label == -1:
            return 2.0  # Already noise = anomalous

        # Find centroid for this cluster
        mask = self.labels_ == cluster_label
        if not np.any(mask):
            return 1.0

        cluster_points = self._data[mask]
        centroid = np.mean(cluster_points, axis=0)

        # Covariance (diagonal approximation for stability)
        cov = np.var(cluster_points, axis=0) + 1e-10

        # Mahalanobis distance
        diff = point - centroid
        dist = np.sqrt(np.sum(diff ** 2 / cov))

        return float(dist)


# ─── Anomaly Detection ─────────────────────────────────────

@dataclass
class RiskAlert:
    """A risk alert generated by Feature E anomaly detection."""
    patient_id: str
    kind: str  # "trajectory_drift" or "anomaly"
    severity: float  # 0.0 - 1.0
    cluster_label: int
    anomaly_score: float
    message: str
    detected_at: str
    previous_cluster: Optional[int] = None


class AnomalyDetector:
    """Detects trajectory drifts and anomalies using clustering."""

    def __init__(self, drift_threshold: float = 1.5):
        self.clusterer = HDBSCANClusterer()
        self.drift_threshold = drift_threshold

    def detect_anomalies(
        self,
        trajectory_embeddings: np.ndarray,  # (N, D)
        patient_ids: List[str],
        previous_labels: Optional[np.ndarray] = None,
    ) -> List[RiskAlert]:
        """Detect anomalies and drifts in patient trajectories.

        Args:
            trajectory_embeddings: (N, D) trajectory embeddings.
            patient_ids: Corresponding patient IDs.
            previous_labels: Labels from a previous time point for drift detection.

        Returns:
            List of RiskAlert objects.
        """
        N = len(patient_ids)
        alerts = []

        # Fit clustering
        labels = self.clusterer.fit(trajectory_embeddings)

        # Check each patient
        for i in range(N):
            pid = patient_ids[i]
            lbl = labels[i]
            score = self.clusterer.anomaly_score(trajectory_embeddings[i], lbl)

            # Anomaly: noise point with high distance
            if lbl == -1 and score > self.drift_threshold:
                alerts.append(RiskAlert(
                    patient_id=pid,
                    kind="anomaly",
                    severity=min(1.0, (score - self.drift_threshold) / 3.0),
                    cluster_label=lbl,
                    anomaly_score=round(score, 3),
                    message=f"Patient trajectory is anomalous — unusual pattern detected",
                    detected_at=datetime.now(timezone.utc).isoformat(),
                ))

            # Drift: patient changed cluster since last evaluation
            if previous_labels is not None and i < len(previous_labels):
                prev = previous_labels[i]
                if prev != -1 and lbl != -1 and prev != lbl:
                    alerts.append(RiskAlert(
                        patient_id=pid,
                        kind="trajectory_drift",
                        severity=min(1.0, abs(float(prev) - float(lbl)) / 5.0),
                        cluster_label=lbl,
                        anomaly_score=round(score, 3),
                        message=f"Patient moved from cluster {prev} to cluster {lbl}",
                        detected_at=datetime.now(timezone.utc).isoformat(),
                        previous_cluster=int(prev),
                    ))

        alerts.sort(key=lambda a: -a.severity)
        logger.info("Anomaly detection: %d alerts from %d patients", len(alerts), N)
        return alerts


# ─── Synthetic Data Generation ─────────────────────────────

def generate_synthetic_cohort(
    num_patients: int = 50,
    num_visits_per_patient: int = 6,
    embed_dim: int = 768,
    seed: int = 42,
    inject_deteriorations: int = 0,
) -> Tuple[Dict[str, List[np.ndarray]], Dict[str, List[Dict]], List[str]]:
    """Generate a synthetic patient cohort with trajectory data.

    Args:
        num_patients: Number of synthetic patients.
        num_visits_per_patient: Average visits per patient.
        embed_dim: Medical text embedding dimension.
        seed: Random seed.
        inject_deteriorations: Number of patients to inject worsening trends.

    Returns:
        (patient_vectors, vitals_history, patient_ids)
    """
    rng = np.random.RandomState(seed)
    patient_ids = [f"patient_{i}" for i in range(num_patients)]

    patient_vectors: Dict[str, List[np.ndarray]] = {}
    vitals_history: Dict[str, List[Dict]] = {}

    for i, pid in enumerate(patient_ids):
        n_visits = max(2, num_visits_per_patient + rng.randint(-2, 3))
        base_vector = rng.randn(embed_dim).astype(np.float32) * 0.5

        drift = np.zeros(embed_dim, dtype=np.float32)

        vecs = []
        vitals = []

        for v in range(n_visits):
            # Add random walk drift
            drift += rng.randn(embed_dim).astype(np.float32) * 0.05

            # For injected deteriorations, add positive drift in later visits
            if i < inject_deteriorations and v > n_visits // 2:
                drift += np.ones(embed_dim, dtype=np.float32) * 0.1

            vec = base_vector + drift + rng.randn(embed_dim).astype(np.float32) * 0.1
            vecs.append(vec)

            # Vitals with worsening trend for deteriorations
            bp_trend = 0
            hr_trend = 0
            if i < inject_deteriorations:
                bp_trend = v * 3  # BP increases over time
                hr_trend = v * 2  # HR increases over time

            vitals.append({
                "bp_systolic": 120 + bp_trend + rng.randint(-10, 10),
                "bp_diastolic": 80 + rng.randint(-5, 5),
                "heart_rate": 72 + hr_trend + rng.randint(-8, 8),
                "weight": 70 + rng.uniform(-2, 2),
            })

        patient_vectors[pid] = vecs
        vitals_history[pid] = vitals

    logger.info("Synthetic cohort: %d patients (avg %.1f visits, %d deteriorations)",
                 num_patients, num_visits_per_patient, inject_deteriorations)
    return patient_vectors, vitals_history, patient_ids


# ─── Evaluation ────────────────────────────────────────────

def evaluate_precision_at_injected(
    alerts: List[RiskAlert],
    injected_patient_ids: set,
) -> Dict[str, float]:
    """Evaluate precision of alerts on injected deteriorations.

    Args:
        alerts: Detected risk alerts.
        injected_patient_ids: Set of patient IDs with known deteriorations.

    Returns:
        dict with precision, recall, f1 for injected deteriorations.
    """
    if not alerts:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "total_alerts": 0}

    alert_patients = set(a.patient_id for a in alerts)
    true_positives = len(alert_patients & injected_patient_ids)
    false_positives = len(alert_patients - injected_patient_ids)
    false_negatives = len(injected_patient_ids - alert_patients)

    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
    recall = true_positives / len(injected_patient_ids) if injected_patient_ids else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    logger.info("Feature E eval: precision=%.3f recall=%.3f f1=%.3f", precision, recall, f1)

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "total_alerts": len(alerts),
    }


def run_full_evaluation(
    num_patients: int = 100,
    inject_deteriorations: int = 10,
    window_size: int = 5,
    seed: int = 42,
) -> Dict[str, Any]:
    """Run full Feature E evaluation pipeline.

    Generates synthetic cohort, clusters trajectories, detects anomalies,
    and evaluates precision on injected deteriorations.

    Args:
        num_patients: Total synthetic patients.
        inject_deteriorations: How many have worsening trends.
        window_size: Trajectory window.
        seed: Random seed.

    Returns:
        Evaluation report dict.
    """
    logger.info("Feature E eval: %d patients, %d deteriorations", num_patients, inject_deteriorations)

    # Generate data
    vectors, vitals, pids = generate_synthetic_cohort(
        num_patients=num_patients,
        inject_deteriorations=inject_deteriorations,
        seed=seed,
    )

    # Compute trajectory embeddings
    embeddings = compute_trajectory_embeddings(vectors, vitals, window_size)

    # Cluster and detect
    detector = AnomalyDetector()
    alerts = detector.detect_anomalies(embeddings, pids)

    # Evaluate
    injected_ids = set(pids[:inject_deteriorations])
    metrics = evaluate_precision_at_injected(alerts, injected_ids)

    # Cluster stats
    n_clusters = len(np.unique(detector.clusterer.labels_)) if detector.clusterer.labels_ is not None else 0
    n_noise = np.sum(detector.clusterer.labels_ == -1) if detector.clusterer.labels_ is not None else 0
    cluster_distribution = {}
    if detector.clusterer.labels_ is not None:
        unique, counts = np.unique(detector.clusterer.labels_, return_counts=True)
        cluster_distribution = {str(k): int(v) for k, v in zip(unique, counts)}

    return {
        "evaluation": metrics,
        "clustering": {
            "n_clusters": n_clusters,
            "noise_points": int(n_noise),
            "cluster_distribution": cluster_distribution,
        },
        "alerts": [
            {
                "patient_id": a.patient_id,
                "kind": a.kind,
                "severity": a.severity,
                "message": a.message,
            }
            for a in alerts
        ],
        "config": {
            "num_patients": num_patients,
            "inject_deteriorations": inject_deteriorations,
            "window_size": window_size,
        },
        "data_note": "All data is synthetic — no real patient information used",
        "security_note": "No real patient data used per UpdatedIdea MD Feature E spec",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }
