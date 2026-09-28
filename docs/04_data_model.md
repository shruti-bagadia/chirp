# Chirp — Data Model

Postgres (Supabase) with pgvector. All tables have `id uuid` primary keys and `created_at` / `updated_at` unless noted. Enums are Postgres enums managed by Alembic.

---

## Overview

```
companies 1───* jobs 1───* job_events
                  │
                  ├───1 tailored_documents
                  └───* application_answers *───1 answers 1───* question_variants

profile_versions   settings   runs   llm_usage   company_stats_daily
```

---

## companies
See `08_company_registry.md` for full field notes.

| Field | Type | Notes |
|---|---|---|
| name | text | unique, normalized |
| aliases | text[] | |
| careers_url | text | |
| platform | enum | greenhouse, lever, ashby, workday, successfactors, darwinbox, oracle, icims, smartrecruiters, own, unknown |
| platform_board_id | text | e.g. Greenhouse board token, Workday tenant/site |
| apply_mode | enum | auto, quick_apply |
| category | enum | banking_fintech, services_consulting, product_saas, ai_first |
| tier | enum | premium, standard, services |
| state | enum | candidate, active, dormant, blocked |
| priority_score | int | 0–100 |
| pinned | enum | none, high, low |
| source | enum | seed, email_alert, pasted_url, suggested |
| last_match_at | timestamptz | |
| consecutive_failures | int | connector failures in a row |

## jobs

| Field | Type | Notes |
|---|---|---|
| company_id | uuid → companies | |
| external_id | text | ID from the platform |
| url | text | as found |
| canonical_url | text | **unique**; tracking params stripped |
| dedupe_key | text | **unique**; hash of company + normalized title + location |
| title | text | |
| location | text | |
| work_mode | enum | hybrid, remote, onsite, unknown |
| description | text | |
| salary_min_lpa / salary_max_lpa | numeric | null if not listed |
| experience_min / experience_max | numeric | parsed; null if unknown |
| posted_at | timestamptz | |
| status | enum | discovered, filtered_out, error, pending_review, approved, applying, needs_attention, applied, rejected, expired |
| status_reason | text | why it's filtered, errored, or needs attention |
| fit_score | int | |
| fit_summary | text | one-line reason |
| fit_gaps | text[] | |
| role_focus | text | used in "why you're a fit" template |
| expected_ctc_lpa | numeric | computed from tier; you can override |
| ctc_overridden | bool | |
| batch | text | e.g. `2026-09-28 AM` |
| attempts | int | processing retries |
| lease_until | timestamptz | set while `applying` |
| applied_at | timestamptz | |
| confirmation_path | text | storage path to confirmation screenshot |

**Indexes:** `(status, fit_score desc)`, `(company_id, status)`, `lease_until`.

## job_events
Append-only audit of every state change.

| Field | Type | Notes |
|---|---|---|
| job_id | uuid → jobs | |
| from_status / to_status | enum | |
| actor | enum | finder, processor, you, applier, nightly |
| note | text | |
| created_at | timestamptz | no `updated_at`; rows never change |

## tailored_documents

| Field | Type | Notes |
|---|---|---|
| job_id | uuid → jobs | unique |
| resume_pdf_path | text | storage path |
| resume_tex | text | rendered source, for debugging |
| selection | jsonb | fact IDs chosen, order, rewrites |
| change_summary | text | shown as "Resume changes" |
| cover_letter | text | |
| fabrication_check | jsonb | pass/fail per rule |
| profile_version | int | which facts version was used |
| prompt_version | text | which prompt version was used |

## answers / question_variants / application_answers
See `09_answer_bank.md`. `question_variants.embedding` is `vector(384)` (size depends on the embedding model; set in migration) with an HNSW index.

## profile_versions
Your facts, fixed answers, and master resume, versioned. The newest row is active.

| Field | Type | Notes |
|---|---|---|
| version | int | unique, increasing |
| facts | jsonb | parsed `facts.yaml` |
| resume_template | text | LaTeX Jinja template |
| note | text | what changed |

## settings
Single row, jsonb, edited from the dashboard.

```json
{
  "fit_threshold": 70,
  "max_jobs_per_run": 30,
  "daily_apply_cap": 8,
  "ctc_tiers": {
    "premium":  {"min": 18, "max": 22, "single": 20, "floor": 15},
    "standard": {"min": 15, "max": 17, "single": 16, "floor": 15},
    "services": {"min": 14, "max": 16, "single": 15, "floor": 14}
  },
  "match_thresholds": {"strong": 0.85, "possible": 0.70},
  "dormant_after_days": 60,
  "schedule": {
    "paused": false,
    "find":  {"times": ["08:30", "13:00"], "days": ["mon","tue","wed","thu","fri"]},
    "apply": {"times": ["10:30", "15:30"], "days": ["mon","tue","wed","thu","fri"]},
    "nightly": {"times": ["02:00"], "days": ["mon","tue","wed","thu","fri","sat","sun"]}
  }
}
```

## runs

| Field | Type | Notes |
|---|---|---|
| kind | enum | finder, processor, nightly, applier |
| started_at / finished_at | timestamptz | |
| status | enum | running, ok, partial, failed |
| counts | jsonb | found, deduped, filtered, scored, tailored, applied, errors |
| llm_requests | int | |
| error | text | |

## run_requests
Manual "Find now" and "Fly now" presses.

| Field | Type | Notes |
|---|---|---|
| kind | enum | find, apply |
| source | enum | dashboard, cli |
| status | enum | waiting, picked_up, done, skipped |
| run_id | uuid → runs | set when picked up |
| created_at / picked_up_at | timestamptz | |

## applier_heartbeat
Single row, updated every minute by the laptop helper.

| Field | Type | Notes |
|---|---|---|
| last_seen_at | timestamptz | older than 3 min = offline |
| version | text | helper version |
| busy | bool | currently applying |

`runs` also gets `trigger` (enum: schedule, manual) and a partial unique index allowing one `running` row per kind (the run lock).

## llm_usage
One row per day for quota tracking.

| Field | Type | Notes |
|---|---|---|
| day | date | unique (IST) |
| provider | text | |
| requests | int | |
| input_tokens / output_tokens | int | |

## company_stats_daily
See `08_company_registry.md`.
