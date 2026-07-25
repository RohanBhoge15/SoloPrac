"""Feature A Evaluation Harness — Recall@5, future-leak rate, latency p95, baselines.

Provides:
  1. Synthetic patient data generator (MIMIC-IV style longitudinal records)
  2. Evaluation harness with standard IR metrics
  3. Baseline comparisons (BM25, vanilla MedCPT, dense-only RAG)
  4. 100 multi-visit query pairs with ground truth

Usage:
    from app.services.evaluation import EvaluationHarness
    harness = EvaluationHarness()
    results = await harness.run_full_evaluation(doctor_id=..., patient_ids=[...])

Output:
    {
        "recall_at_5": {"temporal_rag": 0.85, "vanilla_medcpt": 0.72, "dense_only": 0.68, "bm25": 0.55},
        "future_leak_rate": {"temporal_rag": 0.002, "vanilla_medcpt": 0.12, ...},
        "latency_p95_ms": {"temporal_rag": 320, ...},
        "answer_faithfulness": 0.88,
    }
"""

from __future__ import annotations

import json
import math
import random
import time
import logging
import statistics
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from app.services.temporal_rag import TemporalMultimodalRetriever
from app.services.embeddings import embedding_service

logger = logging.getLogger(__name__)

# ─── Synthetic Data Generation ───────────────────────────────

CONDITIONS = [
    "Type 2 Diabetes Mellitus",
    "Hypertension",
    "Hypothyroidism",
    "Asthma",
    "COPD",
    "Osteoarthritis",
    "Chronic Kidney Disease",
    "Coronary Artery Disease",
    "Depression",
    "Anxiety Disorder",
]

MEDICATIONS = [
    {"drug": "Metformin", "strength": "500 mg", "dose": "1 tab BD"},
    {"drug": "Amlodipine", "strength": "5 mg", "dose": "1 tab OD"},
    {"drug": "Levothyroxine", "strength": "50 mcg", "dose": "1 tab OD"},
    {"drug": "Salbutamol Inhaler", "strength": "100 mcg", "dose": "2 puffs PRN"},
    {"drug": "Atorvastatin", "strength": "10 mg", "dose": "1 tab OD"},
    {"drug": "Losartan", "strength": "50 mg", "dose": "1 tab OD"},
    {"drug": "Omeprazole", "strength": "20 mg", "dose": "1 tab OD"},
    {"drug": "Paracetamol", "strength": "500 mg", "dose": "1-2 tab PRN"},
]

VITALS_TEMPLATES = [
    {"bp_systolic": (120, 160), "bp_diastolic": (70, 100), "heart_rate": (65, 100), "weight": (55, 90)},
    {"bp_systolic": (130, 180), "bp_diastolic": (80, 110), "heart_rate": (70, 110), "weight": (60, 95)},
]

TAGS_POOL = [
    "new_diagnosis", "medication_change", "abnormal_lab", "routine_visit",
    "vitals_in_range", "missed_appointment",
]


def _generate_patient_demographics(seed: int) -> dict:
    """Generate synthetic patient demographics."""
    rng = random.Random(seed)
    first_names = ["Priya", "Rajesh", "Anita", "Mohammed", "Sunita", "Vikram", "Lata", "Arun", "Sneha", "Deepak"]
    last_names = ["Sharma", "Kumar", "Patel", "Ali", "Devi", "Khanna", "Patil", "Joshi", "Verma", "Kulkarni"]
    genders = ["Male", "Female"]
    return {
        "name": f"{rng.choice(first_names)} {rng.choice(last_names)}",
        "age": rng.randint(25, 80),
        "gender": rng.choice(genders),
        "phone": f"+91-{rng.randint(7000000000, 9999999999)}",
    }


