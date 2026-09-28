# Chirp — API Design

Two surfaces in one FastAPI app:
- **Dashboard** (`/`): HTML pages and HTMX partials, session cookie auth
- **Machine API** (`/api/v1`): JSON for the Applier and `chirp` CLI, bearer token auth

Workers on GitHub Actions use the service layer and database directly, not HTTP.

---

## 1. Dashboard pages (GET, HTML)

| Route | Page |
|---|---|
| `/login` | Password login |
| `/` | 🪺 The nest: review queue |
| `/jobs/{id}` | Job detail (drawer on mobile) |
| `/jobs/{id}/quick-apply` | Quick-apply view |
| `/hands` | 🤲 Needs a hand |
| `/flown` | ✉️ Applied history, with callback toggle |
| `/answers` | Answer bank |
| `/companies` | Company registry |
| `/settings` | Tiers, thresholds, cap |

## 2. Dashboard actions (HTMX, return partial HTML)

| Method + route | Body | Effect |
|---|---|---|
| `POST /login` | password | Session cookie |
| `POST /logout` | | Clears session |
| `POST /jobs/bulk` | `action=approve\|reject`, `ids[]` | Transitions each job; returns updated queue + toast |
| `PATCH /jobs/{id}/ctc` | `expected_ctc_lpa` | Override CTC; sets `ctc_overridden` |
| `POST /jobs/{id}/mark-applied` | | For quick-apply jobs you submitted yourself |
| `POST /jobs/{id}/retry` | | `needs_attention` or `error` → `approved` or `discovered` |
| `POST /jobs/{id}/callback` | `got_callback=true\|false` | Track outcomes for metrics |
| `POST /hands/{job_id}/answer` | `question`, `answer`, `save_to_bank` | Saves answer; job → `approved` |
| `POST /answers` | question, answer, type, category | New bank entry |
| `PATCH /answers/{id}` | fields | Edit; bumps version |
| `POST /companies` | `careers_url`, `tier` | Detect platform, create Active company |
| `PATCH /companies/{id}` | `tier`, `pinned`, `state` | Pin, change tier, block, approve candidate |
| `PUT /settings` | settings fields | Validated, saved |
| `PUT /settings/schedule` | times, days per step; paused | Validated (HH:MM, IST); next run times returned |
| `POST /runs/find` | | Find now: dispatches the Finder workflow; "Already running" if locked |
| `POST /runs/apply` | | Fly now: creates a run request for the laptop helper |
| `GET /runs/status` | | Partial: running or idle, last run, next run per step, laptop online |

---

## 3. Machine API (`/api/v1`, JSON)

All requests need `Authorization: Bearer <CHIRP_API_TOKEN>`.

### `POST /api/v1/apply-queue/claim`
Claims approved jobs for the Applier, respecting the daily cap. Sets `status=applying` and a 15-minute lease.

```json
// request
{ "max": 8 }
// response
{
  "remaining_cap_today": 5,
  "jobs": [
    {
      "id": "…",
      "company": "Mastercard",
      "title": "Software Engineer II, Backend",
      "url": "https://…",
      "platform": "greenhouse",
      "apply_mode": "auto",
      "expected_ctc_lpa": 20,
      "resume_pdf_url": "https://…signed…",
      "cover_letter": "…",
      "lease_until": "2026-09-28T05:15:00Z"
    }
  ]
}
```

### `POST /api/v1/jobs/{id}/heartbeat`
Extends the lease while a long form is being filled.

### `POST /api/v1/jobs/{id}/result`
Reports the outcome. Only valid while the caller holds the lease.

```json
{
  "outcome": "applied",            // applied | needs_attention | expired
  "reason": null,                  // e.g. "captcha", "unknown_question", "quick_apply"
  "unanswered_questions": [],      // question texts, for needs_attention
  "answers_submitted": [
    { "question_text": "Notice period", "answer": "15 days", "answer_id": "…", "match_score": 1.0 }
  ],
  "confirmation_screenshot": "base64…"
}
```

### `GET /api/v1/profile`
Active profile for form-filling: name, contact, links, fixed answers. PII is fine here; this never goes to an LLM.

### `POST /api/v1/answers/match`
The Applier embeds the question locally and sends the vector, so the server never needs the embedding model.

```json
// request
{ "question_text": "Describe an area you're working to improve", "embedding": [0.012, …] }
// response
{ "match": "strong", "score": 0.91, "answer_id": "…", "answer": "…", "short_answer": "…" }
```
`match` is `strong`, `possible`, or `none`, using the thresholds in settings.

### `POST /api/v1/applier/checkin`
Called every minute by the laptop helper. Updates the heartbeat and says whether to start.

```json
// request
{ "version": "0.1.0", "busy": false }
// response
{ "start": true, "reason": "manual", "request_id": "…" }   // reason: schedule | manual | null
```

### `POST /api/v1/profile`
Used by `chirp profile push` to upload a new profile version.

---

## 4. Conventions

- **Errors:** `{ "error": { "code": "lease_expired", "message": "…" } }` with proper HTTP status codes
- **Validation:** Pydantic models for every request and response
- **Idempotency:** `result` for a job already in a final state returns 409 and changes nothing
- **Versioning:** everything under `/api/v1`
- **Docs:** FastAPI's OpenAPI page at `/api/docs`, token-protected
