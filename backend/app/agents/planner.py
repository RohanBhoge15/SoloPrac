"""Self-Planning Agent — Maverick generates dynamic execution plans.

Feature B: Replaces the static intent-based planner with a Maverick LLM
that emits a JSON plan. A critic node evaluates each step and decides
re-plan or finish.

Plan Schema:
{
  "goal": "answer doctor's question about BP trend",
  "steps": [
    {"id": 1, "tool": "retrieve_patient_context", "args": {...}, "depends_on": []},
    {"id": 2, "tool": "synthesize_response", "args": {...}, "depends_on": [1]}
  ],
  "budget_tokens": 4000,
  "reasoning": "Need to retrieve BP history before summarizing"
}
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from app.agents.state import AgentIntent
from app.agents.synthesizer import MaverickSynthesizer

logger = logging.getLogger(__name__)

# ─── Planner Prompt ──────────────────────────────────────────

PLANNER_SYSTEM_PROMPT = """You are a planning agent for a clinical AI assistant. Given a doctor's query,
generate a JSON execution plan that satisfies their information need.

Available tools:
- retrieve_patient_context(patient_id, query, doctor_id, k=8): Search patient records
- synthesize_response(context, query): Generate final answer from context
- analyze_image(image_data, patient_id): Analyze a medical image
- compare_images(image_id_1, image_id_2): Compare two patient images
- generate_prescription(patient_id, doctor_id, medications): Generate prescription
- query_calendar_nl(doctor_id, query): Natural language calendar query

Output a valid JSON object with:
{
  "goal": "string — one sentence describing what the plan achieves",
  "steps": [
    {
      "id": int,
      "tool": "string — tool name from list above",
      "args": {object — tool-specific arguments},
      "depends_on": [int — step IDs that must complete first]
    }
  ],
  "budget_tokens": int — max tokens to spend (default 4000),
  "reasoning": "string — why you chose this sequence of steps"
}

Rules:
1. Keep step count minimal (1-4 steps)
2. Dependencies must form a DAG (no circular references)
3. The final step should always produce the response
4. If the query doesn't need tools, use a single synthesize_response step
5. For patient questions, always start with retrieve_patient_context
6. Never invent tool names — use only the tools listed above
"""

CRITIC_SYSTEM_PROMPT = """You are a critic evaluating the execution of a clinical AI plan.

Given the original plan, the result of executed steps, and any errors:
1. Determine if the goal has been met
2. Check if the response is complete and accurate
3. Decide: re-plan (if more information is needed) or finish (if done)

