"""`chirp` command line."""

from __future__ import annotations

import argparse
import getpass
import secrets
import sys
from datetime import UTC


def _password(_: argparse.Namespace) -> int:
    from app.core.security import hash_password

    pw = getpass.getpass("Dashboard password: ")
    if len(pw) < 10:
        print("Use at least 10 characters.", file=sys.stderr)
        return 1
    if pw != getpass.getpass("Again: "):
        print("Passwords didn't match.", file=sys.stderr)
        return 1
    print(f"\nDASHBOARD_PASSWORD_HASH={hash_password(pw)}")
    return 0


def _secret(_: argparse.Namespace) -> int:
    print(secrets.token_urlsafe(32))
    return 0


def _try_board(args: argparse.Namespace) -> int:
    """Read one real board and show what Chirp would keep. No database needed."""
    from datetime import datetime

    from app.connectors.detect import detect
    from app.connectors.http import HttpFetcher
    from app.connectors.registry import connector_for
    from app.services.ctc import Tier
    from app.services.finder import CompanyRef, process_postings

    d = detect(args.url)
    print(f"Platform: {d.platform.value}  board: {d.board_id or '?'}  apply: {d.apply_mode.value}")
    connector = connector_for(d.platform)
    if connector is None or not d.board_id:
        print("Chirp can't read this board automatically yet; jobs here go to quick apply.")
        return 1
    fetcher = HttpFetcher()
    try:
        postings = connector.fetch(d.board_id, fetcher)
    finally:
        fetcher.close()
    out = process_postings(
        CompanyRef(0, d.board_id, Tier(args.tier)),
        postings,
        seen_urls=set(),
        seen_keys=set(),
        now=datetime.now(UTC),
    )
    print(
        f"\n{len(postings)} postings · {out.kept} kept · "
        f"{out.filtered} filtered · {out.duplicates} duplicates\n"
    )
    for j in sorted(out.jobs, key=lambda j: j.status):
        mark = "✓" if j.status == "discovered" else "·"
        why = "" if j.status == "discovered" else f"  ({j.status_reason})"
        print(f" {mark} {j.title} · {j.location} · {j.work_mode}{why}")
    return 0


def _db():
    from app.db.session import get_sessionmaker

    return get_sessionmaker()()


def _companies_seed(_: argparse.Namespace) -> int:
    from app.services.companies import seed

    with _db() as db:
        print(f"Added {seed(db)} companies.")
    return 0


def _companies_add(args: argparse.Namespace) -> int:
    from app.db.enums import Tier
    from app.services.companies import add_from_url

    with _db() as db:
        c = add_from_url(db, args.url, name=args.name, tier=Tier(args.tier))
        print(
            f"{c.name}: {c.platform.value} "
            f"({c.platform_board_id or 'no board id'}), {c.apply_mode.value}"
        )
    return 0


def _companies_list(_: argparse.Namespace) -> int:
    from sqlalchemy import select

    from app.db.models import Company

    with _db() as db:
        for c in db.scalars(select(Company).order_by(Company.state, Company.name)):
            print(f"{c.state.value:<9} {c.tier.value:<8} {c.platform.value:<14} {c.name}")
    return 0


def _find(_: argparse.Namespace) -> int:
    from app.connectors.http import HttpFetcher
    from app.core.logging import setup_logging
    from app.db.enums import RunTrigger
    from workers.finder import run_find

    setup_logging()
    fetcher = HttpFetcher()
    try:
        with _db() as db:
            run = run_find(db, fetcher, trigger=RunTrigger.MANUAL)
    finally:
        fetcher.close()
    if run is None:
        print("A find run is already going.")
        return 1
    print(f"Find {run.status.value}: {run.counts}")
    return 0


def _tailor_test(args: argparse.Namespace) -> int:
    """Score and tailor one job description with your real LLM key. No database needed."""
    from pathlib import Path

    from app.core.config import get_settings
    from app.llm.client import LLMClient
    from app.llm.factory import make_provider
    from app.llm.pii import Redactor
    from app.llm.ratelimit import DailyBudget, MemoryUsage, TokenBucket
    from app.profile.model import Profile
    from app.services.ctc import DEFAULT_BANDS, Tier
    from app.services.processor import process_job
    from app.services.scoring import JobForLLM

    s = get_settings()
    profile = Profile.load(args.profile)
    client = LLMClient(
        make_provider(s),
        Redactor(profile.identity),
        TokenBucket(s.llm_requests_per_minute),
        DailyBudget(s.llm_daily_request_budget, MemoryUsage()),
    )
    job = JobForLLM(
        args.title,
        args.company,
        args.location,
        args.mode,
        Path(args.description).read_text(encoding="utf-8"),
    )
    r = process_job(job, profile=profile, client=client, band=DEFAULT_BANDS[Tier(args.tier)])
    print(f"Status: {r.status.value}" + (f" ({r.reason})" if r.reason else ""))
    if r.score:
        print(
            f"Score: {r.final_score} · {r.score.summary}\nGaps: {', '.join(r.score.gaps) or 'none'}"
        )
    for f in r.fabrication_failures:
        print(f"  ✗ {f}")
    if r.resume:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        stem = args.company.lower().replace(" ", "_")
        (out / f"{stem}_resume.pdf").write_bytes(r.resume.pdf)
        (out / f"{stem}_cover_letter.txt").write_text(r.cover_letter, encoding="utf-8")
        print(f"Saved to {out}/ · CTC {r.ctc_range} · LLM requests used: {client.stats.requests}")
    return 0 if r.resume else 1


