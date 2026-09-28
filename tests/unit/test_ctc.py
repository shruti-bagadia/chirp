import pytest

from app.services.ctc import DEFAULT_BANDS, CtcAction, Tier, TierBand, decide_ctc, validate_override

P, S, V = DEFAULT_BANDS[Tier.PREMIUM], DEFAULT_BANDS[Tier.STANDARD], DEFAULT_BANDS[Tier.SERVICES]


def test_no_salary_listed_uses_tier():
    assert decide_ctc(P).single == 20 and decide_ctc(P).range_text == "18–22 LPA"
    assert decide_ctc(S).single == 16 and decide_ctc(S).range_text == "15–17 LPA"
    assert decide_ctc(V).single == 15 and decide_ctc(V).range_text == "14–16 LPA"


def test_below_floor_is_skipped():
    d = decide_ctc(S, 8, 12)
    assert d.action is CtcAction.SKIP and d.single is None


def test_services_floor_is_14():
    assert decide_ctc(V, 12, 14).action is CtcAction.USE
    assert decide_ctc(V, 10, 13).action is CtcAction.SKIP


def test_between_floor_and_tier_min_is_flagged():
    d = decide_ctc(P, 12, 16)
    assert d.action is CtcAction.FLAG and d.single == 16


def test_posting_range_caps_the_answer():
    d = decide_ctc(P, 15, 19)
    assert d.action is CtcAction.USE
    assert d.single == 19 and d.range_text == "18–19 LPA"


def test_posting_entirely_above_tier_asks_posting_minimum():
    d = decide_ctc(S, 20, 30)
    assert d.action is CtcAction.USE and d.single == 20 and d.range_text == "20 LPA"


def test_posting_overlapping_top_of_tier():
    d = decide_ctc(S, 16, 25)
    assert d.single == 16 and d.range_text == "16–17 LPA"


def test_only_max_listed():
    d = decide_ctc(S, None, 16)
    assert d.action is CtcAction.USE and d.single == 16


def test_swapped_min_max_handled():
    assert decide_ctc(S, 17, 15).action is CtcAction.USE


def test_band_validation():
    with pytest.raises(ValueError):
        TierBand(min=20, max=18, single=19, floor=15)


def test_override_bounds():
    assert validate_override(19) == 19
    for bad in [0, 4.9, 81, 200]:
        with pytest.raises(ValueError):
            validate_override(bad)
