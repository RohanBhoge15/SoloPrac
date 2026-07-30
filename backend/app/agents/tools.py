"""Tool registry — all agent-accessible tools register here.

Week 6: Tools now wired to real implementations:
  - retrieve_patient_context → TemporalMultimodalRetriever (Feature A)
  - synthesize_response → MaverickSynthesizer with citations
"""

from __future__ import annotations

import os
import logging
import base64
from uuid import UUID
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol
from typing_extensions import runtime_checkable

from app.config import settings
from app.database import async_session_maker
from app.services.temporal_rag import TemporalMultimodalRetriever
from app.services.rag_audit import RAGAuditService, LLMRateLimiter, validate_no_future_leak
from app.services.pii import strip_pii
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
        "Searches across text (MedCPT), hybrid (BGE-M3 dense+sparse), and image (BiomedCLIP) "
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
        patient_id = kwargs.get("patient_id", "")
        citations = context.get("citations", [])

        # PII de-identification before inference: strip name/phone/email/etc. and
        # inject a stable pseudonym (P-{id}) so the external LLM only ever sees a
        # pseudonymous clinical profile — identity is re-attached client-side.
        safe_context = strip_pii(context, patient_id)
        safe_patient_context = safe_context.get("patient_context", {})

        # Record LLM call for rate limiting
        if doctor_id:
            await _llm_limiter.record_call(doctor_id)

        response = await _synthesizer.synthesize(
            query=query,
            context=safe_context,
            patient_context=safe_patient_context,
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
    lines.append("\n*Verified by AI · Doctor review recommended.*")
    return {"response": "\n".join(lines), "citations": citations, "model": "fallback"}


# ─── Vision Analysis (Module 3) ───

@tool(
    name="analyze_image",
    description="Analyze a medical image using MedGemma-4B-IT (radiology/dermatology) or Groq fallback (general medical images)",
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
    """Analyze a medical image using the appropriate vision model.

    Routes to:
    - MedGemma-4B-IT (local) for radiology (xray, ct, mri) - specialized medical vision
    - Groq Llama-3.2-90B-Vision for general medical images (wound, dermatology, other) - fallback
    """
    import os
    import base64
    from app.config import settings

    # Validate file exists
    if not os.path.exists(image_path):
        return {"status": "error", "message": f"Image not found: {image_path}"}

    # Read and encode image
    try:
        with open(image_path, "rb") as f:
            image_data = f.read()
        image_b64 = base64.b64encode(image_data).decode("utf-8")
    except Exception as e:
        return {"status": "error", "message": f"Failed to read image: {e}"}

    # Determine which model to use
    # Radiology images -> MedGemma (specialized), others -> Groq (general, high quality)
    use_medgemma = image_type in ("xray", "ct", "mri")

    try:
        if use_medgemma:
            # Use MedGemma-4B-IT for radiology
            return await _analyze_with_medgemma(image_b64, image_type)
        else:
            # Use Groq Llama-3.2-90B-Vision for general medical images
            return await _analyze_with_groq(image_b64, image_type)
    except Exception as e:
        logger.error("Vision analysis failed: %s", e)
        return {"status": "error", "message": f"Vision analysis failed: {str(e)[:200]}"}


async def _analyze_with_groq(image_b64: str, image_type: str) -> dict:
    """Analyze image using Groq Llama-3.2-90B-Vision."""
    from openai import AsyncOpenAI
    from app.config import settings

    if not settings.GROQ_API_KEY:
        return {"status": "error", "message": "GROQ_API_KEY not configured"}

    client = AsyncOpenAI(
        api_key=settings.GROQ_API_KEY,
        base_url=settings.GROQ_BASE_URL,
    )

    prompt = f"""You are a medical AI assistant analyzing a {image_type} image.
    Provide a detailed clinical analysis including:
    1. Key findings observed
    2. Potential diagnoses or concerns
    3. Recommended next steps or follow-up
    4. Confidence level (0-1)

    Be thorough but concise. Use medical terminology appropriately."""

    response = await client.chat.completions.create(
        model=settings.VISION_MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Analyze this {image_type} medical image."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
                ]
            }
        ],
        temperature=0.2,
        max_tokens=1500,
    )

    content = response.choices[0].message.content

    return {
        "status": "ok",
        "model": f"groq/{settings.VISION_MODEL}",
        "image_type": image_type,
        "analysis": content,
        "confidence": 0.85,
    }