Output JSON:
{
  "goal_met": true|false,
  "decision": "replan"|"finish",
  "reasoning": "string — why this decision was made",
  "revised_plan": null|{same schema as plan — only if decision is replan},
  "missing_information": "string — what's still needed if replanning"
}
"""

PLAN_SCHEMA = {
    "type": "json_object",
    "properties": {
        "goal": {"type": "string"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "tool": {"type": "string"},
                    "args": {"type": "object"},
                    "depends_on": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["id", "tool", "args", "depends_on"],
            },
        },
        "budget_tokens": {"type": "integer"},
        "reasoning": {"type": "string"},
    },
    "required": ["goal", "steps", "budget_tokens", "reasoning"],
}


class SelfPlanner:
    """Maverick-based planner that generates dynamic execution plans."""

    def __init__(self):
        self.synthesizer = MaverickSynthesizer()
        self._max_plan_attempts = 3

    def _static_plan_shortcut(
        self,
        query: str,
        intent: AgentIntent,
        patient_id: Optional[str],
        doctor_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """P3.29 — Static fast-path for the intents that always take the same
        shape. Skips the ~10-30s Maverick round-trip when the plan is trivial.

        We keep the LLM-planner for genuinely novel queries where step ordering
        matters (multi-step reasoning, re-plan after errors); for the 80% of
        queries that map cleanly to one of these templates we short-circuit.
        Returning None here means "no shortcut; call the LLM planner".
        """
        # Only shortcut fresh plans (never re-plans — those need LLM to react
        # to the error surface).
        # Callers pass previous_plan=None for the first attempt.
        static_steps: Optional[List[Dict[str, Any]]] = None
        goal = ""

        if intent == AgentIntent.PATIENT_QA and patient_id:
            static_steps = [
                {
                    "id": 1,
                    "tool": "retrieve_patient_context",
                    "args": {"patient_id": patient_id, "query": query, "top_k": 5},
                    "depends_on": [],
                },
                {"id": 2, "tool": "synthesize_response", "args": {"query": query}, "depends_on": [1]},
            ]
            goal = "Answer the question about the patient using the record."
        elif intent == AgentIntent.GENERAL_CHAT:
            static_steps = [
                {"id": 1, "tool": "synthesize_response", "args": {"query": query}, "depends_on": []},
            ]
            goal = "Reply conversationally."

        if not static_steps:
            return None

        return {
            "goal": goal,
            "steps": static_steps,
            "budget_tokens": 4000,
            "reasoning": "static-plan-shortcut (P3.29)",
        }

    async def generate_plan(
        self,
        query: str,
        intent: AgentIntent,
        patient_id: Optional[str] = None,
        doctor_id: Optional[str] = None,
        previous_plan: Optional[Dict] = None,
        previous_errors: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Generate a dynamic execution plan using Maverick.

        Args:
            query: The user's original query.
            intent: Classified intent.
            patient_id: Optional patient UUID string.
            doctor_id: Optional doctor UUID string.
            previous_plan: If re-planning, the previous plan for context.
            previous_errors: Any errors from previous execution.

        Returns:
            Plan dict with goal, steps, budget_tokens, reasoning.
        """
        # P3.29 — first, try the static shortcut. Only fall back to the LLM
        # planner when this is a re-plan (previous_plan present) or the intent
        # isn't in the shortcut table.
        if previous_plan is None and not previous_errors:
            shortcut = self._static_plan_shortcut(query, intent, patient_id, doctor_id)
            if shortcut is not None:
                logger.info("Planner: static shortcut for intent=%s (%d steps)", intent.value, len(shortcut["steps"]))
                return shortcut

        # Build context for the planner
        context = {
            "intent": intent.value,
            "patient_available": patient_id is not None,
        }
        if patient_id:
            context["patient_id"] = patient_id
        if doctor_id:
            context["doctor_id"] = doctor_id

        # Build user message
        user_msg = f"Generate a plan for: {query}\n\nContext: {json.dumps(context, indent=2)}"
        if previous_plan:
            user_msg += f"\n\nPrevious plan (for reference): {json.dumps(previous_plan, indent=2)}"
        if previous_errors:
            user_msg += f"\n\nPrevious execution errors: {json.dumps(previous_errors)}"

        # Get plan from Maverick
        attempts = 0
        while attempts < self._max_plan_attempts:
            try:
                response = await self.synthesizer.synthesize(
                    query=user_msg,
                    context={"mode": "planning"},
                    structured_output={"type": "json_object"},
                )

                raw = response.get("structured") or {}
                if not raw:
                    raw_text = response.get("response", "{}")
                    raw = json.loads(raw_text) if raw_text.strip() else {}

                plan = self._validate_plan(raw)
                if plan:
                    logger.info(
                        "Plan generated: %s (%d steps)",
                        plan["goal"][:80],
                        len(plan["steps"]),
                    )
                    return plan

                attempts += 1
                logger.warning("Invalid plan (attempt %d/%d): %s", attempts, self._max_plan_attempts, str(raw)[:200])
            except Exception as exc:
                attempts += 1
                logger.error("Plan generation failed (attempt %d/%d): %s", attempts, self._max_plan_attempts, exc)

        # Fallback: generate a minimal static plan
        return self._fallback_plan(query, intent, patient_id, doctor_id)

    def _validate_plan(self, raw: Dict) -> Optional[Dict]:
        """Validate plan structure and fix common issues."""
        if not raw or not isinstance(raw, dict):
            return None

        steps = raw.get("steps", [])
        if not steps or not isinstance(steps, list):
            return None

        validated_steps = []
        for s in steps:
            if not isinstance(s, dict):
                continue
            sid = s.get("id")
            tool = s.get("tool")
            if not sid or not tool:
                continue
            validated_steps.append(
                {
                    "id": int(sid),
                    "tool": str(tool),
                    "args": s.get("args", {}),
                    "depends_on": [int(d) for d in s.get("depends_on", []) if isinstance(d, (int, float))],
                }
            )

        if not validated_steps:
            return None

        return {
            "goal": str(raw.get("goal", "Answer the query"))[:200],
            "steps": validated_steps,
            "budget_tokens": int(raw.get("budget_tokens", 4000)),
            "reasoning": str(raw.get("reasoning", ""))[:500],
        }

    def _fallback_plan(
        self, query: str, intent: AgentIntent, patient_id: Optional[str], doctor_id: Optional[str] = None
    ) -> Dict:
        """Fallback static plan when Maverick isn't available."""
        steps = []
        if intent == AgentIntent.PATIENT_QA and patient_id:
            steps = [
                {
                    "id": 1,
                    "tool": "retrieve_patient_context",
                    "args": {
                        "patient_id": patient_id,
                        "query": query,
                        "doctor_id": doctor_id or "",
                        "k": 8,
                    },
                    "depends_on": [],
                },
                {
                    "id": 2,
                    "tool": "synthesize_response",
                    "args": {
                        "context": None,
                        "query": query,
                    },
                    "depends_on": [1],
                },
            ]
        else:
            steps = [
                {
                    "id": 1,
                    "tool": "synthesize_response",
                    "args": {
                        "context": {"intent": intent.value},
                        "query": query,
                    },
                    "depends_on": [],
                },
            ]

        return {
            "goal": f"Answer: {query[:100]}",
            "steps": steps,
            "budget_tokens": 4000,
            "reasoning": "Fallback static plan (Maverick unavailable)",
        }


