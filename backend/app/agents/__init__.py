"""SoloPrac AI — LangGraph Agent System

Architecture:
  ┌─────────────┐
  │   Router    │  Llama-3.1-8B → classifies intent
  └──────┬──────┘
         ▼
  ┌──────────────┐
  │ Tool Executor│  Dispatches to RAG / Doc / Vision / Calendar
  └──────┬──────┘
         ▼
  ┌──────────────┐
  │  Critic      │  Evaluates output → re-plan or finish
  └──────┬──────┘
         ▼
  ┌──────────────┐
  │ Synthesizer  │  Maverick → final response
  └──────────────┘
"""

from app.agents.state import AgentState, AgentIntent, AgentToolCall
from app.agents.router import IntentRouter
from app.agents.tools import tool_registry

__all__ = ["AgentState", "AgentIntent", "AgentToolCall", "IntentRouter", "tool_registry"]
