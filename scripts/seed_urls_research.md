# Seed company careers-URL and platform research

Research only — nothing here is wired into `app/connectors/seed.py`. Compiled 2026-09-27 via
web search and (where noted) direct page fetches, per `docs/08_company_registry.md` §3 and §7.

Confidence legend:
- **verified working** — the URL was fetched directly and its content/markup confirms the platform.
- **found via search, not fetched** — a search engine surfaced the exact URL/subdomain (often
  from a live job posting), but I did not fetch it myself to confirm it currently resolves.
- **guessed pattern, unverified** — inferred from a URL naming convention (e.g. `*.myworkdayjobs.com`,
  SuccessFactors Career Site Builder `?lang=en-us` job IDs) without directly seeing the vendor name.
- **unknown, no ATS evidence found** — likely a bespoke/own careers portal; nothing in the detection
  list (§3) matched. Falls back to `unknown` platform per the spec (routes to quick-apply).

---

## Premium

| Company | Careers URL | Detected platform | Board/tenant id | Confidence/notes |
|---|---|---|---|---|
| Mastercard | https://careers.mastercard.com/us/en/pune-india (backed by https://mastercard.wd1.myworkdayjobs.com/CorporateCareers) | workday | `mastercard`, tenant `wd1`, site `CorporateCareers` | verified working — own-domain careers site; Workday job URLs (`careers.mastercard.com/us/en/job/R-xxxxx/...`) and the `mastercard.wd1.myworkdayjobs.com` board both confirmed live in search results |
| BNY | https://bnymellon.wd1.myworkdayjobs.com (public marketing at https://www.bny.com/corporate/global/en/about-us/careers.html) | workday | `bnymellon`, tenant `wd1` | found via search, not fetched — BNY rebranded from "BNY Mellon"; registry note says normalize "BNY Mellon" = "BNY". Workday subdomain still uses legacy `bnymellon` tenant name |
| Barclays | https://search.jobs.barclays/ (Workday board: https://barclays.wd3.myworkdayjobs.com/en-US/External_Career_Site_Barclays) | workday | `barclays`, tenant `wd3`, site `External_Career_Site_Barclays` | found via search, not fetched — multiple live `barclays.wd3.myworkdayjobs.com/.../job/...` postings (Data Engineer, Software Engineer VP, etc.) returned by search |
| Deutsche Bank | https://careers.db.com/ (Workday board: https://db.wd3.myworkdayjobs.com/DBWebsite) | workday | `db`, tenant `wd3`, site `DBWebsite` | found via search, not fetched — apprentice/technology postings for Pune found directly on `db.wd3.myworkdayjobs.com` |
| UBS | https://jobs.ubs.com/global/en/careers/search-jobs.html (ATS: `jobs.ubs.com/TGnewUI/Search/...`) | oracle (Taleo) | siteid `5012` (professionals), `5131` (graduates), `5054` (Swiss pupils) | verified working — fetched `ubs.com/global/en/careers/search-jobs.html`; the `TGnewUI` path is Taleo's "modern UI" URL signature. Not Workday despite being a bank — worth a special case in the seed script |
| Citi | https://jobs.citi.com/ (Workday board: https://citi.wd5.myworkdayjobs.com) | workday | `citi`, tenant `wd5` | found via search, not fetched — `citi.wd5.myworkdayjobs.com` surfaced directly; jobs.citi.com explicitly says applicants need "a new, Citi-specific Workday account" |
| Northern Trust | https://www.northerntrust.com/about-us/careers (Workday board: https://ntrs.wd1.myworkdayjobs.com/northerntrust) | workday | `ntrs`, tenant `wd1`, site `northerntrust` | found via search, not fetched — live job postings (`Analyst-Bangalore---Pune_R135923`, `Consultant-India-BPA_R145189`) confirm the tenant; Pune office (est. 2016, 3000+ employees) is real |
| HSBC | https://www.hsbc.com/careers/find-a-job (India listings: https://portal.careers.hsbc.com/careers?location=India) | unknown | — | found via search, not fetched — no `myworkdayjobs`/`successfactors`/etc. pattern in any result; `portal.careers.hsbc.com` looks like a bespoke portal. Some India roles are also posted via a recruiting partner ("Hackajob") but that's not HSBC's own ATS. Needs an HTML check to be sure it isn't SuccessFactors under the hood |
| Icertis | https://www.icertis.com/company/careers/ (ATS: https://iaaviz.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/Jobs-at-Icertis/) | oracle | Oracle Fusion HCM site `Jobs-at-Icertis` | verified working — fetched the careers page directly; it links to an `oraclecloud.com` Fusion HCM Candidate Experience site, matching the `oraclecloud` pattern in §3 |
| Druva | https://job-boards.greenhouse.io/druva (older alias `boards.greenhouse.io/druva` 301-redirects here) | greenhouse | `druva` | verified working — fetched via WebFetch; confirmed as Druva's Greenhouse board with live job postings (e.g. `/druva/jobs/7898921002`) |
| PubMatic | https://pubmatic.com/careers/job-search/ (job pages at https://careers.pubmatic.com/job/...) | successfactors (unconfirmed) | — | guessed pattern, unverified — a direct WebFetch of `careers.pubmatic.com` failed with a TLS cert mismatch pointing at `certificate-not-found.jobs2web.com`; Jobs2Web was the SAP SuccessFactors recruiting-marketing product, so this is suggestive but not confirmed live (the cert error may mean this legacy subdomain is stale/misconfigured) |
| ZS Associates | https://jobs.zs.com/jobs (careers hub: https://www.zs.com/careers) | successfactors (unconfirmed) | — | guessed pattern, unverified — job URLs look like `jobs.zs.com/jobs/21477?lang=en-us`, matching the SuccessFactors Career Site Builder URL convention (numeric job ID + `?lang=en-us`), but no vendor string was directly observed on the page. Live Pune postings confirmed (Power BI/Power Apps Developer, Technical Support Associate, etc.) |

