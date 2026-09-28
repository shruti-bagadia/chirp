"""Starting companies. Platforms are detected from the careers URL (see `detect.py`).

`CAREERS_URLS` comes from `scripts/seed_urls_research.md`: only rows marked "verified working"
or "found via search, not fetched", and only URLs that `detect()` recognizes as a known
platform. Everyone else has no URL yet (add one later from the dashboard or
`chirp companies add`) and stays on the unknown platform.
"""

from app.db.enums import CompanyCategory as C
from app.db.enums import CompanyState as S
from app.db.enums import Pinned as P
from app.db.enums import Tier as T

CAREERS_URLS: dict[str, str] = {
    "Mastercard": "https://mastercard.wd1.myworkdayjobs.com/CorporateCareers",
    "Barclays": "https://barclays.wd3.myworkdayjobs.com/en-US/External_Career_Site_Barclays",
    "Deutsche Bank": "https://db.wd3.myworkdayjobs.com/DBWebsite",
    "Northern Trust": "https://ntrs.wd1.myworkdayjobs.com/northerntrust",
    "Icertis": "https://iaaviz.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/Jobs-at-Icertis/",
    "Druva": "https://job-boards.greenhouse.io/druva",
    "FIS": "https://fis.wd5.myworkdayjobs.com/SearchJobs",
    "Fiserv": "https://fiserv.wd5.myworkdayjobs.com/en-US/EXT",
    "Accenture": "https://accenture.wd103.myworkdayjobs.com/AccentureCareers",
    "Amdocs": "https://career4.successfactors.com/careers?company=amdocs",
    "Mindtickle": "https://jobs.lever.co/mindtickle",
    "Qualys": "https://qualys.wd5.myworkdayjobs.com/Careers",
    "Synechron": "https://synechron.wd1.myworkdayjobs.com/SynechronCareers",
    "NVIDIA": "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
    "Tech Mahindra": "https://careers.smartrecruiters.com/TechMahindraLtd1",
    # Verified live (200 OK) directly, beyond the original research pass:
    "Persistent Systems": "https://careers-persistentsystems.icims.com/jobs/intro",
    "Deloitte": "https://southasiacareers.deloitte.com/",
    # US-headquartered companies' India GCCs ("USI"-style captive centers) — a
    # distinct hiring practice from a company's India-market-facing arm, often
    # with more backend/platform engineering roles. Verified live directly.
    "Deloitte USI": "https://usijobs.deloitte.com/",
    "JPMorgan Chase": "https://www.jpmorganchase.com/careers/explore-opportunities",
    "American Express": "https://careers.americanexpress.com/en/sites/CX_1/jobs?location=India&locationLevel=country&mode=location",
    "ADP": "https://jobs.adp.com/en/locations/apac/india/",
    # Pune banking/fintech pass (2026-09-28): each board was queried directly and returned
    # live Pune postings. See "Pune banking/fintech pass" in scripts/seed_urls_research.md.
    # BNY moved off Workday to Oracle Fusion HCM (site CX_3001).
    "BNY": "https://eofe.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/BNY-Careers",
    "State Street": "https://statestreet.wd1.myworkdayjobs.com/Global",
    "TIAA": "https://tiaa.wd1.myworkdayjobs.com/Search",
    "Worldpay": "https://worldpay.wd5.myworkdayjobs.com/Worldpay_External_Careers_Site",
    "TransUnion": "https://transunion.wd5.myworkdayjobs.com/TransUnion",
    "Western Union": "https://westernunion.wd5.myworkdayjobs.com/WesternUnionJobs",
    "Finastra": "https://finastra.wd3.myworkdayjobs.com/FINC",
    "MSCI": "https://globalcareers-msci.icims.com/jobs/intro",
    "Intercontinental Exchange": "https://globalcareers-ice.icims.com/jobs/intro",
    "NICE Actimize": "https://job-boards.greenhouse.io/nice",
    "Addepar": "https://job-boards.greenhouse.io/addepar1",
    # Verified live directly: multiple current (2026) Pune software engineering
    # postings on Global Payments' own careers site. Not the old TSYS Workday
    # board (TSYS's card-issuer business was sold to FIS in Jan 2026, so those
    # postings' ownership was unclear) — this is Global Payments' own, current
    # portal. Custom Next.js site, no platform `detect()` recognizes.
    "Global Payments": "https://jobs.globalpayments.com/",
}

_ROWS: list[dict] = [
    *(
        {"name": n, "tier": T.PREMIUM, "category": C.BANKING_FINTECH}
        for n in [
            "Mastercard",
            "BNY",
            "Barclays",
            "Deutsche Bank",
            "UBS",
            "Citi",
            "Northern Trust",
            "HSBC",
        ]
    ),
    *(
        {"name": n, "tier": T.PREMIUM, "category": C.PRODUCT_SAAS}
        for n in ["Icertis", "Druva", "PubMatic", "ZS Associates"]
    ),
    *(
        {"name": n, "tier": T.STANDARD, "category": C.BANKING_FINTECH}
        for n in ["FIS", "Fiserv", "Bajaj Finserv"]
    ),
    *(
        {"name": n, "tier": T.STANDARD, "category": C.PRODUCT_SAAS}
        for n in ["Amdocs", "BMC Software", "Mindtickle", "Qualys", "Persistent Systems"]
    ),
    *(
        {"name": n, "tier": T.STANDARD, "category": C.SERVICES_CONSULTING}
        for n in ["Deloitte", "Accenture", "Deloitte USI"]
    ),
    *(
        {"name": n, "tier": T.SERVICES, "category": C.SERVICES_CONSULTING, "pinned": P.LOW}
        for n in ["Infosys", "TCS", "Cognizant", "Capgemini", "Zensar", "LTIMindtree"]
    ),
    *(
        {"name": n, "tier": T.STANDARD, "category": C.PRODUCT_SAAS, "state": S.CANDIDATE}
        for n in [
            "Thoughtworks",
            "EPAM",
            "Globant",
            "Synechron",
            "Cybage",
            "Avalara",
            "Principal Global Services",
            "Amazon",
            "NVIDIA",
            "Coforge",
            "Tech Mahindra",
            "Wipro",
            "Hexaware",
            "ADP",
        ]
    ),
    *(
        {"name": n, "tier": T.PREMIUM, "category": C.BANKING_FINTECH, "state": S.CANDIDATE}
        for n in [
            "JPMorgan Chase",
            "American Express",
            "State Street",
            "TIAA",
            "Worldpay",
            "TransUnion",
            "Western Union",
            "Finastra",
            "MSCI",
            "Intercontinental Exchange",
            "NICE Actimize",
            "Addepar",
            "Global Payments",
        ]
    ),
    *(
        {"name": n, "tier": T.STANDARD, "state": S.BLOCKED}
        for n in ["Poonawalla Fincorp", "IIT Bombay", "Technology Innovation Hub"]
    ),
]

SEED_COMPANIES: list[dict] = [
    {**row, "careers_url": CAREERS_URLS[row["name"]]} if row["name"] in CAREERS_URLS else row
    for row in _ROWS
]
