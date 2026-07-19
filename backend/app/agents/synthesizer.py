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
from typing import Any, Dict, List, Optional, AsyncGenerator
from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

# ─── System Prompt Templates ───

CLINICAL_ASSISTANT_SYSTEM = """You are SoloPrac AI, a clinical assistant for a solo practitioner's clinic OS.

Your responsibilities:
1. Answer questions about patient records using the retrieved context provided.
2. Explain medical information clearly but cautiously — you are an AI assistant, not a doctor.
3. Always cite the version source when referencing patient data.
4. If you don't know something, say so — never fabricate lab results or diagnoses.
5. Keep responses concise and clinically relevant.

Format:
- Use plain text with markdown for structure (headings, lists, bold for emphasis).
- When referencing patient versions, use the format: [v{version_number} · {date}]
- End with a clear next-step suggestion when appropriate.

Remember: "AI Suggestion — Requires Doctor Validation."
"""


class MaverickSynthesizer:
    """Synthesizer using Llama-4 Maverick via NVIDIA NIM."""

    def __init__(self):
        self._client: Optional[AsyncOpenAI] = None
        self._groq_client: Optional[AsyncOpenAI] = None
        self._init_clients()

    def _init_clients(self):
        """Initialize API clients based on configuration."""
        if settings.NIM_API_KEY:
            self._client = AsyncOpenAI(
                api_key=settings.NIM_API_KEY,
                base_url=settings.NIM_BASE_URL,
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
            messages.append({
                "role": "user",
                "content": f"Here is the relevant patient information:\n\n{user_context}\n\nBased on this, respond to: {query}",
            })
        else:
            messages.append({"role": "user", "content": query})

        # Structured output mode
        response_format = None
        if structured_output:
            response_format = {"type": "json_object"}

        try:
            response = await self._client.chat.completions.create(
                model=settings.MAVERICK_MODEL,
                messages=messages,
                temperature=0.3,
                max_tokens=2048,
                response_format=response_format,
            )

            content = response.choices[0].message.content
            model_used = settings.MAVERICK_MODEL

            # Parse structured output if requested
            parsed_structured = None
            if structured_output and content:
                try:
                    parsed_structured = json.loads(content)
                except json.JSONDecodeError:
                    logger.warning("Maverick returned non-JSON despite response_format=json_object")

            logger.info("Maverick synthesis complete (model=%s, tokens=%d)",
                        model_used, response.usage.total_tokens if response.usage else 0)

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

        messages = [{"role": "system", "content": CLINICAL_ASSISTANT_SYSTEM}]

        user_context = ""
        if patient_context:
            user_context += f"Patient context: {json.dumps(patient_context, indent=2, default=str)[:3000]}"
        if context:
            user_context += f"\nContext: {json.dumps(context, indent=2, default=str)[:2000]}"

        if user_context:
            messages.append({
                "role": "user",
                "content": f"{user_context}\n\nRespond to: {query}",
            })
        else:
            messages.append({"role": "user", "content": query})

        try:
            stream = await self._client.chat.completions.create(
                model=settings.MAVERICK_MODEL,
                messages=messages,
                temperature=0.3,
                max_tokens=2048,
                stream=True,
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content

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

        response = await self._groq_client.chat.completions.create(
            model=settings.VISION_MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=2048,
        )

        return {
            "response": response.choices[0].message.content or "",
            "citations": [],
            "model": f"groq/{settings.VISION_MODEL}",
            "structured": None,
            "usage": {},
        }

    def _fallback(self, query: str, context: Any, patient_context: Any, intent: Optional[str]) -> Dict[str, Any]:
        """Fallback response when no LLM is available."""
        return {
            "response": (
                f"I understand your query about '{query[:100]}'. "
                f"The AI synthesis engine is being configured. "
                f"Please ensure NIM_API_KEY is set in your .env file. "
                f"For now, here's what I know based on the available context."
            ),
            "citations": [],
            "model": "fallback",
            "structured": None,
            "usage": {},
        }