def _process(_: argparse.Namespace) -> int:
    from app.core.logging import setup_logging
    from app.db.enums import RunTrigger
    from workers.processor import run_process

    setup_logging()
    with _db() as db:
        counts = run_process(db, trigger=RunTrigger.MANUAL)
    print("A process run is already going." if counts is None else f"Processed: {counts}")
    return 0


def _nightly(_: argparse.Namespace) -> int:
    from app.core.logging import setup_logging
    from app.db.enums import RunTrigger
    from workers.nightly import run_nightly

    setup_logging()
    with _db() as db:
        counts = run_nightly(db, trigger=RunTrigger.MANUAL)
    print("A nightly run is already going." if counts is None else f"Nightly: {counts}")
    return 0


def _gmail_sync(_: argparse.Namespace) -> int:
    from app.connectors.gmail_alerts import GmailClient, GmailError
    from app.core.config import get_settings
    from workers.gmail_sync import run_gmail_sync

    s = get_settings()
    try:
        client = GmailClient(
            s.gmail_client_id,
            s.gmail_client_secret.get_secret_value(),
            s.gmail_refresh_token.get_secret_value(),
        )
    except GmailError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    try:
        with _db() as db:
            counts = run_gmail_sync(db, client, s.gmail_label)
    finally:
        client.close()
    print(f"Gmail sync: {counts}")
    return 0


def _profile_push(args: argparse.Namespace) -> int:
    """Upload facts.yaml as a new profile version (workers read it from the database)."""
    from pathlib import Path

    import yaml
    from sqlalchemy import func, select

    from app.db.models import ProfileVersion
    from app.profile.model import Profile

    data = yaml.safe_load(Path(args.path).read_text(encoding="utf-8"))
    Profile.from_dict(data)  # validate before saving
    with _db() as db:
        version = (db.scalar(select(func.max(ProfileVersion.version))) or 0) + 1
        db.add(ProfileVersion(version=version, facts=data, note=args.note))
        db.commit()
    print(f"Profile version {version} saved.")
    return 0


def _apply(args: argparse.Namespace) -> int:
    """Claim approved jobs and drive them through the Applier, once."""
    from app.core.config import get_settings
    from app.core.logging import setup_logging
    from applier.runner import run_apply_once

    setup_logging()
    dry_run = not args.live if args.live else get_settings().apply_dry_run
    with _db() as db:
        counts = run_apply_once(db, dry_run=dry_run, headless=not args.headed)
    print(f"Apply ({'dry run' if dry_run else 'live'}): {counts.as_dict()}")
    return 0


def _applier_watch(args: argparse.Namespace) -> int:
    """The laptop helper: checks every minute for a scheduled or manual apply run."""
    import time
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.core.config import get_settings
    from app.core.defaults import DEFAULT_SETTINGS
    from app.core.logging import setup_logging
    from app.db.enums import RequestStatus, RunKind
    from app.db.models import AppSettings, Run, RunRequest
    from app.services.schedule import StepSchedule, due_slot
    from applier.runner import run_apply_once

    setup_logging()
    print("Applier watching. Ctrl+C to stop.")
    while True:
        now = datetime.now(UTC)
        with _db() as db:
            row = db.get(AppSettings, 1)
            schedule = (row.data if row else DEFAULT_SETTINGS)["schedule"]
            waiting = db.scalar(
                select(RunRequest)
                .where(RunRequest.kind == RunKind.APPLY, RunRequest.status == RequestStatus.WAITING)
                .order_by(RunRequest.created_at)
            )
            last = db.scalar(
                select(Run.started_at)
                .where(Run.kind == RunKind.APPLY)
                .order_by(Run.started_at.desc())
            )
            slot = due_slot(
                StepSchedule.from_dict(schedule["apply"]),
                now,
                last_started=last,
                paused=schedule.get("paused", False),
            )
            if waiting is not None or slot is not None:
                if waiting is not None:
                    waiting.status, waiting.picked_up_at = RequestStatus.PICKED_UP, now
                    db.commit()
                counts = run_apply_once(db, dry_run=get_settings().apply_dry_run)
                print(f"{now:%H:%M:%S} apply: {counts.as_dict()}")
        if args.once:
            return 0
        time.sleep(60)