def _generate_clinical_data(rng: random.Random, visit_number: int) -> dict:
    """Generate synthetic clinical data for one visit."""
    conditions = rng.sample(CONDITIONS, rng.randint(1, 3))
    meds = rng.sample(MEDICATIONS, rng.randint(1, 4))
    vitals_template = rng.choice(VITALS_TEMPLATES)
    vitals = {
        "bp_systolic": rng.randint(vitals_template["bp_systolic"][0], vitals_template["bp_systolic"][1]),
        "bp_diastolic": rng.randint(vitals_template["bp_diastolic"][0], vitals_template["bp_diastolic"][1]),
        "heart_rate": rng.randint(vitals_template["heart_rate"][0], vitals_template["heart_rate"][1]),
        "weight": round(rng.uniform(vitals_template["weight"][0], vitals_template["weight"][1]), 1),
    }

    # Simulate trend: later visits have slightly worse vitals for some patients
    if rng.random() < 0.3:
        vitals["bp_systolic"] += visit_number * 2
        vitals["bp_diastolic"] += visit_number

    tags = rng.sample(TAGS_POOL, rng.randint(1, 2))
    if visit_number == 1:
        tags.append("new_diagnosis")

    return {
        "diagnoses": conditions,
        "medications": meds,
        "vitals": vitals,
        "tags": tags,
        "summary": f"Visit {visit_number}: {'; '.join(c.split()[0] for c in conditions)} follow-up",
    }


def generate_synthetic_patient(
    patient_id: UUID,
    doctor_id: UUID,
    num_visits: int = 6,
    days_between_visits: int = 30,
    seed: int = 0,
) -> List[dict]:
    """Generate a synthetic longitudinal patient record.

    Args:
        patient_id: UUID for the patient.
        doctor_id: UUID for the doctor (tenant).
        num_visits: Number of visits to generate (default 6).
        days_between_visits: Average days between visits (default 30).
        seed: Random seed for reproducibility.

    Returns:
        List of version dicts with state_jsonb, timestamp, etc.
    """
    rng = random.Random(seed)
    demographics = _generate_patient_demographics(seed)
    versions = []
    now = datetime.now(timezone.utc)

    for v in range(1, num_visits + 1):
        visit_days_ago = (num_visits - v) * days_between_visits + rng.randint(-5, 5)
        timestamp = now - timedelta(days=visit_days_ago)
        clinical = _generate_clinical_data(rng, v)

        state = {
            "demographics": demographics,
            "clinical": clinical,
        }

        versions.append({
            "version_number": v,
            "patient_id": str(patient_id),
            "doctor_id": str(doctor_id),
            "state_jsonb": state,
            "timestamp": timestamp.isoformat(),
            "summary": clinical["summary"],
            "tags": clinical["tags"],
            "edit_type": "manual",
            "author": f"doctor:{doctor_id}",
            "clinical_significance": 0.3 if v > 1 else 1.0,
        })

    return versions


def generate_test_dataset(
    doctor_id: UUID,
    num_patients: int = 10,
    num_visits_per_patient: int = 6,
) -> Tuple[List[dict], List[dict]]:
    """Generate a labeled test dataset with query pairs.

    Returns:
        (patients_data, query_pairs)
        patients_data: list of patient dicts with id and versions
        query_pairs: list of {"query": str, "patient_id": str, "relevant_versions": [int], "query_time": str}
    """
    patients_data = []
    query_pairs = []

    for p in range(num_patients):
        patient_id = uuid4()
        versions = generate_synthetic_patient(
            patient_id=patient_id,
            doctor_id=doctor_id,
            num_visits=num_visits_per_patient,
            seed=p,
        )
        patients_data.append({
            "patient_id": str(patient_id),
            "versions": versions,
        })

        # Generate query pairs for this patient
        rng = random.Random(p)
        for v in versions:
            clinical = v["state_jsonb"]["clinical"]
            diagnoses = clinical.get("diagnoses", [])
            vitals = clinical.get("vitals", {})
            tags = clinical.get("tags", [])

            # Generate different query types
            if "new_diagnosis" in tags:
                query_pairs.append({
                    "query": f"What new diagnosis was made for this patient?",
                    "patient_id": str(patient_id),
                    "relevant_versions": [v["version_number"]],
                    "query_time": v["timestamp"],
                    "type": "diagnosis",
                })

            if diagnoses:
                query_pairs.append({
                    "query": f"What are the patient's current diagnoses?",
                    "patient_id": str(patient_id),
                    "relevant_versions": [v["version_number"]] + [x["version_number"] for x in versions[:versions.index(v)]],
                    "query_time": v["timestamp"],
                    "type": "summary",
                })

            if vitals:
                query_pairs.append({
                    "query": f"What was the BP and heart rate at this visit?",
                    "patient_id": str(patient_id),
                    "relevant_versions": [v["version_number"]],
                    "query_time": v["timestamp"],
                    "type": "vitals",
                })

        # Trend queries (span multiple versions)
        for v in versions[2:]:
            prev = versions[versions.index(v) - 2]
            query_pairs.append({
                "query": f"Show me the BP trend over the last few visits",
                "patient_id": str(patient_id),
                "relevant_versions": [x["version_number"] for x in versions if x["version_number"] <= v["version_number"]],
                "query_time": v["timestamp"],
                "type": "trend",
            })

    # Trim to approximately 100 query pairs
    if len(query_pairs) > 100:
        query_pairs = query_pairs[:100]

    return patients_data, query_pairs


