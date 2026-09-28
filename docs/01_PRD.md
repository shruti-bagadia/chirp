# Chirp — Product Requirements

**Owner:** Shruti Bagadia · **Status:** Draft v1 · **Updated:** Sep 27, 2026

---

## 1. Problem

Applying well takes 30–45 minutes per job: finding relevant postings, tailoring the resume, writing a cover letter, and filling out forms. Doing it at volume means either spending hours a day or sending generic applications that ATS filters drop.

## 2. Goal

Send more, better-tailored applications to Pune backend and AI roles at established companies, with about 10 minutes of human effort twice a day, and zero invented claims.

## 3. Non-goals

- Automating LinkedIn, Naukri, or any site whose terms prohibit bots
- Beating captchas or bypassing logins
- Multi-user support (Chirp is single-user by design)
- Writing claims that aren't in the facts file, ever

## 4. User

One user: Shruti. Backend & AI Engineer, 2+ years, Pune, reviewing on her phone and laptop.

## 5. Success metrics

| Metric | Target |
|---|---|
| Human time per application | Under 3 minutes (review + any quick-apply) |
| Applications per week | 25–40, within the daily cap |
| Fabricated claims in submitted resumes | 0 |
| Duplicate applications | 0 |
| Jobs in queue scoring 70+ that you approve | Above 60% (measures scoring quality) |
| Callback rate | Tracked from week 3; baseline for tuning |

## 6. Features

**Priority:** P0 = MVP, required for first live run · P1 = v1, within 2 weeks after MVP · P2 = later

### Discovery
| ID | Requirement | Priority |
|---|---|---|
| D1 | Pull postings from Greenhouse, Lever, and Ashby public job APIs for Active companies | P0 |
| D2 | Add a company by pasting its careers URL; platform detected automatically | P0 |
| D3 | Rule-based pre-filter before any LLM call: title, experience, location, contract length, salary floor, blocklist | P0 |
| D4 | Deduplicate on normalized URL and company + title + location | P0 |
| D5 | Read Workday public job listings (find only; apply goes to quick-apply) | P1 |
| D6 | Discover new companies from job-alert emails (Gmail API, read-only, one label) | P1 |
| D7 | Monthly similar-company suggestions | P2 |

### Scoring and tailoring
| ID | Requirement | Priority |
|---|---|---|
| S1 | Score each job 0–100 against the facts file, with reasons and gaps | P0 |
| S2 | Tailor resume: reorder and reword facts only; output stays one page | P0 |
| S3 | Tailored cover letter per job | P0 |
| S4 | Fabrication check: every bullet maps to a fact; every number and tool is allowed | P0 |
| S5 | PII redaction before every LLM call | P0 |
| S6 | Rate limiting and daily LLM quota tracking | P0 |
| S7 | Swappable LLM provider (Gemini default, Azure OpenAI supported) | P0 |

### Review dashboard
| ID | Requirement | Priority |
|---|---|---|
| R1 | Queue of jobs waiting for review, highest fit first | P0 |
| R2 | Select all, approve or reject in bulk | P0 |
| R3 | Job detail: why it fits, gaps, resume changes, links to posting and PDF | P0 |
| R4 | Edit expected CTC per job before approving | P0 |
| R5 | Quick-apply view for hard portals: resume, cover letter, answers, copy buttons | P0 |
| R6 | "Needs a hand" list with the blocking question or error | P0 |
| R7 | Settings: CTC tiers, thresholds, daily cap | P1 |
| R8 | Companies page: candidates, pins, tiers, blocks | P1 |
| R9 | Basic stats: applied per week, approval rate, callbacks | P2 |
| R10 | Edit Finder and Applier schedule times and days from the dashboard; pause all runs | P0 |
| R11 | "Find now" and "Fly now" buttons to run either step manually at any time | P0 |
| R12 | Run status: running, last run, next run, laptop online or offline | P0 |

### Applying
| ID | Requirement | Priority |
|---|---|---|
| A1 | Local Applier fills and submits Greenhouse and Lever forms | P0 |
| A2 | Ashby forms | P1 |
| A3 | Daily cap enforced; never applies twice to one job | P0 |
| A4 | Anything unexpected → Needs a hand, never a guess | P0 |
| A5 | Record exactly what was submitted, per question | P0 |

### Answer bank
| ID | Requirement | Priority |
|---|---|---|
| B1 | Seed with fixed, rule-based, and starter answers | P0 |
| B2 | Exact and semantic matching (embeddings, pgvector) with confidence tiers | P0 |
| B3 | Answer a new question in the dashboard, saved for reuse; job returns to queue | P0 |
| B4 | Learns alternate wordings from confirmed matches | P1 |

### Company registry
| ID | Requirement | Priority |
|---|---|---|
| C1 | Companies in DB with tier, state, blocklist | P0 |
| C2 | Nightly priority score with pin high / pin low overrides | P1 |
| C3 | Auto-dormant after 60 days without matches | P1 |

## 7. Constraints

- **Cost:** ₹0 per month on free tiers
- **Accounts:** personal only, no employer credentials
- **Privacy:** personal profile data never committed to the public repo
- **Resume:** one page, LaTeX master template preserved
- **Terms:** only public job APIs, careers pages, and your own email

## 8. Risks

| Risk | Mitigation |
|---|---|
| Few target companies use Greenhouse, Lever, or Ashby | Workday finder in P1; quick-apply view covers the rest |
| Gemini free-tier limits change | Provider interface; quota tracking; paid Flash costs a few dollars a month |
| Application forms change and break the Applier | Any unexpected field → Needs a hand; per-platform tests |
| Tailoring invents claims | Structured output tied to fact IDs, deterministic check, review before submit |
| Render free tier sleeps | Only the dashboard runs there; workers run on GitHub Actions |

## 9. Milestones

| Milestone | Scope | Done when |
|---|---|---|
| M0: Skeleton | Repo, config, DB, migrations, CI | Tests pass in CI, app boots |
| M1: Find | D1–D4, C1 | Real jobs land in DB, no duplicates |
| M2: Brain | S1–S7 | 10 tailored PDFs pass manual review |
| M3: Review | R1–R6, B1–B3 | Approve 10 jobs from phone |
| M4: Apply | A1, A3–A5 | 3 live applications submitted and recorded |
| M5: Launch | Scheduling, deploy, one week of daily use | Metrics being recorded |
| v1 | All P1 | |

## 10. Related docs

02 Process design · 03 Architecture · 04 Data model · 05 API · 06 Dashboard · 07 LLM layer · 08 Company registry · 09 Answer bank
