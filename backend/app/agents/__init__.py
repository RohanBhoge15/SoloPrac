"""SoloPrac AI — LangGraph Agent System

Architecture:
  ┌─────────────┐
  │   Router    │  Llama-3.1-8B → classifies intent
  └──────┬──────┘
         ▼
  ┌──────────────┐
  │   Planner    │  Generates step-by-step plan (Feature B)
  └──────┬──────┘
         ▼
  ┌──────────────┐
  │  Executor    │  Runs tool calls with retry + error handling
  └──────┬──────┘
         ▼
  ┌──────────────┐
  │ Synthesizer  │  Maverick → final response with citations
  └──────┬──────┘
         ▼
  ┌──────────────┐
  │  Responder   │  Formats + streams the response (SSE)
  └──────────────┘
"""

from app.agents.state import AgentState, AgentIntent, AgentToolCall
from app.agents.router import IntentRouter
from app.agents.tools import tool_registry
from app.agents.graph import AgentGraph
from app.agents.synthesizer import MaverickSynthesizer

__all__ = [
    "AgentState", "AgentIntent", "AgentToolCall",
    "IntentRouter", "tool_registry",
    "AgentGraph", "MaverickSynthesizer",
]