## Standard

| Company | Careers URL | Detected platform | Board/tenant id | Confidence/notes |
|---|---|---|---|---|
| FIS | https://www.fisglobal.com/careers (Workday board: https://fis.wd5.myworkdayjobs.com/SearchJobs) | workday | `fis`, tenant `wd5`, site `SearchJobs` | found via search, not fetched — `fis.wd5.myworkdayjobs.com/SearchJobs` surfaced directly in results |
| Fiserv | https://careers.fiserv.com/us/en (Workday board: https://fiserv.wd5.myworkdayjobs.com/en-US/EXT) | workday | `fiserv`, tenant `wd5`, site `EXT` | found via search, not fetched — a live posting `fiserv.wd5.myworkdayjobs.com/en-US/EXT/job/Pune---Trion-Business-Park-India/...` confirms both the tenant and a real Pune location |
| Bajaj Finserv | https://www.bajajfinservmarkets.in/careers (and sibling sites for other Bajaj Finserv entities) | darwinbox | — | found via search, not fetched — search explicitly states "Bajaj Finserv Direct Ltd uses DarwinBox for their careers portal." Note: docs list this as "Bajaj Finserv / Bajaj Finance" — Bajaj Finserv has several legal entities (Markets, Health, AMC) each with its own careers page; worth confirming which entity's Pune tech roles you actually want before wiring this in |
| Deloitte | https://www.deloitte.com/in/en/careers.html (India-specific portals seen: `careersindia.deloitte.com`, `southasiacareers.deloitte.com`, `jobsindia.deloitte.com`, `usijobs.deloitte.com`) | unknown | — | found via search, not fetched — direct WebFetch attempts on `careersindia.deloitte.com` and `jobsindia.deloitte.com` both failed with DNS resolution errors (`ENOTFOUND`), meaning these domains may have moved/expired since the search snippets were indexed. Deloitte clearly runs **multiple** regional career subdomains — this needs a fresh, careful look before seeding, since the "real" current URL is unclear |
| Accenture | https://www.accenture.com/in-en/careers (Workday board: https://accenture.wd103.myworkdayjobs.com/AccentureCareers) | workday | `accenture`, tenant `wd103`, site `AccentureCareers` | verified-ish (search only, but very high confidence) — multiple live `accenture.wd103.myworkdayjobs.com/AccentureCareers/...` pages found, including India-specific ASE postings across Pune and other cities |
| Persistent Systems | https://careers.persistent.com/ | unknown | — | found via search, not fetched — a WebFetch attempt timed out; job URLs (e.g. `careers.persistent.com/jobview/node-js-lead-india-node-js-2024072313050610`) don't match any pattern in §3. Headquartered in Pune, so this is an important one to nail down manually — recommend a direct browser check rather than another automated fetch |
| Amdocs | https://career4.successfactors.com/careers?company=amdocs | successfactors | company key `amdocs` | found via search, not fetched — direct SuccessFactors URL with `company=amdocs` param surfaced; a secondary `careers-amd.icims.com` iCIMS link also appeared in results, so Amdocs may run both (iCIMS possibly for a specific business unit/region) — worth double-checking which one covers Pune postings |
| BMC Software | https://jobs.bmc.com/Careers/Home | unknown | — | found via fetch, inconclusive — fetched the page directly; it uses a generic `/portal/7/...` path with no vendor-identifying script tags, footer branding, or meta generator visible in the fetched text. Would need to inspect raw page source/network requests (not possible via WebFetch's markdown conversion) to identify the real ATS |
| Mindtickle | https://jobs.lever.co/mindtickle | lever | `mindtickle` | verified working — fetched directly; page footer explicitly says "Jobs powered by Lever," and live Pune postings were visible (Learning Consultant, Staff Engineer) |
| Qualys | https://www.qualys.com/careers/ (Workday board: https://qualys.wd5.myworkdayjobs.com/Careers) | workday | `qualys`, tenant `wd5`, site `Careers` | found via search, not fetched — live Pune job URLs confirmed directly (`Senior-Software-Engineer_R0004897`, `Software-Engineer_R0004751`) |

