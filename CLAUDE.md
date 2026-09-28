# Chirp: notes for coding agents

Chirp is a single-user job-application pipeline: find Pune backend/AI roles on public job
boards, score and tailor a one-page resume per job (only from verified facts), let the owner
bulk-approve in a small dashboard, then apply. Owner: Shruti. Read `docs/` for the full design.

## Commands
- `make install` · `make test` · `make lint` · `make dev` (dashboard on the real DB at :8000,
  login required — see `DASHBOARD_PASSWORD_HASH`/`make password`)
- `make db-up` (Postgres + pgvector in Docker) · `make migration m="..."` · `make migrate`
- `chirp try-board <careers URL>`: read one real board, no DB
- `chirp tailor-test job.txt --title ... --company ... --tier premium`: real LLM, no DB
- `chirp companies seed|add|list` · `chirp find` · `chirp process` · `chirp profile push`
- `chirp answers seed [path]|backfill` · `chirp apply [--live] [--headed]` ·
  `chirp applier watch [--once]`
- `LLM_PROVIDER=mock` runs `find`/`process`/`apply` with no Gemini key — deterministic scores,
  and tailoring that echoes real `facts.yaml` text back verbatim (always passes fabrication
  check), so the whole pipeline is demoable before a real key is set. See `app/llm/mock.py`.
- `make preview`: single-file offline dashboard preview in `preview/` (still uses `demo_store`)

## Layout
- `app/services/`: pure business logic (states, schedule, ctc, dedupe, prefilter, finder,
  scoring, tailoring, fabrication_check, processor, answers). No I/O here; keep it that way
  (`answers.py` and `companies.py` are the established exceptions — they take a `Session`)
- `app/connectors/`: job boards behind `Connector` (greenhouse, lever, ashby, workday);
  `detect.py` finds the platform from a URL
- `app/llm/`: `LLMProvider`/`EmbeddingProvider` adapters (gemini, azure_openai, mock,
  embeddings.py = local sentence-transformers), `LLMClient` (PII redaction, rate limit, budget,
  JSON parse + one retry), prompts in `prompts/*.md` (versioned)
- `app/resume/`: LaTeX Jinja template + one-page fitting (Tectonic, falls back to pdflatex).
  Tectonic's engine is XeTeX-based, not pdfTeX — the template guards pdfTeX-only primitives
  with `\ifPDFTeX` and escapes en/em dashes to `--`/`---` ligatures so both engines render them
- `app/web/`: FastAPI + Jinja + HTMX dashboard, backed by `db_store.py` (real DB; same method
  surface `demo_store.py` had). `auth.py` = login/session/CSRF. `demo_store.py` still powers
  `make preview` and its own tests, nothing else
- `app/api/v1.py`: machine API for the Applier (bearer token via `CHIRP_API_TOKEN`) — claim,
  heartbeat, result, profile, answers/match, applier/checkin, per docs/05_api_design.md
- `applier/`: `runner.py` (orchestrates one apply run against the DB directly — laptop and
  dashboard are the same machine for now, see docs/03_architecture.md's laptop/server split
  for what changes once this is actually deployed), `browser.py` (Playwright, `channel="msedge"`
  by default since bundled Chromium's download CDN isn't reliably reachable here),
  `form_mapper.py` (pure field-mapping logic, no Playwright import), `runners/base.py` (generic
  label-discovery fill engine shared by every `apply_mode=auto` platform), `runners/{greenhouse,lever,ashby}.py`
  (thin `PlatformConfig`s). Only Greenhouse/Lever/Ashby are `apply_mode=auto`; everything else
  (Workday, SuccessFactors, Oracle, …) is `quick_apply` on purpose — those ATSes' captchas/login
  walls are exactly why CLAUDE.md says never guess
- `workers/`: finder, processor, tick (run on GitHub Actions)
- `tests/unit` (no DB, no network) · `tests/api` (FastAPI TestClient, real Postgres — but a
  dedicated `..._test` database, never the one `DATABASE_URL` points dev tools at; see
  `tests/conftest.py`) · `tests/api/test_applier_form_fill.py` needs a real browser (msedge or
  a Playwright-installed Chromium), skips itself if neither is available

## Rules that must not break
- **Never invent resume claims.** Tailoring may only select/reorder/reword facts by ID. Every
  draft goes through `fabrication_check.check`. Don't weaken it to make a test pass.
- **Never commit personal data.** `profile/`, `.env`, and PDFs are gitignored. Use
  `profile.example/` in tests.
- **No PII to LLMs.** All calls go through `LLMClient`, which redacts and refuses on leaks.
- **All job status changes go through `states.check_transition`** and write a `JobEvent`.
- **No scraping** of sites whose terms forbid bots (LinkedIn, Naukri). Public job APIs only.
- Times shown in IST, stored in UTC. Schedules are editable data, not hardcoded crons.
- UI copy: plain, friendly, sentence case. Theme tokens live in `app/web/static/chirp.css`.

## Status (Sep 2026)
- Done: M0 skeleton, M1 Finder (+ Workday connector), M2 Brain, M3 Review (DB-backed dashboard
  store, login/session/CSRF, answer bank + pgvector matching, Answers/Companies pages under
  `/more`), M4 Applier (Greenhouse/Lever/Ashby, generic label-discovery form fill, dry-run by
  default), a nightly worker (`workers/nightly.py`: priority scoring, dormancy, dormant
  re-checks), and a P1 Gmail job-alert reader (`workers/gmail_sync.py` — code is done and
  tested against fixtures, but untestable end-to-end until Shruti sets up the Google Cloud
  OAuth app + refresh token; see `app/connectors/gmail_alerts.py`'s docstring)
- Verified live on this machine: real `alembic` migration (no shared-enum-type duplication),
  real `chirp find` against 10 real companies' live APIs (3500+ postings, 20 kept), real
  `chirp process` with `LLM_PROVIDER=mock` (20/20 one-page PDFs, 0 fabrication failures), the
  dashboard end to end over HTTP (login → CSRF → approve → PDF download) against that real data,
  the Applier's form-fill engine against a real (Edge-backed) browser, and the Workday
  `search_text` fix against Accenture live (497 candidates → 48 genuine Pune roles surfaced,
  up from near-zero) — 263 tests passing
- 59 seed companies, most with a real `careers_url` + detected platform wired in
  (`app/connectors/seed.py`) — see `scripts/seed_urls_research.md` for the research trail.
  Many were added as `state=candidate` (need Shruti's yes/no in the dashboard before Find
  scans them) rather than assumed Active
- The laptop/desktop CSS breakpoint (`@media (min-width: 860px)` in `chirp.css`) hasn't been
  visually verified in a real browser — no browser tool was available in the session that
  wrote it, only reasoned through the box model. Check it before trusting it fully
- Next: real Gemini key (mock tailoring is safe but generic), `profile/answers.yaml` (never
  fabricated — needs Shruti's real answers), deploy to Render + Supabase + GitHub Actions
  (`render.yaml` + the Actions workflows are ready, just need the accounts), then the
  live-pilot checklist in docs/10_test_plan.md before any real application goes out
