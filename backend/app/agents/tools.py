"""Tool registry — all agent-accessible tools register here."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class AgentTool(Protocol):
    """Protocol for agent tools."""
    name: str
    description: str
    parameters: dict  # JSON Schema

    async def __call__(self, **kwargs) -> Any: ...


class ToolRegistry:
    """Registry that tools self-register into via @tool decorator."""

    def __init__(self):
        self._tools: Dict[str, AgentTool] = {}

    def register(self, tool: AgentTool) -> AgentTool:
        """Register a tool instance or decorated function."""
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")
        return tool

    def get(self, name: str) -> Optional[AgentTool]:
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        """Return tool metadata for LLM function calling."""
        return [
            {"name": t.name, "description": t.description, "parameters": t.parameters}
            for t in self._tools.values()
        ]

    def __contains__(self, name: str) -> bool:
        return name in self._tools


# Global tool registry
tool_registry = ToolRegistry()


def tool(name: str, description: str, parameters: dict):
    """Decorator to register a tool."""
    def decorator(func):
        func.name = name
        func.description = description
        func.parameters = parameters
        tool_registry.register(func)
        return func
    return decorator


# ─── Stub tool definitions (implemented in later weeks) ───

@tool(
    name="retrieve_patient_context",
    description="Retrieve patient context from Qdrant using temporal-aware RAG",
    parameters={
        "type": "object",
        "properties": {
            "patient_id": {"type": "string", "format": "uuid"},
            "query": {"type": "string"},
        },
        "required": ["patient_id", "query"],
    },
)
async def retrieve_patient_context(patient_id: str, query: str, **kwargs) -> dict:
    """Temporal RAG — Feature A. Implemented in Week 6."""
    return {"status": "not_implemented", "message": "Temporal RAG will be built in Week 6"}


@tool(
    name="synthesize_response",
    description="Generate a natural language response using Maverick LLM",
    parameters={
        "type": "object",
        "properties": {
            "context": {"type": "object"},
            "query": {"type": "string"},
        },
        "required": ["context", "query"],
    },
)
async def synthesize_response(context: dict, query: str, **kwargs) -> dict:
    """Maverick response generator — built Week 5."""
    return {"status": "not_implemented"}


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