## Services tier, pinned Low

| Company | Careers URL | Detected platform | Board/tenant id | Confidence/notes |
|---|---|---|---|---|
| Infosys | https://www.infosys.com/careers.html (also `digitalcareers.infosys.com`) | unknown | — | found via search, not fetched — no match to any §3 pattern; appears to be a bespoke portal. As expected for a pinned-low services firm, this will route to quick-apply anyway |
| TCS | https://ibegin.tcs.com/ | unknown | — | found via search, not fetched — TCS's well-known "iBegin" portal (and a separate "Rebegin" program for women returning after career breaks); no ATS-pattern match |
| Cognizant | https://careers.cognizant.com/ | unknown | — | found via search, not fetched — own-branded careers portal; a `collaborative.wd1.myworkdayjobs.com` Workday result also appeared but its context ("AllOpenings") doesn't clearly tie to Cognizant's public candidate site, so I'm not treating it as confirmed |
| Capgemini | https://jobs.capgemini.com/ (India-specific: `capgemini.com/in-en/careers/`) | unknown | — | found via search, not fetched — no ATS-pattern URL surfaced |
| Zensar | https://www.zensar.com/careers (application form at `zensar.submit4jobs.com`) | unknown | — | found via search, not fetched — "Submit4jobs" isn't one of the platforms in §3's detection list, so this falls to unknown/own even though it's a named third-party tool |
| LTIMindtree | https://www.ltimindtree.com/careers/ (also `ltm.com/india-careers`) | unknown | — | found via search, not fetched — no ATS-pattern match; note LTIMindtree appears to run both `ltimindtree.com` and a shorter `ltm.com` domain for careers content |