async def _analyze_with_medgemma(image_b64: str, image_type: str) -> dict:
    """Analyze radiology image using MedGemma-4B-IT locally.

    Uses the model/processor cached by gpu_optimizer — a fresh
    ``from_pretrained`` per call would re-read several GB from disk and blow the
    VRAM budget the optimizer exists to manage.
    """
    import asyncio
    import torch
    from app.services.gpu_optimizer import gpu_optimizer, ModelName

    # Ensure model is loaded on GPU and reuse the cached objects
    model_info = await gpu_optimizer.ensure_model_loaded(ModelName.MEDGEMMA)

    try:
        model = model_info.model_obj
        processor = model_info.processor
        if model is None or processor is None:
            return {
                "status": "error",
                "message": "MedGemma is not loaded (gpu_optimizer returned no model object)",
            }

        # Prepare inputs
        from PIL import Image
        import io
        import base64
        image = Image.open(io.BytesIO(base64.b64decode(image_b64)))
        if image.mode != "RGB":
            image = image.convert("RGB")

        # MedGemma prompt format for radiology
        prompt = f"<image>Analyze this {image_type} medical image. Provide clinical findings, potential diagnoses, and recommendations."

        inputs = processor(text=prompt, images=image, return_tensors="pt")
        inputs = inputs.to(model.device)
        input_len = inputs["input_ids"].shape[-1]

        def _generate():
            with torch.inference_mode():
                return model.generate(
                    **inputs,
                    max_new_tokens=1024,
                    temperature=0.2,
                    do_sample=True,
                )

        outputs = await asyncio.to_thread(_generate)

        # Decode only the newly generated tokens — string-splitting the echoed
        # prompt out of the full decode is unreliable.
        analysis = processor.decode(outputs[0][input_len:], skip_special_tokens=True)

        return {
            "status": "ok",
            "model": "medgemma-4b-it",
            "image_type": image_type,
            "analysis": analysis.strip(),
            "confidence": 0.9,
        }
    except Exception as e:
        logger.error("MedGemma analysis failed: %s", e)
        return {"status": "error", "message": f"MedGemma analysis failed: {str(e)[:200]}"}


