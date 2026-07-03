# 02 · System Architecture

## Overview

The system turns a raw bug submission into a structured, grounded analysis by
combining a **RAG knowledge base** of historical defects with a **multi-agent
pipeline**. There are two data-flow paths:

- **Offline (ingestion):** public datasets → normalize → chunk → embed → index.
  Runs when building/refreshing the knowledge base.
- **Online (analysis):** a submission → parse → retrieve similar defects →
  multi-agent reasoning → structured findings → analytics.

```mermaid
flowchart TB
    subgraph OFFLINE["🗄️ Offline · KB ingestion (Module 2)"]
        DS["Public datasets<br/>Eclipse · Mozilla · Apache"] --> NORM["Normalize → DefectRecord"]
        NORM --> CLEAN["Clean + chunk"]
        CLEAN --> EMB1["Embed (sentence-transformers)"]
        EMB1 --> VDB[("Chroma<br/>vector store")]
    end

    subgraph ONLINE["⚡ Online · analysis pipeline"]
        UI["Streamlit UI<br/>(Module 1: paste / upload)"] --> PARSE["Parse & normalize<br/>type · language · exception chain · signals"]
        PARSE --> RET["Retriever<br/>(embed query → ANN search)"]
        VDB --- RET
        RET --> ORCH{{"LangGraph Orchestrator (Module 3)"}}
        ORCH --> TRIAGE["Triage Agent"]
        ORCH --> LOG["Log Analysis Agent"]
        ORCH --> DUP["Duplicate Agent<br/>(Module 4)"]
        ORCH --> RC["Root Cause Agent"]
        ORCH --> REM["Remediation Agent"]
        TRIAGE & LOG & DUP & RC & REM --> FIND["Structured Findings<br/>(Module 5)"]
        FIND --> ANALYTICS["Pattern Analytics<br/>(Module 6)"]
    end

    LLM["Open HF LLM<br/>(HF Inference API / vLLM / Ollama)"] -. serves .- ORCH
```

> **Milestone 1 scope** implements the shaded pieces end-to-end: the **entire
> offline ingestion path**, the **Bug Submission Module** (parse & normalize),
> and the **Retriever** (the RAG query side), surfaced in the Streamlit UI.
> The orchestrator + 5 agents (Module 3), and Modules 4–6, are scaffolded
> (shared state + retriever + LLM provider are already built) and land in M2+.

---

## Component responsibilities

| # | Module | Responsibility | Status (M1) |
|---|--------|----------------|-------------|
| 1 | **Bug Submission** | Accept paste/upload; detect report vs trace vs log; extract exception chain, log histogram, key signals; normalize | built |
| 2 | **Historical Defect KB + RAG** | Load/normalize datasets; clean, chunk, embed, index; retrieve top-k | built |
| 3 | **Multi-Agent Orchestration** | LangGraph graph coordinating 5 agents over shared state | scaffold (state, roles, LLM provider) |
| 4 | **Duplicate Detection** | Semantic candidate search + threshold, then LLM confirm | retrieval built ·  confirm in M2 |
| 5 | **Structured Findings** | Render triage/root-cause/duplicate/remediation into a report | preview panel |
| 6 | **Pattern Analytics** | Aggregate across defects to find systemic issues | later |

---

## Layered view

```mermaid
flowchart LR
    A["Presentation<br/>Streamlit"] --> B["Application<br/>orchestrator · retriever · parser"]
    B --> C["Domain<br/>DefectRecord · agents' contracts"]
    B --> D["Infrastructure<br/>Chroma · sentence-transformers · HF LLM"]
```

- **Presentation** — `app/streamlit_app.py`. Thin; calls the application layer.
- **Application** — `src/submission` (parse), `src/retrieval` (RAG query),
  `src/agents` (orchestration, M2), `src/ingestion/build_kb` (offline).
- **Domain** — `src/schema.py` (`DefectRecord` + enums) and
  `src/agents/state.py` (`AnalysisState`, agent roles). The shared contracts.
- **Infrastructure** — `src/ingestion/{embeddings,vectorstore}.py`,
  `src/llm/provider.py`. Swappable behind interfaces (change the embedding model
  or LLM backend via config, no code change).

---

## Online analysis sequence (target, M2)

```mermaid
sequenceDiagram
    participant U as User
    participant S as Submission
    participant R as Retriever (RAG)
    participant O as Orchestrator
    participant L as LLM (HF)
    U->>S: paste / upload
    S->>S: parse → type, language, exception chain, signals
    S->>R: normalized_text
    R->>R: embed + ANN search (top-k)
    R-->>O: retrieved historical defects
    O->>L: Triage(prompt + signals)
    O->>L: Log Analysis(exception chain)
    O->>L: Duplicate(candidates) → maybe short-circuit
    O->>L: Root Cause(signals + retrieved)
    O->>L: Remediation(retrieved fixes)
    O-->>U: structured findings + citations
```

The Duplicate agent can **short-circuit**: a confident duplicate skips the
costly root-cause/remediation hops and returns the known defect + its fix.

---

## Deployment / runtime

- **Prototype (now):** everything local — Streamlit + Chroma (persistent on
  disk) + local embeddings. The agent LLM is remote (HF Inference API) or local
  (vLLM/Ollama). Single `pip install`, single `streamlit run`.
- **Scale path:** Chroma → server mode or Qdrant; swap MiniLM → BGE-base for
  recall; move agents onto self-hosted **vLLM** (e.g. Thunder GPU) via the same
  OpenAI-compatible interface. None of these touch agent code — they are config.

See `docs/03_agent_responsibilities.md`, `docs/04_orchestration_flow.md`, and
`docs/05_knowledge_base_data_model.md` for the detailed designs, and
`docs/06_tech_stack.md` for the technology choices.
