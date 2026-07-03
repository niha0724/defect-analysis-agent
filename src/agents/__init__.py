"""Module 3 — Multi-Agent Orchestration (Milestone 2).

Milestone 1 ships the *contract* for the pipeline: the shared state object and
the agent role definitions the LangGraph nodes will implement. The nodes and
the compiled graph land in Milestone 2, on top of the retriever + LLM provider
already built here.
"""
from src.agents.state import AGENT_RESPONSIBILITIES, AgentRole, AnalysisState

__all__ = ["AGENT_RESPONSIBILITIES", "AgentRole", "AnalysisState"]