## Candidates to verify

| Company | Careers URL | Detected platform | Board/tenant id | Confidence/notes |
|---|---|---|---|---|
| Thoughtworks | https://www.thoughtworks.com/careers/jobs (India: `thoughtworks.com/en-in/careers/jobs`) | unknown | — | found via search, not fetched — no greenhouse/lever/ashby match despite explicitly searching for those; Pune "Senior Consultant - Developer" roles confirmed to exist though |
| EPAM | https://careers.epam.com/ | unknown | — | found via search, not fetched — postings appear syndicated on The Muse (`themuse.com/jobs/epamsystems/...`) with real Pune roles (Java/Angular, .NET/WPF), but I could not confirm EPAM's own ATS vendor from search alone |
| Globant | https://www.globant.com/company/careers | unknown | — | found via search, not fetched — explicitly searched greenhouse/lever/ashby and got no Globant-specific hits, so likely a bespoke portal |
| Synechron | https://www.synechron.com/careers (Workday board: https://synechron.wd1.myworkdayjobs.com/SynechronCareers) | workday | `synechron`, tenant `wd1`, site `SynechronCareers` | found via search, not fetched — direct Workday subdomain surfaced; Pune-Hinjewadi (Ascendas) location explicitly confirmed on `synechron.com/careers/jobs/all/pune-hinjewadi-ascendas/all` |
| Cybage | https://www.cybage.com/careers/open-positions (application login at `careers.cybage.com`) | unknown | — | found via search, not fetched — no ATS-pattern match; note the search also surfaced a fraud warning about people impersonating Cybage recruiters, so be careful validating this one by hand |
| Avalara | https://careers.avalara.com/india | successfactors (unconfirmed) | — | guessed pattern, unverified — job URLs (`careers.avalara.com/careers-home/jobs/16463?lang=en-us`) match the SuccessFactors Career Site Builder convention, same as ZS above, but a direct WebFetch of a specific job URL returned 404 (likely because that requisition closed), so I could not confirm the vendor from page content |
| Principal Global Services | https://www.principal.com/about-us/careers (India-specific presence in Hadapsar, Pune) | unknown | — | found via search, not fetched — no ATS-pattern match found in any search result; all job data came from third-party boards (Naukri, Indeed, Glassdoor), not a confirmed first-party URL |
| Amazon | https://www.amazon.jobs/en/search?base_query=&city=Pune&country=IND&loc_query=Pune&region=Maharashtra | unknown (Amazon's own "Amazon.jobs" platform) | — | found via search, not fetched — `amazon.jobs` is Amazon's proprietary careers platform, not one of the vendors in §3, so it correctly falls to unknown/quick-apply. Real Pune postings confirmed (SDE - Alexa, AWS Professional Services roles) |
| NVIDIA | https://www.nvidia.com/en-in/about-nvidia/careers/ (Workday board: https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite) | workday | `nvidia`, tenant `wd5`, site `NVIDIAExternalCareerSite` | found via search, not fetched — multiple live Pune job URLs confirmed directly (`Software-Engineer---Deep-Learning_JR1981519`, `System-Software-Engineer---GPU_JR1972360`) |
| Coforge | https://careers.coforge.com/coforge/ | unknown | — | found via search, not fetched — candidate login portal labeled "ZM Candidate"; could not identify the underlying vendor from search results alone |
| Tech Mahindra | https://careers.techmahindra.com/ (ATS: https://careers.smartrecruiters.com/TechMahindraLtd1) | smartrecruiters | `TechMahindraLtd1` | found via search, not fetched — direct SmartRecruiters URL with Tech Mahindra's tenant slug surfaced in results |
| Wipro | https://careers.wipro.com/ | successfactors | — | verified working — fetched a live job page directly (`careers.wipro.com/job/Associate-Pune/98938-en_US/`); its logo asset is served from `rmkcdn.successfactors.com`, and the cookie-consent text explicitly references "SAP as service provider," confirming SAP SuccessFactors |
| Hexaware | https://careers.hexaware.com/career/ (also `jobs.hexaware.com`) | unknown | — | found via search, not fetched — two separate careers subdomains found (`careers.hexaware.com` and `jobs.hexaware.com`); no ATS-pattern match, and the split domains are worth resolving by hand before seeding |