def _answers_seed(args: argparse.Namespace) -> int:
    """Load starter answers from a YAML file (list of question/answer/type/category)."""
    from pathlib import Path

    import yaml

    from app.db.enums import AnswerCategory, AnswerType
    from app.services.answers import save_answer

    path = Path(args.path)
    if not path.exists():
        print(
            f"{path} doesn't exist yet. Copy profile.example/answers.yaml to {path} "
            "and fill in your real answers first.",
            file=sys.stderr,
        )
        return 1
    rows = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    with _db() as db:
        for row in rows:
            save_answer(
                db,
                row["question"],
                str(row["answer"]),
                category=AnswerCategory(row.get("category", "behavioral")),
                type_=AnswerType(row.get("type", "personal")),
            )
    print(f"Saved {len(rows)} answers from {path}.")
    return 0


def _answers_backfill(_: argparse.Namespace) -> int:
    """Embed any saved questions that don't have a vector yet (local model only)."""
    from app.llm.embeddings import LocalEmbeddingProvider
    from app.services.answers import backfill_embeddings

    with _db() as db:
        n = backfill_embeddings(db, LocalEmbeddingProvider().embed)
    print(f"Embedded {n} question(s).")
    return 0


def _version(_: argparse.Namespace) -> int:
    from app.core.config import get_settings

    print(f"chirp {get_settings().version}")
    return 0


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to a codepage (e.g. cp1252) that can't encode the
    # emoji used in help text and status labels; force UTF-8 so `chirp` doesn't
    # crash on `-h` or on printing job/company state labels.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(prog="chirp", description="Chirp, the job-finding sparrow 🐦")
    sub = parser.add_subparsers(required=True)
    sub.add_parser("password", help="Hash a dashboard password for .env").set_defaults(fn=_password)
    sub.add_parser("secret", help="Generate a random secret or token").set_defaults(fn=_secret)
    sub.add_parser("version", help="Show the version").set_defaults(fn=_version)

    tb = sub.add_parser(
        "try-board", help="Read one careers board and preview matches (no database)"
    )
    tb.add_argument("url")
    tb.add_argument("--tier", default="standard", choices=["premium", "standard", "services"])
    tb.set_defaults(fn=_try_board)

    sub.add_parser("find", help="Run the Finder now").set_defaults(fn=_find)
    sub.add_parser("process", help="Score and tailor discovered jobs now").set_defaults(fn=_process)
    sub.add_parser(
        "nightly", help="Recalculate company priority and check on dormant companies"
    ).set_defaults(fn=_nightly)
    sub.add_parser(
        "gmail-sync", help="Read job-alert emails and add unseen companies as Candidates"
    ).set_defaults(fn=_gmail_sync)

    ap = sub.add_parser("apply", help="Claim approved jobs and run the Applier once")
    ap.add_argument("--live", action="store_true", help="Actually submit (default: dry run)")
    ap.add_argument("--headed", action="store_true", help="Show the browser window")
    ap.set_defaults(fn=_apply)

    applier = sub.add_parser("applier", help="Manage the laptop Applier helper").add_subparsers(
        required=True
    )
    watch = applier.add_parser("watch", help="Check every minute for a due apply run")
    watch.add_argument("--once", action="store_true", help="Check once and exit (for testing)")
    watch.set_defaults(fn=_applier_watch)

    tt = sub.add_parser("tailor-test", help="Score and tailor one job description (no database)")
    tt.add_argument("description", help="Path to a text file with the job description")
    tt.add_argument("--title", required=True)
    tt.add_argument("--company", required=True)
    tt.add_argument("--location", default="Pune")
    tt.add_argument("--mode", default="hybrid", choices=["hybrid", "remote", "onsite", "unknown"])
    tt.add_argument("--tier", default="standard", choices=["premium", "standard", "services"])
    tt.add_argument("--profile", default="profile/facts.yaml")
    tt.add_argument("--out", default=".chirp/tailored")
    tt.set_defaults(fn=_tailor_test)

    prof = sub.add_parser("profile", help="Manage your profile").add_subparsers(required=True)
    push = prof.add_parser("push", help="Upload facts.yaml as a new version")
    push.add_argument("path", nargs="?", default="profile/facts.yaml")
    push.add_argument("--note", default="")
    push.set_defaults(fn=_profile_push)

    comp = sub.add_parser("companies", help="Manage the company registry").add_subparsers(
        required=True
    )
    comp.add_parser("seed", help="Add the starting company list").set_defaults(fn=_companies_seed)
    comp.add_parser("list", help="List companies").set_defaults(fn=_companies_list)
    add = comp.add_parser("add", help="Add or update a company from its careers URL")
    add.add_argument("url")
    add.add_argument("--name")
    add.add_argument("--tier", default="standard", choices=["premium", "standard", "services"])
    add.set_defaults(fn=_companies_add)

    ans = sub.add_parser("answers", help="Manage the answer bank").add_subparsers(required=True)
    seed_ans = ans.add_parser("seed", help="Load starter answers from a YAML file")
    seed_ans.add_argument("path", nargs="?", default="profile/answers.yaml")
    seed_ans.set_defaults(fn=_answers_seed)
    ans.add_parser(
        "backfill", help="Embed saved questions that don't have a vector yet"
    ).set_defaults(fn=_answers_backfill)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
