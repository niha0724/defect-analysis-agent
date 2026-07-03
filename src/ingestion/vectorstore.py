"""Chroma-backed vector store for historical defect chunks.

We compute embeddings ourselves (via :class:`Embedder`) and hand the vectors
to Chroma, rather than registering a Chroma embedding function. That keeps a
single embedding code path shared by ingestion and query time, and makes the
choice of model a pure config value.
"""
from __future__ import annotations

from collections import Counter
from typing import Optional

from config import settings
from src.ingestion.chunking import Chunk
from src.ingestion.embeddings import Embedder, get_embedder


class DefectVectorStore:
    def __init__(
        self,
        persist_dir: Optional[str] = None,
        collection: Optional[str] = None,
        embedder: Optional[Embedder] = None,
    ):
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        self.persist_dir = persist_dir or settings.chroma_path
        self.collection_name = collection or settings.chroma_collection
        self.embedder = embedder or get_embedder()
        self._client = chromadb.PersistentClient(
            path=self.persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
        )
        self._collection = self._get_or_create()

    def _get_or_create(self):
        return self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    # ---------- lifecycle ----------
    @property
    def collection(self):
        return self._collection

    def count(self) -> int:
        return self._collection.count()

    def reset(self) -> None:
        try:
            self._client.delete_collection(self.collection_name)
        except Exception:
            pass
        self._collection = self._get_or_create()

    # ---------- write ----------
    def add_chunks(self, chunks: list[Chunk], batch_size: int = 128, show_progress: bool = True) -> int:
        if not chunks:
            return 0
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            embeddings = self.embedder.encode([c.text for c in batch], show_progress=False)
            self._collection.add(
                ids=[c.chunk_id for c in batch],
                documents=[c.text for c in batch],
                embeddings=embeddings,
                metadatas=[c.metadata for c in batch],
            )
            if show_progress:
                print(f"  indexed {min(i + batch_size, len(chunks))}/{len(chunks)} chunks", flush=True)
        return len(chunks)

    # ---------- read ----------
    def query(self, text: str, k: Optional[int] = None, where: Optional[dict] = None) -> list[dict]:
        k = k or settings.top_k
        emb = self.embedder.encode_one(text)
        res = self._collection.query(
            query_embeddings=[emb],
            n_results=k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        out = []
        for doc, meta, dist in zip(docs, metas, dists):
            out.append({"text": doc, "metadata": meta, "distance": dist, "score": round(1.0 - dist, 4)})
        return out

    # ---------- diagnostics ----------
    def stats(self) -> dict:
        n = self.count()
        got = self._collection.get(include=["metadatas"], limit=max(n, 1))
        metas = got.get("metadatas") or []
        by_source = Counter(m.get("source", "?") for m in metas)
        by_severity = Counter(m.get("severity", "?") for m in metas)
        by_resolution = Counter(m.get("resolution", "?") for m in metas)
        with_trace = sum(1 for m in metas if m.get("has_stack_trace"))
        unique_defects = len({m.get("defect_id") for m in metas})
        return {
            "chunks": n,
            "unique_defects": unique_defects,
            "with_stack_trace": with_trace,
            "by_source": dict(by_source),
            "by_severity": dict(by_severity),
            "by_resolution": dict(by_resolution),
        }
