"""In-memory sample data so the dashboard runs before the database is wired up.

The routes only talk to this through its methods; the real database-backed store
will expose the same methods (M3).
"""

from __future__ import annotations

import copy
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.core.defaults import DEFAULT_SETTINGS
from app.services.ctc import validate_override
from app.services.schedule import DAYS, StepSchedule, format_ist, next_run, parse_time

DEMO_RUN_SECONDS = 3


@dataclass
class DemoJob:
    id: int
    score: int
    title: str
    company: str
    location: str
    mode: str
    ctc: float
    why: str
    matches: list[str]
    gaps: list[str]
    changes: str
    status: str = "pending_review"

    @property
    def cover_letter(self) -> str:
        return (
            f"Dear {self.company} team, over the past two years I've built backend and AI "
            "systems that turn hours of manual work into single API calls, mostly for a "
            "fintech client. I'd love to bring that to this role."
        )


@dataclass
class DemoHand:
    id: str
    kind: str  # question | quick | blocked
    question: str = ""
    companies: list[str] = field(default_factory=list)
    company: str = ""
    role: str = ""
    platform: str = ""
    reason: str = ""


@dataclass
class DemoFlown:
    id: int
    company: str
    role: str
    day: str
    callback: bool = False
    url: str = ""
    expected_ctc: str = "15–17 LPA"
    via: str = "Chirp"  # Chirp (applied automatically) or You (quick apply)

    @property
    def cover_letter(self) -> str:
        return (
            f"Dear {self.company} team, over the past two years I've built backend and AI "
            "systems that turn hours of manual work into single API calls, mostly for a "
            "fintech client. I'd love to bring that to this role."
        )

    @property
    def answers(self) -> list[tuple[str, str]]:
        return [
            ("Notice period", "15 days"),
            ("Expected CTC", self.expected_ctc),
            ("Current location", "Pune"),
            ("Willing to relocate?", "No. Based in Pune; open to Pune hybrid or remote"),
            (
                "Why this company?",
                f"{self.company}'s engineering work lines up with the "
                "backend and AI systems I build.",
            ),
        ]


def _seed_jobs() -> list[DemoJob]:
    rows = [
        (
            92,
            "Backend Engineer II",
            "Mastercard",
            "Pune",
            "Hybrid",
            20,
            "FastAPI and LLM work, fintech domain, 2–4 years asked",
            ["Python", "FastAPI", "LLM", "AWS S3"],
            ["Kafka"],
            "Led with the underwriting engine; moved Docker up in skills",
        ),
        (
            88,
            "Python Developer, AI Platform",
            "Icertis",
            "Pune",
            "Hybrid",
            20,
            "RAG and document AI match their contract intelligence work",
            ["Python", "RAG", "OCR", "Docker"],
            [],
            "Led with the RAG chatbot and document platform",
        ),
        (
            85,
            "Software Engineer, Backend",
            "Druva",
            "India",
            "Remote",
            20,
            "Backend APIs, async processing, storage integrations",
            ["Python", "REST APIs", "Async", "AWS S3"],
            ["Go"],
            "Emphasized the data-access package and Redis caching",
        ),
        (
            81,
            "Backend Engineer",
            "PubMatic",
            "Pune",
            "Hybrid",
            20,
            "High-throughput APIs, caching, background workers",
            ["Python", "Redis", "Docker"],
            ["C++"],
            "Moved Decimal Point performance work higher",
        ),
        (
            79,
            "LLM Engineer",
            "Bajaj Finserv",
            "Pune",
            "Hybrid",
            16,
            "Lending domain plus LLM extraction pipelines",
            ["LLM", "OCR", "Python", "Fintech"],
            [],
            "Led with loan document processing results",
        ),
        (
            76,
            "SDE 2, Python",
            "Persistent Systems",
            "Pune",
            "Onsite",
            16,
            "Python services and client-facing delivery",
            ["Python", "Django", "Microservices"],
            ["Kubernetes"],
            "Highlighted client communication and Agile delivery",
        ),
        (
            74,
            "Python Developer",
            "Fiserv",
            "Pune",
            "Hybrid",
            16,
            "Payments backend, REST APIs, MySQL",
            ["Python", "MySQL", "REST APIs"],
            ["Spark"],
            "Moved SQL and OracleDB up in skills",
        ),
        (
            72,
            "Python Developer, GenAI",
            "Infosys",
            "Pune",
            "Hybrid",
            15,
            "GenAI delivery for enterprise clients",
            ["LLM", "Python", "Azure"],
            [],
            "Led with Azure AI Document Intelligence",
        ),
    ]
    return [DemoJob(i + 1, *r) for i, r in enumerate(rows)]


