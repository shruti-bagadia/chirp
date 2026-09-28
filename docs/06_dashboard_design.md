# Chirp — Dashboard Design

Simple, readable, a little cute. Built for your phone first; works on laptop.

**Rule:** cute touches live in labels, buttons, and empty states. Lists stay clean and fast to scan. Nothing extra on screen.

---

## 1. Theme: dawn meadow (v3)

A calm morning, not a cartoon, and no greens. A realistic house sparrow perches on a blossom branch in front of misty blue mountains at sunrise.

| Token | Value | Use |
|---|---|---|
| `--paper` | `#F2F4F8` | Page background (cool mist) |
| `--panel` | `#FFFFFF` | Lists and cards |
| `--ink` | `#1E2433` | Text |
| `--stone` | `#626B7F` | Secondary text |
| `--primary` | `#2F3F6B` | Primary buttons, high scores, active tab (dusk indigo) |
| `--sparrow` / `--bark` | `#8C5E3C` / `#6B4A35` | The bird and branch |
| `--blossom` | `#E7A3B1` | Petals, selected rows |
| `--honey` | `#B7791F` | Flags, callbacks |
| `--rose` | `#B55468` | Gaps, errors, badge |

- **Type:** Fraunces (headings) + Nunito Sans (body)
- **Checkboxes:** a blossom opens inside the circle when selected
- **Falling effects:** petals, not leaves
- All colors are CSS variables in `chirp.css`, so a new palette is a one-block change

### Forest sounds (optional, off by default)
The speaker button opens a small **Forest sounds** panel with two switches and a volume slider. Everything is synthesized live in the browser, so there are no audio files and no copyright concerns.

- **Birds and brook:** a babbling brook, wind that gusts through the trees now and then (with a leaf rustle), and birds of an Indian morning: house sparrows, bubbly bulbuls, a koel whose calls climb higher, soft spotted-dove coos, a warbler trill, a cuckoo, and a distant woodpecker every half minute or so. Sometimes a second bird answers from the other side. After 7 PM the birds give way to crickets and the odd dove.
- **Soft melody:** a slow kalimba wandering through a gentle pentatonic scale over a warm, barely-there hum, with pauses between phrases.
- **Space:** a light forest echo on birds and melody so it feels outdoors, not in your ear.
- **Moments:** a bright double chirp when the sparrow takes off with approved jobs, a rustle on "Let go," and a two-note chime when the melody turns on.

---

## 1b. Animations

Natural and short, tied to what you just did. All respect `prefers-reduced-motion`.

| Moment | Animation |
|---|---|
| Idle | The sparrow breathes, blinks, tilts its head, and flicks its tail now and then; clouds drift and sun rays shimmer |
| Selecting a job | A blossom opens in the checkbox |
| Ready to fly | Rows lift away; the sparrow takes off from the branch with a sealed letter, flaps along a curved flight path, and returns to its perch a moment later |
| Let go | Rows drop away and a few petals fall |
| Runs in progress | Three soft pulsing dots next to "Finding jobs…" or "Flying applications…" |
| Quick apply done, or a callback | Petals drift down across the screen |
| Answer once | The question card folds away |

---|---|---|
| Opening the app | Chirp hops into the header nest, once per session | 0.6s |
| Idle | Chirp blinks every few seconds; header flowers sway gently | Subtle loop |
| Selecting a job | The checkbox tick blooms into a tiny flower | 0.2s |
| Ready to fly | Selected rows fold into envelopes and slide up; Chirp flies across the screen carrying a letter; toast with falling petals | 1.2s |
| Let go | Rows drift down and turn like falling leaves | 0.5s |
| Refresh | Chirp pecks (instead of a spinner) | While loading |
| Empty nest | Chirp sleeps in the nest; little "z"s float up | Loop |
| Answer once | Question card shrinks away with a sparkle | 0.3s |
| Flown tab | One blossom per application this week; new ones bloom in | 0.4s |
| Got a callback | Toggle pops and Chirp's badge gets a flower | 0.3s |

---

## 2. Navigation

Bottom tab bar on mobile, top bar on laptop. Four tabs only:

**🪺 Nest** · **🤲 Hands** (badge count) · **✉️ Flown** · **⚙️ More** (answers, companies, settings)

---

## 3. Screens

### 3.1 Nest (home, review queue)
```
┌───────────────────────────────┐
│ 🐦 Good morning, Shruti        │
│ 14 in the nest · 3 need a hand │
├───────────────────────────────┤
│ ☐ Select all 14      Refresh  │
├───────────────────────────────┤
│ ☐  92  Backend Engineer II     │
│        Mastercard · Hybrid     │
│        ₹20 LPA                 │
├───────────────────────────────┤
│ ☐  88  Python Developer (AI)   │
│        Icertis · Hybrid        │
│        ₹20 LPA                 │
├───────────────────────────────┤
│ ☐  74  SDE 2, Platform         │
│        Persistent · Onsite ⚑   │
│        ₹16 LPA                 │
├───────────────────────────────┤
│ [ Let go ]  [ Ready to fly 12 ]│  ← sticky bottom bar
└───────────────────────────────┘
```
- Score is the big number on the left. 85+ shows in sparrow brown.
- ⚑ flags onsite roles, per your preference.
- Tapping a row's text opens detail; tapping the checkbox selects.

