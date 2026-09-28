# Chirp — End-to-End Test Plan

---

## 1. Test levels

| Level | What | Tools | Runs |
|---|---|---|---|
| Unit | Pure logic: dedupe keys, prefilter rules, CTC, fabrication check, PII, state transitions | Pytest | Every push |
| Integration | Services + real Postgres with pgvector | Pytest + Postgres container | Every push |
| Contract | Connectors parse real platform responses | Recorded JSON fixtures | Every push; fixtures refreshed monthly |
| E2E pipeline | Finder → Processor → Dashboard → Applier, all real code, fake outside world | Pytest + FakeATS + MockLLM | Every push to `main` |
| E2E UI | Dashboard in a real browser, phone and laptop sizes | Playwright | Every push to `main` |
| Live smoke | Real APIs, real Gemini, no submission | Manual checklist | Before each milestone |
| Live pilot | 3–5 real applications, watched | Manual | Once, at M4 |

## 2. Test environments

| Env | Database | LLM | Job sources | Submits? |
|---|---|---|---|---|
| Local / CI | Postgres container | MockLLM | FakeATS | Only to FakeATS |
| Staging | Second free Supabase project | Gemini (free tier) | Real public APIs | **Never**; `APPLY_DRY_RUN=true` |
| Production | Main Supabase project | Gemini | Real | Yes |

## 3. Test fixtures

- **FakeATS:** a small FastAPI app that imitates Greenhouse, Lever, Ashby, and Workday job listing APIs and application forms. Scenario switches: normal form, file upload, custom question, dropdown question, character-limited field, captcha page, login wall, closed posting, slow page, form that changed layout.
- **MockLLM:** deterministic `LLMProvider`. Returns canned scores and tailoring, and on request: invalid JSON, a fabricated number, a fabricated tool, a never-claim phrase, a 429, a timeout.
- **Golden jobs:** 10 real job descriptions (saved) with expected score bands and must-include facts.
- **Sample profile:** `profile.example/` with fake identity; the real profile is never used in CI.
- **Clock control:** frozen time for schedules, leases, dormancy, and daily caps (IST day boundaries).

## 4. Case format

`ID · Scenario · Expected result · Priority (P0 = must pass for MVP)`

---

## 5. E2E cases

### A. Discovery
| ID | Scenario | Expected | P |
|---|---|---|---|
| A01 | Active Greenhouse company with 5 postings | 5 jobs created as `discovered` with all fields parsed | P0 |
| A02 | Same for Lever | Same | P0 |
| A03 | Same for Ashby | Same | P1 |
| A04 | Same for Workday | Jobs found; `apply_mode=quick_apply` | P1 |
| A05 | Finder runs twice with no new postings | 0 new jobs on second run | P0 |
| A06 | Same posting with different tracking params (`?utm_…`) | Treated as one job | P0 |
| A07 | Same role reposted under a new URL | Caught by company + title + location key | P0 |
| A08 | Posting previously rejected reappears | Not re-added | P0 |
| A09 | Posting previously applied reappears | Not re-added | P0 |
| A10 | Connector returns 500 | Company skipped this run; run status `partial`; other companies still processed | P0 |
| A11 | Connector fails 3 runs in a row | Warning visible in dashboard | P1 |
| A12 | Blocked company has postings | None fetched | P0 |
| A13 | Dormant company | Only fetched on weekly run | P1 |
| A14 | Paste a Greenhouse careers URL in dashboard | Company created, platform detected, `apply_mode=auto` | P0 |
| A15 | Paste a URL on the company's own domain embedding Lever | Detected as Lever from page HTML | P1 |
| A16 | Paste an unrecognizable URL | Platform `unknown`, `apply_mode=quick_apply` | P0 |
| A17 | Job-alert email with 3 companies, 1 new | 1 Candidate company created; others matched by alias | P1 |
| A18 | Email outside the `job-alerts` label | Never read | P1 |

