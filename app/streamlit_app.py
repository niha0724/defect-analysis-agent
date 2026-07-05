"""Milestone 1 prototype UI.

Demonstrates the two working modules end-to-end:
  * Module 1 — Bug Submission: paste or upload -> detect type -> extract signals
  * Module 2 — RAG: query the Historical Defect KB for similar past defects
                    (and flag likely duplicates)

The multi-agent analysis (Triage / Log / Root-Cause / Duplicate / Remediation)
is Milestone 2; its panel here is a labelled preview.

Run from the repo root:  streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import os
import sys

# Make `src` / `config` importable no matter where streamlit is launched from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import streamlit as st

from config import settings
from src.agents.state import AGENT_RESPONSIBILITIES
from src.submission.parsers import parse_submission

st.set_page_config(page_title="Agentic Defect Analysis — M1", page_icon="", layout="wide")

ARTIFACT_BADGE = {
    "bug_report": "Bug report",
    "stack_trace": "Stack trace",
    "error_log": "Error log",
    "mixed": " Mixed (report + trace)",
    "unknown": "❔ Unknown",
}


# --------------------------------------------------------------------------
# Cached heavy resources (embedder + Chroma) load once per session.
# --------------------------------------------------------------------------
@st.cache_resource(show_spinner="Loading embeddings + vector store…")
def get_retriever():
    from src.retrieval import DefectRetriever
    return DefectRetriever()


def kb_ready() -> tuple[bool, int]:
    try:
        r = get_retriever()
        return r.store.count() > 0, r.store.count()
    except Exception as e:  # noqa: BLE001
        st.session_state["_kb_error"] = str(e)
        return False, 0


def render_similarity_results(results, threshold: float) -> None:
    if not results:
        st.info("No similar historical defects found.")
        return
    for r in results:
        dup = r.score >= threshold
        flag = "🔁 **Likely duplicate**" if dup else "🔎 Similar"
        with st.container(border=True):
            c1, c2 = st.columns([5, 1])
            with c1:
                st.markdown(f"{flag} · `{r.defect_id}`  —  **{r.title}**")
                meta = f"source: `{r.source}` · severity: `{r.severity}` · resolution: `{r.resolution}`"
                if r.duplicate_of:
                    meta += f" · dup-of: `{r.duplicate_of}`"
                st.caption(meta)
                if r.is_resolved_fixed and r.metadata.get("resolution"):
                    st.caption("has a known fix — useful for remediation")
            with c2:
                st.metric("similarity", f"{r.score:.2f}")
            if r.url:
                st.caption(f"[open in tracker]({r.url})")


# --------------------------------------------------------------------------
# Sidebar
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("Status")
    ready, n = kb_ready()
    if ready:
        st.success(f"Knowledge base: {n} chunks indexed")
    else:
        st.warning("Knowledge base is empty.")
        st.code("python -m src.ingestion.build_kb --reset", language="bash")
        if st.session_state.get("_kb_error"):
            st.caption(f"detail: {st.session_state['_kb_error']}")
    st.caption(f"Embedding model: `{settings.embedding_model}`")
    st.divider()
    top_k = st.slider("Results (top-k)", 1, 15, settings.top_k)
    dup_threshold = st.slider("Duplicate threshold", 0.3, 0.95, 0.60, 0.05)


st.title("Agentic Defect Analysis System")
st.caption("Milestone 1 prototype — Bug Submission + RAG over a Historical Defect Knowledge Base")

tab_submit, tab_kb = st.tabs(["Submit & Analyze", "Knowledge Base"])

# ==========================================================================
# TAB 1 — Submit & Analyze
# ==========================================================================
with tab_submit:
    mode = st.radio("Input", ["Paste text", "Upload file"], horizontal=True, label_visibility="collapsed")
    raw_text, filename = "", None

    if mode == "Paste text":
        raw_text = st.text_area(
            "Paste a bug report, stack trace, or error log",
            height=240,
            placeholder="java.lang.NullPointerException\n\tat org.eclipse.ui...\n\nor  Traceback (most recent call last): ...",
        )
    else:
        up = st.file_uploader(
            "Upload a report / trace / log",
            type=["txt", "log", "out", "json", "xml", "csv", "py", "java", "js", "trace", "md"],
        )
        if up is not None:
            raw_text = up.read().decode("utf-8", errors="replace")
            filename = up.name
            st.caption(f"Loaded `{filename}` ({len(raw_text):,} chars)")

    go = st.button("Analyze", type="primary", disabled=not raw_text.strip())

    if go and raw_text.strip():
        sub = parse_submission(raw_text, source_filename=filename)
        art = sub.artifact

        # ---- parsed overview ----
        st.subheader("1 · Submission parsed")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Type", ARTIFACT_BADGE.get(art.artifact_type.value, art.artifact_type.value))
        c2.metric("Language", art.language or "—")
        c3.metric("Exceptions", len(art.exceptions))
        c4.metric("Log lines", sum(art.log_level_counts.values()))
        st.markdown(f"**Title:** {sub.title or '—'}")

        # ---- exception chain ----
        if art.exceptions:
            st.markdown("**Exception chain** (deepest = most likely root cause):")
            for i, exc in enumerate(art.exceptions):
                root = " ·root cause" if exc is art.root_cause_exception and len(art.exceptions) > 1 else ""
                with st.expander(f"{'↳ ' * i}{exc.exception_type}{root}", expanded=(i == 0)):
                    if exc.message:
                        st.write(exc.message)
                    if exc.frames:
                        st.code(
                            "\n".join(
                                f"{f.module + '.' if f.module else ''}{f.function or '?'}"
                                f"  ({f.file}:{f.line})" for f in exc.frames[:8]
                            )
                        )

        # ---- log histogram ----
        if art.log_level_counts:
            st.markdown("**Log levels:**")
            st.bar_chart(pd.Series(art.log_level_counts, name="count"))

        # ---- bug fields ----
        if art.bug_fields:
            with st.expander("Extracted bug-report fields"):
                for k, v in art.bug_fields.items():
                    st.markdown(f"**{k.replace('_', ' ').title()}:** {v}")

        # ---- signals ----
        if art.key_signals:
            st.markdown("**Key signals (retrieval anchors):** " + " ".join(f"`{s}`" for s in art.key_signals))
        with st.expander("Normalized text used for retrieval"):
            st.text(sub.normalized_text)

        # ---- RAG retrieval ----
        st.subheader("2 · Similar historical defects (RAG)")
        ready, _ = kb_ready()
        if not ready:
            st.warning("Build the knowledge base first (see sidebar).")
        else:
            results = get_retriever().search_submission(sub, k=top_k)
            dups = [r for r in results if r.score >= dup_threshold]
            if dups:
                st.error(f"{len(dups)} likely duplicate(s) of known defect(s) above threshold {dup_threshold:.2f}.")
            render_similarity_results(results, dup_threshold)

        # ---- M2 preview ----
        st.subheader("3 · Multi-agent analysis")
        st.info("Milestone 2 — the pipeline below will run on these parsed signals + retrieved context.")
        cols = st.columns(len(AGENT_RESPONSIBILITIES))
        for col, (role, desc) in zip(cols, AGENT_RESPONSIBILITIES.items()):
            with col:
                st.markdown(f"**{role.value.replace('_', ' ').title()}**")
                st.caption(desc)

# ==========================================================================
# TAB 2 — Knowledge Base
# ==========================================================================
with tab_kb:
    ready, _ = kb_ready()
    if not ready:
        st.warning("Knowledge base is empty. Build it from the sidebar command.")
    else:
        store = get_retriever().store
        s = store.stats()
        c1, c2, c3 = st.columns(3)
        c1.metric("Unique defects", s["unique_defects"])
        c2.metric("Chunks indexed", s["chunks"])
        c3.metric("With stack trace", s["with_stack_trace"])

        cc1, cc2, cc3 = st.columns(3)
        with cc1:
            st.caption("By source")
            st.bar_chart(pd.Series(s["by_source"], name="defects"))
        with cc2:
            st.caption("By severity")
            st.bar_chart(pd.Series(s["by_severity"], name="defects"))
        with cc3:
            st.caption("By resolution")
            st.bar_chart(pd.Series(s["by_resolution"], name="defects"))

        st.divider()
        st.subheader("Semantic search")
        q = st.text_input("Query the knowledge base", placeholder="e.g. OutOfMemoryError during shuffle")
        if q.strip():
            render_similarity_results(get_retriever().search(q, k=top_k), dup_threshold)
