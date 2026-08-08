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

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, Optional

from app.agents.planner import PlanCritic, SelfPlanner
from app.agents.router import IntentRouter
from app.agents.state import AgentIntent, AgentState, AgentToolCall, create_initial_state
from app.agents.synthesizer import MaverickSynthesizer
from app.agents.tools import tool_registry
from app.services.langfuse import langfuse_client, trace_agent_step
from app.services.pii import get_patient_name_for_reassociation, reassociate_pseudonym, validate_citations

logger = logging.getLogger(__name__)


class AgentGraph:
    """Main agent graph — Feature B: self-planning with critic loop.

    Thread-safe: all mutable state lives in the per-request AgentState dict,
    not on the instance. _add_trace writes into state['trace_events'].
    """

    def __init__(self):
        self.router = IntentRouter()
        self.planner = SelfPlanner()
        self.critic = PlanCritic()
        # Streaming synthesizer for the context-only response path (P0.4).
        # We reuse this instance so the AsyncOpenAI client's HTTP pool stays warm.
        self.synthesizer = MaverickSynthesizer()

    def _add_trace(self, state: AgentState, event: str):
        state.setdefault("trace_events", []).append(event)
        logger.debug("[Agent] %s", event)

    async def _router_node(self, state: AgentState) -> str:
        """Classify user intent."""
        self._add_trace(state, f"Routing query: '{state['user_query'][:60]}...'")

        async with trace_agent_step(
            "router",
            state.get("trace_id", str(uuid.uuid4())),
            doctor_id=str(state.get("doctor_id")) if state.get("doctor_id") else None,
            patient_id=str(state.get("patient_id")) if state.get("patient_id") else None,
            input_data={"query": state["user_query"]},
        ) as span:
            intent, confidence, reasoning = await self.router.classify(state["user_query"])
            state["intent"] = intent
            state["confidence"] = confidence
            state["reasoning"] = reasoning
            state["trace_events"].append(f"Router: {intent.value} (conf={confidence:.2f})")
            if span:
                span.set_output({"intent": intent.value, "confidence": confidence, "reasoning": reasoning})
        return "plan"

    async def _planner_node(self, state: AgentState) -> str:
        """Feature B: Maverick generates dynamic JSON plan."""
        trace_id = state.get("trace_id", str(uuid.uuid4()))
        state["trace_id"] = trace_id
        self._add_trace(state, f"Self-planning for {state['intent'].value}")

        async with trace_agent_step(
            "planner",
            trace_id,
            doctor_id=str(state.get("doctor_id")) if state.get("doctor_id") else None,
            patient_id=str(state.get("patient_id")) if state.get("patient_id") else None,
            input_data={"intent": state["intent"].value, "query": state["user_query"][:200]},
        ) as span:
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
            logger.info(
                "Feature B plan: goal=%s steps=%d reasoning=%s",
                plan["goal"][:100],
                len(plan["steps"]),
                plan["reasoning"][:200],
            )

            if span:
                span.set_output(
                    {
                        "goal": plan["goal"],
                        "steps": plan.get("steps", []),
                        "budget_tokens": plan.get("budget_tokens", 4000),
                        "reasoning": plan.get("reasoning", ""),
                    }
                )

        return "execute"

    async def _executor_node(self, state: AgentState) -> str:
        """Execute one wave of the plan DAG in parallel (P3.30).

        Runs every step whose dependencies are already satisfied concurrently
        via `asyncio.gather`, then returns "execute" if more waves remain or
        "critic" if the plan is drained.
        """
        import asyncio as _asyncio

        plan = state.get("plan", [])
        trace_id = state.get("trace_id", str(uuid.uuid4()))
        executed_ids: set = state.setdefault("executed_step_ids", set())

        # Pick the next wave of ready steps.
        ready = []
        for step in plan:
            sid = step.get("id")
            if sid in executed_ids:
                continue
            deps = step.get("depends_on", []) or []
            if all(d in executed_ids for d in deps):
                ready.append(step)

        if not ready:
            self._add_trace(state, "Executor: no ready steps left")
            return "critic"

        self._add_trace(
            state,
            f"Executor: {len(ready)} step(s) in parallel: " + ", ".join(s.get("tool", "?") for s in ready),
        )

        async def _run_one(step: dict):
            tool_name = step["tool"]
            tool_args = dict(step.get("args") or {})
            if state.get("doctor_id"):
                tool_args.setdefault("doctor_id", str(state["doctor_id"]))
            # Feed dependency results into tools that expect them.
            for dep_id in step.get("depends_on", []) or []:
                for tc in state.get("tool_calls", []):
                    if tc.get("step_id") == dep_id and tc.get("result"):
                        if tool_name == "synthesize_response":
                            tool_args["context"] = tc["result"]
                        break

            tool_fn = tool_registry.get(tool_name)
            if tool_fn is None:
                return step, tool_name, tool_args, None, f"Tool '{tool_name}' not found"

            try:
                async with trace_agent_step(
                    f"tool:{tool_name}",
                    trace_id,
                    doctor_id=str(state.get("doctor_id")) if state.get("doctor_id") else None,
                    patient_id=str(state.get("patient_id")) if state.get("patient_id") else None,
                    input_data={"tool": tool_name, "args": tool_args},
                ) as span:
                    result = await tool_fn(**tool_args)
                    if span:
                        span.set_output({"status": "ok", "result_preview": str(result)[:200]})
                return step, tool_name, tool_args, result, None
            except Exception as exc:
                logger.error("Tool %s failed: %s", tool_name, exc)
                return step, tool_name, tool_args, None, str(exc)

        outcomes = await _asyncio.gather(*(_run_one(s) for s in ready))

        any_error = False
        for step, tool_name, tool_args, result, err in outcomes:
            tc = AgentToolCall(
                tool_name=tool_name,
                tool_args=tool_args,
                result=result,
                error=err,
            )
            tc["step_id"] = step.get("id")
            state["tool_calls"].append(tc)
            if err:
                any_error = True
                state["error_count"] = state.get("error_count", 0) + 1
                state["trace_events"].append(f"Executor: {tool_name} ERROR — {str(err)[:100]}")
            else:
                state["trace_events"].append(f"Executor: {tool_name} OK")
                if tool_name == "retrieve_patient_context" and result:
                    state["retrieved_context"] = result
                    state["citations"] = result.get("citations", [])
                elif tool_name in ("analyze_image", "compare_images"):
                    state["analysis_result"] = result
            executed_ids.add(step.get("id"))

        state["current_step"] = len(executed_ids)

        if any_error:
            return "critic"
        remaining = [s for s in plan if s.get("id") not in executed_ids]
        return "execute" if remaining else "critic"

    async def _executor_node_LEGACY_UNUSED(self, state: AgentState) -> str:
        """(Superseded by DAG executor above — kept temporarily as a reference
        for the sequential shape. Safe to delete after P3.30 is verified.)"""
        plan = state.get("plan", [])
        step_idx = state["current_step"]
        trace_id = state.get("trace_id", str(uuid.uuid4()))

        if step_idx >= len(plan):
            self._add_trace(state, "All steps completed")
            return "critic"

        step = plan[step_idx]
        tool_name = step["tool"]
        tool_args = dict(step["args"])  # copy to avoid mutating plan

        # Inject doctor_id from state for tools that need it
        if state.get("doctor_id"):
            tool_args.setdefault("doctor_id", str(state["doctor_id"]))

        # Resolve dependency results
        for dep_id in step.get("depends_on", []):
            for tc in state.get("tool_calls", []):
                if tc.get("step_id") == dep_id and tc.get("result"):
                    # Fill in dependency for tools that need context
                    if tool_name == "synthesize_response":
                        tool_args["context"] = tc["result"]
                    break

        self._add_trace(state, f"Executing step {step_idx + 1}/{len(plan)}: {tool_name}")

        tool_fn = tool_registry.get(tool_name)
        if tool_fn is None:
            error_msg = f"Tool '{tool_name}' not found"
            state["tool_calls"].append(
                AgentToolCall(
                    tool_name=tool_name,
                    tool_args=tool_args,
                    result=None,
                    error=error_msg,
                )
            )
            state["error_count"] = state.get("error_count", 0) + 1
            state["trace_events"].append(f"Executor: {tool_name} FAILED — {error_msg}")
            state["current_step"] = step_idx + 1
            return "critic"

        # Trace tool execution
        async with trace_agent_step(
            f"tool:{tool_name}",
            trace_id,
            doctor_id=str(state.get("doctor_id")) if state.get("doctor_id") else None,
            patient_id=str(state.get("patient_id")) if state.get("patient_id") else None,
            input_data={"tool": tool_name, "args": tool_args},
        ) as span:
            try:
                result = await tool_fn(**tool_args)
                state["tool_calls"].append(
                    AgentToolCall(
                        tool_name=tool_name,
                        tool_args=tool_args,
                        result=result,
                        error=None,
                    )
                )
                state["trace_events"].append(f"Executor: {tool_name} OK")

                # Store context for downstream use
                if tool_name == "retrieve_patient_context":
                    state["retrieved_context"] = result
                    state["citations"] = result.get("citations", [])
                elif tool_name in ("analyze_image", "compare_images"):
                    state["analysis_result"] = result

                if span:
                    span.set_output({"status": "ok", "result_preview": str(result)[:200]})

            except Exception as exc:
                logger.error("Tool %s failed: %s", tool_name, exc)
                state["tool_calls"].append(
                    AgentToolCall(
                        tool_name=tool_name,
                        tool_args=tool_args,
                        result=None,
                        error=str(exc),
                    )
                )
                state["error_count"] = state.get("error_count", 0) + 1
                state["trace_events"].append(f"Executor: {tool_name} ERROR \u2014 {str(exc)[:100]}")
                if span:
                    span.set_output({"status": "error", "error": str(exc)})
                    span.set_error(str(exc))
                # Stop execution — go to critic for evaluation
                state["current_step"] = step_idx + 1
                return "critic"

        state["current_step"] = step_idx + 1
        # Track which steps have been executed (for re-plan deduplication)
        if "executed_step_ids" not in state:
            state["executed_step_ids"] = set()
        state["executed_step_ids"].add(step["id"])
        return "execute"

    async def _critic_node(self, state: AgentState) -> str:
        """Feature B: Evaluate execution and decide re-plan or finish."""
        self._add_trace(state, "Critic evaluating execution")

        plan_steps = state.get("plan", [])
        tool_calls = state.get("tool_calls", [])
        errors = [tc.get("error", "") for tc in tool_calls if tc.get("error")]
        executed_ids = state.get("executed_step_ids", set())

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

            # Filter out already-executed successful steps to avoid re-execution
            new_steps = []
            for step in revised.get("steps", plan_steps):
                step_id = step.get("id")
                # Only include steps that haven't been executed successfully
                if step_id not in executed_ids:
                    new_steps.append(step)
                else:
                    # Check if the step had an error - if so, allow retry
                    failed = any(tc.get("tool_name") == step.get("tool") and tc.get("error") for tc in tool_calls)
                    if failed:
                        new_steps.append(step)

            if not new_steps:
                # Nothing new to execute, finish
                state["trace_events"].append("Re-plan: no new steps to execute, finishing")
                return "synthesize"

            state["plan"] = new_steps
            state["current_step"] = 0
            state["trace_events"].append(
                f"Re-plan (round {state['replan_count']}): {revised['goal'][:80]} — {len(new_steps)} new step(s)"
            )
            return "execute"

        return "synthesize"

    async def _synthesizer_node(self, state: AgentState) -> str:
        """Decide the response source. Actual token emission happens in run_stream
        so we can stream from Maverick directly when appropriate (P0.4).

        Three response sources, in preference order:
          1. A tool already produced the final answer (synthesize_response
             tool with a non-empty result) — reuse it verbatim.
          2. We have retrieval context and Maverick is configured — set a
             streaming flag; run_stream will call synthesize_stream() and
             yield tokens as they arrive from NIM/Groq.
          3. Fallback — the static context summary in _build_response.
        """
        self._add_trace(state, "Synthesizing final response")

        # 1. Tool-produced answer takes priority.
        for tc in reversed(state.get("tool_calls", [])):
            if tc["tool_name"] == "synthesize_response" and tc["result"]:
                result = tc["result"]
                if isinstance(result, dict):
                    draft = result.get("response", "") or result.get("content", "")
                else:
                    draft = str(result)
                if draft:
                    citations = state.get("citations", [])
                    if citations and draft:
                        draft = validate_citations(draft, citations)
                        state["trace_events"].append("Synthesizer: citations validated")
                    state["draft"] = draft
                    state["stream_from_llm"] = False
                    state["trace_events"].append("Synthesizer: used tool-generated response")
                    return "respond"

        # 2. Stream directly from Maverick when possible — this is the P0.4 fast path.
        if self.synthesizer._client is not None or self.synthesizer._groq_client is not None:
            state["stream_from_llm"] = True
            state["trace_events"].append("Synthesizer: streaming from LLM")
            return "respond"

        # 3. Static fallback — no LLM configured.
        state["draft"] = self._build_response(state)
        state["stream_from_llm"] = False
        state["trace_events"].append("Synthesizer: context response built")
        return "respond"

    def _build_response(self, state: AgentState) -> str:
        """Build response from tool results and context."""
        context = state.get("retrieved_context", {})
        results = context.get("results", []) if isinstance(context, dict) else []
        citations = state.get("citations", [])

        if results:
            lines = ["Based on the patient record, here's what I found:\n"]
            for r in results[:5]:
                vn = r.get("version_number", "?")
                ts = str(r.get("timestamp", ""))[:10]
                summary = r.get("summary", "")
                score = r.get("score", 0)
                lines.append(f"[v{vn}  ·  {ts}] {summary}  (relevance: {score:.3f})")
            lines.append(f"\nRetrieved {len(results)} relevant version(s).")
            lines.append("\n*Verified by AI · Doctor review recommended.*")
            return "\n".join(lines)

        return (
            f"I processed your request about '{state['user_query']}'.\n\n"
            f"*Verified by AI · Doctor review recommended.*"
        )

    async def _responder_node(self, state: AgentState) -> str:
        """Final formatting."""
        self._add_trace(state, "Finalizing response")
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

        All mutable state lives in the per-request AgentState dict, so
        multiple concurrent calls to run_stream do not interfere.

        Yields:
            {"type": "trace", "message": str}
            {"type": "token", "text": str}
            {"type": "done", "response": str, "trace_events": [...], ...}
            {"type": "error", "message": str}
        """
        state = create_initial_state(user_query, doctor_id, patient_id, conversation_id)
        state["replan_count"] = 0

        # Look up real patient name once for re-association (sub-millisecond)
        patient_name = await get_patient_name_for_reassociation(patient_id) if patient_id else None

        # Create the parent Langfuse trace up-front so every child span
        # (router / planner / executor / critic / synthesizer) has a real trace
        # to attach to. Without this, Langfuse v2 SDK drops orphan spans
        # silently — which is what happened before this line existed.
        trace_id = str(uuid.uuid4())
        state["trace_id"] = trace_id
        langfuse_client.create_trace(
            name="agent_run",
            user_id=str(doctor_id),
            session_id=conversation_id,
            input_data={"query": user_query, "patient_id": str(patient_id) if patient_id else None},
            metadata={
                "doctor_id": str(doctor_id),
                "patient_id": str(patient_id) if patient_id else None,
                "conversation_id": conversation_id,
            },
            tags=["agent", "chat"],
            trace_id=trace_id,
        )

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
        yield {"type": "trace", "message": "Understanding your request..."}

        while current_node != "END":
            fn = node_fns.get(current_node)
            if not fn:
                yield {"type": "error", "message": f"Unknown node: {current_node}"}
                break

            try:
                self._add_trace(state, f"Entering node: {current_node}")
                yield {"type": "trace", "message": self._node_label(current_node)}

                next_node = await fn(state)

                # ─── P0.4: streaming synthesis emission ───
                if current_node == "synthesize":
                    if state.get("stream_from_llm"):
                        # Stream tokens directly from Maverick as they arrive.
                        # This makes first-token latency <2s instead of ~30s.
                        context = state.get("retrieved_context") or {}
                        patient_context = context.get("patient_context") if isinstance(context, dict) else None
                        accumulated = ""
                        try:
                            async for chunk in self.synthesizer.synthesize_stream(
                                query=state["user_query"],
                                context=context,
                                patient_context=patient_context,
                            ):
                                # Re-associate pseudonym token-by-token; safe on partial text.
                                out = reassociate_pseudonym(chunk, patient_name) if patient_name else chunk
                                accumulated += out
                                yield {"type": "token", "text": out}
                        except Exception as exc:
                            logger.exception("Streaming synthesis failed: %s", exc)
                            fallback = self._build_response(state)
                            if patient_name:
                                fallback = reassociate_pseudonym(fallback, patient_name)
                            yield {"type": "token", "text": fallback}
                            accumulated = fallback
                        # Validate citations on the completed text.
                        citations = state.get("citations", [])
                        if citations and accumulated:
                            accumulated = validate_citations(accumulated, citations)
                        state["draft"] = accumulated
                    elif state.get("draft"):
                        # Non-streaming path: word-buffer the pre-computed draft.
                        draft = state["draft"]
                        if patient_name:
                            draft = reassociate_pseudonym(draft, patient_name)
                            state["draft"] = draft
                        words = draft.split(" ")
                        buffer = ""
                        for word in words:
                            test = buffer + (" " if buffer else "") + word
                            if len(test) >= 80:
                                if buffer:
                                    yield {"type": "token", "text": buffer + " "}
                                buffer = word
                            else:
                                buffer = test
                        if buffer:
                            yield {"type": "token", "text": buffer}

                current_node = next_node

            except Exception as exc:
                logger.exception("Agent node '%s' failed", current_node)
                yield {"type": "error", "message": f"Agent error in {current_node}: {str(exc)}"}
                state["error_count"] = (state.get("error_count", 0)) + 1
                if state["error_count"] >= state.get("max_retries", 2):
                    break
                node_idx = node_sequence.index(current_node) if current_node in node_sequence else -1
                if node_idx >= 0 and node_idx + 1 < len(node_sequence):
                    current_node = node_sequence[node_idx + 1]
                else:
                    current_node = "synthesize"
                continue

        # Re-associate pseudonym in final response
        final_response = state.get("final_response", "I encountered an error processing your request.")
        if patient_name:
            final_response = reassociate_pseudonym(final_response, patient_name)

        yield {
            "type": "done",
            "response": final_response,
            "intent": state.get("intent", AgentIntent.GENERAL_CHAT).value if state.get("intent") else "unknown",
            "trace_events": state.get("trace_events", []),
            "citations": state.get("citations", []),
            "replan_count": state.get("replan_count", 0),
            "took_ms": (
                (datetime.now(timezone.utc) - state["started_at"]).total_seconds() * 1000
                if state.get("started_at")
                else 0
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
