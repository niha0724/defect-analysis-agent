"""Schemas produced by the Bug Submission Module."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ArtifactType(str, Enum):
    BUG_REPORT = "bug_report"
    STACK_TRACE = "stack_trace"
    ERROR_LOG = "error_log"
    MIXED = "mixed"          # prose bug report with an embedded trace/log
    UNKNOWN = "unknown"


class StackFrame(BaseModel):
    raw: str
    file: Optional[str] = None
    line: Optional[int] = None
    function: Optional[str] = None
    module: Optional[str] = None


class ExceptionInfo(BaseModel):
    exception_type: str
    message: str = ""
    frames: list[StackFrame] = Field(default_factory=list)
    is_cause: bool = False   # True for links in a "Caused by:" chain

    def summary(self) -> str:
        return f"{self.exception_type}: {self.message}".strip().rstrip(":")


class LogEntry(BaseModel):
    raw: str
    timestamp: Optional[str] = None
    level: str = "UNKNOWN"
    logger: Optional[str] = None
    message: str = ""


class ParsedArtifact(BaseModel):
    artifact_type: ArtifactType = ArtifactType.UNKNOWN
    language: Optional[str] = None
    exceptions: list[ExceptionInfo] = Field(default_factory=list)
    log_entries: list[LogEntry] = Field(default_factory=list)
    log_level_counts: dict[str, int] = Field(default_factory=dict)
    bug_fields: dict[str, str] = Field(default_factory=dict)
    key_signals: list[str] = Field(default_factory=list)

    @property
    def root_cause_exception(self) -> Optional[ExceptionInfo]:
        """The deepest exception in the chain — usually the true root cause."""
        return self.exceptions[-1] if self.exceptions else None


class BugSubmission(BaseModel):
    """Fully parsed submission, ready to be embedded / queried / shown."""

    source_filename: Optional[str] = None
    raw_text: str
    artifact: ParsedArtifact
    title: str = ""
    normalized_text: str = ""     # focused text used for RAG retrieval
    char_count: int = 0
    line_count: int = 0