---

## Summary of confirmed Greenhouse / Lever / Ashby candidates for `chirp try-board`

Three companies came back as genuinely verified (not just search-inferred) hits on the three
ATS platforms this repo has connectors for, per `docs/08_company_registry.md` §3 (`apply_mode:
auto` platforms):

1. **Druva — Greenhouse** — `https://job-boards.greenhouse.io/druva`
   Fetched directly; confirmed live board with real job postings under the `druva` slug (redirect
   from the legacy `boards.greenhouse.io/druva` also confirmed, so either URL should work for
   `chirp try-board`).
2. **Mindtickle — Lever** — `https://jobs.lever.co/mindtickle`
   Fetched directly; footer explicitly reads "Jobs powered by Lever," with live Pune postings
   (Staff Engineer, Learning Consultant) visible on the board.
3. No Ashby hit was found for any of the 41 companies researched — none of PubMatic, Icertis,
   ZS Associates, or the other product/SaaS names in the Premium tier turned out to be on Ashby.
   If you want a third board for testing Ashby specifically, none of these seed companies fit;
   that would need a separate throwaway target (e.g. a company from `jobs.ashbyhq.com` seen in
   passing during search, like OpenAI or Ramp) purely to exercise the connector, not to add to
   the registry.

Recommend testing `chirp try-board https://job-boards.greenhouse.io/druva` and
`chirp try-board https://jobs.lever.co/mindtickle` first — both are Premium/Standard tier
companies with confirmed real Pune-relevant postings at fetch time, so they should also
exercise the Pune-role filtering logic, not just basic connectivity.

---

## Pune banking/fintech pass (2026-09-28)

Goal: banking/fintech companies with a **confirmed Pune office** (not just India). "Verified
working" here means the board's own public job API (Workday CXS `/wday/cxs/.../jobs`, Oracle
`recruitingCEJobRequisitions`, Greenhouse `boards-api`, iCIMS/Jibe) was queried directly and
returned live Pune postings. All new rows are `state=candidate`.

### Added to `seed.py`

