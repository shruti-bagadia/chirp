"""Local embedding model for answer-bank matching (never runs on the dashboard).

Uses sentence-transformers, an optional dependency (`pip install -e ".[applier]"`) —
only the laptop Applier and CLI commands like `chirp answers backfill` need it.
"""

from __future__ import annotations

from app.db.models import EMBEDDING_DIM


class LocalEmbeddingProvider:
    """`all-MiniLM-L6-v2`: small, fast, and its 384-dim output matches the
    `question_variants.embedding` column (see `app/db/models.py`)."""

    dim = EMBEDDING_DIM

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers isn't installed. Run: "
                'pip install -e ".[applier]" (only needed on the laptop, never the dashboard).'
            ) from exc
        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vectors]
