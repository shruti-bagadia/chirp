# Answer Bank — Design

Every application question you answer once is saved and reused. The bank starts with your pre-written answers (notice period, CTC, reason for looking) and grows every time the Applier hits a question it hasn't seen.

---

## 1. How it works

```
 Applier finds a question on a form
            │
            ▼
 Search the answer bank for a match (by meaning, not exact wording)
            │
   ┌────────┼──────────────────┐
   ▼        ▼                  ▼
 Strong   Possible            No match
 match    match
   │        │                  │
   ▼        ▼                  ▼
 Use it   Show in review      Job goes to "Needs Attention"
          with the suggested  with the question shown.
          answer; you accept  You answer in the dashboard,
          or edit             and it's saved to the bank.
```

Next time any form asks the same thing, even in different words, the saved answer is used.

---

## 2. Matching by meaning

Forms rarely word questions the same way. These should all match one saved answer:

- "What is your greatest weakness?"
- "Describe an area you're working to improve."
- "What's one thing you'd like to get better at professionally?"

**How:** each saved question is converted into an embedding (a numeric fingerprint of its meaning) and stored in Supabase using pgvector. A new question is embedded the same way, and the closest saved questions are found by similarity.

**Embedding model:** a small local model (sentence-transformers) is free, fast, and keeps your answers private. It runs only on GitHub Actions and your laptop, never on Render, so the free web tier stays light. Swappable through the same provider interface as the LLM.

**Confidence thresholds (tunable in settings):**
| Similarity | Action |
|---|---|
| 0.85 and above | Strong match: used automatically |
| 0.70–0.84 | Possible match: suggested in review, you confirm |
| Below 0.70 | No match: you answer it |

Every match you confirm or correct also teaches the system: confirmed pairs are added as alternate wordings, so future matching gets more accurate.

---

## 3. Fitting answers to each form

A saved answer is your words, but forms vary. Before submitting, the answer is adapted only in these ways:

- **Length:** trimmed to fit the form's character limit, keeping the core point
- **Company name:** "[Company]" placeholders filled in
- **Format:** dropdowns and yes/no fields mapped to the closest option

It never adds new claims. The adapted version is checked against the original and your facts file, and anything that fails the check goes to review instead.

---

## 4. Answer types

| Type | Example | Reuse rule |
|---|---|---|
| Fixed | Notice period, gender, work authorization | Always identical |
| Rule-based | Expected CTC | Computed from the company's tier |
| Personal | Greatest weakness, proudest project | Your words, trimmed to fit |
| Company-specific | Why do you want to join us? | Generated fresh per company from your facts, then reviewed |

---

## 5. Data model

**answers**
| Field | Type | Notes |
|---|---|---|
| id | uuid | |
| canonical_question | text | Your wording of the question |
| answer | text | Your answer |
| short_answer | text | Optional version under 200 characters |
| type | enum | fixed, rule_based, personal, company_specific |
| category | enum | logistics, compensation, behavioral, technical, motivation, diversity |
| times_used | int | |
| last_used_at | timestamp | |
| version | int | Increments on edit; old versions kept |
| created_at / updated_at | timestamp | |

**question_variants**
| Field | Type | Notes |
|---|---|---|
| id | uuid | |
| answer_id | uuid | Links to answers |
| question_text | text | Wording seen on a real form |
| embedding | vector | pgvector |
| source_job_id | uuid | Which application it came from |

**application_answers** (audit trail)
| Field | Type | Notes |
|---|---|---|
| application_id | uuid | |
| question_text | text | As it appeared |
| answer_submitted | text | Exactly what was sent |
| answer_id | uuid | Which bank entry it came from |
| match_score | float | |

The audit trail means you can always see exactly what was said to any company, which is useful before interviews.

---

## 6. Dashboard: Answers page

- **Waiting for you:** new questions from Needs Attention jobs. Answer once; it's saved and those jobs go back into the apply queue automatically.
- **Answer bank:** searchable list by category. Tap to edit; edits apply to future applications only.
- **Before an interview:** open any application to see every answer submitted to that company.

---

## 7. Starter answers to write

Having these ready on day one prevents most Needs Attention items:

- Greatest strength
- Greatest weakness
- Describe a challenging project
- Tell us about a time you led a team or took ownership
- Where do you see yourself in 3–5 years?
- Why are you a good fit for this role? (template with [Company])
- Describe a time you disagreed with a teammate or client
- Anything else you'd like us to know?

---

## 8. Portfolio angle

- Semantic question matching with embeddings and pgvector: real RAG-style retrieval applied to a new problem
- Confidence-tiered automation with a human-in-the-loop fallback
- Self-improving matching from confirmed pairs
- Fact-checked adaptation so reused answers never drift into new claims
- Full audit trail of every submitted answer
