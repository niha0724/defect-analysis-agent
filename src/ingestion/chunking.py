"""Chunk a DefectRecord into embedding-sized passages.

Most historical bug reports are short (title + a few sentences) and fit in a
single chunk. Long descriptions or pasted comment threads are split with a
character sliding window that prefers to break on line/word boundaries, with
overlap so a match near a boundary is never lost.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.ingestion.preprocess import clean_text
from src.schema import DefectRecord


@dataclass
class Chunk:
    chunk_id: str
    text: str
    metadata: dict


def split_text(text: str, size: int, overlap: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]

    step = max(size - overlap, 1)
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + size, n)
        if end < n:  # try to end on a newline or space boundary within the window
            window_floor = start + step
            brk = max(text.rfind("\n", window_floor, end), text.rfind(" ", window_floor, end))
            if brk > start:
                end = brk
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks


def chunk_defect(record: DefectRecord, size: int, overlap: int) -> list[Chunk]:
    base_meta = record.to_metadata()
    text = clean_text(record.combined_text())
    pieces = split_text(text, size, overlap) or [record.title or record.defect_id]
    out: list[Chunk] = []
    for i, piece in enumerate(pieces):
        meta = dict(base_meta)
        meta["chunk_index"] = i
        meta["n_chunks"] = len(pieces)
        out.append(Chunk(chunk_id=f"{record.defect_id}::chunk{i}", text=piece, metadata=meta))
    return out