### B. Pre-filter
| ID | Scenario | Expected | P |
|---|---|---|---|
| B01 | Title "Frontend Engineer" | `filtered_out`, reason "title excluded"; no LLM call | P0 |
| B02 | "Java Backend Developer" with no Python | `filtered_out` | P0 |
| B03 | "5+ years required" | `filtered_out` | P0 |
| B04 | Location Bangalore onsite | `filtered_out` | P0 |
| B05 | Location Mumbai hybrid | `filtered_out` | P0 |
| B06 | Remote, India | Passes | P0 |
| B07 | Pune onsite | Passes, flagged | P0 |
| B08 | 3-month contract | `filtered_out` | P0 |
| B09 | Listed salary 8–12 LPA at a Standard company | `filtered_out` (below floor 15) | P0 |
| B10 | Listed salary 12–15 LPA at a Services company | Passes (floor 14) | P0 |
| B11 | No salary listed | Passes | P0 |
| B12 | Posted 10 days ago | `filtered_out` | P0 |
| B13 | Internship | `filtered_out` | P0 |

### C. Scoring
| ID | Scenario | Expected | P |
|---|---|---|---|
| C01 | Strong-fit golden job | Score in expected band; `pending_review` after tailoring | P0 |
| C02 | Weak-fit golden job | Score below 70; `filtered_out` | P0 |
| C03 | Pune hybrid role | +5 applied | P0 |
| C04 | Pune onsite role | −5 applied and flagged | P0 |
| C05 | LLM returns invalid JSON once | Retried; succeeds | P0 |
| C06 | LLM returns invalid JSON twice | `error` with reason | P0 |
| C07 | 40 jobs pass pre-filter | Only 30 scored this run; 10 stay `discovered` | P0 |
| C08 | Golden set eval | ≥ 8 of 10 within ±10 of expected | P1 |

### D. Tailoring, fabrication check, PDF
| ID | Scenario | Expected | P |
|---|---|---|---|
| D01 | Normal tailoring | PDF in storage, one page, cover letter saved, `pending_review` | P0 |
| D02 | Rewrite changes "95%+" to "98%" | Blocked by number rule; retried; if repeated → `error` | P0 |
| D03 | Rewrite adds "Kubernetes" (not in facts) | Blocked by tool rule | P0 |
| D04 | Unknown fact ID | Blocked | P0 |
| D05 | Summary says "spoke at Impact AI Summit" | Blocked by never-claim list | P0 |
| D06 | Adds a latency % at Decimal Point | Blocked | P0 |
| D07 | Cover letter names a tool not in facts | Blocked | P0 |
| D08 | Content overflows to two pages | Lowest-ranked bullet dropped; recompiled to one page | P0 |
| D09 | Still two pages after 4 attempts | `error` | P0 |
| D10 | Special characters in company name (`&`, `%`, `#`) | LaTeX escaped; compiles | P0 |
| D11 | Tectonic missing or fails | `error`; run continues with next job | P0 |
| D12 | Expected CTC for Premium / Standard / Services company | 20 / 16 / 15 | P0 |
| D13 | Tailoring saved with profile and prompt versions | Both recorded | P1 |

### E. Dashboard: review
| ID | Scenario | Expected | P |
|---|---|---|---|
| E01 | Open Nest with 14 pending jobs | Sorted by score desc; counts correct | P0 |
| E02 | Select all → Ready to fly | All 14 → `approved`; rows fly out; toast shows 14 | P0 |
| E03 | Select 3 → Let go | 3 → `rejected`; rows drift away | P0 |
| E04 | Approve with nothing selected | Button disabled | P0 |
| E05 | Open job detail | Why it fits, gaps, changes, links, CTC shown | P0 |
| E06 | Open resume PDF link | Signed URL opens the right PDF | P0 |
| E07 | Signed URL after expiry | Access denied; reopening detail gives a fresh link | P1 |
| E08 | Edit CTC to 19 then approve | `expected_ctc_lpa=19`, `ctc_overridden=true`; Applier submits 19 | P0 |
| E09 | Enter invalid CTC ("abc", 0, 200) | Rejected inline with a message | P0 |
| E10 | Double-tap Ready to fly | Jobs approved once; no duplicate events | P0 |
| E11 | Approve a job that changed state meanwhile | That job skipped; message says so | P1 |
| E12 | Empty nest | Sleeping Chirp empty state with next run time | P0 |
| E13 | Refresh | New jobs appear without full reload | P0 |

