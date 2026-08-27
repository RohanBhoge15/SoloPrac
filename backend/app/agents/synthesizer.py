"""Maverick Synthesizer — Llama-4 Maverick via NIM with structured output.

Generates final responses to user queries using NVIDIA NIM-hosted
Llama-4 Maverick. Supports:
  - Structured JSON output with Pydantic validation
  - Streaming token generation for SSE delivery
  - Context grounding with patient version citations
  - Fallback to Groq or local if NIM is unavailable

Usage:
    from app.agents.synthesizer import MaverickSynthesizer
    synth = MaverickSynthesizer()
    response = await synth.synthesize(context=ctx, query="...")
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from openai import AsyncOpenAI

from app.config import settings
from app.services.pii import strip_pii

logger = logging.getLogger(__name__)

# ─── System Prompt Templates ───

CLINICAL_ASSISTANT_SYSTEM = """You are SoloPrac AI, a clinical assistant for a solo practitioner's clinic OS.

CRITICAL SAFETY RULES — you must follow these without exception:
1. ONLY answer from the provided patient context. If the answer is not in the retrieved context, say "I don't have enough information from the patient record to answer that." Do NOT generate medical information from your general knowledge.
2. NEVER fabricate lab results, diagnoses, medications, or vital signs. If a value is not in the context, do not invent one.
3. NEVER recommend medication changes, dosage adjustments, or treatment modifications. Only summarize what is recorded.
4. If you are uncertain or the context is ambiguous, say so explicitly.

Your responsibilities:
1. Answer questions about patient records using ONLY the retrieved context provided.
2. Explain medical information clearly but cautiously — you are an AI assistant, not a doctor.
3. Always cite the version source when referencing patient data using the format: [v{version_number} · {date}]
4. When versions contain conflicting information, present the progression over time with timestamps — show what changed, when, and why if documented. For example: "Patient was diagnosed with Diabetes on Jan 5 [v1 · 2026-01-05]. On Feb 15, HbA1c returned to normal and the condition was marked as resolved [v3 · 2026-02-15]."
5. If you can't find the answer in the patient record, say "I don't have enough information from the patient record to answer that."
6. Keep responses concise and clinically relevant.

Format:
- Use plain text with markdown for structure (headings, lists, bold for emphasis).
- When referencing patient versions, use the format: [v{version_number} · {date}]
- End with a clear next-step suggestion when appropriate.

