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
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.agents.graph import AgentGraph
from app.agents.synthesizer import MaverickSynthesizer
from app.agents.tools import tool_registry
from app.dependencies import get_current_doctor

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
                    "data": json.dumps(
                        {
                            "response": event.get("response", ""),
                            "intent": event.get("intent", "unknown"),
                            "trace_events": event.get("trace_events", []),
                            "citations": event.get("citations", []),
                            "took_ms": event.get("took_ms", 0),
                        }
                    ),
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


@router.get("/citation-url")
async def get_citation_url(
    s3_key: str,
    doctor=Depends(get_current_doctor),
):
    """Redirect to a presigned URL for a citation's S3 object.

    The key layout doubles as a bucket-inference hint:
      - `images/…`    → images bucket
      - `documents/…` → documents bucket
      - anything else → pdfs bucket (default, used for prescriptions/invoices/certs)
    """
    from fastapi.responses import RedirectResponse

    from app.services.storage import storage_service

    if not s3_key:
        raise HTTPException(status_code=400, detail="s3_key is required")

    # Infer bucket from key prefix; strip prefix so bucket_type + object key line up
    prefix, _, rest = s3_key.partition("/")
    if prefix == "images":
        bucket, obj_key = "images", rest
    elif prefix == "documents":
        bucket, obj_key = "documents", rest
    else:
        bucket, obj_key = "pdfs", s3_key

    # Confirm the object exists first; 404 is the correct signal to callers.
    if not await storage_service.file_exists(bucket, obj_key):
        raise HTTPException(status_code=404, detail="Citation not found")

    try:
        url = await storage_service.get_presigned_url(bucket, obj_key, expires_in=3600)
        if not url:
            raise HTTPException(status_code=404, detail="Citation not found")
        return RedirectResponse(url=url, status_code=307)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to generate presigned URL for %s: %s", s3_key, exc)
        raise HTTPException(status_code=500, detail="Failed to generate citation URL")
