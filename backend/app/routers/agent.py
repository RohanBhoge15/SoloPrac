"""Agent Chat Router — SSE streaming endpoint for the LangGraph agent.

Provides:
  POST /api/v1/agent/chat  — Send a message, receive SSE stream with agent traces + tokens
  GET  /api/v1/agent/health — Agent health check (NIM connectivity, tool registry)

The SSE stream yields typed events:
  event: trace    — Agent status update ("Searching records...", "Drafting response...")
  event: token    — Streaming text chunk from Maverick synthesis
  event: done     — Final response + metadata + trace_events
  event: error    — Error message
"""

from __future__ import annotations

import json
import uuid
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sse_starlette.sse import EventSourceResponse

from app.dependencies import get_current_doctor
from app.agents.graph import AgentGraph
from app.agents.synthesizer import MaverickSynthesizer
from app.agents.tools import tool_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])

# Global agent instance (reused across requests)
_agent = AgentGraph()
_synthesizer = MaverickSynthesizer()


@router.post("/chat")
async def agent_chat(
    body: dict,
    doctor=Depends(get_current_doctor),
):
    """Send a chat message to the agent. Returns SSE stream with traces + tokens.

    Request body:
    {
        "query": "What is Priya Sharma's BP trend?",
        "patient_id": "uuid (optional)",
        "conversation_id": "string (optional)"
    }

    Response: Server-Sent Events stream
    """
    query = body.get("query", "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")

    patient_id_str = body.get("patient_id")
    patient_id = uuid.UUID(patient_id_str) if patient_id_str else None
    conversation_id = body.get("conversation_id")

    async def event_generator():
        async for event in _agent.run_stream(
            user_query=query,
            doctor_id=doctor.id,
            patient_id=patient_id,
            conversation_id=conversation_id,
        ):
            event_type = event.get("type", "message")

            if event_type == "trace":
                yield {"event": "trace", "data": json.dumps({"message": event["message"]})}

            elif event_type == "token":
                yield {"event": "token", "data": json.dumps({"text": event["text"]})}

            elif event_type == "done":
                yield {
                    "event": "done",
                    "data": json.dumps({
                        "response": event.get("response", ""),
                        "intent": event.get("intent", "unknown"),
                        "trace_events": event.get("trace_events", []),
                        "took_ms": event.get("took_ms", 0),
                    }),
                }

            elif event_type == "error":
                yield {"event": "error", "data": json.dumps({"message": event["message"]})}

    return EventSourceResponse(event_generator())


@router.get("/rate-limit")
async def agent_rate_limit(
    doctor=Depends(get_current_doctor),
):
    """Get LLM rate limit usage for the current doctor."""
    # Get per-doctor LLM usage from the shared rate limiter
    from app.agents.tools import _llm_limiter as llm
    stats = llm.get_stats(str(doctor.id))
    return {
        **stats,
        "description": "Per-doctor LLM API rate limiting. Calls reset every 60 seconds.",
    }


@router.get("/health")
async def agent_health():
    """Check if the agent system is ready."""
    tools = tool_registry.list_tools()
    return {
        "status": "ok",
        "nim_configured": _synthesizer.is_available,
        "tools_registered": len(tools),
        "tools": [t["name"] for t in tools],
    }
