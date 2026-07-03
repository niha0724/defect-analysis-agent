"""Tests for dataset normalization and chunking (no embeddings/vector store)."""
from src.ingestion.chunking import chunk_defect, split_text
from src.ingestion.datasets import load_source
from src.schema import Priority, Resolution, Severity, Source


def _ids(records):
    return {r.defect_id for r in records}


def test_load_eclipse_sample():
    records = list(load_source(Source.ECLIPSE))
    assert records, "expected eclipse sample records"
    assert all(r.defect_id.startswith("eclipse-") for r in records)
    assert all(r.source == Source.ECLIPSE for r in records)


def test_eclipse_duplicate_link():
    records = {r.defect_id: r for r in load_source(Source.ECLIPSE)}
    dup = records["eclipse-1007"]
    assert dup.resolution == Resolution.DUPLICATE
    assert dup.duplicate_of == "eclipse-1001"


def test_jira_filters_out_non_bugs():
    ids = _ids(load_source(Source.APACHE))
    assert "apache-HADOOP-101" in ids          # a Bug -> kept
    assert "apache-HADOOP-110" not in ids       # an Improvement -> filtered


def test_jira_priority_maps_to_severity_and_priority():
    records = {r.defect_id: r for r in load_source(Source.APACHE)}
    hadoop = records["apache-HADOOP-101"]       # priority "Major"
    assert hadoop.severity == Severity.MAJOR
    assert hadoop.priority == Priority.P3
    spark = records["apache-SPARK-202"]         # priority "Critical"
    assert spark.severity == Severity.CRITICAL


def test_stack_trace_and_language_inferred():
    records = {r.defect_id: r for r in load_source(Source.APACHE)}
    assert records["apache-HADOOP-101"].has_stack_trace is True
    assert records["apache-AIRFLOW-405"].language == "python"


def test_limit():
    assert len(list(load_source(Source.MOZILLA, limit=3))) == 3


def test_split_text_short_and_long():
    assert split_text("short text", size=800, overlap=120) == ["short text"]
    long = " ".join(f"word{i}" for i in range(1000))
    pieces = split_text(long, size=200, overlap=40)
    assert len(pieces) > 1
    assert all(len(p) <= 220 for p in pieces)   # ~size, allowing boundary slack


def test_chunk_defect_metadata():
    rec = next(iter(load_source(Source.ECLIPSE)))
    chunks = chunk_defect(rec, size=800, overlap=120)
    assert chunks
    assert chunks[0].metadata["defect_id"] == rec.defect_id
    assert chunks[0].metadata["chunk_index"] == 0
    assert "n_chunks" in chunks[0].metadata
