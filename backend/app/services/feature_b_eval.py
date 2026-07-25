"""Feature B Evaluation — Steps-to-Resolution vs Fixed Pipeline.

Evaluates the self-planning agent against a fixed-pipeline baseline
on 100 synthetic queries. Measures:
  - Steps-to-resolution (lower = better adaptive planning)
  - Success rate per query type
  - Re-plan frequency
  - Plan quality (steps needed vs actual steps)

Usage:
    from app.services.feature_b_eval import FeatureBEvaluator
    evaluator = FeatureBEvaluator()
    report = await evaluator.run_evaluation(doctor_id=..., patient_id=...)
"""

from __future__ import annotations

import json
import time
import logging
import statistics
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from app.agents.graph import AgentGraph
from app.agents.planner import SelfPlanner
from app.agents.state import AgentIntent

logger = logging.getLogger(__name__)

# ─── 100 Synthetic Query Set ───────────────────────────────

QUERY_TYPES = {
    "patient_qa": [
        "What is this patient's current BP trend?",
        "Show me the latest lab results",
        "Has their weight changed significantly?",
        "What medications are they on?",
        "Are there any abnormal vitals?",
        "Summarize the last 3 visits",
        "What's the diagnosis trend?",
        "Show me heart rate history",
        "Any medication changes recently?",
        "Is their condition improving or worsening?",
    ],
    "general_chat": [
        "What can you help me with?",
        "How do I use this system?",
        "Tell me about the features available",
        "What is your name?",
        "How does the AI work?",
        "Help me understand the dashboard",
        "What reports can you generate?",
        "Can you help with prescription?",
        "Is this system secure?",
        "How do I search for a patient?",
    ],
    "scheduling": [
        "What appointments do I have today?",
        "Find available slots tomorrow",
        "Book a 30-minute slot at 3pm",
        "Reschedule the 2pm appointment",
        "Cancel the appointment on Friday",
        "Show my calendar for this week",
        "When is my next free slot?",
        "Block 2-4pm for paperwork",
        "What's my schedule look like?",
        "Find the best time for a follow-up",
    ],
    "image_analysis": [
        "Analyze this wound photo",
        "Compare these two images",
        "Is the wound healing?",
        "Show me the change in wound size",
        "Compare with last week's photo",
        "Any signs of infection?",
        "Measure the wound area",
        "Track the healing progress",
        "Show the overlay comparison",
        "Generate a clinical summary",
    ],
    "prescription": [
        "Generate a prescription for Metformin",
        "Create a prescription for Amlodipine 5mg",
        "Renew the current medications",
        "Generate prescription with 3 medications",
        "Add Paracetamol 500mg PRN",
        "Create antibiotic prescription",
        "Generate refill for existing Rx",
        "Prescribe Levothyroxine 50mcg",
        "Update medication dosage",
        "Generate a prescription for hypertension",
    ],
    "weekly_report": [
        "Generate the weekly report",
        "Show me the executive summary",
        "Create a clinical weekly digest",
        "Generate family-friendly report",
        "What's significant this week?",
        "Show me the weekly trends",
        "Generate report for Mrs. Sharma",
        "Create a report with all metrics",
        "Show significant changes this week",
        "Generate and email the report",
    ],
}


def generate_100_query_set() -> List[Dict[str, Any]]:
    """Generate 100 synthetic queries across all intent types."""
    queries = []
    # 10 from each type = 60; fill remaining with patient_qa and general_chat
    for intent, qlist in QUERY_TYPES.items():
        for q in qlist:
            queries.append({"query": q, "intent": intent, "id": len(queries) + 1})

    # Add 40 more to reach 100
    extra_pqa = [
        "What is the most recent diagnosis?",
        "Show me all medications",
        "Any allergies recorded?",
        "What's the age and gender?",
        "Show me vitals from last visit",
        "Compare BP between visits",
        "Any new symptoms?",
        "What vaccinations are due?",
        "Show me the patient summary",
        "Any chronic conditions?",
        "What was the last visit reason?",
        "List all diagnoses",
        "Show medication history",
        "Any abnormal lab values?",
        "What follow-up is needed?",
        "How is the diabetes management?",
        "Show me the weight trend",
        "Any hospitalizations?",
        "What's the treatment plan?",
        "Show recent notes",
    ]
    for q in extra_pqa:
        queries.append({"query": q, "intent": "patient_qa", "id": len(queries) + 1})

    # Fill to 100
    extra_general = [
        "What is this system?",
        "How do I log out?",
        "What are my shortcuts?",
        "Show me the help menu",
        "How does versioning work?",
    ]
    for q in extra_general:
        queries.append({"query": q, "intent": "general_chat", "id": len(queries) + 1})

    # Add more scheduling
    extra_sched = [
        "Find slots for next Monday",
        "Show tomorrow's schedule",
        "Book emergency slot",
    ]
    for q in extra_sched:
        queries.append({"query": q, "intent": "scheduling", "id": len(queries) + 1})

    # Add more image queries
    extra_image = [
        "Analyze the latest X-ray",
        "Compare pre and post op images",
        "Show healing trajectory",
    ]
    for q in extra_image:
        queries.append({"query": q, "intent": "image_analysis", "id": len(queries) + 1})

    # Add more prescription queries
    extra_rx = [
        "Generate refill prescription",
        "Create a 3-month supply Rx",
        "Prescribe with dosage instructions",
    ]
    for q in extra_rx:
        queries.append({"query": q, "intent": "prescription", "id": len(queries) + 1})

    # Add more weekly report queries
    extra_report = [
        "Generate weekly digest",
        "Create monthly summary report",
        "Show significant clinical events",
    ]
    for q in extra_report:
        queries.append({"query": q, "intent": "weekly_report", "id": len(queries) + 1})

    return queries[:100]


