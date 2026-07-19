"""Intent Router — classifies user queries using Llama-3.1-8B (NIM)."""

from __future__ import annotations

import json
import logging
from typing import Optional
from openai import AsyncOpenAI
from app.config import settings
from app.agents.state import AgentIntent

logger = logging.getLogger(__name__)

# Fallback classification (no API key) — regex-based for development
INTENT_KEYWORDS: dict[AgentIntent, list[str]] = {
    AgentIntent.PATIENT_QA: ["what", "show", "tell", "status", "trend", "history", "last", "when", "how"],
    AgentIntent.IMAGE_ANALYSIS: ["analyze", "look at", "xray", "x-ray", "image", "photo", "scan", "wound"],
    AgentIntent.IMAGE_COMPARE: ["compare", "overlay", "healing", "progress", "before", "after", "change"],
    AgentIntent.DOCUMENT_PARSE: ["upload", "document", "pdf", "scan", "read", "extract", "ocr", "parse"],
    AgentIntent.SCHEDULING: ["book", "schedule", "appointment", "reschedule", "cancel", "off", "free", "slot"],
    AgentIntent.PRESCRIPTION: ["prescribe", "prescription", "rx", "medication", "drug", "medicine"],
    AgentIntent.INVOICE: ["invoice", "bill", "payment", "charge", "receipt"],
    AgentIntent.CERTIFICATE: ["certificate", "sick leave", "fitness", "medical leave"],
    AgentIntent.WEEKLY_REPORT: ["weekly", "report", "digest", "summary", "week"],
    AgentIntent.GENERAL_CHAT: [],  # fallback
}


class IntentRouter:
    """Classifies user intent into one of the known AgentIntent values."""

    def __init__(self):
        self.client: Optional[AsyncOpenAI] = None
        if settings.NIM_API_KEY:
            self.client = AsyncOpenAI(
                api_key=settings.NIM_API_KEY,
                base_url=settings.NIM_BASE_URL,
            )

    async def classify(self, query: str) -> tuple[AgentIntent, float, str]:
        """Classify query → (intent, confidence, reasoning)."""
        # Try LLM first if configured
        if self.client:
            try:
                return await self._llm_classify(query)
            except Exception as e:
                logger.warning(f"LLM classification failed: {e}. Falling back to keyword.")
                return self._keyword_classify(query)

        # Fallback
        return self._keyword_classify(query)

    async def _llm_classify(self, query: str) -> tuple[AgentIntent, float, str]:
        """Use Llama-3.1-8B via NIM for classification."""
        intents_desc = "\n".join(f"  - {e.value}: {e.name.replace('_', ' ').title()}" for e in AgentIntent)
        prompt = (
            "You are an intent classifier for a medical clinic OS. "
            f"Classify the following query into one of:\n{intents_desc}\n\n"
            f"Query: {query}\n\n"
            "Respond with JSON: {\"intent\": \"<intent_value>\", \"confidence\": 0.0-1.0, \"reasoning\": \"...\"}"
        )

        response = await self.client.chat.completions.create(
            model=settings.LLAMA_8B_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=150,
        )

        raw = response.choices[0].message.content
        data = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
        intent = AgentIntent(data["intent"])
        return intent, data.get("confidence", 0.5), data.get("reasoning", "")

    def _keyword_classify(self, query: str) -> tuple[AgentIntent, float, str]:
        """Simple keyword-based fallback classification."""
        q_lower = query.lower()
        best_intent = AgentIntent.GENERAL_CHAT
        best_score = 0
        best_reason = "fallback keyword match"

        for intent, keywords in INTENT_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in q_lower)
            if score > best_score:
                best_score = score
                best_intent = intent
                best_reason = f"matched {score} keyword(s)"

        # Confidence based on how many keywords matched vs total possible
        total_possible = len(INTENT_KEYWORDS[best_intent])
        confidence = min(best_score / max(total_possible, 1) * 0.8, 0.8) if total_possible else 0.3

        return best_intent, confidence, best_reason
