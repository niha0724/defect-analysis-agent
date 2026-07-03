# 03 · Agent Responsibilities

Five specialized agents, each a node in the LangGraph pipeline (Module 3). Every
agent reads from and writes to the shared `AnalysisState`
(`src/agents/state.py`), so they stay decoupled and independently testable. All
agents run on an **open Hugging Face model** via `src/llm/provider.py`.

Design principle: **the agents receive pre-computed signals, not raw text.** The
Bug Submission Module already extracted the exception chain, log histogram, and
key signals; the Retriever already fetched similar defects. Agents reason over
that structured context, which keeps prompts short, cheap, and reliable on
small open models.

---

## 1. Triage Agent

| | |
|---|---|
| **Purpose** | First responder: validate and classify the submission, decide routing. |
| **Inputs** | `submission` (type, language, title, signals). |
| **Outputs** | `triage = {category, severity, priority, component, is_actionable, route}` |
| **Retrieval** | None (fast, cheap gate). |
| **Short-circuit** | If input is empty/non-actionable → stop with a rejection, skip the pipeline. |

*Prompt sketch:* "Given this parsed submission, classify category (crash / perf /
data-loss / UI / build …), predict severity and priority, name the most likely
affected component, and decide if it's actionable. Return JSON."

---

## 2. Log Analysis Agent

| | |
|---|---|
| **Purpose** | Turn stack traces / logs into a concise diagnosis of *what failed*. |
| **Inputs** | Parsed `exceptions` (chain), `log_level_counts`, salient log lines. |
| **Outputs** | `log_findings = {salient_errors, root_exception, error_timeline, level_summary}` |
| **Retrieval** | None (operates on already-parsed structure). |

*Leverages the parser:* the deepest `Caused by:` / chained exception is already
flagged as the root exception, so this agent focuses on interpretation (what the
error implies) rather than extraction.

---

## 3. Duplicate Agent  *(also Module 4)*

| | |
|---|---|
| **Purpose** | Decide whether this defect already exists in the KB. |
| **Inputs** | `retrieved` candidates from the Retriever (`find_duplicates`, cosine ≥ threshold). |
| **Outputs** | `duplicates = [{defect_id, confidence, rationale}]`, `is_duplicate: bool` |
| **Retrieval** | **Yes** — semantic candidates, optionally filtered to same project/source. |
| **Short-circuit** | Confident duplicate → mark `is_duplicate`, skip Root Cause + Remediation, return the canonical defect (and its known fix). |

*Two-stage design:* embeddings give high-recall candidates; the LLM confirms the
top few ("same defect? cite the ID") to remove near-miss false positives. Ground
truth for tuning comes from the datasets' real `duplicate_of` links.

---

## 4. Root Cause Agent

| | |
|---|---|
| **Purpose** | Hypothesize the underlying cause, grounded in evidence. |
| **Inputs** | `submission` signals + `log_findings` + `retrieved` historical defects. |
| **Outputs** | `root_cause = {hypothesis, confidence, evidence, cited_defects[]}` |
| **Retrieval** | **Yes** — similar defects provide precedent and their diagnoses. |

*Grounding requirement:* every hypothesis must cite the retrieved defect IDs it
drew on (or state "no precedent found"). This is the core RAG payoff — verifiable
reasoning instead of a plausible guess.

---

## 5. Remediation Agent

| | |
|---|---|
| **Purpose** | Propose concrete fixes/workarounds. |
| **Inputs** | `root_cause` + `retrieved` defects **filtered to `resolution=fixed`** (their `resolution_note`s carry real fixes). |
| **Outputs** | `remediation = {steps[], code_or_config_hints, references[]}` |
| **Retrieval** | **Yes** — prior *resolved* defects are the primary source of fixes. |

*Why this works:* the KB stores each historical defect's fix note. The
Remediation agent retrieves how structurally-similar bugs were actually resolved
and adapts them — turning closed tickets into actionable guidance.

---

## Shared contract

```python
# src/agents/state.py
class AnalysisState(TypedDict, total=False):
    raw_text, submission                 # inputs
    triage, log_findings                 # per-agent outputs …
    retrieved, duplicates, is_duplicate  # shared RAG context + dedup
    root_cause, remediation
    errors, final_report                 # control
```

Each agent writes only its own namespaced key. `retrieved` is shared context
populated once and read by Duplicate / Root Cause / Remediation, so retrieval
isn't repeated. Model, temperature, and backend are centralized in
`src/llm/provider.py` and `config/settings.py`.
