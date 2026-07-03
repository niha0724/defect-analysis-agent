"""Text cleaning shared by ingestion and query-time normalization."""
from __future__ import annotations

import html
import re

_TAGS = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\f\v]+")
_MULTINL = re.compile(r"\n{3,}")
_URL = re.compile(r"https?://\S+")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")


def clean_text(text: str, redact: bool = False, max_chars: int = 20_000) -> str:
    """Normalize whitespace, unescape HTML entities, strip stray markup.

    Bugzilla ``long_desc`` fields and JIRA descriptions frequently contain HTML
    entities and occasional tags; we normalize them without destroying the
    stack traces or code that carry the diagnostic signal.
    """
    if not text:
        return ""
    text = html.unescape(str(text))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _TAGS.sub(" ", text)
    if redact:
        text = _URL.sub("<url>", text)
        text = _EMAIL.sub("<email>", text)
    # collapse horizontal whitespace but preserve newlines (trace structure)
    text = "\n".join(_WS.sub(" ", line).rstrip() for line in text.split("\n"))
    text = _MULTINL.sub("\n\n", text).strip()
    return text[:max_chars]
