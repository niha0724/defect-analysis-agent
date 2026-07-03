"""Provider-agnostic chat model factory for the agents.

All agents call ``get_chat_model()`` and receive a LangChain chat model — they
never care which backend serves it. Two backends are supported, both running
**open Hugging Face models**:

* ``huggingface``        — HF Inference API / Inference Providers (serverless).
                           Needs only a free HF token. Zero infra.
* ``openai_compatible``  — any OpenAI-compatible server: vLLM (e.g. on your
                           Thunder GPU), Ollama, or LM Studio. Free/local,
                           just point OPENAI_COMPATIBLE_BASE_URL at it.

Switching backend is a one-line change in .env (LLM_PROVIDER=...), so you can
prototype against the serverless API and later move the exact same agents onto
a self-hosted vLLM server for cost/latency without touching agent code.

Heavy imports are deferred into the factory functions so importing this module
(e.g. from the Streamlit app) never drags in LangChain unless an LLM is used.
"""
from __future__ import annotations

from typing import Optional

from config import settings


def get_chat_model(
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
):
    provider = settings.llm_provider.lower()
    temperature = settings.llm_temperature if temperature is None else temperature
    max_tokens = settings.llm_max_tokens if max_tokens is None else max_tokens

    if provider == "huggingface":
        return _hf_chat_model(model or settings.llm_model, temperature, max_tokens)
    if provider in ("openai_compatible", "openai", "vllm", "ollama"):
        return _openai_compatible_chat_model(model or settings.openai_compatible_model, temperature, max_tokens)
    raise ValueError(
        f"Unknown LLM_PROVIDER={settings.llm_provider!r}. Use 'huggingface' or 'openai_compatible'."
    )


def _hf_chat_model(model: str, temperature: float, max_tokens: int):
    if not settings.huggingfacehub_api_token:
        raise RuntimeError(
            "HUGGINGFACEHUB_API_TOKEN is not set. Create a free token at "
            "https://huggingface.co/settings/tokens and put it in .env."
        )
    from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint

    endpoint = HuggingFaceEndpoint(
        repo_id=model,
        task="text-generation",
        huggingfacehub_api_token=settings.huggingfacehub_api_token,
        temperature=max(temperature, 0.01),   # HF endpoint requires strictly > 0
        max_new_tokens=max_tokens,
    )
    return ChatHuggingFace(llm=endpoint)


def _openai_compatible_chat_model(model: str, temperature: float, max_tokens: int):
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        base_url=settings.openai_compatible_base_url,
        api_key=settings.openai_compatible_api_key or "not-needed",
    )


def is_llm_configured() -> bool:
    """True when an LLM backend looks usable — used by the UI to enable/disable
    the (Milestone 2) agent features without importing LangChain."""
    provider = settings.llm_provider.lower()
    if provider == "huggingface":
        return bool(settings.huggingfacehub_api_token)
    return bool(settings.openai_compatible_base_url)
