# 01 · Research & Understanding

Background study that justifies the design decisions in the rest of these docs.
Four areas were studied: **defect-analysis workflows**, **bug-report structure**,
**RAG architecture**, and **semantic-similarity / duplicate-detection techniques**.

---

## 1. Defect-analysis & bug-triage workflows

A defect moves through a fairly universal lifecycle in issue trackers (Bugzilla,
JIRA, GitHub Issues):

```
report → triage → assign → diagnose (root cause) → fix → verify → close
                    │
                    └─ (dedup, set severity/priority/component, route)
```

The expensive, human-intensive, and automatable steps are the early ones:

| Step | What a human does today | Pain point | Our agent |
|------|-------------------------|-----------|-----------|
| Triage | Read report, set severity/priority, pick component | Slow, inconsistent between people | **Triage Agent** |
| Dedup | Search tracker for existing/similar reports | Manual search misses semantic dups | **Duplicate Agent** + RAG |
| Log reading | Scan stack traces / logs for the real error | Tedious, easy to miss the deepest cause | **Log Analysis Agent** |
| Diagnosis | Hypothesize root cause from experience | Depends on tribal knowledge | **Root Cause Agent** (RAG-grounded) |
| Fix guidance | Recall how a similar bug was fixed | Knowledge locked in old closed tickets | **Remediation Agent** (RAG) |

**Key insight that shapes the architecture:** most of the value is in *reusing
history*. A large fraction of incoming defects resemble something already
resolved. So the system is built around a **Historical Defect Knowledge Base**
that every reasoning agent can retrieve from — this is why RAG is the backbone,
not an add-on.

Studies of bug triage repeatedly find that a substantial share of reports are
**duplicates**, and that duplicate/severity assignment is a prime target for
automation — which is exactly what the MSR-2013 Eclipse/Mozilla dataset was
built to support (bug-triage lifecycle, severity prediction, duplicate study).

---

## 2. Bug-report structure

Submissions come in three shapes; the Bug Submission Module must handle all
three and normalize them.

**(a) Structured bug report** — tracker fields + free text:
- *Metadata*: product, component, severity, priority, status, resolution,
  reporter, assignee, dates, `duplicate_of`.
- *Free text*: summary/title, description, steps-to-reproduce, expected vs
  actual, environment/version, comments.

**(b) Stack trace** — highly structured, language-specific:
- Exception **type** + **message**, ordered **frames** (`file:line`, method),
  and a **cause chain** (Java `Caused by:`, Python chained tracebacks). The
  *deepest* cause is usually the real root cause — the parser marks it.

**(c) Error log** — semi-structured lines:
- `timestamp · level · logger · message`, often with an embedded stack trace.
  The level histogram (how many ERROR/FATAL) and the first error are the signal.

**Design consequence:** we parse each shape into a canonical structure
(`ParsedArtifact`) with an **exception chain**, a **log-level histogram**, and
**key signals** (exception types, error codes, file names). Those signals are
high-precision retrieval anchors and are handed to the agents pre-extracted, so
the LLM does not have to re-derive them from raw text.

---

## 3. RAG (Retrieval-Augmented Generation) architecture

RAG grounds an LLM's output in retrieved documents instead of relying on
parametric memory. Canonical pipeline:

```
INGEST (offline):  documents → clean → chunk → embed → index in vector DB
QUERY  (online):   query → embed → ANN search (top-k) → build context → LLM generates grounded answer
```

**Why RAG (vs. fine-tuning) for defect analysis:**
- The knowledge base changes constantly (new bugs daily) — re-indexing is cheap,
  re-fine-tuning is not.
- **Grounding & citations**: the Root Cause and Remediation agents must cite the
  *specific* prior defects they reasoned from. RAG gives verifiable provenance;
  a fine-tuned model hallucinates ticket IDs.
- **Cost / hardware**: with open Hugging Face models, retrieval + a modest
  instruct model beats fine-tuning a large model on limited GPU budget.

