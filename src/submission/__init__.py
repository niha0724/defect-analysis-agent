"""Module 1 — Bug Submission.

Accepts raw text (paste) or an uploaded file, detects whether it is a bug
report, a stack trace, or an error log, and extracts structured signals that
the RAG retriever and the agents consume.
"""
from src.submission.models import (
    ArtifactType,
    BugSubmission,
    ExceptionInfo,
    LogEntry,
    ParsedArtifact,
    StackFrame,
)
from src.submission.parsers import parse_submission, to_defect_record

__all__ = [
    "ArtifactType",
    "BugSubmission",
    "ExceptionInfo",
    "LogEntry",
    "ParsedArtifact",
    "StackFrame",
    "parse_submission",
    "to_defect_record",
]
