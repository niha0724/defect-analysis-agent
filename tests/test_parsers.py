"""Unit tests for the Bug Submission Module parsers (pure-Python, fast)."""
from src.submission.models import ArtifactType
from src.submission.parsers import (
    classify_artifact,
    detect_language,
    parse_submission,
    to_defect_record,
)
from src.schema import Source

PY_TRACE = '''Traceback (most recent call last):
  File "app.py", line 10, in <module>
    main()
  File "app.py", line 6, in main
    return 1 / 0
ZeroDivisionError: division by zero'''

JAVA_TRACE = '''Exception in thread "main" java.lang.NullPointerException: oops
\tat com.example.Foo.bar(Foo.java:42)
\tat com.example.Main.main(Main.java:10)
Caused by: java.lang.IllegalStateException: bad state
\tat com.example.Baz.qux(Baz.java:99)'''

LOG = '''2023-11-05 14:23:01,123 INFO  [main] com.foo.App - starting up
2023-11-05 14:23:02,456 ERROR [pool-1] com.foo.Worker - job failed
2023-11-05 14:23:03,789 WARN  [main] com.foo.App - retrying'''

BUG = '''# Save button does nothing
## Steps to reproduce
1. Open the editor
2. Click save
## Expected
The file is saved
## Actual
Nothing happens and no error is shown'''


def test_python_traceback():
    sub = parse_submission(PY_TRACE)
    assert sub.artifact.artifact_type == ArtifactType.STACK_TRACE
    assert sub.artifact.language == "python"
    root = sub.artifact.root_cause_exception
    assert root.exception_type == "ZeroDivisionError"
    assert any(f.function and "main" in f.function for f in sub.artifact.exceptions[0].frames)


def test_java_traceback_chain():
    sub = parse_submission(JAVA_TRACE)
    assert sub.artifact.language == "java"
    types = [e.exception_type for e in sub.artifact.exceptions]
    assert any(t.endswith("NullPointerException") for t in types)
    assert any(t.endswith("IllegalStateException") for t in types)
    # deepest exception (the "Caused by") is the root cause and is flagged as a cause
    root = sub.artifact.root_cause_exception
    assert root.exception_type.endswith("IllegalStateException")
    assert root.is_cause is True
    # frame parsed with file + line
    f0 = sub.artifact.exceptions[0].frames[0]
    assert f0.file == "Foo.java" and f0.line == 42


def test_error_log():
    sub = parse_submission(LOG)
    assert sub.artifact.artifact_type == ArtifactType.ERROR_LOG
    counts = sub.artifact.log_level_counts
    assert counts.get("ERROR") == 1
    assert counts.get("WARNING") == 1   # WARN normalized to WARNING
    assert counts.get("INFO") == 1


def test_bug_report_fields():
    sub = parse_submission(BUG)
    assert sub.artifact.artifact_type in (ArtifactType.BUG_REPORT, ArtifactType.MIXED)
    fields = sub.artifact.bug_fields
    assert "steps_to_reproduce" in fields
    assert "expected" in fields and "actual" in fields
    assert "save button" in sub.title.lower()


def test_mixed_report_with_trace():
    text = BUG + "\n\n" + JAVA_TRACE
    assert classify_artifact(text) == ArtifactType.MIXED


def test_key_signals_and_record():
    sub = parse_submission(PY_TRACE)
    assert "ZeroDivisionError" in sub.artifact.key_signals
    rec = to_defect_record(sub)
    assert rec.source == Source.USER_SUBMISSION
    assert rec.has_stack_trace is True


def test_detect_language():
    assert detect_language(JAVA_TRACE) == "java"
    assert detect_language(PY_TRACE) == "python"


def test_empty_input_does_not_crash():
    sub = parse_submission("")
    assert sub.artifact.artifact_type == ArtifactType.UNKNOWN
    assert sub.normalized_text is not None