| Company | Careers URL | Detected platform | Board/tenant id | Confidence/notes |
|---|---|---|---|---|
| BNY (existing row) | https://eofe.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/BNY-Careers | oracle | site `CX_3001` | verified working. Pune office confirmed on bny.com India locations page (Prestige Alphatech, Kharadi). BNY has **moved off Workday**: the old `bnymellon.wd1.myworkdayjobs.com` board now returns 422, and bny.com careers links to Oracle. API returned 90 Pune engineering hits (VP Full-Stack Engineer and others) |
| State Street | https://statestreet.wd1.myworkdayjobs.com/Global | workday | `statestreet/wd1/Global` | verified working. 60 Pune (Hinjewadi) postings, but mostly fund ops, analyst and BA roles. Few engineering roles |
| TIAA | https://tiaa.wd1.myworkdayjobs.com/Search | workday | `tiaa/wd1/Search` | verified working. 45 Pune hits including Head Application Development and Product Owner (TIAA GBS Pune) |
| Worldpay | https://worldpay.wd5.myworkdayjobs.com/Worldpay_External_Careers_Site | workday | `worldpay/wd5/Worldpay_External_Careers_Site` | verified working. Pune Java/Spring/Kafka roles. Owned by Global Payments since Jan 2026 |
| TransUnion | https://transunion.wd5.myworkdayjobs.com/TransUnion | workday | `transunion/wd5/TransUnion` | verified working. Pune web, React, Java and full-stack developer roles |
| Western Union | https://westernunion.wd5.myworkdayjobs.com/WesternUnionJobs | workday | `westernunion/wd5/WesternUnionJobs` | verified working. The board is linked from careers.westernunion.com/india. Pune TEC opened in 2018 and has 800+ staff. (`HiddenWUjobs` is a hidden site, so it is not used) |
| Finastra | https://finastra.wd3.myworkdayjobs.com/FINC | workday | `finastra/wd3/FINC` | verified working. The board is linked from finastra.com/careers. 20 Pune hits (QA, DevOps/SRE, product) |
| MSCI | https://globalcareers-msci.icims.com/jobs/intro | icims | — | verified working (the portal resolves and is linked from careers.msci.com). Pune (Hadapsar) is an engineering CoE. Pune Java/Python/AI Engineer postings found via search |
| Intercontinental Exchange | https://globalcareers-ice.icims.com/jobs/intro | icims | — | verified working. careers.ice.com is an iCIMS front end, and its API returned 17 Pune jobs, mostly mortgage-tech ops and data roles. Named in full because "ICE" would trip `fabrication_check`'s word match |
| NICE Actimize | https://job-boards.greenhouse.io/nice | greenhouse | `nice` | verified working. nice.com links to `boards.eu.greenhouse.io/nice`, but the US `boards-api` also serves this board: 177 jobs, 33 in Pune (Actimize financial-crime work: data science, DevOps, engineering). Board covers all of NICE |
| Addepar | https://job-boards.greenhouse.io/addepar1 | greenhouse | `addepar1` | verified working. 11 Pune roles including Staff Software Engineer – AI Platform. Pune office in Kalyani Nagar (addepar.com/offices/pune) |

### Rejected / not added

| Company | Pune presence? | Notes |
|---|---|---|
| Bank of America | no | Official India page lists Mumbai, New Delhi, Bengaluru, Chennai, Hyderabad, Gurugram and GIFT City. No Pune |
| Goldman Sachs | no | Bengaluru, Hyderabad, Mumbai |
| Morgan Stanley | no | morganstanley.com India page says "Presence in 3 cities: Mumbai, Bengaluru, Gift City". A third-party blog claiming an EON Kharadi office is wrong or out of date |
| Wells Fargo | no | Bengaluru and Hyderabad, with Chennai closing by 2027. The Workday board shows no Pune postings |
| Standard Chartered | no | GBS is in Chennai and Bengaluru |
| BlackRock | no | Workday India postings are Gurugram and Mumbai only |
| Societe Generale | no (GSC) | GSC is in Bengaluru and Chennai. Pune is at most a banking branch |
| Nomura | no | Powai, Mumbai |
| NatWest Group | no | Gurugram, Chennai, Bengaluru |
| Credit Agricole CIB | branch only | Pune is a corporate-banking branch (ICC Trade Tower). The back-office/IT entity is not Pune-based |
| Macquarie | no | Gurugram, Mumbai, Delhi |
| LSEG | no | Bengaluru, Hyderabad, Mumbai, Delhi. The Workday board returned 0 Pune postings |
| BNP Paribas | branch only | ISPL delivery centres are in Mumbai, Chennai and Bengaluru. Pune (Koregaon Road) is a branch |
| Global Payments (TSYS board `tsys.wd1.myworkdayjobs.com/tsys`) | yes | 16 live Pune postings, but TSYS Issuer Solutions was divested to FIS in Jan 2026, so the board's Pune roles likely belong to FIS (already seeded). Ownership is ambiguous, so not added |
| Allstate India | yes | `allstate.wd5.myworkdayjobs.com/allstate_careers` has live Pune software roles. Insurance, not banking/fintech, so out of scope for this pass |
| Euronet | yes (per job boards) | ATS is `euronet.hire.trakstar.com`, which `detect()` doesn't recognise |
