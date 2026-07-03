# 06 · Tech Stack

Selected for a fast, **low-cost**, defensible prototype: open-source and local
by default, with a clean path to scale. Everything runs free on a laptop except
the agent LLM, which uses **open Hugging Face models** (free tier or self-hosted).

| Layer | Choice | Why this, and the cost lever |
|-------|--------|------------------------------|
| **Language** | Python 3.10+ | Ecosystem for ML/RAG/agents. |
| **Config** | pydantic-settings + `.env` | One typed source of defaults; swap models/backends without code changes. |
| **Data model** | Pydantic v2 (`DefectRecord`) | One canonical schema for every source + live submissions; validation for free. |
| **Datasets** | Eclipse/Mozilla (MSR 2013) · Apache JIRA | Large, real, and carry duplicate + resolution labels (ground truth). |
| **Embeddings** | **sentence-transformers** `all-MiniLM-L6-v2` (→ BGE for recall) | **Local & free.** Embeddings are the highest-volume call (every chunk + every query), so keeping them off paid APIs is the biggest cost saving. Runs on CPU. |
| **Vector store** | **Chroma** (persistent, HNSW cosine) | Zero-infra, local, good metadata filtering; scales to the full ~200k defects. Swappable for Qdrant/pgvector. |
| **RAG pipeline** | Custom (chunk → embed → index → retrieve) | Thin, transparent, no framework lock-in for the part we most need to control. |
| **Orchestration** | **LangGraph** | Conditional branches + short-circuits + shared state + tracing — matches the real triage workflow (see doc 04). |
| **Agent LLM** | **Open Hugging Face models** (default `Qwen/Qwen2.5-7B-Instruct`) via two interchangeable backends | Free / self-hostable. See below. |
| **UI** | **Streamlit** | Fastest path to a demoable paste/upload UI; ideal for a milestone prototype. |
| **Testing** | pytest | Parser + ingestion unit tests (16 passing); fast, no heavy deps. |

## Agent LLM — one interface, three backends

`src/llm/provider.py` exposes `get_chat_model()`; agents never know the backend.
Chosen by `LLM_PROVIDER` in `.env`:

1. **`huggingface`** — HF Inference API / Inference Providers (serverless). Only
   a free HF token needed. Zero infra — best for the demo.
2. **`openai_compatible` → vLLM** — self-host an open model on a GPU (e.g. the
   **Thunder** GPU credit). OpenAI-compatible, so the same agents point at it via
   `base_url`. Best cost/latency at scale.
3. **`openai_compatible` → Ollama** — the same interface, fully local for
   offline dev.

This decoupling means we prototype on the serverless API today and move onto a
self-hosted vLLM server later **without touching agent code** — only config.

## Why not the obvious alternatives

- **Paid LLM/embedding APIs (OpenAI/Cohere/Voyage)** — higher quality but
  recurring cost; the volume driver (embeddings) is handled well locally, and
  open instruct models are sufficient for triage/dedup/remediation on
  pre-extracted signals.
- **Fine-tuning** — the KB changes daily and we need citations; RAG is cheaper
  and grounded (see doc 01 §3).
- **CrewAI / linear chain** — can't cleanly express the duplicate short-circuit
  and triage gate we want to own and trace.
- **Pinecone / hosted vector DB** — unnecessary cost/dependency at prototype
  scale; Chroma is local and sufficient.

## Dependencies

- `requirements.txt` — core (M1): pydantic, pandas, sentence-transformers,
  chromadb, streamlit. Enough to build the KB and run the demo.
- `requirements-agents.txt` — agent layer (M2): langgraph, langchain,
  langchain-huggingface, langchain-openai.

Split intentionally so the M1 pipeline installs fast and clean without pulling
the agent stack.