### F. Needs a hand
| ID | Scenario | Expected | P |
|---|---|---|---|
| F01 | Two jobs blocked by the same new question | Grouped as one question with both companies | P0 |
| F02 | Answer once, "save to bank" on | Answer saved; both jobs → `approved` | P0 |
| F03 | Answer once, "save to bank" off | Used for those jobs only | P1 |
| F04 | Quick-apply job | Quick-apply view shows resume, cover letter, answers with copy buttons | P0 |
| F05 | I've applied on quick-apply job | → `applied`; counts toward today's cap | P0 |
| F06 | Try again on captcha-blocked job | → `approved` | P0 |
| F07 | Hands badge count | Matches number of `needs_attention` jobs | P0 |
| F08 | Tap an application in Flown | Sheet shows posting link, resume, CTC, every submitted answer, cover letter | P0 |
| F09 | Open application link | Opens the original posting in a new tab | P0 |

### G. Applier: happy paths
| ID | Scenario | Expected | P |
|---|---|---|---|
| G01 | Approved Greenhouse job, standard fields | Submitted to FakeATS; `applied`; confirmation screenshot stored | P0 |
| G02 | Approved Lever job | Same | P0 |
| G03 | Approved Ashby job | Same | P1 |
| G04 | Resume upload field | Tailored PDF for that job is the uploaded file | P0 |
| G05 | Cover letter field | Tailored cover letter pasted with [Company] filled | P0 |
| G06 | Notice period, CTC, location, gender, authorization fields | Fixed and rule-based answers used exactly | P0 |
| G07 | Dropdown "Notice period: Immediate / 15 days / 30 days" | "15 days" selected | P0 |
| G08 | Custom question with a strong bank match | Bank answer used; recorded with match score | P0 |
| G09 | Character-limited field (200 chars) | Short answer used, under limit | P0 |
| G10 | Every submitted answer | Recorded in `application_answers` | P0 |
| G11 | `APPLY_DRY_RUN=true` | Form filled, not submitted; job stays `approved` | P0 |

### H. Applier: failure paths
| ID | Scenario | Expected | P |
|---|---|---|---|
| H01 | Custom question, no bank match | Not submitted; `needs_attention` with question text | P0 |
| H02 | Custom question, possible match only | Not submitted; suggestion shown in Hands | P0 |
| H03 | Captcha page | `needs_attention`, reason "captcha", screenshot | P0 |
| H04 | Login wall | `needs_attention`, reason "login" | P0 |
| H05 | Posting closed | `expired` | P0 |
| H06 | Unknown required field | `needs_attention` with screenshot | P0 |
| H07 | Form layout changed | Detected as unknown fields; `needs_attention`, not a guess | P0 |
| H08 | Page times out | Retried once, then `needs_attention` | P0 |
| H09 | Workday job | `needs_attention`, reason "quick apply"; no browser automation | P0 |
| H10 | Laptop offline mid-run | Lease expires; job back to `approved`; no partial record | P0 |

### I. Answer bank
| ID | Scenario | Expected | P |
|---|---|---|---|
| I01 | "What is your greatest weakness?" vs saved "Greatest weakness" | Strong match | P0 |
| I02 | "Describe an area you're working to improve" | Strong or possible match to weakness | P0 |
| I03 | "What's your notice period?" vs weakness answer | No match | P0 |
| I04 | Confirm a possible match | Wording saved as a variant; next time strong | P1 |
| I05 | Edit an answer | New version used for future applications; past records unchanged | P0 |
| I06 | Adapted answer adds a claim | Fails check; goes to Hands | P1 |
| I07 | Company-specific "Why us?" | Generated per company; goes to review, never auto-submitted | P0 |

