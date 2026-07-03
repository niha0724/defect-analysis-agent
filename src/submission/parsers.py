"""Detect and structure raw bug-report / stack-trace / error-log text.

Everything here is pure-Python + regex (no ML, no network), so it is fast,
deterministic, and unit-testable. The output feeds two consumers:

1. The RAG retriever — via ``BugSubmission.normalized_text`` and ``key_signals``.
2. The agents (Milestone 2) — the Log Analysis and Root Cause agents get the
   parsed exception chain and log-level histogram for free instead of
   re-deriving them from raw text.

Fully supported languages for stack frames: Python and Java (the datasets are
Java-heavy; Python covers most user pastes). JavaScript/TypeScript, C#/.NET,
Go, and Ruby are detected and their exception type + best-effort frames are
extracted by a generic scanner.
"""
from __future__ import annotations

import re
from typing import Optional

from src.schema import DefectRecord, Severity, Source
from src.submission.models import (
    ArtifactType,
    BugSubmission,
    ExceptionInfo,
    LogEntry,
    ParsedArtifact,
    StackFrame,
)

# --------------------------------------------------------------------------
# Compiled patterns
# --------------------------------------------------------------------------
_PY_HEADER = re.compile(r"Traceback \(most recent call last\):")
_PY_FRAME = re.compile(r'^\s*File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<func>.+)$')
_PY_EXC = re.compile(
    r"^(?P<type>[A-Za-z_][\w.]*"
    r"(?:Error|Exception|Warning|Exit|Interrupt|Failure|Timeout|StopIteration|"
    r"KeyboardInterrupt|GeneratorExit))"
    r"(?::\s?(?P<msg>.*))?$"
)
_PY_CHAIN = re.compile(
    r"(During handling of the above exception|"
    r"The above exception was the direct cause)"
)

_JAVA_FRAME = re.compile(r"^\s*at\s+(?P<sig>[\w$.<>]+)\((?P<loc>[^)]*)\)")
_JAVA_EXC = re.compile(
    r"^(?:Exception in thread \"[^\"]*\"\s+)?"
    r"(?P<type>(?:[\w$]+\.)+[\w$]+(?:Exception|Error|Throwable))"
    r"(?::\s?(?P<msg>.*))?$"
)
_JAVA_CAUSE = re.compile(
    r"^Caused by:\s*(?P<type>(?:[\w$]+\.)+[\w$]+(?:Exception|Error|Throwable))"
    r"(?::\s?(?P<msg>.*))?$"
)

_JS_FRAME = re.compile(r"^\s*at\s+(?:(?P<func>[^()]+?)\s+\()?(?P<loc>[^()]+?):(?P<line>\d+):\d+\)?\s*$")
_GENERIC_EXC = re.compile(r"^(?P<type>[A-Za-z_][\w.]*(?:Error|Exception))(?::\s?(?P<msg>.*))?$")

# language fingerprints (substring / regex signals)
_LANG_SIGNALS = {
    "python": [r"Traceback \(most recent call last\)", r'File "[^"]+\.py"', r"\.py\", line \d+"],
    "java": [r"Exception in thread", r"\bat (?:[\w$]+\.)+[\w$]+\(", r"Caused by:", r"\.java:\d+"],
    "javascript": [r"\bat .+\.js:\d+:\d+", r"node_modules", r"ReferenceError", r"\bTypeError: Cannot read"],
    "csharp": [r"System\.[A-Za-z.]+Exception", r"\bat .+\) in .+\.cs:line \d+"],
    "go": [r"^panic:", r"goroutine \d+ \[", r"\.go:\d+ \+0x"],
    "ruby": [r"\.rb:\d+:in ", r"\(([A-Z]\w*Error)\)"],
}

_LOG_LEVEL = re.compile(
    r"\b(?P<level>TRACE|DEBUG|INFO|NOTICE|WARN|WARNING|ERROR|ERR|FATAL|CRITICAL|SEVERE)\b"
)
_TIMESTAMP = re.compile(
    r"(?P<ts>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"
)
_LOGGER = re.compile(r"[\[(]?(?P<logger>(?:[\w$]+\.){2,}[\w$]+)[\])]?")

# high-precision retrieval anchors
_ERROR_CODE = re.compile(
    r"\b(?:ORA-\d{4,5}|SQLSTATE\[\w+\]|errno\s*[:=]?\s*\d+|E\d{3,5}|"
    r"HTTP\s*[45]\d{2}|status(?:\s*code)?\s*[:=]?\s*[45]\d{2}|0x[0-9A-Fa-f]{6,})\b"
)
_FILENAME = re.compile(r"\b[\w./-]+\.(?:java|py|js|ts|tsx|jsx|cs|go|rb|cpp|cc|c|h|kt|scala)\b")

