# Chirp — Architecture

---

## 1. Components

```
 ┌──────────────── GitHub Actions (scheduled) ────────────────┐
 │  Scheduler tick (every 15 min) → Finder → Filter → Score →  │
 │  Tailor → PDF · Nightly upkeep · Find now (dispatch)        │
 └───────────────┬───────────────────────────────┬────────────┘
                 │ SQL                           │ upload
                 ▼                               ▼
 ┌──────────── Supabase ─────────────────────────────────────┐
 │  Postgres + pgvector            Storage (private bucket)   │
 │  jobs, companies, answers...    tailored PDFs, screenshots │
 └──────▲─────────────────────────────────▲──────────────────┘
        │ SQL                             │ signed URLs
 ┌──────┴──────── Render (web) ───────────┴──────┐
 │  FastAPI: dashboard (Jinja + HTMX)             │◄──── You (phone/laptop)
 │           machine API (/api/v1, bearer token)  │
 └──────▲─────────────────────────────────────────┘
        │ HTTPS + token
 ┌──────┴──────── Your laptop ────────────────────┐
 │  Applier helper: chirp applier --watch         │
 │  (Playwright, your Chrome profile)             │
 │  Local embedding model for answer matching     │
 └────────────────────────────────────────────────┘

 External: Greenhouse / Lever / Ashby / Workday public job APIs · Gemini API · Gmail API
```

**Why this split:**
- **Heavy work runs on GitHub Actions.** LLM calls, PDF compiles, and embeddings don't depend on Render being awake, and Actions allows long runs.
- **Render only serves the dashboard and API.** A cold start costs a few seconds when you open it, and nothing breaks.
- **The Applier runs locally** because it needs your logged-in browser sessions, and so captchas can be solved by you on the spot.
- **One codebase.** Workers, web app, and Applier share the same models and services.

---

## 1b. Adapters (swappable parts)

Every outside dependency sits behind a small interface, so swapping one never touches business logic.

| Interface | Implementations | Chosen by |
|---|---|---|
| `LLMProvider` | Gemini, Azure OpenAI, Mock | `LLM_PROVIDER` |
| `Connector` (job boards) | Greenhouse, Lever, Ashby; Workday next | Company's detected platform |
| `Fetcher` (HTTP) | `HttpFetcher`, test fakes | Injected |
| `Storage` (PDFs) | Local folder, Supabase Storage | Supabase keys present or not |
| `UsageStore` (LLM budget) | In-memory, database | Injected |
| Dashboard data store | Sample data (now), database (M3) | Same methods either way |
| `EmbeddingProvider` | Local sentence-transformers (M3) | Config |
| Apply runners | Greenhouse, Lever, Ashby (M4) | Company's platform |

## 2. Tech choices

| Area | Choice | Why |
|---|---|---|
| Language | Python 3.12 | Your core stack |
| Web | FastAPI | Your core stack; async; one app for HTML and API |
| UI | Jinja2 + HTMX + hand-written CSS | No separate frontend build; instant bulk actions |
| ORM / migrations | SQLAlchemy 2.0 + Alembic | Typed models, versioned schema |
| Database | Supabase Postgres + pgvector | Free; vector search built in |
| File storage | Supabase Storage | Free; signed URLs for PDFs |
| LLM | Gemini (free tier) behind a provider interface | ₹0; swap to Azure OpenAI by config |
| Embeddings | sentence-transformers (local) | Free, private; runs in Actions and on laptop only |
| PDF | Jinja2 → LaTeX → Tectonic | Keeps your exact resume format |
| Browser automation | Playwright | Reliable, persistent Chrome profile |
| Scheduling | GitHub Actions cron | Free |
| Hosting | Render free web service | Free; deploys from GitHub |
| Config | pydantic-settings | Typed env config |
| Tests | Pytest + recorded API fixtures | Your stack; no live calls in CI |
| Lint / format | Ruff | Fast, one tool |

---

## 3. Repo structure

