"""LLM access for the agent layer (open Hugging Face models)."""
from src.llm.provider import get_chat_model, is_llm_configured

__all__ = ["get_chat_model", "is_llm_configured"]
