"""Local, free embeddings via sentence-transformers.

Model is loaded lazily on first use so importing this module (e.g. in the
Streamlit app or tests) is cheap. Embeddings are L2-normalized so cosine
similarity reduces to a dot product in the vector store.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Iterable, Optional

from config import settings


class Embedder:
    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or settings.embedding_model
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # heavy import, deferred
            self._model = SentenceTransformer(self.model_name)
        return self._model

    @property
    def dim(self) -> int:
        return self.model.get_sentence_embedding_dimension()

    def encode(self, texts: Iterable[str], batch_size: int = 64, show_progress: bool = False) -> list[list[float]]:
        vecs = self.model.encode(
            list(texts),
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=show_progress,
            convert_to_numpy=True,
        )
        return vecs.tolist()

    def encode_one(self, text: str) -> list[float]:
        return self.encode([text])[0]


@lru_cache(maxsize=2)
def get_embedder(model_name: Optional[str] = None) -> Embedder:
    """Process-wide cached embedder so the model is loaded at most once."""
    return Embedder(model_name)