```
chirp/
├── app/
│   ├── main.py                  # FastAPI app factory
│   ├── core/                    # config, security, logging
│   ├── db/                      # models, session, alembic/
│   ├── services/                # business logic, no HTTP here
│   │   ├── jobs.py              # state machine, transitions, leases
│   │   ├── dedupe.py
│   │   ├── prefilter.py
│   │   ├── scoring.py
│   │   ├── tailoring.py
│   │   ├── fabrication_check.py
│   │   ├── ctc.py
│   │   ├── companies.py
│   │   └── answers.py
│   ├── llm/
│   │   ├── base.py              # LLMProvider, EmbeddingProvider protocols
│   │   ├── gemini.py
│   │   ├── azure_openai.py
│   │   ├── pii.py               # redact / restore
│   │   ├── ratelimit.py         # token bucket + daily budget
│   │   └── prompts/             # versioned prompt templates
│   ├── connectors/              # greenhouse, lever, ashby, workday, gmail_alerts, detect.py
│   ├── resume/                  # template.tex.j2, render.py, compile.py
│   ├── web/                     # routes, templates/, static/
│   └── api/                     # /api/v1 machine routes
├── workers/                     # finder.py, processor.py, nightly.py (Actions entrypoints)
├── applier/                     # cli.py, runners/ (greenhouse, lever, ashby), form_mapper.py
├── profile.example/             # sample facts.yaml, answers.yaml, settings.yaml
├── tests/
├── docs/                        # these docs
├── .github/workflows/           # ci.yml, tick.yml (every 15 min), finder.yml (dispatchable), nightly.yml
├── Dockerfile
├── pyproject.toml
├── .env.example
└── README.md
```

---

## 4. Your personal data

The repo is public for your portfolio, so **no personal data is ever committed.**

- `profile.example/` holds fake sample data so anyone can run the project.
- Your real `facts.yaml`, answers, settings, and master resume live in Supabase. Load or update them with `chirp profile push` from your laptop.
- `.gitignore` blocks `profile/`, `.env`, and `*.pdf` from day one.

---

## 5. Security

| Surface | Protection |
|---|---|
| Dashboard | Single-user password (hashed), signed session cookie, login rate limit, HTTPS |
| Machine API | Bearer token (`CHIRP_API_TOKEN`), constant-time compare |
| Database | Service key used only server-side; never sent to the browser |
| Files | Private bucket; short-lived signed URLs |
| Secrets | `.env` locally; Render env vars; GitHub Actions secrets |
| LLM | PII stripped before every call |
| Gmail | Read-only scope, only the `job-alerts` label |
| Job portal logins | Never stored by Chirp; only in your local Chrome profile |
| GitHub dispatch token | Scoped to one repo and Actions only; server-side only |

---

## 6. Configuration

```
# LLM
LLM_PROVIDER=gemini            # gemini | azure_openai
LLM_MODEL=                     # set per provider
GEMINI_API_KEY=
AZURE_OPENAI_ENDPOINT=         # optional
AZURE_OPENAI_API_KEY=          # optional
LLM_DAILY_REQUEST_BUDGET=900   # stays under the free-tier daily limit
LLM_REQUESTS_PER_MINUTE=10

# Data
DATABASE_URL=
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
STORAGE_BUCKET=chirp-files

# Auth
CHIRP_API_TOKEN=
SESSION_SECRET=
DASHBOARD_PASSWORD_HASH=

# Manual runs
GITHUB_DISPATCH_TOKEN=          # fine-grained, this repo only, Actions: read and write
GITHUB_REPO=shruti-bagadia/chirp

# Gmail (P1)
GMAIL_CLIENT_ID=
GMAIL_CLIENT_SECRET=
GMAIL_REFRESH_TOKEN=
```

Tunable behaviour (thresholds, caps, CTC tiers) lives in the `settings` table, editable from the dashboard, not in env vars.

---

## 7. Observability

- Structured JSON logs with a `run_id` per worker run
- `runs` table: start, end, jobs found, filtered, scored, tailored, errors, LLM requests used
- Dashboard footer shows the last run time and status, so you know Chirp is alive