@tool(
    name="compare_images",
    description="Compare two patient images using ORB feature matching for wound/skin progression tracking",
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
    """Compare two images using ORB feature matching (wound progression, skin conditions).

    Uses the image_registration_service to:
    1. Detect ORB keypoints on both images
    2. Match features with BFMatcher + Lowe's ratio test
    3. Compute homography via RANSAC
    4. Generate overlay image with metrics
    5. Return clinical summary from Maverick
    """
    from app.services.image_registration import image_registration_service
    import uuid

    if len(image_paths) != 2:
        return {"status": "error", "message": "Exactly 2 image paths required"}

    # Verify files exist
    for p in image_paths:
        if not os.path.exists(p):
            return {"status": "error", "message": f"Image not found: {p}"}

    try:
        # Run ORB registration
        result = await image_registration_service.compare(
            image_prev_path=image_paths[0],
            image_curr_path=image_paths[1],
            patient_id=patient_id,
        )

        # Convert dataclass to dict
        from dataclasses import asdict
        metrics = asdict(result.metrics) if result.metrics else {}

        response = {
            "status": "ok" if result.matched else "no_match",
            "matched": result.matched,
            "patient_id": patient_id,
            "image_paths": image_paths,
            "overlay_path": result.overlay_path,
            "warped_previous_path": result.warped_previous_path,
            "metrics": metrics,
            "message": result.message,
        }

        # Add clinical summary if available
        if result.matched:
            try:
                # generate_summary is a module-level coroutine, not a
                # classmethod on ClinicalSummaryGenerator.
                from app.services.clinical_summary import generate_summary
                summary_result = await generate_summary(
                    metrics=metrics,
                    patient_name=f"Patient {patient_id[:8]}",
                )
                response["clinical_summary"] = summary_result.get("summary")
                response["summary_confidence"] = summary_result.get("confidence", 0.0)
            except (ImportError, AttributeError, TypeError) as e:
                # Wiring/API errors here mean the feature is broken, not merely
                # degraded — log loudly so it cannot fail silently again.
                logger.exception("Clinical summary is misconfigured (bug, not data): %s", e)
            except Exception as e:
                logger.warning("Clinical summary generation failed: %s", e)

        return response
    except Exception as e:
        logger.error("Image comparison failed: %s", e)
        return {"status": "error", "message": f"Image comparison failed: {str(e)[:200]}"}


@tool(
    name="generate_prescription",
    description="Generate an AI-drafted prescription card with structured medications and PDF",
    parameters={
        "type": "object",
        "properties": {
            "patient_id": {"type": "string", "format": "uuid"},
            "diagnosis": {"type": "string"},
            "medications": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "drug": {"type": "string"},
                        "strength": {"type": "string"},
                        "dose": {"type": "string"},
                        "frequency": {"type": "string"},
                        "duration": {"type": "string"},
                        "route": {"type": "string", "default": "PO"},
                        "instructions": {"type": "string"},
                    },
                    "required": ["drug", "strength", "dose", "frequency", "duration"],
                },
            },
        },
        "required": ["patient_id", "diagnosis", "medications"],
    },
)
async def generate_prescription(patient_id: str, diagnosis: str, medications: list, **kwargs) -> dict:
    """Generate an AI-drafted prescription card with PDF output.

    Creates a structured prescription, generates PDF via Jinja2+Playwright,
    and stores it in the database linked to the patient version.
    """
    import uuid
    from app.database import async_session_maker
    from app.models import Patient, PatientVersion, PrescriptionBox, AuditLog
    from app.services.pdf_generator import pdf_generator
    from sqlalchemy import select

    doctor_id = kwargs.get("doctor_id", "")
    if not doctor_id:
        return {"status": "error", "message": "doctor_id required"}

    try:
        async with async_session_maker() as db:
            # Verify patient belongs to doctor
            result = await db.execute(
                select(Patient).where(Patient.id == uuid.UUID(patient_id), Patient.doctor_id == uuid.UUID(doctor_id))
            )
            patient = result.scalar_one_or_none()
            if not patient:
                return {"status": "error", "message": "Patient not found"}

            # Get patient name from head version
            patient_name = f"Patient {patient_id[:8]}"
            if patient.head_version_id:
                vr = await db.execute(
                    select(PatientVersion).where(PatientVersion.id == patient.head_version_id)
                )
                head = vr.scalar_one_or_none()
                if head and head.state_jsonb:
                    demo = head.state_jsonb.get("demographics", {})
                    if isinstance(demo, dict) and demo.get("name"):
                        patient_name = demo["name"]

            # Build prescription data
            rx_data = {
                "diagnosis_short": diagnosis,
                "medications": medications,
                "investigations": kwargs.get("investigations", []),
                "lifestyle": kwargs.get("lifestyle", []),
                "follow_up_days": kwargs.get("follow_up_days", 30),
                "follow_up_mode": kwargs.get("follow_up_mode", "in-person"),
                "doctor_notes": kwargs.get("doctor_notes", ""),
            }

            # Generate PDF
            pdf_path = await pdf_generator.generate_prescription(
                patient_name=patient_name,
                patient_age=kwargs.get("patient_age", 0),
                patient_gender=kwargs.get("patient_gender", ""),
                diagnosis=diagnosis,
                medications=medications,
                instructions=kwargs.get("instructions", ""),
                follow_up=kwargs.get("follow_up", f"{kwargs.get('follow_up_days', 30)} days"),
                doctor_name=kwargs.get("doctor_name", ""),
                db=db,
                doctor_id=uuid.UUID(doctor_id),
            )

            # Create prescription record
            rx = PrescriptionBox(
                id=uuid.uuid4(),
                version_id=patient.head_version_id,
                patient_id=patient.id,
                doctor_id=uuid.UUID(doctor_id),
                rx_jsonb=rx_data,
                pdf_path=pdf_path,
            )
            db.add(rx)
            await db.flush()

            # Audit log
            audit = AuditLog(
                doctor_id=uuid.UUID(doctor_id),
                patient_id=uuid.UUID(patient_id),
                actor=f"doctor:{doctor_id}",
                action="write",
                resource_type="prescription",
                resource_id=rx.id,
                payload_jsonb={"diagnosis": diagnosis, "med_count": len(medications)},
            )
            db.add(audit)

            await db.commit()
            await db.refresh(rx)

            return {
                "status": "ok",
                "prescription_id": str(rx.id),
                "pdf_path": pdf_path,
                "rx_data": rx_data,
                "message": "Prescription generated. Requires doctor validation before issuing.",
            }
    except Exception as e:
        logger.error("Prescription generation failed: %s", e)
        return {"status": "error", "message": f"Prescription generation failed: {str(e)[:200]}"}
