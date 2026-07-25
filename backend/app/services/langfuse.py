"""Langfuse Observability Integration — LLM tracing, evaluation, and monitoring.

Provides:
  1. Automatic tracing of all LLM calls (Maverick, Groq, local models)
  2. Agent step tracing (router, planner, executor, critic, synthesizer)
  3. RAG retrieval tracing with scores and metadata
  4. Evaluation metrics (faithfulness, relevance, latency)
  5. Cost tracking per doctor/patient

Usage:
    from app.services.langfuse import langfuse_client, trace_llm_call, trace_agent_step

    # Automatic via decorators or manual
    with trace_llm_call("maverick_synthesis", doctor_id="...", patient_id="...") as span:
        result = await synthesizer.synthesize(...)
        span.output = result
"""

from __future__ import annotations

import os
import json
import logging
import uuid
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Callable
from contextlib import asynccontextmanager
from functools import wraps

from langfuse import Langfuse

from app.config import settings

logger = logging.getLogger(__name__)


class LangfuseClient:
    """Wrapper around Langfuse SDK for SoloPrac AI observability."""

    def __init__(self):
        self._client: Optional[Langfuse] = None
        self._enabled = bool(settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY)
        self._init_client()

    def _init_client(self):
        """Initialize Langfuse client if credentials are available."""
        if self._enabled:
            try:
                self._client = Langfuse(
                    public_key=settings.LANGFUSE_PUBLIC_KEY,
                    secret_key=settings.LANGFUSE_SECRET_KEY,
                    host=settings.LANGFUSE_HOST,
                    debug=settings.DEBUG,
                )
                # Test connection
                self._client.auth_check()
                logger.info("Langfuse client initialized successfully")
            except Exception as e:
                logger.warning(f"Langfuse initialization failed: {e}. Observability disabled.")
                self._enabled = False
                self._client = None

    @property
    def is_enabled(self) -> bool:
        return self._enabled and self._client is not None

    def create_trace(
        self,
        name: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        input_data: Optional[Dict] = None,
        output_data: Optional[Dict] = None,
        metadata: Optional[Dict] = None,
        tags: Optional[List[str]] = None,
    ) -> Optional[str]:
        """Create a new trace and return trace_id."""
        if not self.is_enabled:
            return None

        trace_id = str(uuid.uuid4())
        try:
            self._client.trace(
                id=trace_id,
                name=name,
                user_id=user_id,
                session_id=session_id,
                input=input_data,
                output=output_data,
                metadata=metadata or {},
                tags=tags or [],
            )
            return trace_id
        except Exception as e:
            logger.warning(f"Langfuse trace creation failed: {e}")
            return None

    def create_span(
        self,
        trace_id: str,
        name: str,
        input_data: Optional[Dict] = None,
        output_data: Optional[Dict] = None,
        metadata: Optional[Dict] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        level: str = "DEFAULT",
    ) -> Optional[str]:
        """Create a span within a trace."""
        if not self.is_enabled:
            return None

        span_id = str(uuid.uuid4())
        try:
            self._client.span(
                id=span_id,
                trace_id=trace_id,
                name=name,
                input=input_data,
                output=output_data,
                metadata=metadata or {},
                start_time=start_time or datetime.now(timezone.utc),
                end_time=end_time,
                level=level,
            )
            return span_id
        except Exception as e:
            logger.warning(f"Langfuse span creation failed: {e}")
            return None

    def create_generation(
        self,
        trace_id: str,
        name: str,
        model: str,
        model_parameters: Optional[Dict] = None,
        input_data: Optional[Any] = None,
        output_data: Optional[Any] = None,
        usage: Optional[Dict] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        metadata: Optional[Dict] = None,
    ) -> Optional[str]:
        """Create a generation (LLM call) within a trace."""
        if not self.is_enabled:
            return None

        generation_id = str(uuid.uuid4())
        try:
            self._client.generation(
                id=generation_id,
                trace_id=trace_id,
                name=name,
                model=model,
                model_parameters=model_parameters or {},
                input=input_data,
                output=output_data,
                usage=usage,
                start_time=start_time or datetime.now(timezone.utc),
                end_time=end_time,
                metadata=metadata or {},
            )
            return generation_id
        except Exception as e:
            logger.warning(f"Langfuse generation creation failed: {e}")
            return None

    def score(
        self,
        trace_id: str,
        name: str,
        value: float,
        comment: Optional[str] = None,
        data_type: str = "NUMERIC",
    ) -> bool:
        """Add a score/evaluation to a trace."""
        if not self.is_enabled:
            return False

        try:
            self._client.score(
                trace_id=trace_id,
                name=name,
                value=value,
                comment=comment,
                data_type=data_type,
            )
            return True
        except Exception as e:
            logger.warning(f"Langfuse scoring failed: {e}")
            return False

    def flush(self):
        """Flush all pending events to Langfuse."""
        if self.is_enabled:
            try:
                self._client.flush()
            except Exception as e:
                logger.warning(f"Langfuse flush failed: {e}")

    def shutdown(self):
        """Shutdown the client gracefully."""
        if self._client:
            try:
                self._client.shutdown()
            except Exception:
                pass


