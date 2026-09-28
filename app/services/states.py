"""Job state machine.

Every status change in Chirp goes through `check_transition`. Nothing updates a job's
status directly, so the rules below are the single source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class JobStatus(StrEnum):
    DISCOVERED = "discovered"
    FILTERED_OUT = "filtered_out"
    ERROR = "error"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    APPLYING = "applying"
    NEEDS_ATTENTION = "needs_attention"
    APPLIED = "applied"
    REJECTED = "rejected"
    EXPIRED = "expired"


class Actor(StrEnum):
    FINDER = "finder"
    PROCESSOR = "processor"
    YOU = "you"
    APPLIER = "applier"
    NIGHTLY = "nightly"
    SYSTEM = "system"  # lease expiry and other automatic housekeeping


S = JobStatus

FINAL_STATES: frozenset[JobStatus] = frozenset({S.FILTERED_OUT, S.APPLIED, S.REJECTED, S.EXPIRED})

# (from, to) -> actors allowed to make that move
_ALLOWED: dict[tuple[JobStatus, JobStatus], frozenset[Actor]] = {
    (S.DISCOVERED, S.FILTERED_OUT): frozenset({Actor.PROCESSOR}),
    (S.DISCOVERED, S.ERROR): frozenset({Actor.PROCESSOR}),
    (S.DISCOVERED, S.PENDING_REVIEW): frozenset({Actor.PROCESSOR}),
    (S.ERROR, S.DISCOVERED): frozenset({Actor.YOU}),
    (S.PENDING_REVIEW, S.APPROVED): frozenset({Actor.YOU}),
    (S.PENDING_REVIEW, S.REJECTED): frozenset({Actor.YOU}),
    (S.PENDING_REVIEW, S.EXPIRED): frozenset({Actor.NIGHTLY, Actor.APPLIER}),
    (S.APPROVED, S.APPLYING): frozenset({Actor.APPLIER}),
    (S.APPROVED, S.REJECTED): frozenset({Actor.YOU}),
    (S.APPROVED, S.EXPIRED): frozenset({Actor.NIGHTLY, Actor.APPLIER}),
    (S.APPLYING, S.APPLIED): frozenset({Actor.APPLIER}),
    (S.APPLYING, S.NEEDS_ATTENTION): frozenset({Actor.APPLIER}),
    (S.APPLYING, S.EXPIRED): frozenset({Actor.APPLIER}),
    # lease expired (Actor.SYSTEM) or the Applier deliberately releasing a dry-run
    # claim after peeking at the form without submitting (test plan G11)
    (S.APPLYING, S.APPROVED): frozenset({Actor.SYSTEM, Actor.APPLIER}),
    (S.NEEDS_ATTENTION, S.APPROVED): frozenset({Actor.YOU}),
    (S.NEEDS_ATTENTION, S.APPLIED): frozenset({Actor.YOU}),  # quick apply done by hand
    (S.NEEDS_ATTENTION, S.REJECTED): frozenset({Actor.YOU}),
    (S.NEEDS_ATTENTION, S.EXPIRED): frozenset({Actor.YOU, Actor.NIGHTLY}),
}

UI_LABELS: dict[JobStatus, str] = {
    S.DISCOVERED: "Just found",
    S.FILTERED_OUT: "Filtered out",
    S.ERROR: "Hit a snag",
    S.PENDING_REVIEW: "🪺 In the nest",
    S.APPROVED: "🪽 Ready to fly",
    S.APPLYING: "✈️ Flying",
    S.NEEDS_ATTENTION: "🤲 Needs a hand",
    S.APPLIED: "✉️ Flown",
    S.REJECTED: "🍃 Let go",
    S.EXPIRED: "🍂 Closed",
}


class InvalidTransition(ValueError):
    """Raised when a status change isn't allowed."""


@dataclass(frozen=True, slots=True)
class Transition:
    from_status: JobStatus
    to_status: JobStatus
    actor: Actor
    note: str | None = None


def allowed_targets(current: JobStatus, actor: Actor) -> set[JobStatus]:
    """Statuses this actor may move a job to from `current`."""
    return {to for (frm, to), actors in _ALLOWED.items() if frm == current and actor in actors}


def check_transition(
    current: JobStatus, target: JobStatus, actor: Actor, note: str | None = None
) -> Transition:
    """Validate a move and return the event to record. Raises InvalidTransition."""
    current, target, actor = JobStatus(current), JobStatus(target), Actor(actor)
    if current == target:
        raise InvalidTransition(f"Job is already {current.value}.")
    if current in FINAL_STATES:
        raise InvalidTransition(f"{current.value} is final; it can't change.")
    actors = _ALLOWED.get((current, target))
    if actors is None:
        raise InvalidTransition(f"Can't move from {current.value} to {target.value}.")
    if actor not in actors:
        raise InvalidTransition(
            f"{actor.value} can't move a job from {current.value} to {target.value}."
        )
    return Transition(current, target, actor, note)
