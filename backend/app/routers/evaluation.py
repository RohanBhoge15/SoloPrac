"""Evaluation Router — run evaluation harness for all features (A-F).

Endpoints:
  POST /api/v1/evaluation/run — Run full Feature A evaluation
  GET  /api/v1/evaluation/status — Check evaluation status
  POST /api/v1/evaluation/feature-b — Run Feature B evaluation (100 queries)
  POST /api/v1/evaluation/feature-c — Run Feature C projector evaluation
  POST /api/v1/evaluation/feature-e — Run Feature E clustering evaluation
  GET  /api/v1/evaluation/research-data — Research data management report
"""

from __future__ import annotations

import uuid
import logging
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_doctor
from app.models import Doctor
from app.services.evaluation import EvaluationHarness
from app.services.feature_b_eval import FeatureBEvaluator, generate_100_query_set
from app.services.feature_c_projector import ProjectorTrainer, generate_synthetic_pairs
from app.services.feature_c_eval import evaluate_projector, run_qualitative_panel
from app.services.feature_e_clustering import run_full_evaluation as run_feature_e_eval
from app.services.research_data_mgmt import (
    export_langfuse_metrics,
    verify_data_anonymization,
    get_research_data_report,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.post("/run")
async def run_evaluation(
    num_patients: int = 10,
    doctor: Doctor = Depends(get_current_doctor),
):
    """Run the full Feature A evaluation suite on synthetic data."""
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
        "description": "Evaluation harness for all 6 research features (A-F)",
        "features": {
            "A": "Temporal Multimodal RAG",
            "B": "Self-Planning Agent (100-query set)",
            "C": "Cross-Modal Linear Projector (Recall@K)",
            "D": "Zero-Shot Schema Alignment",
            "E": "Trajectory Clustering (HDBSCAN + anomaly)",
            "F": "Significance-Aware Weekly Reports (Likert study)",
        },
    }


@router.post("/feature-b")
async def evaluate_feature_b(
    doctor: Doctor = Depends(get_current_doctor),
):
    """Run Feature B evaluation: self-planning vs fixed pipeline on 100 queries."""
    evaluator = FeatureBEvaluator()
    report = await evaluator.run_evaluation(
        doctor_id=doctor.id,
        patient_id=None,
    )
    return report


@router.get("/feature-b/queries")
async def get_feature_b_queries():
    """Get the 100-query test set for Feature B."""
    queries = generate_100_query_set()
    return {"total": len(queries), "queries": queries}


@router.post("/feature-c")
async def evaluate_feature_c(
    num_pairs: int = Query(200, ge=10, le=1000),
    held_out_pairs: int = Query(50, ge=10, le=200),
):
    """Run Feature C projector training + evaluation.

    Trains linear projector W on N pairs, evaluates Recall@K on held-out pairs.
    """
    trainer = ProjectorTrainer()

    # Generate training pairs
    train_images, train_texts = generate_synthetic_pairs(
        num_pairs=num_pairs, seed=42,
    )

    # Train projector
    result = trainer.train(train_images, train_texts)
    W = result["W"]

    # Generate held-out pairs
    held_out_images, held_out_texts = generate_synthetic_pairs(
        num_pairs=held_out_pairs, seed=99,
    )

    # Evaluate
    eval_report = evaluate_projector(W, held_out_images, held_out_texts)

    return {
        "training": result,
        "evaluation": eval_report,
    }


@router.post("/feature-e")
async def evaluate_feature_e(
    num_patients: int = Query(100, ge=10, le=500),
    inject_deteriorations: int = Query(10, ge=1, le=50),
):
    """Run Feature E clustering evaluation on synthetic data.

    Generates synthetic cohort, clusters trajectories, detects anomalies,
    and evaluates precision on injected deteriorations.
    """
    report = run_feature_e_eval(
        num_patients=num_patients,
        inject_deteriorations=inject_deteriorations,
    )
    return report


@router.get("/research-data")
async def get_research_data():
    """Get research data management report for the paper."""
    return get_research_data_report()


@router.post("/langfuse-export")
async def export_langfuse():
    """Export Langfuse metrics for the paper."""
    return export_langfuse_metrics()
