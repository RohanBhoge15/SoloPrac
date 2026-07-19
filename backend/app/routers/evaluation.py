"""Evaluation Router — run Feature A evaluation harness via API.

Endpoints:
  POST /api/v1/evaluation/run — Run full evaluation on synthetic data
  GET  /api/v1/evaluation/status — Check evaluation status
"""

from __future__ import annotations

import uuid
import logging
from fastapi import APIRouter, Depends
from app.dependencies import get_current_doctor
from app.models import Doctor
from app.services.evaluation import EvaluationHarness

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.post("/run")
async def run_evaluation(
    num_patients: int = 10,
    doctor: Doctor = Depends(get_current_doctor),
):
    """Run the full Feature A evaluation suite on synthetic data.

    Generates N synthetic patients with longitudinal records, then evaluates:
      - Temporal RAG (full multimodal with temporal decay)
      - Dense-only baseline (vanilla MedCPT)
      - Future-leak rate comparison
      - Latency p95/p99
    """
    harness = EvaluationHarness()
    await harness.generate_test_data(
        doctor_id=doctor.id,
        num_patients=num_patients,
        num_visits=6,
    )

    results = await harness.run_full_evaluation(
        doctor_id=doctor.id,
        num_patients=num_patients,
    )

    # Optionally run BM25 on a subset
    bm25_results = await harness.run_bm25_baseline(
        doctor_id=doctor.id,
        num_patients=min(num_patients, 3),
    )
    results.update(bm25_results)

    return results


@router.get("/status")
async def evaluation_status():
    """Check the evaluation endpoint."""
    return {
        "status": "ready",
        "description": "Evaluation harness for Feature A (Temporal Multimodal RAG)",
        "metrics": ["Recall@5", "Future-leak rate", "Latency p95", "Answer faithfulness"],
        "baselines": ["Temporal RAG (full)", "Dense-only MedCPT", "BM25 keyword"],
    }
