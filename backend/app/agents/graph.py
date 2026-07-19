"""LangGraph Agent — Main Graph with Self-Planning Agent (Feature B).

Graph structure:
    START → router → [plan → execute → critic → (re-plan↩ | finish)]
                                            ↕ (up to 3 re-plan rounds)
                          → synthesize → respond → END

Feature B: Maverick generates JSON plans dynamically. Critic node evaluates
execution and decides re-plan vs finish. Plans logged for paper tables.

Usage:
    from app.agents.graph import AgentGraph
    agent = AgentGraph()
    result = await agent.run(user_query="...", doctor_id=..., patient_id=...)
"""

from __future__ import annotations

import uuid
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, AsyncGenerator

from app.agents.state import AgentState, AgentIntent, AgentToolCall, create_initial_state
from app.agents.router import IntentRouter
from app.agents.tools import tool_registry
from app.agents.planner import SelfPlanner, PlanCritic

logger = logging.getLogger(__name__)


class AgentGraph:
    """Main agent graph — Feature B: self-planning with critic loop."""

    def __init__(self):
        self.router = IntentRouter()
        self.planner = SelfPlanner()
        self.critic = PlanCritic()
        self._trace: List[str] = []

    def _reset_trace(self):
        self._trace = []

    def _add_trace(self, event: str):
        self._trace.append(event)
        logger.debug("[Agent] %s", event)

    async def _router_node(self, state: AgentState) -> str:
        """Classify user intent."""
        self._add_trace(f"Routing query: '{state['user_query'][:60]}...'")
        intent, confidence, reasoning = await self.router.classify(state["user_query"])
        state["intent"] = intent
        state["confidence"] = confidence
        state["reasoning"] = reasoning
        state["trace_events"].append(f"Router: {intent.value} (conf={confidence:.2f})")
        return "plan"

    async def _planner_node(self, state: AgentState) -> str:
        """Feature B: Maverick generates dynamic JSON plan."""
        self._add_trace(f"Self-planning for {state['intent'].value}")

        # Generate plan using Maverick
        plan = await self.planner.generate_plan(
            query=state["user_query"],
            intent=state["intent"],
            patient_id=str(state["patient_id"]) if state.get("patient_id") else None,
            doctor_id=str(state["doctor_id"]) if state.get("doctor_id") else None,
        )

        state["plan"] = plan.get("steps", [])
        state["current_step"] = 0
        state["replan_count"] = state.get("replan_count", 0)
        state["trace_events"].append(
            f"Planner (Feature B): {plan['goal'][:80]} — {len(plan['steps'])} step(s) planned"
        )

        # Log plan for paper evaluation
        logger.info("Feature B plan: goal=%s steps=%d reasoning=%s",
                     plan["goal"][:100], len(plan["steps"]), plan["reasoning"][:200])

        return "execute"

    async def _executor_node(self, state: AgentState) -> str:
        """Execute the current step."""
        plan = state.get("plan", [])
        step_idx = state["current_step"]

        if step_idx >= len(plan):
            self._add_trace("All steps completed")
            return "critic"

        step = plan[step_idx]
        tool_name = step["tool"]
        tool_args = step["args"]

        # Resolve dependency results
        for dep_id in step.get("depends_on", []):
            for tc in state.get("tool_calls", []):
                if tc.get("step_id") == dep_id and tc.get("result"):
                    # Fill in dependency for tools that need context
                    if tool_name == "synthesize_response":
                        tool_args["context"] = tc["result"]
                    break

        self._add_trace(f"Executing step {step_idx + 1}/{len(plan)}: {tool_name}")

        tool_fn = tool_registry.get(tool_name)
        if tool_fn is None:
            error_msg = f"Tool '{tool_name}' not found"
            state["tool_calls"].append(AgentToolCall(
                tool_name=tool_name, tool_args=tool_args, result=None, error=error_msg,
            ))
            state["error_count"] = state.get("error_count", 0) + 1
            state["trace_events"].append(f"Executor: {tool_name} FAILED — {error_msg}")
            state["current_step"] = step_idx + 1
            return "critic"

        try:
            result = await tool_fn(**tool_args)
            state["tool_calls"].append(AgentToolCall(
                tool_name=tool_name, tool_args=tool_args, result=result, error=None,
            ))
            state["trace_events"].append(f"Executor: {tool_name} OK")

            # Store context for downstream use
            if tool_name == "retrieve_patient_context":
                state["retrieved_context"] = result
                state["citations"] = result.get("citations", [])
            elif tool_name in ("analyze_image", "compare_images"):
                state["analysis_result"] = result

        except Exception as exc:
            logger.error("Tool %s failed: %s", tool_name, exc)
            state["tool_calls"].append(AgentToolCall(
                tool_name=tool_name, tool_args=tool_args, result=None, error=str(exc),
            ))
            state["error_count"] = state.get("error_count", 0) + 1
            state["trace_events"].append(f"Executor: {tool_name} ERROR — {str(exc)[:100]}")

        state["current_step"] = step_idx + 1
        return "execute"

    async def _critic_node(self, state: AgentState) -> str:
        """Feature B: Evaluate execution and decide re-plan or finish."""
        self._add_trace("Critic evaluating execution")

        plan_steps = state.get("plan", [])
        tool_calls = state.get("tool_calls", [])
        errors = [tc.get("error", "") for tc in tool_calls if tc.get("error")]

        evaluation = await self.critic.evaluate(
            plan={"goal": f"Plan for: {state['user_query'][:100]}", "steps": plan_steps},
            tool_results=tool_calls,
            errors=errors,
            replan_count=state.get("replan_count", 0),
        )

        state["trace_events"].append(f"Critic: {evaluation['decision']} — {evaluation['reasoning'][:100]}")

        if evaluation["decision"] == "replan":
            state["replan_count"] = state.get("replan_count", 0) + 1

            # Generate a revised plan using the planner with error context
            revised = await self.planner.generate_plan(
                query=state["user_query"],
                intent=state["intent"],
                patient_id=str(state["patient_id"]) if state.get("patient_id") else None,
                doctor_id=str(state["doctor_id"]) if state.get("doctor_id") else None,
                previous_plan={"steps": plan_steps},
                previous_errors=errors,
            )

            state["plan"] = revised.get("steps", plan_steps)
            state["current_step"] = 0
            state["trace_events"].append(
                f"Re-plan (round {state['replan_count']}): {revised['goal'][:80]} — {len(state['plan'])} step(s)"
            )
            return "execute"

        return "synthesize"

    async def _synthesizer_node(self, state: AgentState) -> str:
        """Generate the final response."""
        self._add_trace("Synthesizing final response")

        # Check if a tool already produced the response
        for tc in reversed(state.get("tool_calls", [])):
            if tc["tool_name"] == "synthesize_response" and tc["result"]:
                result = tc["result"]
                if isinstance(result, dict):
                    draft = result.get("response", "") or result.get("content", "")
                else:
                    draft = str(result)
                if draft:
                    state["draft"] = draft
                    state["trace_events"].append("Synthesizer: used tool-generated response")
                    return "respond"

        # Build from context
        state["draft"] = self._build_response(state)
        state["trace_events"].append("Synthesizer: context response built")
        return "respond"

    def _build_response(self, state: AgentState) -> str:
        """Build response from tool results and context."""
        context = state.get("retrieved_context", {})
        results = context.get("results", []) if isinstance(context, dict) else []
        citations = state.get("citations", [])

        if results:
            lines = [f"Based on the patient record, here's what I found:\n"]
            for r in results[:5]:
                vn = r.get("version_number", "?")
                ts = str(r.get("timestamp", ""))[:10]
                summary = r.get("summary", "")
                score = r.get("score", 0)
                lines.append(f"[v{vn}  ·  {ts}] {summary}  (relevance: {score:.3f})")
            lines.append(f"\nRetrieved {len(results)} relevant version(s).")
            lines.append("\n*AI Suggestion — Requires Doctor Validation.*")
            return "\n".join(lines)

        return (
            f"I processed your request about '{state['user_query']}'.\n\n"
            f"*AI Suggestion — Requires Doctor Validation.*"
        )

    async def _responder_node(self, state: AgentState) -> str:
        """Final formatting."""
        self._add_trace("Finalizing response")
        state["final_response"] = state.get("draft", "I wasn't able to process that request.")
        state["completed_at"] = datetime.now(timezone.utc)
        state["trace_events"].append("Response delivered")
        return "END"

    # ─── Streaming Entry Point ───

    async def run_stream(
        self,
        user_query: str,
        doctor_id: uuid.UUID,
        patient_id: Optional[uuid.UUID] = None,
        conversation_id: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Run the agent graph and yield events.

        Yields:
            {"type": "trace", "message": str}
            {"type": "token", "text": str}
            {"type": "done", "response": str, "trace_events": [...], ...}
            {"type": "error", "message": str}
        """
        self._reset_trace()
        state = create_initial_state(user_query, doctor_id, patient_id, conversation_id)
        state["replan_count"] = 0

        node_sequence = ["router", "plan", "execute", "critic", "synthesize", "respond"]
        node_fns = {
            "router": self._router_node,
            "plan": self._planner_node,
            "execute": self._executor_node,
            "critic": self._critic_node,
            "synthesize": self._synthesizer_node,
            "respond": self._responder_node,
        }

        current_node = "router"
        yield {"type": "trace", "message": "🧠 Understanding your request..."}

        while current_node != "END":
            fn = node_fns.get(current_node)
            if not fn:
                yield {"type": "error", "message": f"Unknown node: {current_node}"}
                break

            try:
                self._add_trace(f"Entering node: {current_node}")
                yield {"type": "trace", "message": self._node_label(current_node)}

                next_node = await fn(state)

                # Stream draft tokens
                if current_node == "synthesize" and state.get("draft"):
                    draft = state["draft"]
                    for i in range(0, len(draft), 80):
                        yield {"type": "token", "text": draft[i:i + 80]}

                current_node = next_node

            except Exception as exc:
                logger.exception("Agent node '%s' failed", current_node)
                yield {"type": "error", "message": f"Agent error in {current_node}: {str(exc)}"}
                state["error_count"] = (state.get("error_count", 0)) + 1
                if state["error_count"] >= state.get("max_retries", 2):
                    break
                continue

        yield {
            "type": "done",
            "response": state.get("final_response", "I encountered an error processing your request."),
            "intent": state.get("intent", AgentIntent.GENERAL_CHAT).value if state.get("intent") else "unknown",
            "trace_events": state.get("trace_events", []),
            "replan_count": state.get("replan_count", 0),
            "took_ms": (
                (datetime.now(timezone.utc) - state["started_at"]).total_seconds() * 1000
                if state.get("started_at") else 0
            ),
        }

    def _node_label(self, node: str) -> str:
        labels = {
            "router": "🧠 Understanding your request...",
            "plan": "📋 Planning with Maverick (Feature B)...",
            "execute": "🔍 Executing plan steps...",
            "critic": "✅ Evaluating results (Feature B critic)...",
            "synthesize": "✍️ Drafting response...",
            "respond": "✅ Finalizing...",
        }
        return labels.get(node, f"Processing ({node})...")
