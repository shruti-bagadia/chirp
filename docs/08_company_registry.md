# Company Registry — Design

The company list is not a static file. It lives in the database as its own table, grows on its own, ranks itself, and prunes companies that stop hiring. You approve additions and can override any priority.

---

## 1. Lifecycle

```
            discovered                you approve
 (new) ───────────────► Candidate ───────────────► Active ◄──────┐
                           │                         │            │
                           │ you reject              │ 60 days,   │ matching job
                           ▼                         │ no matches │ appears again
                        Blocked                      ▼            │
                                                  Dormant ────────┘
```

| State | Meaning | How often the Finder checks it |
|---|---|---|
| Candidate | Found automatically, waiting for your yes/no | Not checked until approved |
| Active | In rotation | Every run (twice daily) |
| Dormant | No matching jobs in 60 days | Weekly |
| Blocked | Never apply (current employer, client, rejected) | Never |

Seeded blocks: Poonawalla Fincorp, IIT Bombay / Technology Innovation Hub.

---

## 2. How the list grows

### A. Job alert emails (main source, no scraping)
Set up alerts on LinkedIn, Naukri, and Instahire for your target titles in Pune. They email you daily. The backend reads those emails through the Gmail API, pulls out company names and job links, and adds unseen companies as **Candidates**. Nothing ever touches those sites directly, so there's no terms-of-service risk.

### B. Careers-page links you paste
In the dashboard, paste any careers URL. The backend detects the platform and adds the company as Active.

### C. Related companies
When you approve a job, the backend notes the company's domain and type. Once a month, Gemini suggests up to 10 similar Pune employers as Candidates. These are always suggestions, never auto-activated.

---

## 3. Automatic platform detection

Removes the manual "Platform" column. Given a careers URL, the backend checks, in order:

1. **URL patterns:** `boards.greenhouse.io`, `jobs.lever.co`, `jobs.ashbyhq.com`, `myworkdayjobs.com`, `successfactors`, `darwinbox`, `oraclecloud` / `taleo`, `icims`, `smartrecruiters`
2. **Page HTML:** script tags and embeds that reveal the platform when a company uses its own domain
3. **Fallback:** `Unknown`, which routes all its jobs to the quick-apply view

Each platform maps to a connector (for finding jobs) and an apply mode (`auto` for Greenhouse / Lever / Ashby, `quick_apply` for the rest).

---

## 4. Priority score (0–100)

Recalculated nightly. Higher priority means checked first, shown first, and more of the daily cap.

| Signal | Weight | Source |
|---|---|---|
| Tier (Premium / Standard) | 25 | Your settings |
| Domain fit (fintech, AI, lending, banking) | 20 | Company type |
| Stack fit (Python / FastAPI / LLM in recent postings) | 20 | Parsed from job descriptions |
| Pune hybrid or remote availability | 15 | Parsed from job descriptions |
| Your approval rate for this company's jobs | 10 | Dashboard history |
| Hiring activity (matching jobs, last 30 days) | 10 | Finder history |

**Your overrides always win:**
- **Pin High / Pin Low:** locks a company's priority regardless of score (IT services firms are seeded as Pin Low)
- **Tier change:** moves it between Premium and Standard (also changes its expected CTC)
- **Block:** removes it permanently

Displayed as **High** (70+), **Medium** (40–69), **Low** (under 40).

---

## 5. Data model

**companies**
| Field | Type | Notes |
|---|---|---|
| id | uuid | |
| name | text | Unique, normalized ("BNY Mellon" = "BNY") |
| aliases | text[] | For matching names from emails |
| careers_url | text | |
| platform | enum | greenhouse, lever, ashby, workday, successfactors, darwinbox, oracle, icims, smartrecruiters, own, unknown |
| platform_board_id | text | e.g. Greenhouse board token, for the API |
| apply_mode | enum | auto, quick_apply |
| category | enum | banking_fintech, services_consulting, product_saas, ai_first |
| tier | enum | premium, standard, services |
| state | enum | candidate, active, dormant, blocked |
| priority_score | int | 0–100, nightly |
| pinned | enum | none, high, low |
| source | enum | seed, email_alert, pasted_url, suggested |
| last_match_at | timestamp | Drives Dormant |
| created_at / updated_at | timestamp | |

**company_stats_daily** (for priority and README metrics): company_id, date, jobs_found, jobs_matched, jobs_approved, jobs_applied

---

## 6. Dashboard: Companies page

Kept deliberately simple.

- **Candidates to review:** a short list with Approve / Block. Approve asks for tier only; everything else is detected.
- **Active list:** name, priority badge, platform, tier. Tap to pin, change tier, or block.
- **Add company:** one field, paste a careers URL.

Dormant companies are hidden unless you open a filter.

---

## 7. Seed list

Initial Active companies. Platforms are filled in automatically once careers URLs are added.

**Premium:** Mastercard, BNY, Barclays, Deutsche Bank, UBS, Citi, Northern Trust, HSBC, Icertis, Druva, PubMatic, ZS Associates

**Standard:** FIS, Fiserv, Bajaj Finserv / Bajaj Finance, Deloitte, Accenture, Persistent Systems, Amdocs, BMC Software, Mindtickle, Qualys

**Services tier, pinned Low:** Infosys, TCS, Cognizant, Capgemini, Zensar, LTIMindtree

**Additional seeds to verify** (believed to hire engineers in Pune; start as Candidates so you confirm each):
Thoughtworks, EPAM, Globant, Synechron, Cybage, Avalara, Principal Global Services, Amazon, NVIDIA, Coforge, Tech Mahindra, Wipro, Hexaware

---

## 8. New credential needed

- **Gmail API (Google Cloud project, OAuth):** read-only access to job alert emails. Use a filter so the app only reads messages labeled `job-alerts`. Free.

---

## 9. Portfolio angle

- Self-maintaining entity registry with a state machine and nightly scoring job
- Platform fingerprinting from URLs and HTML
- Feedback loop: your approvals change future priorities
- Terms-safe discovery through email parsing instead of scraping
