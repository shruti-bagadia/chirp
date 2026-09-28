"""Dashboard routes (HTML + HTMX partials), backed by the database (M3)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.services.schedule import ScheduleError
from app.storage import LocalStorage, make_storage
from app.web.auth import is_authed, require_csrf_on_mutation, require_login
from app.web.auth import login as do_login
from app.web.auth import logout as do_logout
from app.web.db_store import DbStore, utcnow
from app.web.templating import TEMPLATE_DIR, configure, greeting

templates = Jinja2Templates(directory=TEMPLATE_DIR)
configure(templates.env)

STEPS = {"find", "apply"}


def get_store(db: Session = Depends(get_db)) -> DbStore:
    return DbStore(db)


# Public: login/logout only. Everything else in `router` requires a session.
public_router = APIRouter(include_in_schema=False)

# Protected dashboard routes. CSRF is only enforced for state-changing methods
# (see `require_csrf_on_mutation`), so this can sit in front of GET pages too.
router = APIRouter(
    include_in_schema=False,
    dependencies=[Depends(require_login), Depends(require_csrf_on_mutation)],
)


def base_ctx(
    store: DbStore, now: datetime, tab: str = "nest", request: Request | None = None
) -> dict:
    s = get_settings()
    running = next((k for k in ("find", "apply") if store.is_running(k, now)), None)
    return {
        "tab": tab,
        "greeting": greeting(now),
        "first_name": s.owner_first_name,
        "version": s.version,
        "data_mode": "live",
        "static": "/static",
        "preview": False,
        "counts": store.counts(),
        "running": running,
        "paused": store.schedule["paused"],
        "next_find": store.next_label("find", now),
        "next_fly": store.next_label("apply", now),
        "schedule": store.schedule,
        "tiers": store.settings["ctc_tiers"],
        "limits": store.settings,
        "csrf_token": request.session.get("csrf", "") if request else "",
    }


def render(
    request: Request,
    names: str | list[str],
    ctx: dict,
    triggers: dict | None = None,
    headers: dict | None = None,
    status_code: int = 200,
    extra_html: str = "",
) -> HTMLResponse:
    """Render one or more templates into one response (extra ones are usually OOB swaps)."""
    names = [names] if isinstance(names, str) else names
    ctx.setdefault(
        "csrf_token", request.session.get("csrf", "") if hasattr(request, "session") else ""
    )
    html = "".join(templates.get_template(n).render({"request": request, **ctx}) for n in names)
    html += extra_html
    resp = HTMLResponse(html, status_code=status_code)
    if triggers:
        resp.headers["HX-Trigger"] = json.dumps(triggers)
    for k, v in (headers or {}).items():
        resp.headers[k] = v
    return resp


# ---------- Login / logout ----------


@public_router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    if is_authed(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request, "login.html", {"greeting": greeting(utcnow()), "static": "/static", "error": None}
    )


@public_router.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, password: str = Form(...)):
    error = do_login(request, password)
    if error:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"greeting": greeting(utcnow()), "static": "/static", "error": error},
            status_code=401,
        )
    return RedirectResponse("/", status_code=303)


@public_router.post("/logout")
def logout_submit(request: Request):
    do_logout(request)
    return RedirectResponse("/login", status_code=303)


# ---------- Pages ----------


@router.get("/", response_class=HTMLResponse)
def nest(request: Request, store: DbStore = Depends(get_store)):
    now = utcnow()
    store.finish_runs(now)
    return render(
        request, "nest.html", {**base_ctx(store, now, "nest", request), "jobs": store.pending()}
    )


@router.get("/hands", response_class=HTMLResponse)
def hands(request: Request, store: DbStore = Depends(get_store)):
    now = utcnow()
    return render(
        request, "hands.html", {**base_ctx(store, now, "hands", request), "hands": store.hands}
    )


@router.get("/flown", response_class=HTMLResponse)
def flown(request: Request, store: DbStore = Depends(get_store)):
    now = utcnow()
    store.finish_runs(now)
    return render(
        request, "flown.html", {**base_ctx(store, now, "flown", request), "flown": store.flown}
    )


@router.get("/more", response_class=HTMLResponse)
def more(request: Request, store: DbStore = Depends(get_store)):
    ctx = {
        **base_ctx(store, utcnow(), "more", request),
        "answers": store.answers(),
        "candidates": store.candidate_companies(),
        "active": store.active_companies(),
    }
    return render(request, "more.html", ctx)


# ---------- Nest ----------


@router.get("/partials/queue", response_class=HTMLResponse)
def queue(request: Request, store: DbStore = Depends(get_store)):
    return render(
        request,
        "partials/_queue.html",
        {**base_ctx(store, utcnow(), "nest", request), "jobs": store.pending()},
    )


@router.post("/jobs/bulk", response_class=HTMLResponse)
def bulk(
    request: Request,
    action: str = Form(...),
    ids: list[str] = Form(default=[]),
    store: DbStore = Depends(get_store),
):
    try:
        n = store.decide(ids, action)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    now = utcnow()
    ctx = {**base_ctx(store, now, "nest", request), "jobs": store.pending()}
    if action == "approve":
        trig = {"chirp:approved": {"count": n, "when": f"Chirp takes off at {ctx['next_fly']}."}}
    else:
        trig = {"chirp:rejected": {"count": n}}
    return render(request, ["partials/_queue.html", "partials/_counts_oob.html"], ctx, trig)


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_detail(job_id: str, request: Request, store: DbStore = Depends(get_store)):
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return render(request, "partials/_detail.html", {"j": job})


@router.post("/jobs/{job_id}/ctc", response_class=HTMLResponse)
def job_ctc(
    job_id: str,
    request: Request,
    expected_ctc: str = Form(...),
    store: DbStore = Depends(get_store),
):
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    try:
        store.set_ctc(job_id, float(expected_ctc))
        job = store.get_job(job_id)
    except ValueError:
        return render(
            request, "partials/_ctc.html", {"j": job, "error": "Enter a number between 5 and 80."}
        )
    oob = f'<div class="ctc" id="row-ctc-{job.id}" hx-swap-oob="true">₹{job.ctc:g} LPA</div>'
    return render(
        request,
        "partials/_ctc.html",
        {"j": job},
        {"chirp:toast": f"CTC for {job.company} set to ₹{job.ctc:g} LPA"},
        extra_html=oob,
    )


# ---------- Files (tailored PDFs) ----------


@router.get("/files/{path:path}")
def file_download(path: str):
    storage = make_storage(get_settings())
    if not isinstance(storage, LocalStorage):
        raise HTTPException(404, "Not found")
    full = storage.root / path
    if not full.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(full, media_type="application/pdf", filename=Path(path).name)


# ---------- Hands ----------


def _hand_or_404(store: DbStore, hand_id: str):
    hand = store.get_hand(hand_id)
    if hand is None:
        raise HTTPException(404, "Not found")
    return hand


@router.get("/hands/{hand_id}/answer", response_class=HTMLResponse)
def answer_form(hand_id: str, request: Request, store: DbStore = Depends(get_store)):
    return render(request, "partials/_answer.html", {"h": _hand_or_404(store, hand_id)})


@router.post("/hands/{hand_id}/answer", response_class=HTMLResponse)
def answer_save(
    hand_id: str,
    request: Request,
    answer: str = Form(""),
    save: bool = Form(False),
    store: DbStore = Depends(get_store),
):
    hand = _hand_or_404(store, hand_id)
    try:
        store.answer(hand_id, answer, save_to_bank=save)
    except ValueError as exc:
        return render(
            request,
            "partials/_answer.html",
            {"h": hand, "error": str(exc)},
            headers={"HX-Retarget": "#sheet-body", "HX-Reswap": "innerHTML"},
        )
    n = len(hand.companies)
    ctx = {**base_ctx(store, utcnow(), "hands", request), "hands": store.hands}
    return render(
        request,
        ["partials/_hands.html", "partials/_counts_oob.html"],
        ctx,
        {
            "chirp:close-sheet": True,
            "chirp:toast": f"Saved. {n} job{'s' if n != 1 else ''} back in line to fly.",
        },
    )


@router.get("/hands/{hand_id}/quick", response_class=HTMLResponse)
def quick_apply(hand_id: str, request: Request, store: DbStore = Depends(get_store)):
    return render(request, "partials/_quick.html", {"h": _hand_or_404(store, hand_id)})


@router.post("/hands/{hand_id}/applied", response_class=HTMLResponse)
def quick_applied(hand_id: str, request: Request, store: DbStore = Depends(get_store)):
    hand = _hand_or_404(store, hand_id)
    store.mark_applied(hand_id)
    ctx = {**base_ctx(store, utcnow(), "hands", request), "hands": store.hands}
    return render(
        request,
        ["partials/_hands.html", "partials/_counts_oob.html"],
        ctx,
        {
            "chirp:close-sheet": True,
            "chirp:celebrate": True,
            "chirp:toast": f"{hand.company} marked as flown.",
        },
    )


@router.post("/hands/{hand_id}/retry", response_class=HTMLResponse)
def retry(hand_id: str, request: Request, store: DbStore = Depends(get_store)):
    _hand_or_404(store, hand_id)
    store.retry(hand_id)
    ctx = {**base_ctx(store, utcnow(), "hands", request), "hands": store.hands}
    return render(
        request,
        ["partials/_hands.html", "partials/_counts_oob.html"],
        ctx,
        {"chirp:toast": "Back in line to fly."},
    )


# ---------- Flown ----------


@router.get("/flown/{flown_id}", response_class=HTMLResponse)
def flown_detail(flown_id: str, request: Request, store: DbStore = Depends(get_store)):
    f = store.get_flown(flown_id)
    if f is None:
        raise HTTPException(404, "Not found")
    return render(request, "partials/_flown_detail.html", {"f": f})


@router.post("/flown/{flown_id}/callback", response_class=HTMLResponse)
def callback(flown_id: str, request: Request, store: DbStore = Depends(get_store)):
    try:
        f = store.toggle_callback(flown_id)
    except KeyError as exc:
        raise HTTPException(404, "Not found") from exc
    trig = (
        {"chirp:celebrate": True, "chirp:toast": "A callback! Well flown."} if f.callback else None
    )
    return render(request, "partials/_callback.html", {"f": f}, trig)


# ---------- Answers ----------


@router.get("/answers/{answer_id}", response_class=HTMLResponse)
def answer_edit_form(answer_id: str, request: Request, store: DbStore = Depends(get_store)):
    a = store.get_answer(answer_id)
    if a is None:
        raise HTTPException(404, "Not found")
    return render(request, "partials/_answer_edit.html", {"a": a})


@router.post("/answers/{answer_id}", response_class=HTMLResponse)
def answer_edit_save(
    answer_id: str,
    request: Request,
    answer: str = Form(...),
    short_answer: str = Form(""),
    store: DbStore = Depends(get_store),
):
    a = store.get_answer(answer_id)
    if a is None:
        raise HTTPException(404, "Not found")
    try:
        store.update_answer(answer_id, answer, short_answer)
    except ValueError as exc:
        return render(request, "partials/_answer_edit.html", {"a": a, "error": str(exc)})
    ctx = {**base_ctx(store, utcnow(), "more", request), "answers": store.answers()}
    return render(
        request,
        "partials/_answers.html",
        ctx,
        {"chirp:close-sheet": True, "chirp:toast": "Answer saved."},
    )


# ---------- Companies ----------


def _companies_response(request: Request, store: DbStore, error: str | None = None) -> HTMLResponse:
    ctx = {
        **base_ctx(store, utcnow(), "more", request),
        "candidates": store.candidate_companies(),
        "active": store.active_companies(),
        "error": error,
    }
    return render(request, "partials/_companies.html", ctx)


@router.post("/companies", response_class=HTMLResponse)
def company_add(
    request: Request,
    url: str = Form(...),
    tier: str = Form("standard"),
    store: DbStore = Depends(get_store),
):
    try:
        store.add_company(url, tier)
    except Exception as exc:
        return _companies_response(request, store, f"Couldn't add that company: {exc}")
    return _companies_response(request, store)


@router.post("/companies/{company_id}/approve", response_class=HTMLResponse)
def company_approve(
    company_id: str,
    request: Request,
    tier: str = Form("standard"),
    store: DbStore = Depends(get_store),
):
    if store.get_company(company_id) is None:
        raise HTTPException(404, "Not found")
    store.approve_candidate(company_id, tier)
    return _companies_response(request, store)


@router.post("/companies/{company_id}/block", response_class=HTMLResponse)
def company_block(company_id: str, request: Request, store: DbStore = Depends(get_store)):
    if store.get_company(company_id) is None:
        raise HTTPException(404, "Not found")
    store.block_company(company_id)
    return _companies_response(request, store)


@router.post("/companies/{company_id}/pin", response_class=HTMLResponse)
def company_pin(
    company_id: str,
    request: Request,
    pinned: str = Form(...),
    store: DbStore = Depends(get_store),
):
    if store.get_company(company_id) is None:
        raise HTTPException(404, "Not found")
    store.set_company_pin(company_id, pinned)
    return _companies_response(request, store)


# ---------- Schedule, limits, runs ----------


def _schedule_response(request: Request, store: DbStore, error: str | None = None) -> HTMLResponse:
    ctx = {**base_ctx(store, utcnow(), "more", request), "error": error}
    return render(request, ["partials/_schedule.html", "partials/_strip_oob.html"], ctx)


@router.post("/settings/schedule/add", response_class=HTMLResponse)
def schedule_add(
    request: Request,
    step: str = Form(...),
    time: str = Form(""),
    store: DbStore = Depends(get_store),
):
    if step not in STEPS:
        raise HTTPException(400, "Unknown step")
    try:
        store.add_time(step, time)
    except ScheduleError as exc:
        return _schedule_response(request, store, str(exc))
    return _schedule_response(request, store)


@router.post("/settings/schedule/remove", response_class=HTMLResponse)
def schedule_remove(
    request: Request,
    step: str = Form(...),
    time: str = Form(...),
    store: DbStore = Depends(get_store),
):
    if step not in STEPS:
        raise HTTPException(400, "Unknown step")
    store.remove_time(step, time)
    return _schedule_response(request, store)


@router.post("/settings/schedule/day", response_class=HTMLResponse)
def schedule_day(request: Request, day: str = Form(...), store: DbStore = Depends(get_store)):
    try:
        store.toggle_day(day)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _schedule_response(request, store)


@router.post("/settings/pause", response_class=HTMLResponse)
def pause(request: Request, store: DbStore = Depends(get_store)):
    paused = store.toggle_pause()
    msg = "Chirp is resting. Manual runs still work." if paused else "Chirp is awake again."
    ctx = base_ctx(store, utcnow(), "more", request)
    if request.headers.get("HX-Target") == "schedule":
        return render(
            request,
            ["partials/_schedule.html", "partials/_strip_oob.html"],
            ctx,
            {"chirp:toast": msg},
        )
    return render(request, "partials/_strip.html", ctx, {"chirp:toast": msg})


@router.post("/settings/limit", response_class=HTMLResponse)
def limit(
    request: Request,
    name: str = Form(...),
    delta: int = Form(...),
    store: DbStore = Depends(get_store),
):
    try:
        store.step_limit(name, delta)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return render(request, "partials/_limits.html", {"limits": store.settings})


@router.post("/runs/{kind}", response_class=HTMLResponse)
def run_now(kind: str, request: Request, store: DbStore = Depends(get_store)):
    if kind not in STEPS:
        raise HTTPException(404, "Unknown run")
    now = utcnow()
    started = store.start_run(kind, now)
    msg = (
        ("Chirp is looking for new jobs." if kind == "find" else "Chirp is taking off.")
        if started
        else "Already running. One run at a time."
    )
    return render(
        request, "partials/_strip.html", base_ctx(store, now, "nest", request), {"chirp:toast": msg}
    )


@router.get("/runs/strip", response_class=HTMLResponse)
def run_strip(request: Request, store: DbStore = Depends(get_store)):
    now = utcnow()
    finished = store.finish_runs(now)
    trig = None
    if finished:
        trig = {
            "chirp:toast": " ".join(msg for _, msg in finished),
            "chirp:refresh-queue": True,
        }
        if any(kind == "apply" for kind, _ in finished):
            trig["chirp:celebrate"] = True
    return render(
        request,
        ["partials/_strip.html", "partials/_counts_oob.html"],
        base_ctx(store, now, "nest", request),
        trig,
    )