# Global instance
langfuse_client = LangfuseClient()


# ─── Context Managers for Easy Tracing ───

@asynccontextmanager
async def trace_llm_call(
    name: str,
    model: str,
    doctor_id: Optional[str] = None,
    patient_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    metadata: Optional[Dict] = None,
):
    """Context manager to trace an LLM call.

    Usage:
        async with trace_llm_call("maverick_synthesis", "nvidia/llama-4-maverick-17b", doctor_id=doc_id) as span:
            result = await synthesizer.synthesize(...)
            span.output = result
    """
    if not langfuse_client.is_enabled:
        yield None
        return

    _trace_id = trace_id or str(uuid.uuid4())
    _start = datetime.now(timezone.utc)

    # Create trace if new
    if not trace_id:
        langfuse_client.create_trace(
            name=name,
            user_id=doctor_id,
            session_id=patient_id,
            metadata=metadata or {},
            tags=["llm_call", model.replace("/", "-")],
        )

    _gen_id = langfuse_client.create_generation(
        trace_id=_trace_id,
        name=name,
        model=model,
        start_time=_start,
        metadata={"doctor_id": doctor_id, "patient_id": patient_id, **(metadata or {})},
    )

    class GenerationSpan:
        def __init__(self):
            self.input = None
            self.output = None
            self.usage = None
            self.metadata = {}

        def set_input(self, data):
            self.input = data

        def set_output(self, data):
            self.output = data

        def set_usage(self, usage_dict):
            self.usage = usage_dict

        def add_metadata(self, key, value):
            self.metadata[key] = value

    span = GenerationSpan()
    try:
        yield span
    finally:
        _end = datetime.now(timezone.utc)
        if langfuse_client.is_enabled and _gen_id:
            langfuse_client.create_generation(
                trace_id=_trace_id,
                name=name,
                model=model,
                input_data=span.input,
                output_data=span.output,
                usage=span.usage,
                start_time=_start,
                end_time=_end,
                metadata={**span.metadata, "doctor_id": doctor_id, "patient_id": patient_id},
            )


@asynccontextmanager
async def trace_agent_step(
    step_name: str,
    trace_id: str,
    doctor_id: Optional[str] = None,
    patient_id: Optional[str] = None,
    input_data: Optional[Dict] = None,
    metadata: Optional[Dict] = None,
):
    """Context manager to trace an agent graph step.

    Usage:
        async with trace_agent_step("router", trace_id, doctor_id=doc_id) as span:
            intent = await router.classify(query)
            span.output = {"intent": intent.value}
    """
    if not langfuse_client.is_enabled:
        yield None
        return

    _start = datetime.now(timezone.utc)
    _span_id = langfuse_client.create_span(
        trace_id=trace_id,
        name=step_name,
        input_data=input_data,
        metadata={"doctor_id": doctor_id, "patient_id": patient_id, **(metadata or {})},
        start_time=_start,
    )

    class AgentSpan:
        def __init__(self):
            self.output = None
            self.metadata = {}
            self.level = "DEFAULT"

        def set_output(self, data):
            self.output = data

        def add_metadata(self, key, value):
            self.metadata[key] = value

        def set_error(self, error: str):
            self.level = "ERROR"
            self.output = {"error": error}

    span = AgentSpan()
    try:
        yield span
    finally:
        _end = datetime.now(timezone.utc)
        langfuse_client.create_span(
            trace_id=trace_id,
            name=step_name,
            input_data=input_data,
            output_data=span.output,
            metadata={**span.metadata, "doctor_id": doctor_id, "patient_id": patient_id},
            start_time=_start,
            end_time=_end,
            level=span.level,
        )