class PlanCritic:
    """Critic node that evaluates execution results and decides re-plan vs finish."""

    def __init__(self):
        self.synthesizer = MaverickSynthesizer()
        self._max_critic_attempts = 2
        self._max_replan_rounds = 3

    async def evaluate(
        self,
        plan: Dict[str, Any],
        tool_results: List[Dict],
        errors: List[str],
        replan_count: int = 0,
    ) -> Dict[str, Any]:
        """Evaluate execution and decide re-plan or finish.

        Args:
            plan: The original plan.
            tool_results: Results from executed tool calls.
            errors: Any errors that occurred.
            replan_count: How many re-plan rounds have happened.

        Returns:
            {"decision": "replan"|"finish", "revised_plan": dict|None, "reasoning": str}
        """
        # If too many re-plan rounds, force finish
        if replan_count >= self._max_replan_rounds:
            return {
                "goal_met": True,
                "decision": "finish",
                "reasoning": f"Max re-plan rounds ({self._max_replan_rounds}) reached",
                "revised_plan": None,
                "missing_information": "",
            }

        # If no errors and tools executed, finish
        if not errors and tool_results:
            last_tool = tool_results[-1]
            if last_tool.get("tool_name") == "synthesize_response":
                return {
                    "goal_met": True,
                    "decision": "finish",
                    "reasoning": "All steps completed successfully",
                    "revised_plan": None,
                    "missing_information": "",
                }

        # If there are errors, try re-plan with Maverick
        if errors:
            return await self._critic_replan(plan, tool_results, errors)

        # No errors but more steps remain — continue
        return {
            "goal_met": False,
            "decision": "replan",
            "reasoning": "Additional steps may be needed",
            "revised_plan": None,
            "missing_information": "",
        }

    async def _critic_replan(
        self,
        plan: Dict,
        results: List[Dict],
        errors: List[str],
    ) -> Dict[str, Any]:
        """Use Maverick to decide if re-plan is needed."""
        critic_context = {
            "original_goal": plan.get("goal", ""),
            "steps_planned": len(plan.get("steps", [])),
            "tool_results": [
                {
                    "tool": tc.get("tool_name"),
                    "success": tc.get("error") is None,
                    "result_preview": str(tc.get("result", ""))[:300],
                }
                for tc in results
            ],
            "errors": errors,
        }

        prompt = (
            f"Evaluate this execution:\n\n"
            f"{json.dumps(critic_context, indent=2, default=str)}\n\n"
            f"Should we re-plan or finish?"
        )

        try:
            response = await self.synthesizer.synthesize(
                query=prompt,
                context={"mode": "critic"},
                structured_output={"type": "json_object"},
            )

            raw = response.get("structured") or {}
            if not raw:
                raw_text = response.get("response", "{}")
                raw = json.loads(raw_text) if raw_text.strip() else {}

            if raw.get("decision") == "replan":
                return {
                    "goal_met": False,
                    "decision": "replan",
                    "reasoning": raw.get("reasoning", "Re-planning needed"),
                    "revised_plan": raw.get("revised_plan", None),
                    "missing_information": raw.get("missing_information", ""),
                }

            return {
                "goal_met": True,
                "decision": "finish",
                "reasoning": raw.get("reasoning", "Goal met"),
                "revised_plan": None,
                "missing_information": "",
            }

        except Exception as exc:
            logger.error("Critic evaluator failed: %s", exc)
            # If critic fails, finish to avoid infinite loops
            return {
                "goal_met": True,
                "decision": "finish",
                "reasoning": "Critic evaluation failed — finishing to be safe",
                "revised_plan": None,
                "missing_information": "",
            }

    def _fallback_evaluation(self) -> Dict[str, Any]:
        """Fallback critic decision."""
        return {
            "goal_met": True,
            "decision": "finish",
            "reasoning": "Critic fallback (Maverick unavailable)",
            "revised_plan": None,
            "missing_information": "",
        }