def _seed_hands() -> list[DemoHand]:
    return [
        DemoHand(
            "q1",
            "question",
            question="What's your biggest weakness?",
            companies=["Mastercard", "Druva"],
        ),
        DemoHand(
            "q2",
            "question",
            question="Describe a time you disagreed with a teammate.",
            companies=["Icertis"],
        ),
        DemoHand(
            "k1",
            "quick",
            company="Deutsche Bank",
            role="Backend Developer",
            platform="SuccessFactors",
        ),
        DemoHand("k2", "quick", company="Barclays", role="Python Engineer", platform="Workday"),
        DemoHand("b1", "blocked", company="UBS", role="Software Engineer", reason="captcha"),
    ]


def _seed_flown() -> list[DemoFlown]:
    return [
        DemoFlown(
            1,
            "Northern Trust",
            "Backend Developer",
            "Mon",
            url="https://example.com/jobs/northern-trust-backend",
            expected_ctc="18–22 LPA",
        ),
        DemoFlown(
            2,
            "FIS",
            "Python Engineer",
            "Mon",
            callback=True,
            url="https://example.com/jobs/fis-python",
        ),
        DemoFlown(
            3,
            "Mindtickle",
            "Backend Engineer",
            "Tue",
            url="https://example.com/jobs/mindtickle-backend",
        ),
        DemoFlown(
            4,
            "Qualys",
            "Software Engineer, APIs",
            "Tue",
            url="https://example.com/jobs/qualys-apis",
            via="You",
        ),
    ]


class DemoStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.jobs = _seed_jobs()
        self.hands = _seed_hands()
        self.flown = _seed_flown()
        self.settings = copy.deepcopy(DEFAULT_SETTINGS)
        self.run_started: dict[str, datetime | None] = {"find": None, "apply": None}
        self._next_flown_id = 100

    # ----- Nest -----
    def pending(self) -> list[DemoJob]:
        return sorted(
            (j for j in self.jobs if j.status == "pending_review"), key=lambda j: -j.score
        )

    def approved(self) -> list[DemoJob]:
        return [j for j in self.jobs if j.status == "approved"]

    def get_job(self, job_id: int) -> DemoJob | None:
        return next((j for j in self.jobs if j.id == job_id), None)

    def decide(self, ids: list[int], action: str) -> int:
        if action not in {"approve", "reject"}:
            raise ValueError("Action must be approve or reject.")
        target = "approved" if action == "approve" else "rejected"
        n = 0
        with self._lock:
            for j in self.jobs:
                if j.id in ids and j.status == "pending_review":
                    j.status = target
                    n += 1
        return n

    def set_ctc(self, job_id: int, value: float) -> DemoJob:
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        job.ctc = validate_override(value)
        return job

    # ----- Hands -----
    def get_hand(self, hand_id: str) -> DemoHand | None:
        return next((h for h in self.hands if h.id == hand_id), None)

    def _drop_hand(self, hand_id: str) -> DemoHand:
        hand = self.get_hand(hand_id)
        if hand is None:
            raise KeyError(hand_id)
        self.hands = [h for h in self.hands if h.id != hand_id]
        return hand

    def answer(self, hand_id: str, text: str) -> DemoHand:
        if not text.strip():
            raise ValueError("Write an answer first.")
        return self._drop_hand(hand_id)

    def mark_applied(self, hand_id: str) -> DemoHand:
        hand = self._drop_hand(hand_id)
        self._add_flown(hand.company, hand.role, via="You")
        return hand

    def retry(self, hand_id: str) -> DemoHand:
        return self._drop_hand(hand_id)

    # ----- Flown -----
    def _add_flown(self, company: str, role: str, via: str = "Chirp") -> None:
        self._next_flown_id += 1
        self.flown.insert(
            0,
            DemoFlown(
                self._next_flown_id,
                company,
                role,
                "Today",
                url="https://example.com/jobs/new",
                via=via,
            ),
        )

    def get_flown(self, flown_id: int) -> DemoFlown | None:
        return next((x for x in self.flown if x.id == flown_id), None)

    def toggle_callback(self, flown_id: int) -> DemoFlown:
        f = next((x for x in self.flown if x.id == flown_id), None)
        if f is None:
            raise KeyError(flown_id)
        f.callback = not f.callback
        return f

    # ----- Schedule and limits -----
    @property
    def schedule(self) -> dict:
        return self.settings["schedule"]

    def add_time(self, step: str, value: str) -> None:
        t = parse_time(value).strftime("%H:%M")
        times = self.schedule[step]["times"]
        if t not in times:
            times.append(t)
            times.sort()

    def remove_time(self, step: str, value: str) -> None:
        self.schedule[step]["times"] = [t for t in self.schedule[step]["times"] if t != value]

    def toggle_day(self, day: str) -> None:
        if day not in DAYS:
            raise ValueError(f"Unknown day: {day}")
        for step in ("find", "apply"):
            days = self.schedule[step]["days"]
            if day in days:
                days.remove(day)
            else:
                days.append(day)
                days.sort(key=DAYS.index)

    def toggle_pause(self) -> bool:
        self.schedule["paused"] = not self.schedule["paused"]
        return self.schedule["paused"]

    def step_limit(self, name: str, delta: int) -> int:
        bounds = {"daily_apply_cap": (1, 20), "fit_threshold": (50, 95)}
        if name not in bounds:
            raise ValueError(f"Unknown limit: {name}")
        low, high = bounds[name]
        self.settings[name] = max(low, min(high, self.settings[name] + delta))
        return self.settings[name]

    # ----- Runs (simulated) -----
    def start_run(self, kind: str, now: datetime) -> bool:
        """Start a demo run. Returns False if one is already running (the run lock)."""
        if any(self.is_running(k, now) for k in self.run_started):
            return False
        self.run_started[kind] = now
        return True

    def is_running(self, kind: str, now: datetime) -> bool:
        started = self.run_started.get(kind)
        return started is not None and now - started < timedelta(seconds=DEMO_RUN_SECONDS)

    def finish_runs(self, now: datetime) -> list[str]:
        """Apply the effects of demo runs that just finished. Returns toast messages."""
        messages = []
        for kind, started in list(self.run_started.items()):
            if started is None or self.is_running(kind, now):
                continue
            self.run_started[kind] = None
            if kind == "find":
                if not self.pending():
                    offset = max((j.id for j in self.jobs), default=0)
                    for j in _seed_jobs():
                        j.id += offset
                        self.jobs.append(j)
                    messages.append("Found 8 new jobs. They're in the nest.")
                else:
                    messages.append("Nest is up to date.")
            else:
                cap = self.settings["daily_apply_cap"]
                ready = self.approved()[:cap]
                for j in ready:
                    j.status = "applied"
                    self._add_flown(j.company, j.title)
                messages.append(f"Flew {len(ready)} application{'s' if len(ready) != 1 else ''}.")
        return messages

    def next_label(self, step: str, now: datetime) -> str:
        s = StepSchedule.from_dict(self.schedule[step])
        nxt = next_run(s, now, paused=self.schedule["paused"])
        return format_ist(nxt, now) if nxt else "not scheduled"

    # ----- Counts -----
    def counts(self) -> dict:
        return {
            "nest": len(self.pending()),
            "hands": len(self.hands),
            "ready": len(self.approved()),
        }


_store = DemoStore()


def get_store() -> DemoStore:
    return _store


def utcnow() -> datetime:
    return datetime.now(UTC)
