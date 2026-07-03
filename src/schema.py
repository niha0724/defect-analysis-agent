"""Canonical data model for the whole system.

Every heterogeneous source — Eclipse/Mozilla Bugzilla dumps, Apache JIRA
exports, and live user submissions — is normalized into a single
``DefectRecord``. This is the contract the Knowledge Base, the retriever, and
all five agents share, so downstream code never has to care where a defect
came from.

Design notes
------------
* Enums normalize the messy vocabulary of different trackers (JIRA "Blocker"
  vs Bugzilla "blocker" vs "P1") into one controlled set.
* ``duplicate_of`` and ``resolution`` are first-class: the public datasets
  ship real duplicate links and fix resolutions, which become *ground truth*
  for the Duplicate agent and knowledge for the Remediation agent.
* ``to_metadata()`` emits only Chroma-legal scalar types (str/int/float/bool),
  so a record can be indexed and filtered without extra plumbing.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Source(str, Enum):
    ECLIPSE = "eclipse"
    MOZILLA = "mozilla"
    APACHE = "apache"
    USER_SUBMISSION = "user_submission"


class Severity(str, Enum):
    BLOCKER = "blocker"
    CRITICAL = "critical"
    MAJOR = "major"
    NORMAL = "normal"
    MINOR = "minor"
    TRIVIAL = "trivial"
    ENHANCEMENT = "enhancement"
    UNKNOWN = "unknown"


class Priority(str, Enum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"
    P5 = "P5"
    UNKNOWN = "unknown"


class Status(str, Enum):
    NEW = "new"
    ASSIGNED = "assigned"
    REOPENED = "reopened"
    RESOLVED = "resolved"
    VERIFIED = "verified"
    CLOSED = "closed"
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    UNKNOWN = "unknown"


class Resolution(str, Enum):
    FIXED = "fixed"
    DUPLICATE = "duplicate"
    WONTFIX = "wontfix"
    INVALID = "invalid"
    WORKSFORME = "worksforme"
    INCOMPLETE = "incomplete"
    UNRESOLVED = "unresolved"
    DONE = "done"
    UNKNOWN = "unknown"


class DefectRecord(BaseModel):
    """One normalized historical (or freshly submitted) defect."""

    defect_id: str = Field(..., description="Globally unique, source-prefixed, e.g. 'apache-HADOOP-1234'")
    source: Source

    project: str = ""                 # product / JIRA project, e.g. "Platform", "HADOOP"
    component: str = ""               # sub-component, e.g. "UI", "namenode"

    title: str = ""
    description: str = ""

    severity: Severity = Severity.UNKNOWN
    priority: Priority = Priority.UNKNOWN
    status: Status = Status.UNKNOWN
    resolution: Resolution = Resolution.UNKNOWN

    duplicate_of: Optional[str] = None      # canonical defect_id this duplicates
    resolution_note: str = ""               # fix summary / closing comment (remediation knowledge)

    has_stack_trace: bool = False
    language: Optional[str] = None          # inferred programming language, if any
    keywords: list[str] = Field(default_factory=list)

    reporter: str = ""
    assignee: str = ""
    created_at: str = ""
    resolved_at: str = ""
    url: str = ""

    # ---------- Derived text ----------
    def combined_text(self) -> str:
        """The text that gets embedded / retrieved against.

        Title is repeated intentionally: it is the highest-signal field for
        semantic matching, so weighting it slightly improves retrieval.
        """
        parts = [
            f"[{self.source.value}] {self.title}",
            self.title,
            self.description,
        ]
        if self.resolution_note:
            parts.append(f"Resolution: {self.resolution_note}")
        if self.component:
            parts.append(f"Component: {self.component}")
        return "\n".join(p for p in parts if p and p.strip())

    def to_metadata(self) -> dict:
        """Chroma-legal metadata: scalars only, with empty strings dropped.

        Storing ``""`` for absent fields can trip a metadata-segment compaction
        bug in the Chroma 1.x core when a whole batch shares empty fields, so we
        omit empties entirely. Readers use ``dict.get(key, "")``.
        """
        meta = {
            "defect_id": self.defect_id,
            "source": self.source.value,
            "project": self.project,
            "component": self.component,
            "title": self.title,
            "severity": self.severity.value,
            "priority": self.priority.value,
            "status": self.status.value,
            "resolution": self.resolution.value,
            "duplicate_of": self.duplicate_of or "",
            "has_stack_trace": self.has_stack_trace,
            "language": self.language or "",
            "keywords": ", ".join(self.keywords),
            "url": self.url,
        }
        return {k: v for k, v in meta.items() if isinstance(v, bool) or v}