class FixedPipelineAgent:
    """Fixed pipeline baseline — non-adaptive, always executes the same steps.

    No routing, no planning, no re-planning, no critic.
    Always: retrieve context → synthesize response (2 steps).
    This serves as the non-adaptive baseline for Feature B comparison.
    """

    def __init__(self):
        self._initialized = False
        self._retrieve_fn = None
        self._synthesize_fn = None

    async def _ensure_initialized(self):
        if self._initialized:
            return
        try:
            from app.agents.tools import retrieve_patient_context, synthesize_response
            self._retrieve_fn = retrieve_patient_context
            self._synthesize_fn = synthesize_response
            self._initialized = True
        except ImportError as exc:
            logger.warning("FixedPipelineAgent: tools unavailable (%s)", exc)

    async def run(
        self,
        query: str,
        doctor_id: UUID,
        patient_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """Run the fixed 2-step pipeline: retrieve → synthesize."""
        start = time.time()
        steps = 0
        errors = 0
        response_text = ""

        await self._ensure_initialized()

        # Step 1: Retrieve patient context
        try:
            if self._retrieve_fn:
                context = await self._retrieve_fn(
                    query=query, doctor_id=doctor_id, patient_id=patient_id
                )
                steps += 1
            else:
                errors += 1
        except Exception as exc:
            logger.warning("Fixed pipeline retrieve failed: %s", exc)
            errors += 1
            context = None

        # Step 2: Synthesize response
        try:
            if self._synthesize_fn and context is not None:
                response_text = await self._synthesize_fn(
                    query=query, context=context, doctor_id=doctor_id
                )
                steps += 1
            else:
                errors += 1
        except Exception as exc:
            logger.warning("Fixed pipeline synthesize failed: %s", exc)
            errors += 1

        took_ms = (time.time() - start) * 1000

        return {
            "response": str(response_text)[:200] if response_text else "",
            "took_ms": round(took_ms, 1),
            "execution_steps": steps,
            "plan_attempts": 0,
            "critic_decisions": 0,
            "replan_count": 0,
            "errors": errors,
            "success": errors == 0 and steps > 0,
        }


class FeatureBEvaluator:
    """Evaluate Feature B self-planning agent vs fixed pipeline baseline."""

    def __init__(self):
        self.agent = AgentGraph()
        self.planner = SelfPlanner()
        self.fixed_pipeline = FixedPipelineAgent()

    async def run_single_query(
        self,
        query: str,
        doctor_id: UUID,
        patient_id: Optional[UUID] = None,
        use_self_planning: bool = True,
    ) -> Dict[str, Any]:
        """Run a single query through the agent.

        Returns metrics: steps taken, errors, re-plan count, success.
        """
        start = time.time()

        results = []
        async for event in self.agent.run_stream(
            user_query=query,
            doctor_id=doctor_id,
            patient_id=patient_id,
        ):
            results.append(event)

        took_ms = (time.time() - start) * 1000

        # Parse results
        done_event = next((e for e in results if e["type"] == "done"), {})
        error_event = next((e for e in results if e["type"] == "error"), None)

        trace_events = done_event.get("trace_events", [])
        replan_count = done_event.get("replan_count", 0)
        response = done_event.get("response", "")

        # Count actual execution steps (not routing/planning/synthesizing)
        execution_steps = sum(1 for e in trace_events if "Executor:" in e)
        plan_steps = sum(1 for e in trace_events if "Planner" in e)
        critic_steps = sum(1 for e in trace_events if "Critic:" in e)
        error_steps = sum(1 for e in trace_events if "FAILED" in e or "ERROR" in e)

        return {
            "response": response[:200],
            "took_ms": round(took_ms, 1),
            "execution_steps": execution_steps,
            "plan_attempts": plan_steps,
            "critic_decisions": critic_steps,
            "replan_count": replan_count,
            "errors": error_steps,
            "success": error_event is None,
        }

    async def run_evaluation(
        self,
        doctor_id: UUID,
        patient_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """Run full evaluation on the 100-query set.

        Runs both self-planning and fixed-pipeline arms for comparison.

        Returns:
            {
                "self_planning": {...metrics...},
                "fixed_pipeline": {...metrics...},
                "overall": {...summary...},
                "per_intent": {...breakdown by intent...},
                "per_query": [...],
            }
        """
        queries = generate_100_query_set()
        logger.info("Feature B eval: %d queries across both arms", len(queries))

        sp_results = []
        fp_results = []

        for q in queries:
            logger.info("Query %d/%d: %s (%s)", q["id"], len(queries), q["query"][:60], q["intent"])

            # Self-planning arm
            sp_result = await self.run_single_query(
                query=q["query"],
                doctor_id=doctor_id,
                patient_id=patient_id,
                use_self_planning=True,
            )
            sp_result["query_id"] = q["id"]
            sp_result["query"] = q["query"]
            sp_result["intent"] = q["intent"]
            sp_results.append(sp_result)

            # Fixed-pipeline arm
            fp_result = await self.fixed_pipeline.run(
                query=q["query"],
                doctor_id=doctor_id,
                patient_id=patient_id,
            )
            fp_result["query_id"] = q["id"]
            fp_result["query"] = q["query"]
            fp_result["intent"] = q["intent"]
            fp_results.append(fp_result)

        def _aggregate(results: List[Dict]) -> Dict[str, Any]:
            steps_all = [r["execution_steps"] for r in results]
            replans_all = [r["replan_count"] for r in results]
            times_all = [r["took_ms"] for r in results]
            success_count = sum(1 for r in results if r["success"])
            n = len(results)
            return {
                "total_queries": n,
                "success_rate": round(success_count / n * 100, 1) if n else 0,
                "avg_steps_to_resolution": round(statistics.mean(steps_all), 1) if steps_all else 0,
                "median_steps": round(statistics.median(steps_all), 1) if steps_all else 0,
                "max_steps": max(steps_all) if steps_all else 0,
                "min_steps": min(steps_all) if steps_all else 0,
                "avg_replan_count": round(statistics.mean(replans_all), 1) if replans_all else 0,
                "queries_requiring_replan": sum(1 for r in results if r["replan_count"] > 0),
                "avg_latency_ms": round(statistics.mean(times_all), 1) if times_all else 0,
                "p95_latency_ms": round(
                    sorted(times_all)[int(len(times_all) * 0.95)], 1
                ) if times_all else 0,
            }

        # Per-intent aggregation (self-planning)
        per_intent = {}
        for intent in set(q["intent"] for q in queries):
            intent_results = [r for r in sp_results if r["intent"] == intent]
            per_intent[intent] = {
                "count": len(intent_results),
                "avg_steps": round(
                    statistics.mean(r["execution_steps"] for r in intent_results), 1
                ) if intent_results else 0,
                "avg_replans": round(
                    statistics.mean(r["replan_count"] for r in intent_results), 1
                ) if intent_results else 0,
                "avg_time_ms": round(
                    statistics.mean(r["took_ms"] for r in intent_results), 1
                ) if intent_results else 0,
                "success_rate": round(
                    sum(1 for r in intent_results if r["success"]) / len(intent_results) * 100, 1
                ) if intent_results else 0,
            }

        # Overall metrics for both arms
        report = {
            "self_planning": _aggregate(sp_results),
            "fixed_pipeline": _aggregate(fp_results),
            "comparison": {
                "steps_reduction_pct": round(
                    (1 - (
                        statistics.mean([r["execution_steps"] for r in sp_results]) /
                        statistics.mean([r["execution_steps"] for r in fp_results])
                    )) * 100, 1
                ) if sp_results and fp_results and statistics.mean([r["execution_steps"] for r in fp_results]) > 0 else None,
                "success_rate_delta_pp": round(
                    (
                        sum(1 for r in sp_results if r["success"]) / len(sp_results) -
                        sum(1 for r in fp_results if r["success"]) / len(fp_results)
                    ) * 100, 1
                ) if sp_results and fp_results else None,
                "latency_reduction_pct": round(
                    (1 - (
                        statistics.mean([r["took_ms"] for r in sp_results]) /
                        statistics.mean([r["took_ms"] for r in fp_results])
                    )) * 100, 1
                ) if sp_results and fp_results and statistics.mean([r["took_ms"] for r in fp_results]) > 0 else None,
            },
            "per_intent": per_intent,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "Feature B eval complete: SP success=%.1f%% steps=%.1f | FP success=%.1f%% steps=%.1f",
            report["self_planning"]["success_rate"],
            report["self_planning"]["avg_steps_to_resolution"],
            report["fixed_pipeline"]["success_rate"],
            report["fixed_pipeline"]["avg_steps_to_resolution"],
        )

        return report