# bug-report section labels -> canonical field name
_SECTION_LABELS = {
    "summary": "summary",
    "title": "summary",
    "description": "description",
    "steps to reproduce": "steps_to_reproduce",
    "steps": "steps_to_reproduce",
    "reproduction": "steps_to_reproduce",
    "how to reproduce": "steps_to_reproduce",
    "expected": "expected",
    "expected behavior": "expected",
    "expected result": "expected",
    "actual": "actual",
    "actual behavior": "actual",
    "actual result": "actual",
    "observed": "actual",
    "environment": "environment",
    "system": "environment",
    "platform": "environment",
    "version": "version",
    "severity": "severity",
    "priority": "priority",
}
# "Label: inline value"  (optionally prefixed by markdown #'s or **bold**)
_LABEL_COLON = re.compile(
    r"^\s*#{0,4}\s*\**\s*(?P<label>[A-Za-z][A-Za-z /]{1,30}?)\s*\**\s*[:：]\s*(?P<inline>.*)$"
)
# "## Heading"  (markdown heading with no colon and nothing after it)
_LABEL_HEADING = re.compile(
    r"^\s*#{1,4}\s*\**\s*(?P<label>[A-Za-z][A-Za-z /]{1,30}?)\s*\**\s*$"
)
_SEVERITY_KEYWORDS = {
    Severity.BLOCKER: ["blocker", "showstopper", "data loss", "corruption"],
    Severity.CRITICAL: ["critical", "crash", "hang", "deadlock", "cannot start", "unusable"],
    Severity.MAJOR: ["major", "broken", "fails", "exception", "error", "regression"],
    Severity.MINOR: ["minor", "cosmetic", "typo", "small"],
    Severity.TRIVIAL: ["trivial", "nit"],
}


# --------------------------------------------------------------------------
# Language + artifact-type detection
# --------------------------------------------------------------------------
def detect_language(text: str) -> Optional[str]:
    scores: dict[str, int] = {}
    for lang, patterns in _LANG_SIGNALS.items():
        scores[lang] = sum(len(re.findall(p, text, re.MULTILINE)) for p in patterns)
    best = max(scores, key=scores.get) if scores else None
    return best if best and scores[best] > 0 else None


def _looks_like_trace(text: str) -> bool:
    if _PY_HEADER.search(text) or "Exception in thread" in text or "Caused by:" in text:
        return True
    if text.lstrip().startswith("panic:") or "goroutine " in text:
        return True
    return len(_JAVA_FRAME.findall(text)) + len(_PY_FRAME.findall(text)) >= 2


def _count_log_lines(lines: list[str]) -> int:
    n = 0
    for ln in lines:
        if _LOG_LEVEL.search(ln) and (_TIMESTAMP.search(ln) or ln.lstrip().startswith("[")):
            n += 1
    return n


def _has_bug_prose(text: str, lines: list[str]) -> bool:
    lower = text.lower()
    if any(lbl in lower for lbl in ("steps to reproduce", "expected", "actual result", "reproduc")):
        return True
    if re.search(r"^\s*#{1,4}\s+\w", text, re.MULTILINE):     # markdown headings
        return True
    # A block of natural-language lines (spaces, few symbols) suggests prose.
    prose = [ln for ln in lines if len(ln.split()) >= 6 and ln.count("/") < 2 and "at " != ln[:3]]
    return len(prose) >= 3


def classify_artifact(text: str) -> ArtifactType:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ArtifactType.UNKNOWN

    is_trace = _looks_like_trace(text)
    log_lines = _count_log_lines(lines)
    has_prose = _has_bug_prose(text, lines)

    log_ratio = log_lines / max(len(lines), 1)

    if has_prose and is_trace:
        return ArtifactType.MIXED
    if log_lines >= 3 and log_ratio >= 0.25:
        return ArtifactType.ERROR_LOG
    if is_trace:
        return ArtifactType.STACK_TRACE
    if has_prose:
        return ArtifactType.BUG_REPORT
    return ArtifactType.UNKNOWN


