"""Agent state definitions — typed graph state for LangGraph."""

from __future__ import annotations

from typing import Optional, List, Dict, Any, TypedDict, Annotated
from uuid import UUID
from datetime import datetime, timezone, timezone
from enum import Enum


class AgentIntent(str, Enum):
    """Known intent types the router can classify."""
    PATIENT_QA = "patient_qa"
    IMAGE_ANALYSIS = "image_analysis"
    IMAGE_COMPARE = "image_compare"
    DOCUMENT_PARSE = "document_parse"
    SCHEDULING = "scheduling"
    PRESCRIPTION = "prescription"
    INVOICE = "invoice"
    CERTIFICATE = "certificate"
    WEEKLY_REPORT = "weekly_report"
    GENERAL_CHAT = "general_chat"


class AgentToolCall(TypedDict):
    """A tool call emitted by the planner node."""
    tool_name: str
    tool_args: Dict[str, Any]
    result: Optional[Any]
    error: Optional[str]


class AgentState(TypedDict):
    """State passed through the LangGraph agent nodes."""

    # User input
    user_query: str
    user_id: UUID
    doctor_id: UUID
    patient_id: Optional[UUID]
    conversation_id: Optional[str]

    # Router output
    intent: Optional[AgentIntent]
    confidence: float
    reasoning: Optional[str]

    # Planned steps
    plan: Optional[List[Dict[str, Any]]]  # [{step_id, tool, args, depends_on}]
    current_step: int

    # Execution
    tool_calls: Annotated[List[AgentToolCall], "accumulate"]
    retrieved_context: Optional[Dict[str, Any]]
    analysis_result: Optional[Dict[str, Any]]

    # Synthesis
    draft: Optional[str]
    citations: Optional[List[Dict[str, Any]]]
    final_response: Optional[str]

    # Control flow
    error_count: int
    max_retries: int
    trace_events: List[str]

    # Metadata
    started_at: datetime
    completed_at: Optional[datetime]
    langfuse_trace_id: Optional[str]

    # Feature B: Self-Planning
    replan_count: int

    # Image registration (Module 4)
    uploaded_images: Optional[List[str]]
    comparison_results: Optional[List[Dict[str, Any]]]


def create_initial_state(
    user_query: str,
    doctor_id: UUID,
    patient_id: Optional[UUID] = None,
    conversation_id: Optional[str] = None,
) -> AgentState:
    """Create a fresh agent state for a new request."""
    return AgentState(
        user_query=user_query,
        user_id=doctor_id,
        doctor_id=doctor_id,
        patient_id=patient_id,
        conversation_id=conversation_id,
        intent=None,
        confidence=0.0,
        reasoning=None,
        plan=None,
        current_step=0,
        tool_calls=[],
        retrieved_context=None,
        analysis_result=None,
        draft=None,
        citations=None,
        final_response=None,
        error_count=0,
        max_retries=2,
        trace_events=["Agent initialized"],
        started_at=datetime.now(timezone.utc),
        completed_at=None,
        langfuse_trace_id=None,
        replan_count=0,
        uploaded_images=None,
        comparison_results=None,
    )
