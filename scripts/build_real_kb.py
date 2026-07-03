"""Build the Knowledge Base from the REAL downloaded public datasets.

Prereqs (see scripts/download_datasets.py):
  * Apache  -> data/raw/issues.csv                 (Kaggle: tedlozzo/apaches-jira-issues)
  * Eclipse -> data/raw/msr2013/eclipse/<Product>/ (MSR2013, extracted from eclipse.tar.gz)
  * Mozilla -> data/raw/msr2013/mozilla/<Product>/ (MSR2013, extracted from mozilla.tar.gz)

The full datasets are huge (Apache issues.csv alone is 1.9 GB, Eclipse+Mozilla
~200k defects), so we cap per source with --limit to keep embedding tractable
on CPU. Loaders stream/chunk, so peak memory stays low.

    python scripts/build_real_kb.py --reset --limit 3000
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from src.ingestion.chunking import chunk_defect
from src.ingestion.datasets import load_source
from src.ingestion.vectorstore import DefectVectorStore
from src.schema import Source

REAL_PATHS = {
    Source.APACHE: settings.raw_dir / "issues.csv",
    Source.ECLIPSE: settings.raw_dir / "msr2013" / "eclipse",
    Source.MOZILLA: settings.raw_dir / "msr2013" / "mozilla",
}


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the KB from real downloaded datasets.")
    ap.add_argument("--limit", type=int, default=3000, help="max defects per source")
    ap.add_argument("--reset", action="store_true", help="wipe the collection first")
    args = ap.parse_args()

    store = DefectVectorStore()
    if args.reset:
        print("Resetting collection ...")
        store.reset()

    grand_records = 0
    for source, path in REAL_PATHS.items():
        if not path.exists():
            print(f"[skip] {source.value}: {path} not found — run scripts/download_datasets.py")
            continue
        print(f"Loading {source.value} from {path} (limit {args.limit}) ...")
        records = list(load_source(source, path=path, limit=args.limit))
        chunks = []
        for rec in records:
            chunks.extend(chunk_defect(rec, settings.chunk_size, settings.chunk_overlap))
        store.add_chunks(chunks, show_progress=False)
        grand_records += len(records)
        print(f"  -> indexed {len(records)} {source.value} defects ({len(chunks)} chunks)")

    s = store.stats()
    print("\n=== Real-data Knowledge Base ===")
    print(f"  loaded defects : {grand_records}")
    print(f"  unique in store: {s['unique_defects']}")
    print(f"  chunks         : {s['chunks']}")
    print(f"  by source      : {s['by_source']}")
    print(f"  by severity    : {s['by_severity']}")
    print(f"  by resolution  : {s['by_resolution']}")


if __name__ == "__main__":
    main()
