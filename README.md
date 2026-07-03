#  Agentic Defect Analysis System

An AI system that analyzes software defects by combining **RAG over a knowledge
base of historical bugs** with a **multi-agent pipeline** (triage → log analysis
→ duplicate detection → root cause → remediation). Submit a bug report, stack
trace, or error log; get back a structured, grounded analysis that cites the
prior defects it reasoned from.

> **Milestone 1 status — working prototype.** The Bug Submission Module and the
> Historical Defect Knowledge Base (RAG pipeline) are built, tested, and
> demoable end-to-end. The multi-agent layer (Module 3) is scaffolded — shared
> state, agent roles, retriever, and LLM provider are in place — and is
> implemented in Milestone 2.

---

## The six modules

| # | Module | M1 status |
|---|--------|-----------|
| 1 | **Bug Submission** — paste/upload → detect report vs trace vs log → extract exception chain, log histogram, key signals |  built + tested |
| 2 | **Historical Defect KB + RAG** — normalize datasets → clean → chunk → embed → index → retrieve |  built + tested |
| 3 | **Multi-Agent Orchestration** (Triage · Log · Root Cause · Duplicate · Remediation) via LangGraph |  scaffolded (M2) |
| 4 | **Duplicate Detection** — semantic candidates + threshold + LLM confirm |  retrieval built ·  confirm (M2) |
| 5 | **Structured Findings** display |  preview (M2) |
| 6 | **Pattern Analytics** — systemic-issue detection |  later |

---

## Quickstart

```bash
# 1. Install core deps (Bug Submission + RAG + UI)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Generate the bundled sample data (already committed, but reproducible)
python scripts/make_sample_data.py

# 3. Build the knowledge base from the sample data (no Kaggle needed)
python -m src.ingestion.build_kb --reset --query "NullPointerException when saving the editor"

# 4. Run the prototype UI
streamlit run app/streamlit_app.py

# 5. Run the tests
pytest
```

For the multi-agent layer (M2): `pip install -r requirements-agents.txt` and set
an LLM backend in `.env` (copy from `.env.example`).

---

## Verified demo output

Building the KB from the bundled sample and querying it (step 3 above):

```
=== Knowledge Base stats ===
  unique defects : 33   chunks : 34   with trace : 12
  by source      : {eclipse: 12, mozilla: 10, apache: 12}
  by resolution  : {fixed: 25, duplicate: 3, unresolved: 3, wontfix: 2, worksforme: 1}

=== Retrieval: 'NullPointerException when saving the editor' ===
  [1] score=0.824  eclipse-1001  (eclipse/major/fixed)      NullPointerException when saving editor…
  [2] score=0.794  eclipse-1007  (eclipse/major/duplicate)  Saving a file throws NPE in SaveHandler…
```

Hits **[1]** and **[2]** are a real duplicate pair (`eclipse-1007 → eclipse-1001`)
— the RAG layer surfaces both the matching defect and its known duplicate.
Cross-project semantic match also works: *"job runs out of heap memory during
shuffle"* → `apache-SPARK-202` (OutOfMemoryError during shuffle) at 0.67.

---

## How it works

```
OFFLINE  datasets → normalize (DefectRecord) → clean → chunk → embed → Chroma
ONLINE   submit → parse → embed query → retrieve top-k → [agents, M2] → findings
```

- **Bug Submission** parses three input shapes (bug report / stack trace / error
  log), extracts the exception cause-chain (marking the deepest as root cause),
  builds a log-level histogram, and pulls out high-precision retrieval signals.
- **Knowledge Base** normalizes Eclipse/Mozilla (Bugzilla) and Apache (JIRA)
  data into one canonical schema, then chunks/embeds/indexes it. Retrieval uses
  local sentence-transformer embeddings + cosine ANN, with metadata filtering.

Full design: [`docs/`](docs/) — architecture, agents, orchestration, data model.

---

## Project structure

```
config/            typed settings (pydantic-settings + .env)
src/
  schema.py        canonical DefectRecord + enums (the shared contract)
  submission/      Module 1 — parsers (report/trace/log) + schemas
  ingestion/       Module 2 — datasets, preprocess, chunking, embeddings, vectorstore, build_kb
  retrieval/       semantic search + duplicate matching over the KB
  llm/             open-HF LLM provider (HF Inference API / vLLM / Ollama)
  agents/          Module 3 — shared state + agent roles (orchestration in M2)
app/               Streamlit prototype UI
data/sample/       bundled Eclipse/Mozilla/Apache CSVs (runnable out of the box)
scripts/           make_sample_data.py · download_datasets.py · build_real_kb.py
tests/             pytest — parser + ingestion unit tests (16 passing)
docs/              design documentation (01–06)
```

---

## Datasets

The bundled sample (`data/sample/`) runs with **zero setup**. To seed the KB
with the **real public datasets** (verified — 9,000 defects indexed):

```bash
# Apache needs a free Kaggle token (~/.kaggle/kaggle.json); Eclipse+Mozilla are public.
python scripts/download_datasets.py --run
python scripts/build_real_kb.py --reset --limit 3000
```

Real-data build (verified output):

```
loaded defects : 9000    chunks : 12493
by source      : {apache: 6493, eclipse: 3000, mozilla: 3000}   # chunk counts
by severity    : {major: 4825, normal: 3876, minor: 1737, critical: 691, blocker: 462, ...}
by resolution  : {fixed: 7910, duplicate: 1294, invalid: 1135, worksforme: 752, ...}

Retrieval 'NullPointerException during build'  → eclipse-175808 (fixed)  0.64
Retrieval 'out of memory java heap'            → apache-CACTUS-213       0.64
Retrieval 'browser crash on startup'           → mozilla-415528          0.64
```

Sources:
- **Apache JIRA issues** — [Kaggle `tedlozzo/apaches-jira-issues`](https://www.kaggle.com/datasets/tedlozzo/apaches-jira-issues) (`issues.csv`, 1.9 GB — the loader streams it in chunks)
- **Eclipse & Mozilla Defect Tracking Dataset** — Lamkanfi et al., MSR 2013 · [GitHub mirror](https://github.com/ansymo/msr2013-bug_dataset) (per-product XML, ~200k genuine defects)

---

## Tech stack (summary)

Python · Pydantic · **sentence-transformers** (local embeddings) · **Chroma**
(vector DB) · **LangGraph** (orchestration) · **open Hugging Face LLMs**
(HF Inference API / vLLM / Ollama) · **Streamlit** · pytest.
Full rationale in [`docs/06_tech_stack.md`](docs/06_tech_stack.md).

---

## Roadmap

- **M1 (done)** — Bug Submission Module · Historical Defect KB + RAG (seeded with 9k real Apache/Eclipse/Mozilla defects) · design docs.
- **M2** — implement the 5 LangGraph agents; LLM-confirmed duplicate detection;
  structured findings display.
- **M3+** — pattern analytics / systemic-issue detection (Module 6); evaluation
  on the datasets' ground-truth duplicate & resolution labels.

## Documentation

1. [Research & understanding](docs/01_research_notes.md)
2. [System architecture](docs/02_system_architecture.md)
3. [Agent responsibilities](docs/03_agent_responsibilities.md)
4. [Orchestration flow](docs/04_orchestration_flow.md)
5. [Knowledge base data model](docs/05_knowledge_base_data_model.md)
6. [Tech stack](docs/06_tech_stack.md)
