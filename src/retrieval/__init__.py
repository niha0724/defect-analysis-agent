"""Retrieval + similarity matching over the Historical Defect KB.

Shared by the RAG demo, the Duplicate Detection module (Module 4), and the
Duplicate / Root Cause / Remediation agents (Module 3).
"""
from src.retrieval.retriever import DefectRetriever, RetrievedDefect

__all__ = ["DefectRetriever", "RetrievedDefect"]
