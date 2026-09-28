"""Score and tailor one job.

Pure orchestration: the LLM client, compiler, and clock are injected.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from app.llm.base import BudgetExhausted, LLMError, SchemaError
from app.llm.client import LLMClient
from app.profile.model import Profile
from app.resume.render import CompileError, FittedResume, compile_pdf, fit_one_page
from app.services import scoring, tailoring
from app.services.ctc import CtcAction, TierBand, decide_ctc
from app.services.fabrication_check import TailorDraft, check
from app.services.states import JobStatus


@dataclass
class ProcessResult:
    status: JobStatus
    reason: str | None = None
    score: scoring.ScoreResult | None = None
    final_score: int | None = None
    resume: FittedResume | None = None
    cover_letter: str | None = None
    expected_ctc: float | None = None
    ctc_range: str | None = None
    flags: list[str] = field(default_factory=list)
    fabrication_failures: list[str] = field(default_factory=list)


def process_job(
    job: scoring.JobForLLM,
    *,
    profile: Profile,
    client: LLMClient,
    band: TierBand,
    salary: tuple[float | None, float | None] = (None, None),
    threshold: int = 70,
    compile_fn: Callable[[str], bytes] = compile_pdf,
) -> ProcessResult:
    """discovered -> pending_review | filtered_out | error.

    BudgetExhausted propagates so the run stops.
    """
    flags: list[str] = []

    ctc = decide_ctc(band, *salary)
    if ctc.action is CtcAction.SKIP:
        return ProcessResult(JobStatus.FILTERED_OUT, ctc.reason)
    if ctc.action is CtcAction.FLAG:
        flags.append("low_pay")

    # 1. Score
    try:
        system, user = scoring.build_prompt(job, profile)
        score = client.generate(
            system=system, user=user, parse=scoring.ScoreResult.from_dict, max_output_tokens=600
        )
    except BudgetExhausted:
        raise
    except (SchemaError, LLMError) as exc:
        return ProcessResult(JobStatus.ERROR, f"Scoring failed: {exc}")
    final = scoring.adjusted_score(score, job.work_mode)
    if final < threshold:
        return ProcessResult(
            JobStatus.FILTERED_OUT, f"Fit score {final} is below {threshold}", score, final
        )

    # 2. Tailor, with one corrective retry if the fabrication check fails
    draft: TailorDraft | None = None
    failures: list[str] = []
    for attempt in range(2):
        try:
            system, user = tailoring.build_prompt(job, profile, score.role_focus, failures or None)
            draft = client.generate(
                system=system,
                user=user,
                parse=tailoring.parse_draft,
                max_output_tokens=2500,
                temperature=0.3,
            )
        except BudgetExhausted:
            raise
        except (SchemaError, LLMError) as exc:
            return ProcessResult(JobStatus.ERROR, f"Tailoring failed: {exc}", score, final)
        draft.cover_letter = tailoring.fill_company(draft.cover_letter, job.company)
        report = check(draft, profile, job.company)
        if report.passed:
            failures = []
            break
        failures = report.failures
        if attempt == 1:
            return ProcessResult(
                JobStatus.ERROR,
                "Fabrication check failed twice",
                score,
                final,
                fabrication_failures=failures,
            )

    # 3. Render and fit on one page
    try:
        fitted = fit_one_page(profile, draft, job.company, compile_fn=compile_fn)
    except CompileError as exc:
        return ProcessResult(JobStatus.ERROR, str(exc).splitlines()[0], score, final)

    if job.work_mode == "onsite":
        flags.append("onsite")
    return ProcessResult(
        JobStatus.PENDING_REVIEW,
        None,
        score,
        final,
        fitted,
        draft.cover_letter,
        ctc.single,
        ctc.range_text,
        flags,
    )
