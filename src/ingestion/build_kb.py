"""Build (or rebuild) the Historical Defect Knowledge Base.

Examples
--------
    # Build from the bundled sample data (no Kaggle needed):
    python -m src.ingestion.build_kb --reset

    # Build from real downloaded CSVs and smoke-test retrieval:
    python -m src.ingestion.build_kb --data-dir data/raw --reset \\
        --query "NullPointerException when saving editor"
"""
from __future__ import annotations

import argparse
from typing import Optional

from config import settings
from src.ingestion.chunking import chunk_defect
from src.ingestion.datasets import load_all
from src.ingestion.vectorstore import DefectVectorStore
from src.schema import Source

SOURCE_BY_NAME = {"eclipse": Source.ECLIPSE, "mozilla": Source.MOZILLA, "apache": Source.APACHE}


def build(
    sources: list[Source],
    base_dir: Optional[str] = None,
    limit: Optional[int] = None,
    reset: bool = False,
) -> tuple[DefectVectorStore, int, int]:
    store = DefectVectorStore()
    if reset:
        print("Resetting collection ...")
        store.reset()

    print(f"Loading records from {'sample' if not base_dir else base_dir} for: {[s.value for s in sources]}")
    records = list(load_all(sources, base_dir=base_dir, limit_per_source=limit))
    print(f"Loaded {len(records)} defect records.")

    chunks = []
    for rec in records:
        chunks.extend(chunk_defect(rec, settings.chunk_size, settings.chunk_overlap))
    print(f"Produced {len(chunks)} chunks. Embedding with '{settings.embedding_model}' ...")

    store.add_chunks(chunks)
    return store, len(records), len(chunks)


def _print_stats(store: DefectVectorStore) -> None:
    s = store.stats()
    print("\n=== Knowledge Base stats ===")
    print(f"  unique defects : {s['unique_defects']}")
    print(f"  chunks         : {s['chunks']}")
    print(f"  with trace     : {s['with_stack_trace']}")
    print(f"  by source      : {s['by_source']}")
    print(f"  by severity    : {s['by_severity']}")
    print(f"  by resolution  : {s['by_resolution']}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the Historical Defect Knowledge Base.")
    ap.add_argument("--sources", nargs="+", default=["eclipse", "mozilla", "apache"],
                    choices=list(SOURCE_BY_NAME))
    ap.add_argument("--data-dir", default=None,
                    help="Directory containing <source>_*.csv files. Defaults to bundled sample.")
    ap.add_argument("--limit", type=int, default=None, help="Max records per source.")
    ap.add_argument("--reset", action="store_true", help="Wipe the collection before indexing.")
    ap.add_argument("--query", default=None, help="Run a retrieval smoke test after building.")
    args = ap.parse_args()

    sources = [SOURCE_BY_NAME[s] for s in args.sources]
    store, n_records, n_chunks = build(sources, base_dir=args.data_dir, limit=args.limit, reset=args.reset)
    _print_stats(store)

    if args.query:
        print(f"\n=== Retrieval smoke test: {args.query!r} ===")
        for i, hit in enumerate(store.query(args.query), 1):
            m = hit["metadata"]
            print(f"[{i}] score={hit['score']:.3f}  {m['defect_id']}  ({m['source']}/{m['severity']}/{m['resolution']})")
            print(f"     {m['title'][:90]}")


if __name__ == "__main__":
    main()
