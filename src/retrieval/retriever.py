"""Semantic retrieval and duplicate matching over the defect KB.

The vector store indexes *chunks*; callers want *defects*. This layer
over-fetches chunks, collapses them back to unique defects keeping the best
score per defect, and returns clean result objects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from config import settings
from src.ingestion.vectorstore import DefectVectorStore
from src.submission.models import BugSubmission


@dataclass
class RetrievedDefect:
    defect_id: str
    source: str
    title: str
    score: float               # cosine similarity in [-1, 1]; ~1 = near identical
    severity: str = ""
    status: str = ""
    resolution: str = ""
    duplicate_of: str = ""
    component: str = ""
    url: str = ""
    text: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def is_resolved_fixed(self) -> bool:
        return self.resolution in ("fixed", "done")


class DefectRetriever:
    #: default similarity above which two defects are treated as likely duplicates
    DUPLICATE_THRESHOLD = 0.60

    def __init__(self, store: Optional[DefectVectorStore] = None):
        self.store = store or DefectVectorStore()

    def _collapse(self, hits: list[dict], k: int) -> list[RetrievedDefect]:
        best: dict[str, RetrievedDefect] = {}
        for h in hits:
            m = h["metadata"]
            did = m.get("defect_id", "")
            if did not in best or h["score"] > best[did].score:
                best[did] = RetrievedDefect(
                    defect_id=did,
                    source=m.get("source", ""),
                    title=m.get("title", ""),
                    score=h["score"],
                    severity=m.get("severity", ""),
                    status=m.get("status", ""),
                    resolution=m.get("resolution", ""),
                    duplicate_of=m.get("duplicate_of", ""),
                    component=m.get("component", ""),
                    url=m.get("url", ""),
                    text=h["text"],
                    metadata=m,
                )
        return sorted(best.values(), key=lambda r: r.score, reverse=True)[:k]

    def search(self, query: str, k: Optional[int] = None, where: Optional[dict] = None) -> list[RetrievedDefect]:
        k = k or settings.top_k
        # over-fetch chunks so collapsing to unique defects still fills k slots
        hits = self.store.query(query, k=k * 4, where=where)
        return self._collapse(hits, k)

    def search_submission(self, submission: BugSubmission, k: Optional[int] = None) -> list[RetrievedDefect]:
        """Retrieve historical defects similar to a live submission."""
        return self.search(submission.normalized_text, k=k)

    def find_duplicates(
        self,
        query: str,
        k: int = 5,
        threshold: Optional[float] = None,
    ) -> list[RetrievedDefect]:
        """Return candidate duplicates ranked by similarity.

        Downstream (the Duplicate agent) confirms these with the LLM; here we
        just surface high-similarity candidates above ``threshold``.
        """
        threshold = self.DUPLICATE_THRESHOLD if threshold is None else threshold
        return [r for r in self.search(query, k=k) if r.score >= threshold]
