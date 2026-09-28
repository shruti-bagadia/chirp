# 🐦 Chirp

**A little sparrow that finds jobs and flies your applications out.**

Chirp finds backend and AI roles on company careers pages, scores each one against your
real experience, tailors a one-page resume and cover letter, and queues them in a cute
review dashboard. Approve a batch with one tap, and Chirp applies. Every claim on every
resume is checked against your facts, so nothing is ever made up.

> Status: **M1 Finder + M2 Brain built; dashboard on sample data.** See `docs/` for the full design.

## How it works

1. **Find**: pulls postings from public job APIs (Greenhouse, Lever, Ashby, Workday)
2. **Filter**: cheap rules first (title, experience, location, salary floor), then LLM scoring
3. **Tailor**: rewrites only verified facts, checked in code for invented numbers or tools
4. **Review**: bulk approve on your phone
5. **Fly**: a local Playwright helper applies; anything unexpected waits for a human

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
make install
cp .env.example .env          # fill in values
make db-up                    # local Postgres with pgvector (Docker)
make migration m="initial"    # first time only
make migrate
make dev                      # http://localhost:8000 (runs on sample data)
make test
make preview                  # single-file offline preview in preview/

# Try a real board, no database needed:
chirp try-board https://jobs.lever.co/<company>

# Score and tailor one job with your Gemini key, no database needed:
chirp tailor-test job.txt --title "Backend Engineer" --company "Acme" --tier premium
```

## Stack

FastAPI · SQLAlchemy 2 · Alembic · Postgres + pgvector (Supabase) · Jinja + HTMX ·
Gemini (swappable) · Playwright · GitHub Actions · Render

## Docs

| Doc | |
|---|---|
| [PRD](docs/01_PRD.md) | What and why |
| [Process design](docs/02_process_design.md) | States, schedules, flows |
| [Architecture](docs/03_architecture.md) | Components and hosting |
| [Data model](docs/04_data_model.md) | Tables |
| [API](docs/05_api_design.md) | Routes |
| [Dashboard](docs/06_dashboard_design.md) | Screens and theme |
| [LLM layer](docs/07_llm_layer.md) | Providers, prompts, fabrication check |
| [Company registry](docs/08_company_registry.md) | Self-growing company list |
| [Answer bank](docs/09_answer_bank.md) | Reusable form answers |
| [Test plan](docs/10_test_plan.md) | 160+ end-to-end cases |
