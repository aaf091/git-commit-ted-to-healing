# ABI Ops Radar — Hackathon Starter Kit

A reusable framework for **ABI-style healthcare-ops problems**: messy data in →
clean, structured, **evidence-backed** issues out, in a review dashboard.

> **Mindset:** don't predict the exact problem — predict its *shape*. The shape
> is always: healthcare data is messy, manual workflows miss money / compliance /
> action items, and you need a reliable automation layer **with evidence**.

This kit ships the plumbing so you spend kickoff hours on the *actual* problem,
not on `/upload` boilerplate.

---

## What's in the box

```
healthAi/
├─ backend/                  FastAPI + pandas + RapidFuzz
│  ├─ app/
│  │  ├─ config.py           ⭐ THE FILE YOU EDIT AT KICKOFF (schema, rules, matching, labels)
│  │  ├─ store.py            in-memory dataset store
│  │  ├─ schemas.py          API response models
│  │  ├─ services/
│  │  │  ├─ ingestion.py     CSV/JSON read + column auto-mapping
│  │  │  ├─ cleaning.py      normalize dates / phones / numbers / text
│  │  │  ├─ matching.py      RapidFuzz blocking + weighted scoring + clustering
│  │  │  ├─ rules_engine.py  declarative, sandboxed rule evaluation
│  │  │  └─ flagging.py      unified issue queue + stats
│  │  └─ routers/            /upload /patients /dedupe /rules /flagged-events
│  ├─ generate_data.py       synthetic MESSY dataset generator
│  └─ requirements.txt
└─ frontend/                 React + Vite + Tailwind
   └─ src/
      ├─ api.js              one thin API client
      ├─ App.jsx             shell: header, stat cards, tabs
      └─ components/         UploadPanel, StatCards, IssueQueue, DataTable, PatientDetail (+evidence)
```

---

## Run it (2 terminals)

**Backend**
```bash
cd backend
python -m pip install -r requirements.txt
python generate_data.py            # writes data/synthetic_patients.csv
python -m uvicorn main:app --reload --port 8000
```
API docs: http://localhost:8000/docs

**Frontend**
```bash
cd frontend
npm install
npm run dev                        # http://localhost:5173  (proxies /api -> :8000)
```

Then open the app → upload `backend/data/synthetic_patients.csv` → review the queue.

---

## The demo story (90 seconds)

1. **"Messy healthcare data goes in."** Drag in the CSV — inconsistent casing,
   four date formats, duplicate patients, missing fields, unbilled procedures.
2. **"Clean, structured insights come out."** Stat cards: records, issues,
   high-severity, duplicate clusters, **estimated $ recoverable**.
3. **"Staff review high-confidence issues first."** The queue is pre-sorted by
   severity then confidence. Every item is filterable.
4. **"And they trust it, because every flag shows its evidence."** Click any
   issue → the record + the exact fields that triggered it. No black box.

---

## ⚡ Kickoff playbook — map the problem, then edit these knobs

When the real problem + data drop, do this in order:

### 1. Map the problem to a pattern
| If the problem is about…            | Lean on…                          |
|-------------------------------------|-----------------------------------|
| Fragmented / messy patient data     | `ingestion.py` + `cleaning.py`    |
| Eligibility / billing / compliance  | `config.RULES` + `rules_engine.py`|
| Duplicate records / entity matching | `config.MATCH_CONFIG` + `matching.py` |
| Missed billable events / gaps       | `config.RULES` (revenue category) |

The dashboard (queue + detail + evidence) works for **all** of them unchanged.

### 2. Edit `backend/app/config.py` — almost everything lives here
- **`SCHEMA`** — point canonical fields at the real column names (list several
  candidates; first match wins). Run `/upload` and watch `unmapped_columns` in
  the UI to catch fields you missed.
- **`REQUIRED_FIELDS / DATE_FIELDS / NUMERIC_FIELDS`** — so cleaning normalizes
  the right columns.
- **`RULES`** — add/remove rules as plain data. Each `expr` is evaluated per row
  with helpers: `has() missing() missing_any([]) truthy() norm() num()`.
  Example new rule:
  ```python
  {"id": "high_dollar_unbilled", "label": "High-value unbilled claim",
   "category": "revenue", "severity": "high",
   "expr": "num(charge_amount) > 1000 and not truthy(billed)",
   "explain": "A claim over $1,000 was never billed.",
   "evidence_fields": ["charge_amount", "billed", "procedure_code"]}
  ```
