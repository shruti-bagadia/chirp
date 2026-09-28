# Chirp — LLM Layer

> **Built in M2.** Code: `app/llm/` (providers, client, PII, rate limits), `app/services/scoring.py`, `tailoring.py`, `fabrication_check.py`, `processor.py`, `app/resume/`. Implementation notes: outputs are validated by small `from_dict` parsers (no Pydantic needed in the core, so it's testable anywhere); tailoring returns `skills_priority` (up to 12 allowed skills, most relevant first) instead of a full skills order; project titles and tool lists come from the fact's `title`/`tools` and are never rewritten; key numbers are bolded automatically.

Scoring and tailoring, done safely: swappable providers, no PII sent out, quota-aware, and structured so invented claims are caught by code, not by hope.

---

## 1. Provider interface

```python
class LLMProvider(Protocol):
    name: str

    def generate_json(
        self,
        *,
        system: str,
        user: str,
        schema: type[BaseModel],
        max_output_tokens: int,
        temperature: float = 0.2,
    ) -> BaseModel: ...


class EmbeddingProvider(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...
```

- `GeminiProvider` (default) and `AzureOpenAIProvider` implement `LLMProvider`.
- `LocalEmbeddingProvider` (sentence-transformers) implements `EmbeddingProvider`.
- Chosen by `LLM_PROVIDER` in config. Model names come from config, never hardcoded.
- Every call returns a Pydantic model. Invalid JSON → one retry with the validation error included → then fail.

**Wrapper applied to every call, in order:**
1. **PII redaction** (section 3)
2. **Rate limiter + daily budget** (section 4)
3. Provider call with timeout
4. Schema validation
5. **PII restore** on the output
6. Usage recorded in `llm_usage`

---

## 2. Facts file with IDs

Every claim has an ID. The LLM picks and rewrites by ID; it can't introduce new facts because the code only renders what maps to an ID.

```yaml
identity:
  title: Backend & AI Engineer
  years: 2
experience:
  - id: tih
    company: Technology Innovation Hub, IIT Bombay
    role: Python Developer
    dates: Aug 2025 – Present
    facts:
      - id: tih.fdp
        text: Led a team of 4 building an OCR + LLM document-processing backend ...
        numbers: ["4", "2–6 hours", "2–4 minutes", "95%+"]
        tools: [Python, FastAPI, OCR, LLM, AWS S3]
        tags: [fintech, genai, leadership, backend]
      - id: tih.uw
        ...
skills:
  allowed: [Python, FastAPI, Django, ...]
never_claim:
  - "latency percentage at Decimal Point"
  - "spoke or keynoted at events"
```

`numbers` and `tools` are the whitelist the fabrication check enforces per fact.

---

## 3. PII redaction

Before any LLM call, replace:
| Real | Placeholder |
|---|---|
| Full name | `[CANDIDATE]` |
| Phone | `[PHONE]` |
| Email | `[EMAIL]` |
| LinkedIn / GitHub URLs | `[LINKEDIN]` / `[GITHUB]` |

Detection uses exact values from the profile plus regex for phone and email patterns. After the call, placeholders are restored. A unit test asserts no profile PII value ever appears in an outgoing request body.

---

## 4. Rate limiting and budget

- **Token bucket:** `LLM_REQUESTS_PER_MINUTE` (default 10). Calls wait for a token.
- **Daily budget:** `LLM_DAILY_REQUEST_BUDGET` (default 900, under the free tier's daily limit). Checked against `llm_usage` before each call.
- **When exhausted:** raises `BudgetExhausted`; the processor stops cleanly and leaves remaining jobs as `discovered` for the next run.
- **429 from provider:** exponential backoff with jitter, max 3 tries.

**Budget per job:** 1 scoring call + 1 tailoring call (+1 retry at most) ≈ 2–3 requests. 30 jobs per run × 2 runs ≈ 150 requests a day.

---

## 5. Prompts

Stored as versioned files in `app/llm/prompts/` (e.g. `score_v1.md`). The version is saved with every output, so results can be compared when prompts change.

### 5.1 Scoring (`score_v1`)

**System:**
> You evaluate how well a candidate fits a job. Use only the candidate facts provided. Be strict: missing core requirements lower the score. Respond with JSON matching the schema.

**User:** job title, company, location, description (truncated to ~3,000 words), candidate facts (redacted), target preferences.

**Output schema:**
```python
class ScoreResult(BaseModel):
    score: int  # 0–100
    must_haves_matched: list[str]
    gaps: list[str]  # requirements not in facts
    seniority_fit: Literal["under", "match", "over"]
    location_fit: Literal["pune_hybrid", "remote", "pune_onsite", "other"]
    summary: str  # one line, max 20 words
    role_focus: str  # e.g. "LLM-powered backend services"
```

**Rubric given in the prompt:** core stack match 40, domain match 20, seniority match 20, responsibilities match 20.

### 5.2 Tailoring (`tailor_v1`)

**System:**
> You tailor a one-page resume for a specific job. You may only select, reorder, and reword the candidate's facts, referenced by ID. Never add tools, numbers, employers, titles, or claims not present in the fact you are rewriting. Keep every number exactly as written. Respond with JSON matching the schema.

**Output schema:**
```python
class BulletRewrite(BaseModel):
    fact_id: str
    text: str  # reworded, max ~35 words


class TailorResult(BaseModel):
    summary: str  # 2–3 sentences, built from facts
    summary_fact_ids: list[str]  # facts the summary draws on
    skills_order: list[str]  # subset + order of allowed skills
    experience: dict[str, list[BulletRewrite]]  # keyed by experience id
    change_summary: str  # "Led with X; moved Y up"
    cover_letter: str  # 150–220 words, uses [Company]
```

---

## 6. Fabrication check (deterministic, no LLM)

Runs on every `TailorResult`. Any failure blocks the job.

| Rule | Check |
|---|---|
| Known facts only | Every `fact_id` exists in the active profile |
| Numbers preserved | Every number in a rewrite appears in that fact's `numbers` |
| Tools allowed | Every tool or technology named appears in that fact's `tools` or `skills.allowed` |
| Skills allowed | `skills_order` is a subset of `skills.allowed` |
| Summary grounded | Numbers and tools in `summary` appear in the facts listed in `summary_fact_ids` |
| Never-claim list | No phrase from `never_claim` appears |
| No new employers | No company names outside the profile and the target company |
| Cover letter | Same number and tool rules, against all facts |

Tool detection uses a curated vocabulary of ~300 tech terms, matched case-insensitively with word boundaries.

---

## 7. Rendering and the one-page loop

1. Jinja2 renders `template.tex.j2` (LaTeX-safe delimiters, all text escaped).
2. Tectonic compiles to PDF.
3. Page count checked. If more than one page: drop the lowest-ranked bullet from the longest section, recompile. Max 4 attempts, then `error`.

---

## 8. Quality checks

- **Golden set:** 10 real job descriptions with hand-reviewed expected scores (±10) and must-include facts. Run with `make eval` whenever prompts change.
- **CI:** providers are mocked with recorded responses. Fabrication check and PII tests run on every push.
- **Weekly review:** approval rate by score band. If most 70–75 jobs get rejected, raise the threshold.