# --------------------------------------------------------------------------
# Stack-trace extraction
# --------------------------------------------------------------------------
def _parse_python(text: str) -> list[ExceptionInfo]:
    exceptions: list[ExceptionInfo] = []
    lines = text.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        if _PY_HEADER.search(lines[i]):
            frames: list[StackFrame] = []
            i += 1
            while i < n:
                m = _PY_FRAME.match(lines[i])
                if m:
                    frames.append(
                        StackFrame(
                            raw=lines[i].strip(),
                            file=m.group("file"),
                            line=int(m.group("line")),
                            function=m.group("func"),
                        )
                    )
                    i += 1  # skip the source-code line that follows a frame
                    if i < n and not _PY_FRAME.match(lines[i]) and not lines[i].strip().startswith("File"):
                        i += 1
                    continue
                exc = _PY_EXC.match(lines[i].strip())
                if exc:
                    exceptions.append(
                        ExceptionInfo(
                            exception_type=exc.group("type"),
                            message=(exc.group("msg") or "").strip(),
                            frames=frames,
                            is_cause=bool(exceptions),
                        )
                    )
                    i += 1
                    break
                if lines[i].strip() == "" or _PY_CHAIN.search(lines[i]):
                    i += 1
                    continue
                break
        else:
            i += 1
    return exceptions


def _parse_java(text: str) -> list[ExceptionInfo]:
    exceptions: list[ExceptionInfo] = []
    current: Optional[ExceptionInfo] = None
    for line in text.splitlines():
        cause = _JAVA_CAUSE.match(line)
        head = cause or _JAVA_EXC.match(line.strip())
        frame = _JAVA_FRAME.match(line)
        if head and not frame:
            current = ExceptionInfo(
                exception_type=head.group("type"),
                message=(head.group("msg") or "").strip(),
                is_cause=bool(cause),
            )
            exceptions.append(current)
        elif frame and current is not None:
            sig = frame.group("sig")
            loc = frame.group("loc")
            file_, line_no = None, None
            locm = re.match(r"(?P<file>[^:]+):(?P<line>\d+)", loc)
            if locm:
                file_, line_no = locm.group("file"), int(locm.group("line"))
            func = sig.rsplit(".", 1)[-1]
            module = sig.rsplit(".", 1)[0] if "." in sig else None
            current.frames.append(
                StackFrame(raw=line.strip(), file=file_, line=line_no, function=func, module=module)
            )
    return exceptions


def _parse_generic(text: str, language: Optional[str]) -> list[ExceptionInfo]:
    """Best-effort for JS / C# / Go / Ruby: first exception line + JS-style frames."""
    exceptions: list[ExceptionInfo] = []
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        stripped = line.strip()
        m = _GENERIC_EXC.match(stripped) or re.match(r"^(?P<type>panic):\s?(?P<msg>.*)$", stripped)
        if m and "type" in m.groupdict():
            exc = ExceptionInfo(
                exception_type=m.group("type"),
                message=(m.groupdict().get("msg") or "").strip(),
            )
            for f in lines[idx + 1 :]:
                fm = _JS_FRAME.match(f)
                if fm:
                    exc.frames.append(
                        StackFrame(
                            raw=f.strip(),
                            file=fm.group("loc"),
                            line=int(fm.group("line")),
                            function=(fm.group("func") or "").strip() or None,
                        )
                    )
                elif exc.frames:
                    break
            exceptions.append(exc)
            if len(exceptions) >= 3:
                break
    return exceptions


def extract_exceptions(text: str, language: Optional[str]) -> list[ExceptionInfo]:
    if language == "python" or _PY_HEADER.search(text):
        exc = _parse_python(text)
        if exc:
            return exc
    if language == "java" or "Exception in thread" in text or "Caused by:" in text:
        exc = _parse_java(text)
        if exc:
            return exc
    return _parse_generic(text, language)


# --------------------------------------------------------------------------
# Log parsing
# --------------------------------------------------------------------------
def extract_log_entries(text: str) -> tuple[list[LogEntry], dict[str, int]]:
    entries: list[LogEntry] = []
    counts: dict[str, int] = {}
    for line in text.splitlines():
        lvl = _LOG_LEVEL.search(line)
        ts = _TIMESTAMP.search(line)
        if not lvl or not (ts or line.lstrip().startswith("[")):
            continue
        level = lvl.group("level").upper()
        level = {"WARN": "WARNING", "ERR": "ERROR"}.get(level, level)
        logger_m = _LOGGER.search(line)
        message = line[lvl.end():].lstrip(" -:\t]")
        entries.append(
            LogEntry(
                raw=line.strip(),
                timestamp=ts.group("ts") if ts else None,
                level=level,
                logger=logger_m.group("logger") if logger_m else None,
                message=message.strip(),
            )
        )
        counts[level] = counts.get(level, 0) + 1
    return entries, counts