@asynccontextmanager
async def trace_rag_retrieval(
    trace_id: str,
    doctor_id: str,
    patient_id: str,
    query: str,
    metadata: Optional[Dict] = None,
):
    """Context manager to trace RAG retrieval with detailed metrics."""
    if not langfuse_client.is_enabled:
        yield None
        return

    _start = datetime.now(timezone.utc)

    class RagSpan:
        def __init__(self):
            self.results = []
            self.citations = []
            self.meta = {}
            self.latency_ms = 0

        def set_results(self, results: List[Dict]):
            self.results = results

        def set_citations(self, citations: List[Dict]):
            self.citations = citations

        def add_metadata(self, key, value):
            self.meta[key] = value

    span = RagSpan()
    try:
        yield span
    finally:
        _end = datetime.now(timezone.utc)
        span.latency_ms = int((_end - _start).total_seconds() * 1000)

        langfuse_client.create_span(
            trace_id=trace_id,
            name="retrieve_patient_context",
            input_data={"query": query, "patient_id": patient_id},
            output_data={
                "num_results": len(span.results),
                "citations": span.citations,
                "latency_ms": span.latency_ms,
                **span.meta,
            },
            metadata={
                "doctor_id": doctor_id,
                "patient_id": patient_id,
                "modality": "multimodal_rag",
                **(metadata or {}),
            },
            start_time=_start,
            end_time=_end,
        )


def trace_function(name: str):
    """Decorator to trace a function as a Langfuse span."""
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            if not langfuse_client.is_enabled:
                return await func(*args, **kwargs)

            trace_id = str(uuid.uuid4())
            _start = datetime.now(timezone.utc)

            # Create trace
            langfuse_client.create_trace(
                name=name,
                metadata={"function": func.__name__},
                tags=["function_trace"],
            )

            # Create span
            _span_id = langfuse_client.create_span(
                trace_id=trace_id,
                name=name,
                input_data={"args": str(args)[:500], "kwargs": str(kwargs)[:500]},
                start_time=_start,
            )

            try:
                result = await func(*args, **kwargs)
                _end = datetime.now(timezone.utc)
                langfuse_client.create_span(
                    trace_id=trace_id,
                    name=name,
                    output_data={"result": str(result)[:1000]},
                    start_time=_start,
                    end_time=_end,
                    level="DEFAULT",
                )
                return result
            except Exception as e:
                _end = datetime.now(timezone.utc)
                langfuse_client.create_span(
                    trace_id=trace_id,
                    name=name,
                    output_data={"error": str(e)},
                    start_time=_start,
                    end_time=_end,
                    level="ERROR",
                )
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            if not langfuse_client.is_enabled:
                return func(*args, **kwargs)

            trace_id = str(uuid.uuid4())
            _start = datetime.now(timezone.utc)

            langfuse_client.create_trace(
                name=name,
                metadata={"function": func.__name__},
                tags=["function_trace"],
            )

            _span_id = langfuse_client.create_span(
                trace_id=trace_id,
                name=name,
                input_data={"args": str(args)[:500], "kwargs": str(kwargs)[:500]},
                start_time=_start,
            )

            try:
                result = func(*args, **kwargs)
                _end = datetime.now(timezone.utc)
                langfuse_client.create_span(
                    trace_id=trace_id,
                    name=name,
                    output_data={"result": str(result)[:1000]},
                    start_time=_start,
                    end_time=_end,
                    level="DEFAULT",
                )
                return result
            except Exception as e:
                _end = datetime.now(timezone.utc)
                langfuse_client.create_span(
                    trace_id=trace_id,
                    name=name,
                    output_data={"error": str(e)},
                    start_time=_start,
                    end_time=_end,
                    level="ERROR",
                )
                raise

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# ─── Evaluation Helpers ───

FAITHFULNESS_JUDGE_SYSTEM = """You are an impartial evaluator for a clinical AI assistant.

Score how FAITHFUL the assistant's response is to the retrieved context — i.e. whether
every clinical claim in the response is supported by the provided context, with no
fabricated diagnoses, lab values, medications, or facts.

Scoring rubric (0.0–1.0):
- 1.0  Every claim is directly grounded in the context; nothing invented.
- 0.7  Mostly grounded; minor unsupported phrasing but no clinical fabrication.
- 0.4  Partially grounded; some claims lack support in the context.
- 0.0  Largely fabricated or contradicts the context.

Respond ONLY with JSON: {"score": <float 0-1>, "reason": "<one sentence>"}"""

RELEVANCE_JUDGE_SYSTEM = """You are an impartial evaluator for a clinical AI assistant.

Score how RELEVANT the assistant's response is to the user's query — i.e. whether it
actually answers what was asked, without drifting off-topic.

Scoring rubric (0.0–1.0):
- 1.0  Directly and completely answers the query.
- 0.7  Answers the query but with some tangential content.
- 0.4  Partially addresses the query.
- 0.0  Does not address the query.

Respond ONLY with JSON: {"score": <float 0-1>, "reason": "<one sentence>"}"""


