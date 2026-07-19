"""Tool registry — all agent-accessible tools register here.

Week 6: Tools now wired to real implementations:
  - retrieve_patient_context → TemporalMultimodalRetriever (Feature A)
  - synthesize_response → MaverickSynthesizer with citations
"""

from __future__ import annotations

import logging
from uuid import UUID
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol

from app.config import settings
from app.database import async_session_maker
from app.services.temporal_rag import TemporalMultimodalRetriever
from app.services.rag_audit import RAGAuditService, LLMRateLimiter, validate_no_future_leak
from app.agents.synthesizer import MaverickSynthesizer

logger = logging.getLogger(__name__)

# Global audit and rate limit services
_rag_audit = RAGAuditService()
_llm_limiter = LLMRateLimiter()


@runtime_checkable
class AgentTool(Protocol):
    """Protocol for agent tools."""
    name: str
    description: str
    parameters: dict

    async def __call__(self, **kwargs) -> Any: ...


class ToolRegistry:
    """Registry that tools self-register into via @tool decorator."""

    def __init__(self):
        self._tools: Dict[str, AgentTool] = {}

    def register(self, tool: AgentTool) -> AgentTool:
        self._tools[tool.name] = tool
        logger.info("Registered tool: %s", tool.name)
        return tool

    def get(self, name: str) -> Optional[AgentTool]:
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {"name": t.name, "description": t.description, "parameters": t.parameters}
            for t in self._tools.values()
        ]

    def __contains__(self, name: str) -> bool:
        return name in self._tools


tool_registry = ToolRegistry()
_rag_retriever = TemporalMultimodalRetriever()
_synthesizer = MaverickSynthesizer()


def tool(name: str, description: str, parameters: dict):
    """Decorator to register a tool."""
    def decorator(func):
        func.name = name
        func.description = description
        func.parameters = parameters
        tool_registry.register(func)
        return func
    return decorator


# ─── Feature A: Temporal Multimodal RAG ───

@tool(
    name="retrieve_patient_context",
    description=(
        "Retrieve patient medical context using temporal-aware multimodal RAG. "
        "Searches across text (MedCPT), hybrid (BGE-M3 dense+sparse), and image (NV-CLIP) "
        "vectors with temporal decay weighting and clinical significance scoring."
    ),
    parameters={
        "type": "object",
        "properties": {
            "patient_id": {"type": "string", "format": "uuid"},
            "query": {"type": "string"},
            "k": {"type": "integer", "default": 8},
        },
        "required": ["patient_id", "query"],
    },
)
async def retrieve_patient_context(patient_id: str, query: str, k: int = 8, **kwargs) -> dict:
    """Feature A: Temporal-aware multimodal retrieval with audit + leak check."""
    if not patient_id or not query:
        return {"status": "error", "message": "patient_id and query are required"}

    doctor_id = kwargs.get("doctor_id", "")
    if not doctor_id:
        logger.warning("retrieve_patient_context: no doctor_id provided")
        return {"status": "ok", "results": [], "citations": [], "meta": {"note": "No doctor_id"}}

    try:
        result = await _rag_retriever.retrieve(
            query=query,
            patient_id=patient_id,
            doctor_id=doctor_id,
            query_time=datetime.now(timezone.utc),
            k=k,
        )
        results_data = result.get("results", [])
        citations_data = result.get("citations", [])
        meta = result.get("meta", {})

        # Future-leak validation (Dev: zero future-leak enforcement)
        leak_check = validate_no_future_leak(results_data, datetime.now(timezone.utc))
        if not leak_check["passed"]:
            logger.error("FUTURE LEAK DETECTED: %d version(s) from the future!", leak_check["leaked"])

        # RAG audit logging (Dev: every retrieval logged)
        try:
            async with async_session_maker() as db:
                scores = [r.get("score", 0) for r in results_data]
                await _rag_audit.log_retrieval(
                    db_session=db,
                    doctor_id=UUID(doctor_id) if doctor_id else None,
                    patient_id=patient_id,
                    query=query,
                    modalities_used=meta.get("modalities_used", 0),
                    num_results=len(results_data),
                    latency_ms=meta.get("took_ms", 0),
                    min_score=min(scores) if scores else 0,
                    max_score=max(scores) if scores else 0,
                    future_leak_count=leak_check["leaked"],
                    citation_ids=[c.get("version_number", "") for c in citations_data],
                )
        except Exception as audit_exc:
            logger.warning("RAG audit log failed (non-blocking): %s", audit_exc)

        return {
            "status": "ok",
            "results": results_data,
            "citations": citations_data,
            "meta": {**meta, "future_leak_check": leak_check},
        }
    except Exception as exc:
        logger.error("Temporal RAG retrieval failed: %s", exc)
        return {
            "status": "error",
            "message": str(exc)[:200],
            "results": [],
            "citations": [],
        }


