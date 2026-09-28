# Chirp — Process Design

How work moves through Chirp, when each step runs, what can fail, and where you step in.

---

## 1. Schedule (flexible)

Nothing is hardcoded. Times and days live in `settings.schedule` and are edited in the dashboard. Defaults:

| Step | Default times (IST) | Days | Where it runs |
|---|---|---|---|
| Find + process | 08:30, 13:00 | Mon–Fri | GitHub Actions |
| Fly (apply) | 10:30, 15:30 | Mon–Fri | Your laptop |
| Nightly upkeep | 02:00 | Daily | GitHub Actions |

**Manual runs, anytime:**
- **Find now** in the dashboard starts a Finder run immediately.
- **Fly now** tells your laptop to start applying immediately.
- From the laptop terminal: `chirp find` or `chirp apply`.

**Pause:** one switch ("Chirp is resting") stops all scheduled runs. Manual runs still work.

### How flexible scheduling works

**Finder (GitHub Actions):** GitHub's cron can't be edited from an app, so a tiny **scheduler tick** workflow runs every 15 minutes. It reads `settings.schedule` and the `runs` table and exits in seconds unless a run is due. If one is due, it starts the Finder. Public repos get free Actions minutes, so the ticks cost nothing.

**Find now:** the dashboard calls GitHub's `workflow_dispatch` API to start the Finder workflow straight away. Needs one fine-grained GitHub token limited to this repo's Actions.

**Applier (laptop):** runs as a small background helper, `chirp applier --watch`. Every minute it checks in with the API: it reports that the laptop is online, and asks whether a scheduled or requested run is due. **Fly now** in the dashboard creates a run request; the helper picks it up within a minute. If the laptop is off, the dashboard shows "Laptop offline" and the request waits until it's back.

**Rules:**
- One run of each kind at a time (run lock). Pressing Find now during a run shows "Already running" instead of starting another.
- A scheduled time that passes while paused or offline is skipped, not stacked up. Fly now requests wait for the laptop.
- Schedule changes take effect at the next tick, within 15 minutes.
- Times are always IST; stored and compared in UTC.

---

## 2. Job state machine

```
                  ┌──────────────► filtered_out   (failed rules or score < 70)
                  │
 discovered ──────┼──────────────► error          (processing failed 3 times)
                  │
                  ▼
           pending_review ───────► rejected
                  │
                  ▼ you approve
              approved ◄──────────────────┐
                  │ Applier claims        │ you answer the question
                  ▼                       │
              applying ──────────► needs_attention
                  │
                  ├──────────────► applied
                  └──────────────► expired  (posting closed)
```

| Code state | Dashboard label | Who moves it out |
|---|---|---|
| discovered | (hidden) | Processor |
| filtered_out | (hidden; visible in a filter) | Nobody |
| error | (hidden; visible in a filter) | Retry button |
| pending_review | 🪺 In the nest | You |
| approved | 🪽 Ready to fly | Applier |
| applying | ✈️ Flying | Applier (or lease timeout) |
| needs_attention | 🤲 Needs a hand | You |
| applied | ✉️ Flown | Final |
| rejected | 🍃 Let go | Final |
| expired | 🍂 Closed | Final |

**Rules:**
- All transitions go through one service function that checks the move is allowed and writes a row to `job_events`. Nothing updates `status` directly.
- `applying` uses a **lease**: the Applier claims a job with `lease_until = now + 15 min`. If the laptop crashes, the lease expires and the job returns to `approved`. Two Applier runs can never grab the same job.
- Rejected, filtered, and applied jobs are never deleted, so dedupe always sees them.

---

## 3. Flows

### 3.1 Find
1. Load Active companies, highest priority first.
2. For each, call its platform connector for current postings.
3. Normalize each posting: canonical URL (tracking params stripped), company, title, location, description, salary if listed, posted date.
4. **Dedupe:** skip if the canonical URL exists, or the same company + normalized title + location exists in any state.
5. Insert new jobs as `discovered`. Update the company's `last_match_at` if any job survives the pre-filter later.

### 3.2 Pre-filter (rules only, no LLM)
Cheap checks first, to save LLM quota. Any failure → `filtered_out` with a reason.
- Company is blocked
- Title doesn't match target titles, or matches exclusions (frontend, QA, Java-only, .NET-only, intern)
- Experience asked above 4 years
- Location isn't Pune or Remote–India
- Contract under 6 months
- Listed salary tops out below the tier's minimum
- Posted more than 7 days ago

### 3.3 Score
1. Redact PII.
2. LLM returns: score, matched must-haves, gaps, seniority fit, location fit, one-line reason, role focus.
3. Adjustments: +5 Pune hybrid, −5 Pune onsite (and flag).
4. Below 70 → `filtered_out`. Otherwise continue.
5. Stop scoring when this run hits 30 jobs or the daily LLM budget.

### 3.4 Tailor
1. LLM selects and rewrites facts by ID, orders skills, drafts the cover letter.
2. **Fabrication check** (deterministic; see 07). Failure → retry once with the errors listed; second failure → `error`.
3. Render the LaTeX template, compile to PDF, check it's one page. If two pages, drop the lowest-ranked bullet and recompile.
4. Upload PDF and cover letter to storage. Compute expected CTC from the company's tier.
5. Status → `pending_review`.

### 3.5 Review (you)
1. Open the dashboard. Jobs sorted by score.
2. Tap any job for details; edit CTC if needed.
3. Select all or pick, then approve or reject.

### 3.6 Apply
1. `chirp apply` claims up to the remaining daily cap from `approved`, highest score first.
2. For each: open the posting in Playwright using your Chrome profile.
3. If the posting is gone → `expired`.
4. If the platform has no apply runner → mark as `needs_attention` with reason "quick apply" (shows in the quick-apply view).
5. Fill standard fields from the profile, upload the tailored PDF, paste the cover letter.
6. For every other question: search the answer bank.
   - Strong match → use it.
   - Possible match or none → stop, → `needs_attention` with the question text. Nothing is guessed.
7. Submit. Screenshot the confirmation. Record every answer sent. → `applied`.
8. Any unexpected page (captcha, login, error) → `needs_attention` with a screenshot.

### 3.7 Needs a hand (you)
- **New question:** answer it once in the dashboard. It's saved to the answer bank and the job goes back to `approved`.
- **Quick apply:** open the quick-apply view, copy the pieces in, submit on the company's site, tap "Mark as applied."
- **Blocked by captcha or login:** solve it, then tap "Try again."

---

## 4. Failure handling

| Failure | What happens |
|---|---|
| Connector API down or changed | Log, skip that company this run, alert in dashboard if it fails 3 runs in a row |
| LLM quota or rate limit hit | Remaining jobs stay `discovered` and are picked up next run |
| LLM returns invalid JSON | Retry once; then `error` |
| Fabrication check fails twice | `error`, visible under a filter with the reason |
| PDF won't fit one page after trimming | `error` |
| Applier crash mid-job | Lease expires; job returns to `approved` |
| Form field the Applier doesn't recognize | `needs_attention` with screenshot |
| Daily cap reached | Remaining jobs wait in `approved` |

---

## 5. Where you're needed

| When | What | Time |
|---|---|---|
| Twice daily | Review and approve | ~5 min each |
| As they appear | Answer new questions, quick-apply hard portals | 2–3 min each |
| Weekly | Glance at stats, tune threshold or companies | 10 min |
| Rarely | Solve a captcha, re-log into a portal | — |