# --------------------------------------------------------------------------
# Bug-report field extraction
# --------------------------------------------------------------------------
def extract_bug_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    lines = text.splitlines()
    current_key: Optional[str] = None
    buffer: list[str] = []

    def flush():
        if current_key and buffer:
            val = "\n".join(buffer).strip()
            if val:
                fields[current_key] = fields.get(current_key, "") + ("\n" if current_key in fields else "") + val

    for line in lines:
        m = _LABEL_COLON.match(line)
        inline = m.group("inline").strip() if m else ""
        if not m:
            m = _LABEL_HEADING.match(line)   # markdown "## Heading" form
        label = m.group("label").strip().lower() if m else None
        if label in _SECTION_LABELS:
            flush()
            current_key = _SECTION_LABELS[label]
            buffer = [inline] if inline else []
        elif current_key:
            buffer.append(line)
    flush()

    # Title: explicit summary, else first markdown heading, else first line.
    if "summary" not in fields:
        heading = re.search(r"^\s*#{1,4}\s+(?P<h>.+)$", text, re.MULTILINE)
        if heading:
            fields["summary"] = heading.group("h").strip()
        else:
            first = next((ln.strip() for ln in lines if ln.strip()), "")
            if first:
                fields["summary"] = first[:200]
    return fields


def guess_severity(text: str) -> Severity:
    lower = text.lower()
    for sev, kws in _SEVERITY_KEYWORDS.items():
        if any(kw in lower for kw in kws):
            return sev
    return Severity.UNKNOWN


# --------------------------------------------------------------------------
# Retrieval signals + normalization
# --------------------------------------------------------------------------
def extract_key_signals(text: str, exceptions: list[ExceptionInfo]) -> list[str]:
    signals: list[str] = []
    for exc in exceptions:
        signals.append(exc.exception_type)
        for fr in exc.frames[:3]:
            if fr.module:
                signals.append(f"{fr.module}.{fr.function}" if fr.function else fr.module)
            elif fr.function:
                signals.append(fr.function)
    signals += _ERROR_CODE.findall(text)
    signals += _FILENAME.findall(text)[:5]
    # dedupe, preserve order, cap
    seen, out = set(), []
    for s in signals:
        s = s.strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out[:20]


def build_normalized_text(
    title: str,
    exceptions: list[ExceptionInfo],
    log_counts: dict[str, int],
    bug_fields: dict[str, str],
    key_signals: list[str],
    raw_text: str,
) -> str:
    parts: list[str] = []
    if title:
        parts.append(title)
    for exc in exceptions:
        parts.append(exc.summary())
        top = [f.function for f in exc.frames[:3] if f.function]
        if top:
            parts.append("in " + " -> ".join(top))
    for key in ("steps_to_reproduce", "expected", "actual", "description", "environment"):
        if bug_fields.get(key):
            parts.append(f"{key.replace('_', ' ')}: {bug_fields[key]}")
    if key_signals:
        parts.append("signals: " + ", ".join(key_signals))
    if not parts:                      # fallback: nothing structured found
        parts.append(raw_text[:1500])
    text = "\n".join(parts)
    return text[:4000]


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------
def parse_submission(raw_text: str, source_filename: Optional[str] = None) -> BugSubmission:
    """Parse a pasted string or an uploaded file's contents into a BugSubmission."""
    raw_text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    language = detect_language(raw_text)
    artifact_type = classify_artifact(raw_text)

    exceptions = extract_exceptions(raw_text, language)
    log_entries, log_counts = extract_log_entries(raw_text)
    bug_fields = (
        extract_bug_fields(raw_text)
        if artifact_type in (ArtifactType.BUG_REPORT, ArtifactType.MIXED)
        else {}
    )
    key_signals = extract_key_signals(raw_text, exceptions)

    title = bug_fields.get("summary", "")
    if not title and exceptions:
        title = exceptions[0].summary()[:200]
    if not title:
        title = next((ln.strip() for ln in raw_text.splitlines() if ln.strip()), "")[:200]

    artifact = ParsedArtifact(
        artifact_type=artifact_type,
        language=language,
        exceptions=exceptions,
        log_entries=log_entries,
        log_level_counts=log_counts,
        bug_fields=bug_fields,
        key_signals=key_signals,
    )
    normalized = build_normalized_text(title, exceptions, log_counts, bug_fields, key_signals, raw_text)

    return BugSubmission(
        source_filename=source_filename,
        raw_text=raw_text,
        artifact=artifact,
        title=title,
        normalized_text=normalized,
        char_count=len(raw_text),
        line_count=raw_text.count("\n") + 1,
    )


def to_defect_record(submission: BugSubmission) -> DefectRecord:
    """Represent a live submission as a DefectRecord so it can be embedded /
    queried against the KB with the exact same code path as historical data."""
    art = submission.artifact
    return DefectRecord(
        defect_id="submission-current",
        source=Source.USER_SUBMISSION,
        title=submission.title,
        description=submission.normalized_text,
        severity=guess_severity(submission.raw_text),
        has_stack_trace=bool(art.exceptions),
        language=art.language,
        keywords=art.key_signals,
    )