### J. Leases, caps, concurrency
| ID | Scenario | Expected | P |
|---|---|---|---|
| J01 | Daily cap 8, 12 approved | 8 applied today; 4 stay `approved` | P0 |
| J02 | Cap counts quick-apply "I've applied" | Yes | P0 |
| J03 | Cap resets at midnight IST (not UTC) | Correct day boundary | P0 |
| J04 | Two Applier runs start together | No job claimed by both | P0 |
| J05 | Long form, heartbeat sent | Lease extended; not reclaimed | P0 |
| J06 | Result posted after lease expired | 409; job state unchanged | P0 |
| J07 | Result posted twice | Second returns 409 | P0 |

### K. Company registry and nightly
| ID | Scenario | Expected | P |
|---|---|---|---|
| K01 | Nightly run | Priorities recalculated for all Active companies | P1 |
| K02 | Pinned high company with low score | Stays High | P1 |
| K03 | Services company | Seeded Pin Low; scanned after High and Medium | P1 |
| K04 | 60 days without matches | → Dormant | P1 |
| K05 | Dormant company gets a match on weekly check | → Active | P1 |
| K06 | Approve a Candidate | → Active with chosen tier | P1 |
| K07 | Block a company with pending jobs | Pending jobs → `rejected`; never fetched again | P1 |
| K08 | Change tier Standard → Premium | New jobs use Premium CTC; existing approved jobs keep their CTC | P1 |

### L. Scheduling and runs
| ID | Scenario | Expected | P |
|---|---|---|---|
| L01 | Finder workflow at 03:00 UTC | Runs; `runs` row with counts | P0 |
| L02 | Run fails midway | `runs.status=failed` with error; next run starts clean | P0 |
| L03 | Two finder runs overlap | Second exits early (run lock) | P0 |
| L04 | Dashboard footer | Shows last run time and status | P0 |
| L05 | Change Find times to 09:00 and 17:00 | Next tick after 09:00 IST starts Finder; 08:30 no longer runs | P0 |
| L06 | Remove Friday from Find days | No Finder run on Friday | P0 |
| L07 | Pause on | No scheduled runs of any kind; manual runs still work | P0 |
| L08 | Find now | Finder starts within a minute; run marked `trigger=manual` | P0 |
| L09 | Find now while Finder is running | "Already running"; no second run | P0 |
| L10 | Fly now with laptop online | Helper starts within 1 minute | P0 |
| L11 | Fly now with laptop offline | Dashboard shows offline; request starts when helper checks in | P0 |
| L12 | Scheduled time passes while laptop offline | Skipped, not stacked; next time runs normally | P0 |
| L13 | Invalid time ("25:00", "9am") | Rejected with a message | P0 |
| L14 | Scheduled time on the IST/UTC date boundary (e.g. 01:00 IST) | Runs on the correct IST day | P0 |
| L15 | Dispatch token missing or expired | Find now shows a clear error; scheduled runs unaffected | P1 |

### M. Security and privacy
| ID | Scenario | Expected | P |
|---|---|---|---|
| M01 | Open dashboard without login | Redirect to login | P0 |
| M02 | Wrong password 10 times | Rate limited | P0 |
| M03 | Machine API without token or wrong token | 401 | P0 |
| M04 | Outgoing LLM request bodies | Contain no name, phone, email, or profile URLs | P0 |
| M05 | Supabase service key | Never in any HTML, JS, or API response | P0 |
| M06 | PDF bucket | Private; direct URL without signature denied | P0 |
| M07 | Repo scan | No `.env`, real profile, or PDFs committed (CI secret scan) | P0 |
| M08 | Session cookie | HttpOnly, Secure, SameSite | P0 |
| M09 | HTMX POSTs | CSRF token required | P0 |

