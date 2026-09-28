import pytest

from app.services.states import (
    FINAL_STATES,
    Actor,
    InvalidTransition,
    allowed_targets,
    check_transition,
)
from app.services.states import (
    JobStatus as S,
)


def test_happy_path_through_to_applied():
    path = [
        (S.DISCOVERED, S.PENDING_REVIEW, Actor.PROCESSOR),
        (S.PENDING_REVIEW, S.APPROVED, Actor.YOU),
        (S.APPROVED, S.APPLYING, Actor.APPLIER),
        (S.APPLYING, S.APPLIED, Actor.APPLIER),
    ]
    for frm, to, actor in path:
        event = check_transition(frm, to, actor)
        assert (event.from_status, event.to_status, event.actor) == (frm, to, actor)


def test_needs_attention_loop_back_to_approved():
    check_transition(S.APPLYING, S.NEEDS_ATTENTION, Actor.APPLIER)
    check_transition(S.NEEDS_ATTENTION, S.APPROVED, Actor.YOU)


def test_quick_apply_marked_applied_by_you():
    check_transition(S.NEEDS_ATTENTION, S.APPLIED, Actor.YOU)


def test_lease_expiry_returns_job_to_approved():
    check_transition(S.APPLYING, S.APPROVED, Actor.SYSTEM)


def test_applier_cannot_approve_jobs():
    with pytest.raises(InvalidTransition):
        check_transition(S.PENDING_REVIEW, S.APPROVED, Actor.APPLIER)


def test_you_cannot_mark_applying():
    with pytest.raises(InvalidTransition):
        check_transition(S.APPROVED, S.APPLYING, Actor.YOU)


def test_cannot_skip_review():
    with pytest.raises(InvalidTransition):
        check_transition(S.DISCOVERED, S.APPROVED, Actor.PROCESSOR)


@pytest.mark.parametrize("final", sorted(FINAL_STATES))
def test_final_states_never_change(final):
    for target in S:
        if target == final:
            continue
        for actor in Actor:
            with pytest.raises(InvalidTransition):
                check_transition(final, target, actor)


def test_same_state_is_rejected():
    with pytest.raises(InvalidTransition):
        check_transition(S.APPROVED, S.APPROVED, Actor.YOU)


def test_allowed_targets_for_you_in_review():
    assert allowed_targets(S.PENDING_REVIEW, Actor.YOU) == {S.APPROVED, S.REJECTED}


def test_accepts_plain_strings():
    event = check_transition("pending_review", "approved", "you")
    assert event.to_status is S.APPROVED