**Empty:** Chirp in a nest. *"Chirp's nest is empty. New jobs land here after the next run at 1:00 PM."*
**After approving:** peach toast. *"12 ready to fly! Chirp takes off at 3:30 PM, or run `chirp apply`."*

**Run strip** (under the header, one line):
```
Next find 1:00 PM · Next fly 3:30 PM    [ Find now ] [ Fly now ]
```
- While running: Chirp pecks next to the step name, *"Finding jobs…"*; buttons disabled.
- Laptop offline: *"Laptop offline · Fly now will start when it's back."*
- Paused: *"Chirp is resting 💤"* with a "Wake up" link.

### 3.2 Job detail
```
┌───────────────────────────────┐
│ ← Backend Engineer II          │
│   Mastercard · Pune · Hybrid   │
├───────────────────────────────┤
│ 92  Why it fits                │
│ FastAPI + LLM work, fintech    │
│ domain, 2–4 yrs asked          │
│                                │
│ Gaps                           │
│ Kafka mentioned (not in facts) │
│                                │
│ Resume changes                 │
│ Led with underwriting engine;  │
│ moved Docker up in skills      │
│                                │
│ Expected CTC   [ ₹20 LPA ✎ ]   │
│                                │
│ Open posting · Open resume PDF │
│ Read cover letter ▾            │
├───────────────────────────────┤
│ [ Let go ]     [ Ready to fly ]│
└───────────────────────────────┘
```

### 3.3 Hands (needs attention)
Grouped by what's needed, most useful first:
```
New questions (2)
  "What's your biggest weakness?"
  → Mastercard, Druva            [ Answer once ]

Quick apply (3)
  Deutsche Bank · SuccessFactors [ Open ]

Blocked (1)
  Barclays · captcha             [ Try again ]
```
Answering a new question shows a text box, a "Save to answer bank" toggle (on by default), and releases every job waiting on it.

### 3.4 Quick apply
One screen with everything to copy into a hard portal:
```
Deutsche Bank · Backend Developer
[ Open application ↗ ]

Resume PDF           [ Download ]
Cover letter         [ Copy ]
Notice period        15 days   [ Copy ]
Expected CTC         20 LPA    [ Copy ]
Why this company?    …         [ Copy ]
…

[ I've applied ✓ ]
```

### 3.5 Flown
Applied history, newest first. Each row: company, role, date, and a "Got a callback?" toggle. This powers your callback-rate metric.

**Tap any application** to open it: an **Open application** button (the posting you applied to), the resume sent, expected CTC given, every answer submitted, the cover letter, and the callback toggle. Useful right before an interview.

Includes jobs Chirp never touched — applied to by hand and marked from the "Tailor an
external job" screen, or detected from a Gmail application-confirmation email. These rows
skip whatever doesn't apply (expected CTC, submitted answers) and their row says "applied by
you" instead of naming a posting Chirp found.

### 3.4b Tailor an external job (under More)
For a job found outside Chirp entirely — LinkedIn, Naukri, a referral, a company's own
careers page — that Chirp could never auto-apply to anyway. Paste company, title, location,
and the job description; get back a tailored resume PDF and cover letter through the same
tailoring and fabrication check as every other job, just without a fit-score gate (you already
decided to apply). Nothing is saved until you tap **I've applied**, which logs it to Flown.

### 3.6 More
- **Answers:** search, filter by category, tap to edit
- **Companies:** candidates to approve at the top; active list with priority pill, tier, pin; "Add company" field for a careers URL
- **Schedule:** time chips for Find and Fly (tap × to remove, "+ Add time" to add), weekday toggles, and a "Chirp is resting" pause switch
- **Settings:** CTC tiers, fit threshold, daily cap, match thresholds

---

## 4. Copy guide

- Plain, friendly, short. Sentence case.
- One button name per action, everywhere: **Ready to fly** (approve), **Let go** (reject), **Answer once**, **I've applied**, **Try again**.
- Errors say what happened and what to do: *"Couldn't reach the database. Check your connection and tap Refresh."*
- No exclamation marks except the approve toast.

---

## 5. HTMX interactions

| Action | Swap |
|---|---|
| Bulk approve or reject | Removes rows, updates header counts, shows toast |
| Edit CTC | Inline field replaces the value; saves on blur |
| Answer once | Question card collapses; Hands badge updates |
| Refresh | Re-renders the queue list only |