### N. LLM quota and providers
| ID | Scenario | Expected | P |
|---|---|---|---|
| N01 | Daily budget reached mid-run | Stops cleanly; rest stay `discovered`; run `partial` | P0 |
| N02 | Provider 429 | Backoff and retry; succeeds within 3 tries | P0 |
| N03 | Provider timeout | Retry; then job `error` | P0 |
| N04 | Switch `LLM_PROVIDER` to `azure_openai` | Same pipeline passes with Azure mock | P1 |
| N05 | Requests per minute | Never above configured limit | P0 |

### O. Resilience
| ID | Scenario | Expected | P |
|---|---|---|---|
| O01 | Database unreachable at dashboard load | Friendly error with retry | P0 |
| O02 | Storage upload fails | Job `error`; retried next run | P0 |
| O03 | Render cold start | Dashboard loads within ~60s; nothing lost | P1 |
| O04 | Supabase paused after inactivity | Documented recovery; data intact | P2 |

### P. UI quality
| ID | Scenario | Expected | P |
|---|---|---|---|
| P01 | 380px phone width | No horizontal scroll; sticky bar visible | P0 |
| P02 | Laptop width | Centered layout, readable line lengths | P0 |
| P03 | Keyboard only | Every action reachable; focus visible | P1 |
| P04 | `prefers-reduced-motion` | Animations replaced by instant changes | P0 |
| P05 | Contrast | All text ≥ 4.5:1 | P1 |
| P06 | Screen reader labels | Checkboxes and buttons named | P1 |
| P07 | First page load | No sound plays until the speaker button is tapped | P0 |
| P08 | Sound panel: toggle birds, toggle melody, move volume | Each layer fades in/out independently; volume changes smoothly; no console errors | P1 |
| P09 | Approve with sound on | Take-off chirp plays once | P2 |
| P10 | After 7 PM with birds on | Crickets instead of daytime birds | P2 |

### Q. Full journeys
| ID | Journey | Expected | P |
|---|---|---|---|
| Q01 | **A normal day:** Finder finds 20 → 12 filtered → 8 in nest → approve 7, reject 1 → Applier: 5 applied, 1 new question, 1 quick-apply → answer question → rerun: 1 applied → mark quick-apply done | 7 applied, 1 rejected, all answers recorded, cap respected, no duplicates | P0 |
| Q02 | **Next day:** same postings still live | None reappear | P0 |
| Q03 | **Quota day:** budget runs out at job 15 of 25 | 15 in nest; 10 processed next run | P0 |
| Q04 | **Bad LLM day:** MockLLM fabricates on 3 jobs | 3 in `error`; 0 fabricated PDFs anywhere | P0 |
| Q05 | **Crash day:** Applier killed after 2 of 6 | 2 applied, 4 return to `approved` after lease; rerun applies 4 | P0 |
| Q06 | **Profile update:** add a new fact, push profile | New tailoring uses it; old PDFs unchanged and linked to old version | P1 |
| Q07 | **New company:** paste URL → next run finds jobs → approve → applied | Works end to end | P0 |

---

## 6. Exit criteria

| Milestone | Must pass |
|---|---|
| M1 Find | A01–A02, A05–A10, A12, A14, A16, B01–B13 |
| M2 Brain | C01–C07, D01–D12, M04, N01–N03, N05 |
| M3 Review | E01–E06, E08–E10, E12–E13, F01–F02, F04–F07, I01–I03, I05, I07, M01–M03, M05–M09, P01–P02, P04 |
| M4 Apply | G01–G02, G04–G11, H01–H10, J01–J07 |
| M5 Launch | L01–L15, O01–O02, Q01–Q05, Q07, live smoke, live pilot |
| v1 | All P1 |

## 7. Live pilot checklist (M4)

- [ ] Staging dry run: 10 jobs through the full pipeline, `APPLY_DRY_RUN=true`
- [ ] Manually read all 10 PDFs and cover letters against the facts file
- [ ] Switch to production; approve 3 real jobs you genuinely want
- [ ] Watch each submission live; check the confirmation screenshot
- [ ] Confirm each company's confirmation email arrives
- [ ] Check `application_answers` matches what you'd have written