async def _llm_judge(system_prompt: str, user_prompt: str) -> Optional[float]:
    """Run an LLM-as-judge call via the Maverick synthesizer client.

    Returns a float score in [0, 1], or None if no LLM is available or the
    call/parse fails (caller falls back to a heuristic).
    """
    from app.agents.synthesizer import MaverickSynthesizer

    synth = MaverickSynthesizer()
    client = synth._client or synth._groq_client
    if client is None:
        return None

    model = settings.MAVERICK_MODEL if synth._client else settings.VISION_MODEL
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=256,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or ""
        parsed = json.loads(content)
        score = float(parsed.get("score"))
        return max(0.0, min(score, 1.0))
    except Exception as exc:  # noqa: BLE001 — judge is best-effort
        logger.warning("LLM judge call failed, falling back to heuristic: %s", exc)
        return None


def _word_overlap(a: str, b: str, boost: float) -> float:
    """Fraction of words in `a` also present in `b`, scaled by `boost`, capped at 1.0."""
    a_words = set(a.lower().split())
    b_words = set(b.lower().split())
    if not a_words or not b_words:
        return 0.0
    return min(len(a_words & b_words) / len(a_words) * boost, 1.0)


async def evaluate_faithfulness(
    trace_id: str,
    query: str,
    response: str,
    context: List[Dict],
) -> float:
    """Evaluate response faithfulness to retrieved context using LLM-as-judge.

    Uses Maverick (NIM) as an evaluator LLM; falls back to a word-overlap
    heuristic when no LLM is configured. Returns score 0-1.
    """
    if not langfuse_client.is_enabled:
        return 0.0
    if not context or not response:
        return 0.0

    context_text = " ".join(
        str(c.get("text", "")) for c in context if isinstance(c, dict)
    ).strip()
    if not context_text:
        return 0.0

    judge_score = await _llm_judge(
        FAITHFULNESS_JUDGE_SYSTEM,
        f"CONTEXT:\n{context_text[:6000]}\n\nRESPONSE:\n{response[:3000]}",
    )
    if judge_score is not None:
        score, comment = judge_score, "LLM-as-judge (Maverick)"
    else:
        score, comment = _word_overlap(response, context_text, 1.2), "Word-overlap heuristic (LLM unavailable)"

    langfuse_client.score(
        trace_id=trace_id,
        name="faithfulness",
        value=score,
        comment=comment,
    )
    return score


async def evaluate_relevance(
    trace_id: str,
    query: str,
    response: str,
) -> float:
    """Evaluate response relevance to query using LLM-as-judge.

    Uses Maverick (NIM) as an evaluator LLM; falls back to a keyword-overlap
    heuristic when no LLM is configured. Returns score 0-1.
    """
    if not langfuse_client.is_enabled:
        return 0.0
    if not query or not response:
        return 0.0

    judge_score = await _llm_judge(
        RELEVANCE_JUDGE_SYSTEM,
        f"QUERY:\n{query[:2000]}\n\nRESPONSE:\n{response[:3000]}",
    )
    if judge_score is not None:
        score, comment = judge_score, "LLM-as-judge (Maverick)"
    else:
        score, comment = _word_overlap(query, response, 1.3), "Keyword-overlap heuristic (LLM unavailable)"

    langfuse_client.score(
        trace_id=trace_id,
        name="relevance",
        value=score,
        comment=comment,
    )
    return score


async def evaluate_retrieval_quality(
    trace_id: str,
    query: str,
    retrieved: List[Dict],
    ground_truth_versions: Optional[List[int]] = None,
) -> Dict[str, float]:
    """Evaluate retrieval quality (Recall@5, MRR) against known ground truth.

    Computes real metrics from the retrieved ranking vs. the labeled relevant
    versions. Returns {} when ground truth is unavailable — never fabricates a
    score. Requires labeled `ground_truth_versions` (version_numbers) to score.
    """
    if not ground_truth_versions or not retrieved:
        return {}

    retrieved_versions = [
        r.get("version_number") for r in retrieved if r.get("version_number") is not None
    ]
    relevant = set(ground_truth_versions)
    if not relevant or not retrieved_versions:
        return {}

    # Recall@5
    top5 = set(retrieved_versions[:5])
    recall_at_5 = len(top5 & relevant) / len(relevant)

    # Mean Reciprocal Rank — rank of first relevant hit
    mrr = 0.0
    for rank, vn in enumerate(retrieved_versions, start=1):
        if vn in relevant:
            mrr = 1.0 / rank
            break

    metrics = {"recall_at_5": round(recall_at_5, 4), "mrr": round(mrr, 4)}

    if langfuse_client.is_enabled:
        for name, value in metrics.items():
            langfuse_client.score(trace_id, name, value)

    return metrics