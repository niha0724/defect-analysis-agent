"""Shared state + role registry for the multi-agent analysis pipeline.

The orchestration graph (Milestone 2) is a LangGraph ``StateGraph`` over
``AnalysisState``. Each agent is a node that reads the fields it needs and
writes its own namespaced result, so nodes stay decoupled and independently
testable. Sketch of the graph::

    submission ─▶ Triage ─▶ Log Analysis ─▶ Duplicate ─┬─(duplicate)─▶ Report
                                                        └─(new)─▶ Root Cause ─▶ Remediation ─▶ Report

Triage may short-circuit invalid/insufficient input; Duplicate may short-circuit
when it finds a confident match, skipping the expensive root-cause/remediation
hops.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, TypedDict


class AgentRole(str, Enum):
    TRIAGE = "triage"
    LOG_ANALYSIS = "log_analysis"
    ROOT_CAUSE = "root_cause"
    DUPLICATE = "duplicate"
    REMEDIATION = "remediation"


AGENT_RESPONSIBILITIES: dict[AgentRole, str] = {
    AgentRole.TRIAGE: (
        "Validate and classify the submission: category, predicted severity & "
        "priority, affected component/module, and a routing decision. Rejects "
        "empty or non-actionable input early."
    ),
    AgentRole.LOG_ANALYSIS: (
        "Read stack traces and error logs (using the parsed exception chain and "
        "log-level histogram), pick out the salient errors, timeline, and the "
        "deepest 'Caused by' exception."
    ),
    AgentRole.ROOT_CAUSE: (
        "Hypothesize the underlying cause using the parsed signals PLUS retrieved "
        "historical defects (RAG). Produces a ranked cause hypothesis with "
        "evidence and cited prior defects."
    ),
    AgentRole.DUPLICATE: (
        "Compare the submission against KB candidates from the retriever; decide "
        "whether it duplicates a known defect and cite the canonical ID with a "
        "confidence score."
    ),
    AgentRole.REMEDIATION: (
        "Propose concrete fixes/workarounds, grounded in the resolutions and fix "
        "notes of similar historical defects retrieved from the KB."
    ),
}


class AnalysisState(TypedDict, total=False):
    """State passed between LangGraph nodes. All keys optional (total=False)."""

    # ---- inputs ----
    raw_text: str
    source_filename: str
    submission: dict[str, Any]          # serialized BugSubmission

    # ---- per-agent outputs (namespaced) ----
    triage: dict[str, Any]              # {category, severity, priority, component, route}
    log_findings: dict[str, Any]        # {salient_errors, root_exception, level_counts}
    retrieved: list[dict[str, Any]]     # RetrievedDefect dicts (shared RAG context)
    duplicates: list[dict[str, Any]]    # confirmed/likely duplicate candidates
    is_duplicate: bool
    root_cause: dict[str, Any]          # {hypothesis, confidence, evidence, citations}
    remediation: dict[str, Any]         # {steps, references}

    # ---- control / bookkeeping ----
    errors: list[str]
    final_report: dict[str, Any]