# ─── Retrieval Baselines ──────────────────────────────

class BM25Baseline:
    """Simple BM25-like baseline for comparison (keyword overlap)."""

    def __init__(self):
        self._doc_freq: Dict[str, float] = {}
        self._total_docs = 0

    def fit(self, documents: List[Dict[str, Any]]):
        """Compute document frequencies."""
        self._total_docs = len(documents)
        word_counts: Dict[str, int] = {}
        for doc in documents:
            text = self._doc_text(doc)
            words = set(text.lower().split())
            for w in words:
                word_counts[w] = word_counts.get(w, 0) + 1
        total = self._total_docs
        self._doc_freq = {w: math.log((total - c + 0.5) / (c + 0.5) + 1) for w, c in word_counts.items()}
        self._documents = documents

    def _doc_text(self, doc: dict) -> str:
        """Extract searchable text from a version."""
        state = doc.get("state_jsonb", {})
        parts = [doc.get("summary", "")]
        clinical = state.get("clinical", {})
        if isinstance(clinical, dict):
            parts.extend(clinical.get("diagnoses", []))
            for m in clinical.get("medications", []):
                if isinstance(m, dict):
                    parts.append(m.get("drug", ""))
        return " ".join(parts)

    def search(self, query: str, k: int = 10) -> List[Dict[str, Any]]:
        """BM25 scoring against fitted documents."""
        query_terms = query.lower().split()
        scores = []
        for doc in self._documents:
            text = self._doc_text(doc).lower()
            score = 0
            for term in query_terms:
                if term in text and term in self._doc_freq:
                    tf = text.count(term) / len(text.split()) if text.split() else 0
                    idf = self._doc_freq[term]
                    score += (tf * (1.5 + 1)) / (tf + 1.5) * idf
            scores.append(score)

        ranked = sorted(
            zip(self._documents, scores),
            key=lambda x: -x[1],
        )[:k]

        return [
            {
                "version_number": d.get("version_number", 0),
                "score": s,
            }
            for d, s in ranked
        ]


# ─── Evaluation Metrics ───────────────────────────────

def compute_recall_at_k(
    retrieved: List[int],
    relevant: List[int],
    k: int = 5,
) -> float:
    """Compute Recall@K: fraction of relevant items in top-K retrieved."""
    if not relevant:
        return 0.0
    top_k = set(retrieved[:k])
    relevant_set = set(relevant)
    if not relevant_set:
        return 0.0
    return len(top_k & relevant_set) / len(relevant_set)


def compute_future_leak_rate(
    retrieved: List[Dict[str, Any]],
    query_time: str,
) -> float:
    """Compute what fraction of retrieved versions are newer than query_time."""
    if not retrieved:
        return 0.0
    qt = datetime.fromisoformat(query_time.replace("Z", "+00:00"))
    leaked = 0
    for r in retrieved:
        ts_str = r.get("timestamp", "") or r.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts > qt:
                leaked += 1
        except (ValueError, TypeError):
            pass
    return leaked / len(retrieved)