- **`MATCH_CONFIG`** — tune `weights`, `blocking_fields`, and the
  match/review thresholds for the entity you're deduping.
- **`DASHBOARD`** — relabel the UI (app name, tagline, nouns) for the problem.

### 3. (If the schema is very different) the data table & detail auto-adapt
Both render whatever canonical fields exist — no edits needed for new columns.

### 4. Swap the demo dataset
Replace `generate_data.py` (or just upload the provided data). Keep the
generator around to fabricate edge cases the judges' data might not show.

---

## API reference

| Method | Path                      | Purpose                                   |
|--------|---------------------------|-------------------------------------------|
| GET    | `/meta`                   | dashboard labels, schema fields, rule list|
| POST   | `/upload`                 | ingest CSV/JSON, returns mapping + preview|
| GET    | `/patients`               | list cleaned records (data table)         |
| GET    | `/patients/{row_id}`      | one record + its flags (detail/evidence)  |
| POST   | `/dedupe`                 | run fuzzy matching → duplicate clusters   |
| GET    | `/rules`                  | configured rules                          |
| POST   | `/rules/evaluate`         | run only the rules engine                 |
| POST   | `/flagged-events/run`     | run full pipeline (rules + dedupe), cache |
| GET    | `/flagged-events`         | unified issue queue (filterable)          |
| GET    | `/flagged-events/stats`   | headline numbers for the cards            |
| POST   | `/flagged-events/{id}/status`  | resolve / dismiss / confirm / reopen a flag |
| POST   | `/flagged-events/{id}/explain` | AI-drafted explanation + suggested action |

Filters on `/flagged-events`: `severity`, `category`, `type`, `status`, `min_confidence`.

### Review workflow (resolve / dismiss / confirm)

The queue is a real worklist, not just a list. Each flag carries a `status`
(`open` → `resolved` / `dismissed` / `confirmed`), set via the detail panel.
Statuses persist to `backend/data/flag_status.json` keyed by the deterministic
`flag_id`, so a reviewer's decisions survive a backend restart. The dashboard
defaults to showing **open** issues and the stat cards track cleared vs. total.

### AI layer (assistive, evidence stays source-of-truth)

`POST /flagged-events/{id}/explain` runs **claude-haiku-4-5** to draft a
plain-English explanation + one concrete next action for a flag. Key design
choice: the LLM is given the deterministic rule result and its evidence and is
told *not* to re-judge — it only phrases and recommends. The UI labels it
clearly as an AI suggestion, separate from the evidence panel.

**It degrades gracefully:** with no `ANTHROPIC_API_KEY` set (or any API error),
it returns a deterministic templated next-action instead, so the demo never
depends on a network call. To enable the real model:

```bash
# backend terminal, before starting uvicorn
export ANTHROPIC_API_KEY=sk-ant-...   # PowerShell: $env:ANTHROPIC_API_KEY="sk-ant-..."
```

Edit the `MODEL` constant or `SYSTEM` prompt in
[backend/app/services/ai.py](backend/app/services/ai.py) to retune at kickoff.

---

## Design choices (so you can defend them to judges)

- **Config-driven, not hardcoded.** Schema, rules, and matching are data — you
  adapt to the real problem by editing config, not rewriting logic.
- **Evidence over black-box AI.** Every flag carries the exact fields that
  triggered it. Confidence is explainable (rule certainty × evidence completeness),
  not a mystery score. Healthcare reviewers won't trust "AI says so."
- **Blocking before scoring.** Dedupe blocks on a coarse key first, so it scales
  past tiny demo datasets instead of going O(n²) over everything.
- **In-memory store on purpose.** Zero setup for a hackathon. Swap for SQLite if
  you genuinely need persistence — only `store.py` changes.

---

## Stretch ideas if you have time

- Export the reviewed queue to CSV (the closing-demo "here's the worklist" moment).
- Side-by-side merge UI for duplicate clusters.
- Per-user review assignment / audit trail on status changes.
- Swap the in-memory store for SQLite if you need durable history beyond statuses.

Already built: ✅ resolve/dismiss/confirm workflow with persistence, ✅ AI
explanation+action layer (evidence stays source of truth).
