# WoundScope

**Automated Medicare Part B wound-care billing eligibility for skilled nursing facilities.**

WoundScope reads a facility's patient records — insurance, diagnoses, and messy
free-text nurse notes — and tells a biller **which wound patients can be billed to
Medicare Part B, and why.** Every decision is explained, backed by the original source
text, and shown in a clean dashboard.

> Built for the Pulse Foundry × ABI Frameworks healthcare-data hackathon.
> Runs on **synthetic** patient data — no real PHI.

---

## New here? Start with this.

```bash
# 1. install (Python 3.11+)
pip install -r requirements.txt

# 2. pull the data + run the analysis  (≈ a few minutes; survives the API's 30% failures)
python run.py all

# 3. open the dashboard
python -m uvicorn api:app --port 8000     # → http://localhost:8000
```

Open **http://localhost:8000**, click any patient, and you'll see the whole story:
the decision, the rules it passed/failed, and the exact note text behind each value.
The pitch deck is at **/slides.html**.

*(If `python` isn't 3.11+, use `python3.13` — the code uses modern type syntax.)*

---

## The problem (in one paragraph)

A facility can bill Medicare Part B when it treats a wound — but only if the patient
has **(1)** an active wound, **(2)** active Part B coverage, and **(3)** proper
documentation (length, width, depth + drainage). That information is scattered across
coverage records, diagnosis codes, and inconsistent nurse notes, so today a biller
checks every patient by hand. WoundScope automates the collection and triage.

## How it works (the pipeline)

```
PointClickCare API  →  Collect  →  Read  →  Decide  →  Show
 (30% rate-limited)    (SQLite)   (extract) (route)   (dashboard)
```

1. **Collect** (`woundscope/ingest.py`, `api_client.py`) — pulls every record,
   retrying through the API's 30% random failures, with a backfill pass so **no
   patient is dropped**. Stores raw data in a local SQLite file.
2. **Read** (`woundscope/extract.py`, `note_templates.py`, `clinical.py`) — extracts
   wound type, location, measurements, and drainage from the 4 real note formats and 2
   assessment formats; handles multiple wounds per note; repairs garbled text; backfills
   wound type from the diagnosis code. Keeps an **evidence snippet** for every value.
3. **Decide** (`woundscope/route.py`) — checks the three Part B rules and routes each
   patient to **auto-accept / flag-for-review / reject**, with a plain-English reason
   and a confidence score.
4. **Show** (`api.py`, `web/`) — a dashboard with a review queue and a per-patient
   evaluation log, evidence, multi-wound breakdown, and a billed/dismissed workflow.

## The three decisions

| Decision | Meaning |
|---|---|
| **Auto-Accept** | Has Part B + at least one fully-documented wound → ready to bill. |
| **Flag for Review** | Eligible, but documentation is incomplete or ambiguous → a human checks. |
| **Reject** | Not billable — no active wound, wrong insurance, or unreliable data. |

On 300 synthetic patients: **135 auto-accept · 10 review · 155 reject**, 0 records
dropped, wound depth recovered for 285/300.

---

## Repo map

```
api.py              FastAPI backend: serves the results API + the web dashboard
run.py              one-command runner: ingest → extract → route → CSV
requirements.txt    Python dependencies

woundscope/         the pipeline (importable package)
  api_client.py     resilient PointClickCare client (retry/backoff, ID resolution)
  ingest.py         concurrent ingestion + completeness backfill → SQLite
  db.py             SQLite schema
  note_templates.py parsers for the 4 real note formats + 2 assessment formats
  clinical.py       wound ICD-10 coverage, type inference, location/abbrev repair
  extract.py        merges sources into wounds (multi-wound clustering) + evidence
  route.py          eligibility rules → auto-accept / review / reject + reasoning
  pipeline.py       orchestrates extract → route → results table
  export.py         results → CSV for billers

web/                the dashboard (static front end)
  index.html, styles.css, app.js, favicon.svg, slides.html (pitch deck)
```

## Documentation index

| Doc | Read it for |
|---|---|
| **README.md** (this file) | Start here — what it is + how to run it |
| **OVERVIEW.md** | Plain-English explanation for non-technical readers |
| **TECHNICAL_AND_DEMO.md** | How each technical problem was solved + judge Q&A + demo script |
| **DESIGN.md** | Architecture, diagrams, guardrails, full edge-case list |
| **COMPLIANCE.md** | EHR / PHI / HIPAA posture |
| **UI_GUIDE.md** | What the dashboard does + a demo walkthrough |
| **MERGE.md** | Who built what (the team merge) |

## Tech stack

Python · FastAPI · SQLite · vanilla HTML/CSS/JavaScript · PointClickCare mock API.
No build step, dependency-light, runs locally.

## Built by

A four-person team — each owning the strongest piece, merged into one build:
resilient ingestion + note parsers, multi-wound extraction + evidence, full diagnosis
coverage + text repair, and confidence-gated routing + compliance + dashboard.
See **MERGE.md** for details.
