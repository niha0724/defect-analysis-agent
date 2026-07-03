# 05 · Knowledge Base Data Model

The KB is a **vector store of historical-defect chunks**, each carrying rich
scalar metadata. Every heterogeneous source normalizes into one canonical record
(`DefectRecord`, `src/schema.py`) before it is chunked, embedded, and indexed.

## Canonical record — `DefectRecord`

| Field | Type | Purpose |
|-------|------|---------|
| `defect_id` | str (PK) | Globally unique, source-prefixed: `eclipse-1001`, `apache-HADOOP-101` |
| `source` | enum | `eclipse` · `mozilla` · `apache` · `user_submission` |
| `project` | str | product / JIRA project (`Platform`, `HADOOP`) |
| `component` | str | sub-component (`UI`, `namenode`) |
| `title` | str | summary / short description |
| `description` | str | full body / steps / trace |
| `severity` | enum | `blocker…trivial` (normalized) |
| `priority` | enum | `P1…P5` |
| `status` | enum | `new…closed` |
| `resolution` | enum | `fixed · duplicate · wontfix · invalid · worksforme · …` |
| `duplicate_of` | str? | canonical `defect_id` this duplicates → **dedup ground truth** |
| `resolution_note` | str | fix summary / closing comment → **remediation knowledge** |
| `has_stack_trace` | bool | inferred; enables trace-aware retrieval/filters |
| `language` | str? | inferred programming language |
| `keywords` | list | issue type, extracted signals |
| `reporter`/`assignee`/`created_at`/`resolved_at`/`url` | str | provenance |

Two fields are deliberately first-class because they are the project's payoff:
`duplicate_of` (ground truth for the **Duplicate agent**) and `resolution_note`
(source material for the **Remediation agent**).

## Source → canonical mapping

**Bugzilla (Eclipse / Mozilla)** — `normalize_bugzilla()`:

| Source column | Canonical | Notes |
|---|---|---|
| `bug_id` | `defect_id` (prefixed) | |
| `short_desc` | `title` | |
| `long_desc`/`description`/`comments` | `description` | |
| `bug_severity` | `severity` | name-matched to enum |
| `priority` | `priority` | `P1…P5` |
| `bug_status` | `status` | |
| `resolution` | `resolution` | |
| `dup_id` | `duplicate_of` | prefixed with source |

**JIRA (Apache)** — `normalize_jira()`:

| Source column | Canonical | Notes |
|---|---|---|
| `key` | `defect_id` (prefixed) | e.g. `apache-HADOOP-101` |
| `summary` | `title` | |
| `description` | `description` | |
| `priority` | `severity` **and** `priority` | JIRA has no separate severity; Blocker→P1/CRITICAL, Critical→P2, Major→P3… |
| `status` / `resolution` | `status` / `resolution` | |
| `components` | `component` | |
| `issuetype` | filter | keep only `Bug`/`Defect` (drop improvements/tasks) |

Loaders are **alias-tolerant** (`_first()` tries many column names) so they
survive the renaming that differs across real-world exports.

## Chunking

- `combined_text()` = title (weighted) + description + resolution note +
  component. This is what gets embedded.
- Short reports → **1 chunk**. Long bodies → sliding window
  (`chunk_size=800`, `overlap=120` chars) breaking on line/word boundaries.
- Chunk id = `{defect_id}::chunk{i}`; metadata carries `chunk_index`, `n_chunks`
  so results collapse back to unique defects at query time.

## Vector store layout (Chroma)

One collection `historical_defects`, cosine space (HNSW):

| Chroma field | Content |
|---|---|
| `ids` | `{defect_id}::chunk{i}` |
| `documents` | chunk text |
| `embeddings` | sentence-transformers vector (L2-normalized, 384-d for MiniLM) |
| `metadatas` | scalar projection of `DefectRecord.to_metadata()` — `defect_id, source, project, component, title, severity, priority, status, resolution, duplicate_of, has_stack_trace, language, keywords, url` |

Metadata is scalar-only (Chroma constraint), which enables **filtered retrieval**:
`where={"source": "apache"}`, `where={"resolution": "fixed"}` (Remediation),
`where={"has_stack_trace": True}`, etc.

## Verified stats (bundled sample)

Built via `python -m src.ingestion.build_kb --reset`:

```
unique defects : 33          (34 rows − 1 non-bug improvement filtered)
chunks         : 34
with trace     : 12
by source      : {eclipse: 12, mozilla: 10, apache: 12}   # counts are per-chunk
by severity    : {major: 16, critical: 8, normal: 5, minor: 3, blocker: 2}
by resolution  : {fixed: 25, duplicate: 3, unresolved: 3, wontfix: 2, worksforme: 1}
```

(`by source` sums to 34 chunks, not 33 defects — one long Apache issue split
into two chunks.)

The 3 duplicate records (`eclipse-1007`, `mozilla-2005`, `apache-HADOOP-104`)
carry real `duplicate_of` links to their originals, providing end-to-end
ground truth for evaluating the Duplicate agent.

## Query path

`DefectRetriever` (`src/retrieval/retriever.py`): embed query → ANN search
(over-fetch `k×4` chunks) → collapse to unique defects (best score each) → return
top-k `RetrievedDefect`s. `find_duplicates()` filters to cosine ≥ 0.60.
The identical `combined_text` / `normalized_text` path is used for both
historical records and live submissions, so a submission is matched against
history with the same embedding function that built the index.
