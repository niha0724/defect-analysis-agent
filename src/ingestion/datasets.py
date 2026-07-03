"""Load public bug datasets and normalize them into ``DefectRecord``.

Supported sources
-----------------
* **Eclipse / Mozilla** — the Eclipse & Mozilla Defect Tracking Dataset
  (Lamkanfi et al., MSR 2013). Bugzilla schema: ``bug_id, product, component,
  bug_severity, priority, short_desc, bug_status, resolution, dup_id, ...``.
  The original ships as XML; the common Kaggle / GitHub mirrors export flat
  CSVs, which is what we read here.
* **Apache** — Apache issues exported from JIRA (Kaggle
  ``tedlozzo/apaches-jira-issues`` and similar). JIRA schema: ``key, project,
  issuetype, summary, description, priority, status, resolution, components``.

The loaders are alias-tolerant: real-world exports rename columns constantly,
so ``_first()`` tries a list of known aliases for every field. Unknown values
degrade gracefully to ``UNKNOWN`` rather than crashing ingestion.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator, Optional

import pandas as pd

from src.ingestion.preprocess import clean_text
from src.schema import DefectRecord, Priority, Resolution, Severity, Source, Status
from src.submission.parsers import detect_language

# --------------------------------------------------------------------------
# Vocabulary normalization
# --------------------------------------------------------------------------
_SEVERITY_MAP = [
    ("blocker", Severity.BLOCKER),
    ("critical", Severity.CRITICAL),
    ("major", Severity.MAJOR),
    ("normal", Severity.NORMAL),
    ("minor", Severity.MINOR),
    ("trivial", Severity.TRIVIAL),
    ("enhancement", Severity.ENHANCEMENT),
    ("feature", Severity.ENHANCEMENT),
]
_PRIORITY_MAP = {
    "p1": Priority.P1, "p2": Priority.P2, "p3": Priority.P3, "p4": Priority.P4, "p5": Priority.P5,
    "highest": Priority.P1, "high": Priority.P2, "medium": Priority.P3, "normal": Priority.P3,
    "low": Priority.P4, "lowest": Priority.P5,
    "blocker": Priority.P1, "critical": Priority.P2, "major": Priority.P3,
    "minor": Priority.P4, "trivial": Priority.P5,
}
_STATUS_MAP = [
    ("unconfirmed", Status.NEW), ("new", Status.NEW), ("open", Status.OPEN),
    ("in progress", Status.IN_PROGRESS), ("in_progress", Status.IN_PROGRESS),
    ("assigned", Status.ASSIGNED), ("reopened", Status.REOPENED),
    ("resolved", Status.RESOLVED), ("verified", Status.VERIFIED),
    ("closed", Status.CLOSED), ("done", Status.CLOSED),
]
_RESOLUTION_MAP = [
    ("fixed", Resolution.FIXED), ("done", Resolution.DONE),
    ("duplicate", Resolution.DUPLICATE),
    ("wontfix", Resolution.WONTFIX), ("won't fix", Resolution.WONTFIX), ("won't do", Resolution.WONTFIX),
    ("invalid", Resolution.INVALID), ("not a bug", Resolution.INVALID),
    ("worksforme", Resolution.WORKSFORME), ("works for me", Resolution.WORKSFORME),
    ("cannot reproduce", Resolution.WORKSFORME), ("incomplete", Resolution.INCOMPLETE),
]

_TRACE_HINT = re.compile(
    r"Traceback \(most recent call last\)|Exception in thread|Caused by:|"
    r"\bat (?:[\w$]+\.){2,}[\w$]+\(|^panic:",
    re.MULTILINE,
)


def _first(row: dict, keys: list[str], default: str = "") -> str:
    for k in keys:
        if k in row and pd.notna(row[k]) and str(row[k]).strip():
            return str(row[k]).strip()
    return default


def _map_severity(text: str) -> Severity:
    t = text.lower()
    for needle, sev in _SEVERITY_MAP:
        if needle in t:
            return sev
    return Severity.UNKNOWN


def _map_priority(text: str) -> Priority:
    return _PRIORITY_MAP.get(text.lower().strip(), Priority.UNKNOWN)


def _map_status(text: str) -> Status:
    t = text.lower()
    for needle, st in _STATUS_MAP:
        if needle in t:
            return st
    return Status.UNKNOWN


def _map_resolution(text: str) -> Resolution:
    t = text.lower()
    if not t:
        return Resolution.UNRESOLVED
    for needle, res in _RESOLUTION_MAP:
        if needle in t:
            return res
    return Resolution.UNRESOLVED


def _has_trace(text: str) -> bool:
    return bool(_TRACE_HINT.search(text or ""))


# --------------------------------------------------------------------------
# Per-source normalizers
# --------------------------------------------------------------------------
def _bugzilla_url(source: Source, bug_id: str) -> str:
    if source == Source.ECLIPSE:
        return f"https://bugs.eclipse.org/bugs/show_bug.cgi?id={bug_id}"
    if source == Source.MOZILLA:
        return f"https://bugzilla.mozilla.org/show_bug.cgi?id={bug_id}"
    return ""


def normalize_bugzilla(row: dict, source: Source) -> Optional[DefectRecord]:
    bug_id = _first(row, ["bug_id", "id", "bugID", "bug id", "bugid"])
    if not bug_id:
        return None
    title = _first(row, ["short_desc", "summary", "title", "shortdesc", "short description"])
    desc = _first(row, ["description", "long_desc", "comments", "comment", "detail"])
    resolution = _map_resolution(_first(row, ["resolution", "current_resolution"]))
    dup = _first(row, ["dup_id", "duplicate_of", "dupID", "duplicate"])
    text = f"{title}\n{desc}"

    return DefectRecord(
        defect_id=f"{source.value}-{bug_id}",
        source=source,
        project=_first(row, ["product", "project"]),
        component=_first(row, ["component"]),
        title=clean_text(title, max_chars=500),
        description=clean_text(desc),
        severity=_map_severity(_first(row, ["bug_severity", "severity"])),
        priority=_map_priority(_first(row, ["priority"])),
        status=_map_status(_first(row, ["bug_status", "status", "current_status"])),
        resolution=resolution,
        duplicate_of=f"{source.value}-{dup}" if dup else None,
        resolution_note=clean_text(_first(row, ["resolution_note", "fix", "resolution_desc"]), max_chars=1000),
        has_stack_trace=_has_trace(text),
        language=detect_language(text),
        reporter=_first(row, ["reporter", "reported_by"]),
        assignee=_first(row, ["assigned_to", "assignee", "owner"]),
        created_at=_first(row, ["creation_ts", "opening", "created", "creation_time", "opendate"]),
        resolved_at=_first(row, ["delta_ts", "resolved", "resolution_date", "closed"]),
        url=_bugzilla_url(source, bug_id),
    )


_JIRA_PRIORITY_TO_SEVERITY = {
    "blocker": Severity.BLOCKER, "critical": Severity.CRITICAL, "major": Severity.MAJOR,
    "minor": Severity.MINOR, "trivial": Severity.TRIVIAL,
}


def normalize_jira(row: dict, source: Source = Source.APACHE) -> Optional[DefectRecord]:
    key = _first(row, ["key", "issue_key", "issuekey", "issue key", "id"])
    if not key:
        return None
    title = _first(row, ["summary", "title", "short_desc"])
    desc = _first(row, ["description", "desc", "detail"])
    pri_text = _first(row, ["priority", "priority_name"])
    dup = _first(row, ["duplicate_of", "dup_id", "duplicate"])
    project = _first(row, ["project", "project_key", "project_name"]) or key.split("-")[0]
    text = f"{title}\n{desc}"

    # JIRA has no separate "severity"; priority names double as severity.
    severity = _JIRA_PRIORITY_TO_SEVERITY.get(pri_text.lower(), Severity.UNKNOWN)

    return DefectRecord(
        defect_id=f"{source.value}-{key}",
        source=source,
        project=project,
        component=_first(row, ["components", "component"]),
        title=clean_text(title, max_chars=500),
        description=clean_text(desc),
        severity=severity,
        priority=_map_priority(pri_text),
        status=_map_status(_first(row, ["status"])),
        resolution=_map_resolution(_first(row, ["resolution"])),
        duplicate_of=f"{source.value}-{dup}" if dup else None,
        resolution_note=clean_text(_first(row, ["resolution_note", "comments", "fix"]), max_chars=1000),
        has_stack_trace=_has_trace(text),
        language=detect_language(text),
        reporter=_first(row, ["reporter", "creator"]),
        assignee=_first(row, ["assignee"]),
        created_at=_first(row, ["created", "created_at", "creation_date"]),
        resolved_at=_first(row, ["resolutiondate", "resolved", "resolution_date", "updated"]),
        url=f"https://issues.apache.org/jira/browse/{key}",
        keywords=[t for t in _first(row, ["issuetype", "type"]).split() if t],
    )


# --------------------------------------------------------------------------
# File loading
# --------------------------------------------------------------------------
SAMPLE_FILES = {
    Source.ECLIPSE: "eclipse_bugs.csv",
    Source.MOZILLA: "mozilla_bugs.csv",
    Source.APACHE: "apache_issues.csv",
}
_NORMALIZERS = {
    Source.ECLIPSE: normalize_bugzilla,
    Source.MOZILLA: normalize_bugzilla,
    Source.APACHE: normalize_jira,
}


def load_source(
    source: Source,
    path: Optional[Path] = None,
    limit: Optional[int] = None,
    keep_only_bugs: bool = True,
) -> Iterator[DefectRecord]:
    """Yield normalized DefectRecords for one source from a CSV file."""
    if path is None:
        from config import settings
        path = settings.sample_dir / SAMPLE_FILES[source]
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Dataset for {source.value} not found at {path}")

    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    df.columns = [c.strip().lower() for c in df.columns]

    # For JIRA exports, optionally keep only defects (drop improvements/tasks).
    if source == Source.APACHE and keep_only_bugs:
        type_col = next((c for c in ("issuetype", "issue_type", "type") if c in df.columns), None)
        if type_col:
            df = df[df[type_col].str.lower().str.contains("bug|defect", na=False)]

    normalizer = _NORMALIZERS[source]
    count = 0
    for _, row in df.iterrows():
        rec = normalizer(dict(row), source) if source == Source.APACHE else normalizer(dict(row), source)
        if rec is None:
            continue
        yield rec
        count += 1
        if limit and count >= limit:
            break


def load_all(
    sources: list[Source],
    base_dir: Optional[Path] = None,
    limit_per_source: Optional[int] = None,
) -> Iterator[DefectRecord]:
    for source in sources:
        path = None
        if base_dir is not None:
            path = Path(base_dir) / SAMPLE_FILES[source]
        yield from load_source(source, path=path, limit=limit_per_source)
