"""Expected CTC rules, by company tier."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Tier(StrEnum):
    PREMIUM = "premium"
    STANDARD = "standard"
    SERVICES = "services"


@dataclass(frozen=True, slots=True)
class TierBand:
    min: float
    max: float
    single: float
    floor: float

    def __post_init__(self) -> None:
        if not (0 < self.floor <= self.min <= self.single <= self.max):
            raise ValueError("Tier band must satisfy 0 < floor <= min <= single <= max.")


DEFAULT_BANDS: dict[Tier, TierBand] = {
    Tier.PREMIUM: TierBand(min=18, max=22, single=20, floor=15),
    Tier.STANDARD: TierBand(min=15, max=17, single=16, floor=15),
    Tier.SERVICES: TierBand(min=14, max=16, single=15, floor=14),
}


class CtcAction(StrEnum):
    USE = "use"  # answer normally
    FLAG = "flag"  # posting pays below the tier range; answer, but show in review
    SKIP = "skip"  # posting pays below the floor; don't apply


@dataclass(frozen=True, slots=True)
class CtcDecision:
    action: CtcAction
    single: float | None
    range_text: str | None
    reason: str | None = None


def _fmt(value: float) -> str:
    return f"{value:g}"


def range_text(low: float, high: float) -> str:
    return f"{_fmt(low)} LPA" if low == high else f"{_fmt(low)}–{_fmt(high)} LPA"


def decide_ctc(
    band: TierBand, posted_min: float | None = None, posted_max: float | None = None
) -> CtcDecision:
    """Work out what expected CTC to give for a job.

    - No salary listed: the tier's range and single number.
    - Posting tops out below the floor: skip.
    - Posting tops out below the tier's minimum: use the posting's top, and flag it.
    - Posting starts above the tier's maximum: ask the posting's minimum.
    - Otherwise: stay inside both the tier range and the posting's range.
    """
    if posted_max is None:
        return CtcDecision(CtcAction.USE, band.single, range_text(band.min, band.max))

    low_post = posted_min if posted_min is not None else posted_max
    if low_post > posted_max:
        low_post, posted_max = posted_max, low_post

    if posted_max < band.floor:
        return CtcDecision(
            CtcAction.SKIP,
            None,
            None,
            f"Posting tops out at {_fmt(posted_max)} LPA, below your {_fmt(band.floor)} LPA floor.",
        )
    if posted_max < band.min:
        return CtcDecision(
            CtcAction.FLAG,
            posted_max,
            range_text(posted_max, posted_max),
            f"Posting tops out at {_fmt(posted_max)} LPA, below the "
            f"{range_text(band.min, band.max)} tier range.",
        )

    if low_post > band.max:
        # The whole posting pays above the tier: never undersell, ask the posting's minimum.
        return CtcDecision(CtcAction.USE, low_post, range_text(low_post, low_post))

    low = max(band.min, low_post)
    high = min(band.max, posted_max)
    single = min(max(band.single, low), high)
    return CtcDecision(CtcAction.USE, single, range_text(low, high))


def validate_override(value: float) -> float:
    """Per-job CTC edits from the dashboard."""
    if not 5 <= value <= 80:
        raise ValueError("Enter a number between 5 and 80.")
    return round(value, 1)