Remember: "Verified by AI · Doctor review recommended."
"""


class MaverickSynthesizer:
    """Singleton synthesizer using Llama-4 Maverick via NVIDIA NIM.

    Use get_instance() to get the shared singleton.
    """

    _instance: Optional["MaverickSynthesizer"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._client: Optional[AsyncOpenAI] = None
        self._groq_client: Optional[AsyncOpenAI] = None
        self._init_clients()

    def _init_clients(self):
        """Initialize API clients based on configuration."""
        if settings.NIM_API_KEY:
            self._client = AsyncOpenAI(
                api_key=settings.NIM_API_KEY,
                base_url=settings.NIM_BASE_URL,
                timeout=120.0,
                max_retries=0,
            )
            logger.info("MaverickSynthesizer: NIM client initialized (model=%s)", settings.MAVERICK_MODEL)

        if settings.GROQ_API_KEY:
            self._groq_client = AsyncOpenAI(
                api_key=settings.GROQ_API_KEY,
                base_url=settings.GROQ_BASE_URL,
            )
            logger.info("MaverickSynthesizer: Groq client initialized (model=%s)", settings.VISION_MODEL)

    @property
    def is_available(self) -> bool:
        return self._client is not None

    async def synthesize(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        patient_context: Optional[Dict[str, Any]] = None,
        intent: Optional[str] = None,
        citations: Optional[List[Dict[str, Any]]] = None,
        structured_output: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate a response using Maverick.

        Args:
            query: The user's original query.
            context: Optional context from previous tool calls.
            patient_context: Retrieved patient version context.
            intent: The classified intent.
            citations: Version citations to include.
            structured_output: If provided, requests JSON response matching this schema.

        Returns:
            {"response": str, "citations": [...], "model": str, "structured": dict|None}
        """
        if self._client is None:
            logger.warning("NIM client not configured — using fallback response")
            return self._fallback(query, context, patient_context, intent)

        # PII de-identification guard at the LLM boundary. Strips name/phone/email/
        # etc. from anything sent to the external LLM, so no caller can leak identity
        # regardless of what it passes. Idempotent — safe if already stripped upstream.
        context = strip_pii(context)
        patient_context = strip_pii(patient_context)

        # Build messages
        messages = [{"role": "system", "content": CLINICAL_ASSISTANT_SYSTEM}]

        # Add patient context if available
        user_context = ""
        if patient_context:
            user_context += f"Patient context: {json.dumps(patient_context, indent=2, default=str)[:3000]}\n\n"
        if context:
            user_context += f"Additional context: {json.dumps(context, indent=2, default=str)[:2000]}\n\n"
        if citations:
            user_context += f"Relevant versions: {json.dumps(citations, default=str)[:1000]}\n\n"

        if user_context:
            messages.append(
                {
                    "role": "user",
                    "content": f"Here is the relevant patient information:\n\n{user_context}\n\nBased on this, respond to: {query}",
                }
            )
        else:
            messages.append({"role": "user", "content": query})

        # Structured output mode
        response_format = None
        if structured_output and settings.MAVERICK_STRUCTURED_OUTPUT:
            response_format = {"type": "json_object"}

        # P3.32 — bound the LLM call so a stalled NIM connection can't hang
        # the whole request forever. 60s is generous for even the biggest
        # answer; on TimeoutError we fall through to the retry / Groq path.
        import asyncio as _asyncio

        try:
            # nemotron-3.5 defaults to emitting a long "thinking process" block;
            # reasoning_effort=none makes it answer directly, which is what the
            # app surfaces to users. (The param is ignored harmlessly by models
            # that don't support it.)
            response = await _asyncio.wait_for(
                self._client.chat.completions.create(
                    model=settings.MAVERICK_MODEL,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=2048,
                    response_format=response_format,
                    reasoning_effort="none",
                ),
                timeout=120.0,
            )

            content = response.choices[0].message.content
            model_used = settings.MAVERICK_MODEL

            # Parse structured output if requested
            parsed_structured = None
            if structured_output and content:
                try:
                    parsed_structured = json.loads(content)
                except json.JSONDecodeError:
                    import re as _re

                    fenced = _re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
                    try:
                        parsed_structured = json.loads(fenced)
                    except json.JSONDecodeError:
                        logger.warning("Maverick returned non-JSON despite response_format=json_object")

            logger.info(
                "Maverick synthesis complete (model=%s, tokens=%d)",
                model_used,
                response.usage.total_tokens if response.usage else 0,
            )

            return {
                "response": content or "",
                "citations": citations or [],
                "model": model_used,
                "structured": parsed_structured,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0,
                },
            }

        except Exception as exc:
            logger.error("Maverick API call failed: %s", exc)
            # Retry without response_format — some NIM models hang on json_object mode.
            if response_format:
                try:
                    response = await _asyncio.wait_for(
                        self._client.chat.completions.create(
                            model=settings.MAVERICK_MODEL,
                            messages=messages,
                            temperature=0.3,
                            max_tokens=2048,
                            reasoning_effort="none",
                        ),
                        timeout=120.0,
                    )
                    content = response.choices[0].message.content
                    logger.info(
                        "Maverick synthesis retried without response_format (model=%s)", settings.MAVERICK_MODEL
                    )
                    return {
                        "response": content or "",
                        "citations": citations or [],
                        "model": settings.MAVERICK_MODEL,
                        "structured": None,
                        "usage": {
                            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                            "total_tokens": response.usage.total_tokens if response.usage else 0,
                        },
                    }
                except Exception as retry_exc:
                    logger.error("Maverick retry (no response_format) also failed: %s", retry_exc)

            # Try Groq fallback
            if self._groq_client:
                try:
                    return await self._groq_fallback(query, user_context, intent)
                except Exception as groq_exc:
                    logger.error("Groq fallback also failed: %s", groq_exc)

            return self._fallback(query, context, patient_context, intent)

    async def synthesize_stream(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        patient_context: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from Maverick via SSE.

        Yields text chunks as they arrive from the API.
        Falls back to yielding the full response at once if NIM is unavailable.
        """
        if self._client is None:
            fallback = self._fallback(query, context, None, None)
            yield fallback["response"]
            return

        # PII de-identification guard at the LLM boundary (see synthesize()).
        context = strip_pii(context)
        patient_context = strip_pii(patient_context)

        messages = [{"role": "system", "content": CLINICAL_ASSISTANT_SYSTEM}]

        user_context = ""
        if patient_context:
            user_context += f"Patient context: {json.dumps(patient_context, indent=2, default=str)[:3000]}"
        if context:
            user_context += f"\nContext: {json.dumps(context, indent=2, default=str)[:2000]}"

        if user_context:
            messages.append(
                {
                    "role": "user",
                    "content": f"{user_context}\n\nRespond to: {query}",
                }
            )
        else:
            messages.append({"role": "user", "content": query})

        # P3.32 — bound the initial connection to 60s. Once the stream starts
        # producing tokens we don't add a per-chunk timeout, because NIM/Groq
        # can legitimately pause between tokens on long generations; a stall
        # will be detected by the caller (SSE keep-alive on the frontend).
        import asyncio as _asyncio

        try:
            stream = await _asyncio.wait_for(
                self._client.chat.completions.create(
                    model=settings.MAVERICK_MODEL,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=2048,
                    stream=True,
                ),
                timeout=60.0,
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content

        except _asyncio.TimeoutError:
            logger.error("Maverick streaming timed out after 60s — retrying via Groq")
            # Retry once via Groq fallback if configured.
            if self._groq_client:
                try:
                    groq_result = await self._groq_fallback(query, user_context, None)
                    yield groq_result.get("response", "")
                    return
                except Exception as groq_exc:
                    logger.error("Groq retry failed: %s", groq_exc)
            fallback = self._fallback(query, context, None, None)
            yield fallback["response"]
        except Exception as exc:
            logger.error("Maverick streaming failed: %s", exc)
            fallback = self._fallback(query, context, None, None)
            yield fallback["response"]

    async def _groq_fallback(self, query: str, user_context: str, intent: Optional[str]) -> Dict[str, Any]:
        """Fallback to Groq's Llama-3.2-90B-Vision."""
        messages = [{"role": "system", "content": CLINICAL_ASSISTANT_SYSTEM}]
        if user_context:
            messages.append({"role": "user", "content": f"{user_context}\nQuery: {query}"})
        else:
            messages.append({"role": "user", "content": query})

        # P3.32 — same 60s cap for Groq. If both providers stall we surface a
        # deterministic error message instead of a hung request.
        import asyncio as _asyncio

        response = await _asyncio.wait_for(
            self._groq_client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=messages,
                temperature=0.3,
                max_tokens=2048,
            ),
            timeout=60.0,
        )

        return {
            "response": response.choices[0].message.content or "",
            "citations": [],
            "model": f"groq/{settings.GROQ_MODEL}",
            "structured": None,
            "usage": {},
        }

    def _fallback(self, query: str, context: Any, patient_context: Any, intent: Optional[str]) -> Dict[str, Any]:
        """Fallback response when no LLM is available."""
        # Build a helpful fallback from retrieved context
        fallback_parts = []
        if patient_context and isinstance(patient_context, dict):
            if patient_context.get("query"):
                fallback_parts.append(f"Based on the query: {patient_context['query']}")
            if patient_context.get("results"):
                count = len(patient_context["results"])
                fallback_parts.append(f"I found {count} relevant version(s) in the patient record.")
        if context and isinstance(context, dict):
            if context.get("query_results"):
                count = len(context["query_results"])
                fallback_parts.append(f"Retrieved {count} matching records from the timeline.")

        if fallback_parts:
            response = " ".join(fallback_parts) + "\n\n"
        else:
            response = f"I understand your query about '{query[:100]}'. "

        # Check what's missing
        missing_keys = []
        if not settings.NIM_API_KEY:
            missing_keys.append("NIM_API_KEY")
        if not settings.GROQ_API_KEY:
            missing_keys.append("GROQ_API_KEY")

        if missing_keys:
            response += (
                f"The AI synthesis engine requires {', '.join(missing_keys)} to be configured. "
                f"Please add them to your .env file and restart the backend. "
                f"Patient context was retrieved successfully — review it above."
            )
        else:
            response += "The AI service is temporarily unavailable. Please try again shortly."

        return {
            "response": response,
            "citations": [],
            "model": "fallback",
            "structured": None,
            "usage": {},
        }