**Design choices derived from RAG best practice:**
- *Chunking*: bug reports are short, so most become a single chunk; long
  descriptions/comment threads are split with **overlap** so a match near a
  boundary is not lost (see `chunking.py`).
- *Embeddings*: local **sentence-transformers** (MiniLM / BGE) — free, fast on
  CPU, and good enough for short technical text. Chosen over paid embedding APIs
  because embeddings are called on *every* chunk and *every* query (the highest-
  volume LLM-adjacent call), so keeping them local is the biggest cost lever.
- *Retrieval*: cosine similarity over an **HNSW** index (Chroma) for
  approximate-nearest-neighbour search that scales to the full ~200k-defect set.
- *Metadata filtering*: retrieval can be constrained by `source`, `severity`,
  `resolution`, etc., so the Duplicate agent can prefer same-project matches and
  the Remediation agent can prefer `resolution=fixed` defects.

---

## 4. Semantic similarity & duplicate detection

**Lexical vs. semantic.** Keyword/TF-IDF matching misses paraphrases
("app crashes on launch" vs "browser dies at startup"). **Dense embeddings**
place semantically similar text nearby in vector space, catching duplicates that
share no keywords. The classic duplicate-bug-detection literature moved exactly
this way: from TF-IDF/BM25 towards embedding-based similarity.

**Technique used here:**
- Encode text with a sentence-transformer → L2-normalized vector.
- Similarity = **cosine** (dot product of normalized vectors), in `[-1, 1]`.
- **Duplicate decision** = similarity above a threshold (default `0.60`), then
  (in M2) an LLM confirmation step to cut false positives. This two-stage
  "cheap recall → precise confirm" pattern is standard for dedup.
- **Evaluation** (planned, M2+): the public datasets ship real `duplicate_of`
  links, giving ground truth to measure **recall@k** and tune the threshold.

**Why a threshold + LLM confirm rather than threshold alone:** embeddings give
high recall but imperfect precision; a short LLM judgment on the top candidates
("are these the same defect? cite the ID") removes near-miss false positives
cheaply. The bundled sample includes real duplicate pairs
(`eclipse-1007→eclipse-1001`, `mozilla-2005→mozilla-2001`,
`apache-HADOOP-104→HADOOP-101`) to validate this end to end.

---

## 5. Datasets studied

| Source | Dataset | Scale | Schema |
|--------|---------|-------|--------|
| Eclipse + Mozilla | **Eclipse & Mozilla Defect Tracking Dataset** (Lamkanfi et al., MSR 2013) | ~200k genuine defects (Eclipse ~47k, Mozilla ~168k) | Bugzilla: `bug_id, product, component, bug_severity, priority, short_desc, bug_status, resolution, dup_id, …` (ships as XML; CSV mirrors exist) |
| Apache | **Apache issues exported from JIRA** (Kaggle `tedlozzo/apaches-jira-issues`; Zenodo mirror) | 100k+ issues across many Apache projects | JIRA: `key, project, issuetype, summary, description, priority, status, resolution, components, …` |

These were chosen because they are large, real, and — crucially — carry
**resolutions and duplicate links**, which become ground truth for the Duplicate
and Remediation agents. See `docs/05_knowledge_base_data_model.md` for the exact
field-by-field mapping into our canonical schema.

---

## References

- A. Lamkanfi, J. Pérez, S. Demeyer. *The Eclipse and Mozilla Defect Tracking
  Dataset: A Genuine Dataset for Mining Bug Information.* MSR 2013.
  <https://doi.org/10.1109/MSR.2013.6624028> ·
  mirror <https://github.com/ansymo/msr2013-bug_dataset>
- Apache JIRA issues (Kaggle): <https://www.kaggle.com/datasets/tedlozzo/apaches-jira-issues>
- Lewis et al. *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks.* 2020.
- Reimers & Gurevych. *Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks.* 2019.
- Chroma (vector DB) <https://docs.trychroma.com> · sentence-transformers <https://www.sbert.net> · LangGraph <https://langchain-ai.github.io/langgraph/>