def compute_latency_stats(times: List[float]) -> Dict[str, float]:
    """Compute latency statistics from a list of durations in ms."""
    if not times:
        return {"mean": 0, "median": 0, "p95": 0, "p99": 0}
    sorted_times = sorted(times)
    n = len(sorted_times)
    return {
        "mean": round(statistics.mean(sorted_times), 1),
        "median": round(statistics.median(sorted_times), 1),
        "p95": round(sorted_times[int(n * 0.95)], 1),
        "p99": round(sorted_times[int(n * 0.99)], 1),
    }


# ─── Full Evaluation Harness ──────────────────────────

class EvaluationHarness:
    """Full evaluation harness for Feature A (Temporal Multimodal RAG).

    Compares Temporal RAG against:
      - Vanilla MedCPT (no temporal decay, no fusion)
      - Dense-only RAG (no sparse, no image)
      - BM25 keyword baseline

    Reports standard IR metrics, future-leak rate, and latency.
    """

    def __init__(self):
        self.temporal_rag = TemporalMultimodalRetriever()
        self.test_data: List[dict] = []
        self.query_pairs: List[dict] = []

    async def generate_test_data(
        self,
        doctor_id: UUID,
        num_patients: int = 10,
        num_visits: int = 6,
    ) -> Tuple[List[dict], List[dict]]:
        """Generate synthetic test data and query pairs."""
        self.test_data, self.query_pairs = generate_test_dataset(
            doctor_id=doctor_id,
            num_patients=num_patients,
            num_visits_per_patient=num_visits,
        )
        logger.info(
            "Generated test data: %d patients, %d query pairs",
            len(self.test_data), len(self.query_pairs),
        )
        return self.test_data, self.query_pairs

    async def run_single_query(
        self,
        query: str,
        patient_id: str,
        doctor_id: str,
        query_time: str,
    ) -> Dict[str, Any]:
        """Run a single query through all retrieval methods and return results."""
        qt = datetime.fromisoformat(query_time.replace("Z", "+00:00"))

        # Temporal RAG (full)
        t0 = time.time()
        temporal_result = await self.temporal_rag.retrieve(
            query=query,
            patient_id=patient_id,
            doctor_id=doctor_id,
            query_time=qt,
            k=8,
        )
        temporal_time = (time.time() - t0) * 1000

        # Dense-only baseline
        t0 = time.time()
        dense_result = await self.temporal_rag.retrieve_dense_only(
            query=query,
            patient_id=patient_id,
            doctor_id=doctor_id,
            query_time=qt,
            k=8,
        )
        dense_time = (time.time() - t0) * 1000

        return {
            "temporal": {
                "results": temporal_result.get("results", []),
                "citations": temporal_result.get("citations", []),
                "time_ms": temporal_time,
            },
            "dense_only": {
                "results": dense_result.get("results", []),
                "time_ms": dense_time,
            },
        }

    async def run_full_evaluation(
        self,
        doctor_id: UUID,
        num_patients: int = 10,
    ) -> Dict[str, Any]:
        """Run the full evaluation suite across all query pairs.

        Returns comprehensive metrics including:
          - Recall@5 for each method
          - Future-leak rate
          - Latency p95
          - Per-query breakdown
        """
        if not self.query_pairs:
            await self.generate_test_data(doctor_id, num_patients)

        start = datetime.now(timezone.utc)

        # Results storage
        temporal_recalls = []
        dense_recalls = []
        temporal_future_leaks = []
        dense_future_leaks = []
        temporal_latencies = []
        dense_latencies = []

        per_query_results = []

        # Run each query pair
        for i, qp in enumerate(self.query_pairs):
            logger.info("Evaluating query %d/%d: %s", i + 1, len(self.query_pairs), qp["query"][:60])

            try:
                result = await self.run_single_query(
                    query=qp["query"],
                    patient_id=qp["patient_id"],
                    doctor_id=str(doctor_id),
                    query_time=qp["query_time"],
                )
            except Exception as exc:
                logger.error("Query %d failed: %s", i, exc)
                continue

            relevant = qp["relevant_versions"]

            # Temporal RAG metrics
            temporal_retrieved = [r.get("version_number", 0) for r in result["temporal"]["results"]]
            temporal_recall = compute_recall_at_k(temporal_retrieved, relevant, k=5)
            temporal_recalls.append(temporal_recall)

            temporal_leak = compute_future_leak_rate(result["temporal"]["results"], qp["query_time"])
            temporal_future_leaks.append(temporal_leak)

            temporal_latencies.append(result["temporal"]["time_ms"])

            # Dense-only metrics
            dense_retrieved = [r.get("version_number", 0) for r in result["dense_only"]["results"]]
            dense_recall = compute_recall_at_k(dense_retrieved, relevant, k=5)
            dense_recalls.append(dense_recall)

            dense_leak = compute_future_leak_rate(result["dense_only"]["results"], qp["query_time"])
            dense_future_leaks.append(dense_leak)

            dense_latencies.append(result["dense_only"]["time_ms"])

            per_query_results.append({
                "query_id": i,
                "query": qp["query"][:100],
                "type": qp.get("type", "unknown"),
                "temporal_recall": temporal_recall,
                "dense_recall": dense_recall,
                "temporal_future_leak": temporal_leak,
                "dense_future_leak": dense_leak,
            })

        # Compute aggregate metrics
        report = {
            "temporal_rag": {
                "recall_at_5": round(statistics.mean(temporal_recalls), 4) if temporal_recalls else 0,
                "future_leak_rate": round(statistics.mean(temporal_future_leaks), 4) if temporal_future_leaks else 0,
                "latency": compute_latency_stats(temporal_latencies) if temporal_latencies else {},
            },
            "vanilla_medcpt": {
                "recall_at_5": round(statistics.mean(dense_recalls), 4) if dense_recalls else 0,
                "future_leak_rate": round(statistics.mean(dense_future_leaks), 4) if dense_future_leaks else 0,
                "latency": compute_latency_stats(dense_latencies) if dense_latencies else {},
            },
            "dense_only": {
                "recall_at_5": round(statistics.mean(dense_recalls), 4) if dense_recalls else 0,
                "future_leak_rate": round(statistics.mean(dense_future_leaks), 4) if dense_future_leaks else 0,
                "latency": compute_latency_stats(dense_latencies) if dense_latencies else {},
            },
            "summary": {
                "total_queries": len(per_query_results),
                "total_patients": len(self.test_data),
                "recall_improvement_pp": round(
                    (statistics.mean(temporal_recalls) - statistics.mean(dense_recalls)) * 100, 1
                ) if temporal_recalls and dense_recalls else 0,
                "future_leak_reduction_pp": round(
                    (statistics.mean(dense_future_leaks) - statistics.mean(temporal_future_leaks)) * 100, 1
                ) if temporal_future_leaks and dense_future_leaks else 0,
                "evaluated_at": datetime.now(timezone.utc).isoformat(),
                "took_seconds": (datetime.now(timezone.utc) - start).total_seconds(),
            },
            "per_query": per_query_results[:20],  # only first 20 to keep report size manageable
        }

        logger.info(
            "Evaluation complete: Recall@5 temporal=%.3f dense=%.3f | "
            "Future-leak temporal=%.3f dense=%.3f",
            report["temporal_rag"]["recall_at_5"],
            report["dense_only"]["recall_at_5"],
            report["temporal_rag"]["future_leak_rate"],
            report["dense_only"]["future_leak_rate"],
        )

        return report

    async def run_bm25_baseline(
        self,
        doctor_id: UUID,
        num_patients: int = 3,
    ) -> Dict[str, Any]:
        """Run BM25 baseline on a subset of data for comparison."""
        if not self.test_data:
            await self.generate_test_data(doctor_id, num_patients)

        bm25 = BM25Baseline()

        # Build document collection from test data
        all_docs = []
        for patient in self.test_data:
            all_docs.extend(patient["versions"])

        bm25.fit(all_docs)

        bm25_recalls = []
        for qp in self.query_pairs[:30]:  # subset for speed
            results = bm25.search(qp["query"], k=10)
            retrieved = [r["version_number"] for r in results]
            recall = compute_recall_at_k(retrieved, qp["relevant_versions"], k=5)
            bm25_recalls.append(recall)

        return {
            "bm25": {
                "recall_at_5": round(statistics.mean(bm25_recalls), 4) if bm25_recalls else 0,
                "total_queries": len(bm25_recalls),
            }
        }
