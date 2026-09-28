"""Answer bank: save new answers and match a question against saved ones.

Semantic matching uses cosine similarity over `question_variants.embedding` (pgvector).
Embeddings are computed by callers that have a local model available (the Applier, or
`chirp` CLI commands) — never here, and never on the dashboard process, per the "no
embeddings on Render" rule in docs/07_llm_layer.md / docs/09_answer_bank.md.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import AnswerCategory, AnswerType
from app.db.models import Answer, QuestionVariant


def save_answer(
    db: Session,
    question: str,
    answer_text: str,
    *,
    category: AnswerCategory = AnswerCategory.BEHAVIORAL,
    type_: AnswerType = AnswerType.PERSONAL,
    source_job_id=None,
) -> Answer:
    """Save a freshly-answered question as a new bank entry (or a new variant of one)."""
    row = Answer(
        canonical_question=question.strip(),
        answer=answer_text.strip(),
        type=type_,
        category=category,
    )
    db.add(row)
    db.flush()
    db.add(
        QuestionVariant(
            answer_id=row.id, question_text=question.strip(), source_job_id=source_job_id
        )
    )
    db.commit()
    return row


@dataclass(frozen=True, slots=True)
class MatchResult:
    tier: str  # "strong" | "possible" | "none"
    score: float
    answer_id: str | None = None
    answer: str | None = None
    short_answer: str | None = None


def match_question(
    db: Session,
    embedding: list[float],
    *,
    strong: float = 0.85,
    possible: float = 0.70,
) -> MatchResult:
    """Find the closest saved question by cosine similarity.

    pgvector's `<=>` operator is cosine *distance*; similarity = 1 - distance.
    """
    row = db.execute(
        select(
            QuestionVariant,
            (1 - QuestionVariant.embedding.cosine_distance(embedding)).label("similarity"),
        )
        .where(QuestionVariant.embedding.is_not(None))
        .order_by(QuestionVariant.embedding.cosine_distance(embedding))
        .limit(1)
    ).first()
    if row is None:
        return MatchResult("none", 0.0)
    variant, similarity = row
    similarity = float(similarity)
    if similarity >= strong:
        tier = "strong"
    elif similarity >= possible:
        tier = "possible"
    else:
        return MatchResult("none", similarity)
    answer = db.get(Answer, variant.answer_id)
    return MatchResult(tier, similarity, str(answer.id), answer.answer, answer.short_answer)


def backfill_embeddings(db: Session, embed) -> int:
    """Embed any `question_variants` rows saved without one (e.g. from the dashboard,
    which never runs a local model). `embed` is an `EmbeddingProvider.embed`-shaped
    callable: `list[str] -> list[list[float]]`. Meant to be called from the Applier or
    a CLI command, which do have a local model. Returns how many rows were embedded.
    """
    rows = db.scalars(select(QuestionVariant).where(QuestionVariant.embedding.is_(None))).all()
    if not rows:
        return 0
    vectors = embed([r.question_text for r in rows])
    for row, vec in zip(rows, vectors, strict=True):
        row.embedding = vec
    db.commit()
    return len(rows)
