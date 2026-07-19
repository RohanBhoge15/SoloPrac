"""LangGraph Agent — Main Graph with Router → Plan → Execute → Synthesize → Respond.

The agent processes user queries through a directed graph:
  1. Router node — classifies intent (delegates to IntentRouter)
  2. Planner node — Maverick generates a step-by-step execution plan (Feature B)
  3. Executor node — runs tool calls with retry + error handling
  4. Synthesizer node — Maverick produces the final answer (Feature A grounding)
  5. Responder node — formats + streams the response

Graph structure (LangGraph):
    START → router → [plan → execute → synthesize → respond] → END
                          ↑__________| (re-plan on critic failure)

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

logger = logging.getLogger(__name__)


class AgentGraph:
    """Main agent graph — orchestrates the complete doctor-assistant flow.

    Does NOT use LangGraph's graph builder directly (to keep imports lightweight).
    Instead, uses a state-machine pattern where each node is an async method
    that returns the next node name. Compatible with SSE streaming.
    """

    def __init__(self):
        self.router = IntentRouter()
        self._trace: List[str] = []

    def _reset_trace(self):
        self._trace = []

    def _add_trace(self, event: str):
        self._trace.append(event)
        logger.debug("[Agent] %s", event)

    async def _router_node(self, state: AgentState) -> str:
        """Classify user intent and set the direction."""
        self._add_trace(f"Routing query: '{state['user_query'][:60]}...'")
        intent, confidence, reasoning = await self.router.classify(state["user_query"])

        state["intent"] = intent
        state["confidence"] = confidence
        state["reasoning"] = reasoning
        state["trace_events"].append(f"Router: {intent.value} (conf={confidence:.2f})")

        logger.info("Intent: %s (conf=%.2f) — %s", intent.value, confidence, reasoning)
        return "plan"

    async def _planner_node(self, state: AgentState) -> str:
        """Generate or infer the execution plan based on intent."""
        self._add_trace(f"Planning execution for {state['intent'].value}")

        # Build plan based on intent
        steps = []
        intent = state["intent"]

        if intent == AgentIntent.PATIENT_QA and state.get("patient_id"):
            steps = [
                {"step_id": 1, "tool": "retrieve_patient_context", "args": {
                    "patient_id": str(state["patient_id"]),
                    "query": state["user_query"],
                }, "depends_on": []},
                {"step_id": 2, "tool": "synthesize_response", "args": {
                    "context": None,  # filled by step 1
                    "query": state["user_query"],
                }, "depends_on": [1]},
            ]
        elif intent == AgentIntent.IMAGE_ANALYSIS:
            steps = [
                {"step_id": 1, "tool": "analyze_image", "args": {}, "depends_on": []},
                {"step_id": 2, "tool": "synthesize_response", "args": {}, "depends_on": [1]},
            ]
        elif intent == AgentIntent.IMAGE_COMPARE:
            steps = [
                {"step_id": 1, "tool": "compare_images", "args": {}, "depends_on": []},
                {"step_id": 2, "tool": "synthesize_response", "args": {}, "depends_on": [1]},
            ]
        elif intent == AgentIntent.PRESCRIPTION:
            steps = [
                {"step_id": 1, "tool": "generate_prescription", "args": {}, "depends_on": []},
            ]
        elif intent == AgentIntent.GENERAL_CHAT:
            steps = [
                {"step_id": 1, "tool": "synthesize_response", "args": {
                    "context": {"mode": "general_chat"},
                    "query": state["user_query"],
                }, "depends_on": []},
            ]
        else:
            # Default: just synthesize
            steps = [
                {"step_id": 1, "tool": "synthesize_response", "args": {
                    "context": {"intent": intent.value},
                    "query": state["user_query"],
                }, "depends_on": []},
            ]

        state["plan"] = steps
        state["current_step"] = 0
        state["trace_events"].append(f"Planner: {len(steps)} step(s) planned")
        return "execute"

    async def _executor_node(self, state: AgentState) -> str:
        """Execute the current step's tool call."""
        plan = state.get("plan", [])
        step_idx = state["current_step"]

        if step_idx >= len(plan):
            self._add_trace("All steps completed")
            return "synthesize"

        step = plan[step_idx]
        tool_name = step["tool"]
        tool_args = step["args"]

        # Check dependencies
        dep_ids = step.get("depends_on", [])
        for dep_id in dep_ids:
            dep_step = plan[dep_id - 1] if dep_id - 1 < len(plan) else None
            if dep_step and dep_step.get("_result") is None:
                logger.warning("Step %d depends on step %d which hasn't run", step_idx + 1, dep_id)
                # Fill in dependency results from previous tool calls
                for tc in state.get("tool_calls", []):
                    if tc["tool_name"] == dep_step["tool"]:
                        step["args"]["context"] = tc["result"]
                        break

        self._add_trace(f"Executing step {step_idx + 1}: {tool_name}")

        # Look up tool
        tool_fn = tool_registry.get(tool_name)
        if tool_fn is None:
            error_msg = f"Tool '{tool_name}' not found in registry"
            logger.error(error_msg)
            state["tool_calls"].append(AgentToolCall(
                tool_name=tool_name,
                tool_args=tool_args,
                result=None,
                error=error_msg,
            ))
            state["error_count"] = state.get("error_count", 0) + 1
            state["trace_events"].append(f"Executor: {tool_name} FAILED — {error_msg}")

            if state["error_count"] >= state.get("max_retries", 2):
                return "synthesize"
            return "execute"

        # Execute tool
        try:
            result = await tool_fn(**tool_args)
            state["tool_calls"].append(AgentToolCall(
                tool_name=tool_name,
                tool_args=tool_args,
                result=result,
                error=None,
            ))
            step["_result"] = result
            state["trace_events"].append(f"Executor: {tool_name} OK")

            # Store context for synthesis
            if tool_name == "retrieve_patient_context":
                state["retrieved_context"] = result
            elif tool_name in ("analyze_image", "compare_images"):
                state["analysis_result"] = result

        except Exception as exc:
            logger.error("Tool %s failed: %s", tool_name, exc)
            state["tool_calls"].append(AgentToolCall(
                tool_name=tool_name,
                tool_args=tool_args,
                result=None,
                error=str(exc),
            ))
            state["error_count"] = state.get("error_count", 0) + 1
            state["trace_events"].append(f"Executor: {tool_name} ERROR — {str(exc)[:100]}")

            if state["error_count"] >= state.get("max_retries", 2):
                return "synthesize"

        state["current_step"] = step_idx + 1

        if state["current_step"] >= len(plan):
            return "synthesize"
        return "execute"

    async def _synthesizer_node(self, state: AgentState) -> str:
        """Generate the final response using Maverick or fallback."""
        self._add_trace("Synthesizing final response")

        # Gather context from tool results
        context_parts = []
        if state.get("retrieved_context"):
            context_parts.append(f"Retrieved context: {json.dumps(state['retrieved_context'], indent=2)[:2000]}")
        if state.get("analysis_result"):
            context_parts.append(f"Analysis: {json.dumps(state['analysis_result'], indent=2)[:1000]}")

        tool_results = state.get("tool_calls", [])
        if tool_results:
            last_tool = tool_results[-1]
            if last_tool["result"] and last_tool["tool_name"] == "synthesize_response":
                # Tool already generated the response
                draft = last_tool["result"].get("response", "") if isinstance(last_tool["result"], dict) else str(last_tool["result"])
                state["draft"] = draft
                state["trace_events"].append("Synthesizer: used tool-generated response")
                return "respond"

        # Build fallback response from intent + context
        intent = state.get("intent", AgentIntent.GENERAL_CHAT)
        if intent == AgentIntent.PATIENT_QA:
            state["draft"] = self._build_qa_response(state)
        elif intent == AgentIntent.GENERAL_CHAT:
            state["draft"] = self._build_chat_response(state)
        elif intent == AgentIntent.IMAGE_ANALYSIS:
            state["draft"] = "Image analysis feature will be available in Week 8/9."
        elif intent == AgentIntent.SCHEDULING:
            state["draft"] = "Voice scheduling will be available in Week 10/11."
        else:
            state["draft"] = f"I understand you're asking about '{state['user_query']}'. This feature is being prepared."

        state["trace_events"].append("Synthesizer: fallback response generated")
        return "respond"

    def _build_qa_response(self, state: AgentState) -> str:
        """Build a QA response from retrieved context."""
        context = state.get("retrieved_context", {})
        if context and context.get("status") != "not_implemented":
            return f"Based on the patient record: {json.dumps(context, indent=2)[:1000]}"

        patient_id = state.get("patient_id")
        if patient_id:
            return (
                f"I can help you with patient information. "
                f"I see patient ID {patient_id} is selected. "
                f"To give you a detailed answer about '{state['user_query']}', "
                f"I need the Temporal RAG system (Feature A) which will be active in Week 6."
            )
        return (
            f"You asked: '{state['user_query']}'. "
            f"Please select a patient first so I can look up their records."
        )

    def _build_chat_response(self, state: AgentState) -> str:
        """Build a general chat response."""
        query = state["user_query"]
        if "help" in query.lower() or "what can you" in query.lower():
            return (
                "I'm your AI clinical assistant. I can help you with:\n\n"
                "1. **Patient Q&A** — Ask about a patient's history, vitals, trends\n"
                "2. **Image Analysis** — Analyze X-rays, wound photos, skin conditions (coming Week 8)\n"
                "3. **Document Parsing** — Extract data from uploaded documents (coming Week 7)\n"
                "4. **Prescriptions** — Generate AI-assisted prescriptions (coming Week 9)\n"
                "5. **Scheduling** — Voice and text-based appointment management (coming Week 10)\n\n"
                "Select a patient from the sidebar to get started!"
            )
        return (
            f"I received your message. To best assist you, I can help with patient questions, "
            f"image analysis, document processing, prescriptions, and scheduling. "
            f"Try asking about a specific patient or use a command from the palette (Cmd+K)."
        )

    async def _responder_node(self, state: AgentState) -> str:
        """Final formatting and metadata."""
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
        """Run the agent graph and yield events as they happen.

        Yields:
            {"type": "trace", "message": str}
            {"type": "token", "text": str}  — streaming tokens from synthesis
            {"type": "done", "response": str, "trace_events": [...]}
            {"type": "error", "message": str}
        """
        self._reset_trace()
        state = create_initial_state(user_query, doctor_id, patient_id, conversation_id)

        node_sequence = ["router", "plan", "execute", "synthesize", "respond"]
        node_fns = {
            "router": self._router_node,
            "plan": self._planner_node,
            "execute": self._executor_node,
            "synthesize": self._synthesizer_node,
            "respond": self._responder_node,
        }

        current_node = "router"

        yield {"type": "trace", "message": f"Agent starting — classifying your request..."}

        while current_node != "END":
            fn = node_fns.get(current_node)
            if not fn:
                yield {"type": "error", "message": f"Unknown node: {current_node}"}
                break

            try:
                self._add_trace(f"Entering node: {current_node}")
                yield {"type": "trace", "message": self._node_label(current_node)}

                next_node = await fn(state)

                # If we're in synthesize and have a draft, stream it token-style
                if current_node == "synthesize" and state.get("draft"):
                    draft = state["draft"]
                    # Yield in chunks for smooth streaming
                    chunk_size = 80
                    for i in range(0, len(draft), chunk_size):
                        chunk = draft[i:i + chunk_size]
                        yield {"type": "token", "text": chunk}

                current_node = next_node

            except Exception as exc:
                logger.exception("Agent node '%s' failed", current_node)
                yield {"type": "error", "message": f"Agent error in {current_node}: {str(exc)}"}
                state["error_count"] = (state.get("error_count", 0)) + 1
                if state["error_count"] >= state.get("max_retries", 2):
                    break
                # Retry current node
                continue

        yield {
            "type": "done",
            "response": state.get("final_response", "I encountered an error processing your request."),
            "intent": state.get("intent", AgentIntent.GENERAL_CHAT).value if state.get("intent") else "unknown",
            "trace_events": state.get("trace_events", []),
            "took_ms": (
                (datetime.now(timezone.utc) - state["started_at"]).total_seconds() * 1000
                if state.get("started_at") else 0
            ),
        }

    def _node_label(self, node: str) -> str:
        labels = {
            "router": "🧠 Understanding your request...",
            "plan": "📋 Planning the approach...",
            "execute": "🔍 Searching records...",
            "synthesize": "✍️ Drafting response...",
            "respond": "✅ Finalizing...",
        }
        return labels.get(node, f"Processing ({node})...")