# ─── Maverick Synthesis with Citations ───

@tool(
    name="synthesize_response",
    description="Generate a response using Maverick LLM with version citations",
    parameters={
        "type": "object",
        "properties": {
            "context": {"type": "object", "description": "Retrieved context + citations"},
            "query": {"type": "string", "description": "Original user query"},
        },
        "required": ["context", "query"],
    },
)
async def synthesize_response(context: dict, query: str, **kwargs) -> dict:
    """Generate a response with Maverick, incorporating cited versions."""
    doctor_id = kwargs.get("doctor_id", "")

    # Dev: per-doctor LLM rate limiting
    if doctor_id:
        allowed, info = await _llm_limiter.check_rate_limit(doctor_id)
        if not allowed:
            logger.warning("LLM rate limit exceeded for doctor %s: %d RPM", doctor_id, info["current_rpm"])
            return _build_fallback_response(context, query)

    if not _synthesizer.is_available:
        if doctor_id:
            await _llm_limiter.record_call(doctor_id)
        return _build_fallback_response(context, query)

    try:
        patient_context = context.get("patient_context", {})
        citations = context.get("citations", [])

        # Record LLM call for rate limiting
        if doctor_id:
            await _llm_limiter.record_call(doctor_id)

        response = await _synthesizer.synthesize(
            query=query,
            context=context,
            patient_context=patient_context,
            citations=citations,
        )
        return response
    except Exception as exc:
        logger.error("Synthesis failed: %s", exc)
        return _build_fallback_response(context, query)


def _build_fallback_response(context: dict, query: str) -> dict:
    """Build a readable fallback from retrieved context when Maverick unavailable."""
    results = context.get("results", [])
    citations = context.get("citations", [])
    if not results:
        return {
            "response": "I don't have enough information to answer that. Please try a more specific query.",
            "citations": [],
            "model": "fallback",
        }
    lines = [f"Based on the patient record, here's what I found for: {query}\n"]
    for r in results[:5]:
        lines.append(
            f"[v{r.get('version_number', '?')}  ·  {str(r.get('timestamp', ''))[:10]}] "
            f"{r.get('summary', '')}  (score: {r.get('score', 0):.3f})"
        )
    lines.append(f"\nShowing {min(len(results), 5)} of {len(results)} results.")
    lines.append("\n*AI Suggestion — Requires Doctor Validation.*")
    return {"response": "\n".join(lines), "citations": citations, "model": "fallback"}


# ─── Stubs for future weeks ───

@tool(
    name="analyze_image",
    description="Analyze a medical image using Groq 90B-V or MedGemma-4B",
    parameters={
        "type": "object",
        "properties": {
            "image_path": {"type": "string"},
            "image_type": {"type": "string", "enum": ["xray", "ct", "mri", "wound", "dermatology", "other"]},
        },
        "required": ["image_path", "image_type"],
    },
)
async def analyze_image(image_path: str, image_type: str, **kwargs) -> dict:
    """Vision analysis — built Week 9."""
    return {"status": "not_implemented"}


@tool(
    name="compare_images",
    description="Compare two images using ORB feature matching (wound progression)",
    parameters={
        "type": "object",
        "properties": {
            "patient_id": {"type": "string", "format": "uuid"},
            "image_paths": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["patient_id", "image_paths"],
    },
)
async def compare_images(patient_id: str, image_paths: list, **kwargs) -> dict:
    """ORB image registration — built Week 8."""
    return {"status": "not_implemented"}


@tool(
    name="generate_prescription",
    description="Generate an AI-drafted prescription card",
    parameters={
        "type": "object",
        "properties": {
            "patient_id": {"type": "string", "format": "uuid"},
            "diagnosis": {"type": "string"},
        },
        "required": ["patient_id", "diagnosis"],
    },
)
async def generate_prescription(patient_id: str, diagnosis: str, **kwargs) -> dict:
    """Prescription box — built Week 9."""
    return {"status": "not_implemented"}
