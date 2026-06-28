# ABI Wound-Care Eligibility Radar

A data pipeline that identifies which post-acute patients qualify for **Medicare
Part B wound-care billing** — by ingesting the PointClickCare mock API, extracting
wound details from free-text notes + structured assessments, and routing each
patient to **auto_accept / flag_for_review / reject** with plain-English,
evidence-backed reasoning a biller can act on.

> Built for the ABI Frameworks Hackathon. API: `https://hackathon.prod.pulsefoundry.ai`

---

## What it does (the pipeline)

```
PointClickCare API ──▶ Extraction ──▶ Eligibility rules ──▶ Routing + reasoning ──▶ Biller dashboard
(429-resilient)      (notes + raw_json)  (wound+PartB+docs)   (auto/review/reject)    (evidence-backed)
```

1. **Ingestion** ([pcc_client.py](backend/app/services/pcc_client.py)) — fetches
   patients, diagnoses, coverage, notes, assessments. The API returns HTTP 429 on
   ~30% of calls; every request **retries with backoff honoring `Retry-After`**, so
   a sync never loses data — it just absorbs the rate-limits (the UI shows how many).
2. **Extraction** ([extraction.py](backend/app/services/extraction.py)) — pulls wound
   type, stage, location, **length/width/depth (cm)**, drainage amount + type from
   three source shapes in order of trust: structured assessment fields → assessment
   narrative → free-text notes (Envive prose *and* terse SPN). Every field records
   **where it came from**.
3. **Eligibility + routing** ([eligibility.py](backend/app/services/eligibility.py)) —
   joins coverage + diagnoses + extracted wound and decides:
   - **auto_accept** — active wound + active Part B + complete L×W×D + drainage. Submit.
   - **flag_for_review** — eligible but documentation incomplete/ambiguous. Human check.
   - **reject** — not billable (no wound, no Part B, or nothing extractable).
   Each decision carries explicit **pass/fail criteria** and a plain-English summary.
4. **Dashboard** (React) — routing queue, eligibility table, and a **biller detail
   panel** that traces every field back to the raw note/assessment/coverage/diagnosis.
5. **AI layer** (optional) — drafts a biller-friendly narrative; deterministic
   reasoning stays the source of truth, and it falls back to a template with no API key.

---

## Run it (2 terminals)

**Backend**
```bash
cd backend
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```
API docs: http://localhost:8000/docs

**Frontend**
```bash
cd frontend
npm install
npm run dev          # http://localhost:5173  (proxies /api -> :8000)
```

Open the app → pick a facility → **Run sync** → review the routing queue.

---

## The demo story (for a non-technical biller)

1. **"Messy EHR data in."** Click sync — it pulls from PointClickCare, retrying
   through the API's rate-limiting (watch the "429s absorbed" counter).
2. **"Clean decisions out."** Cards: patients, **auto-accept / flag / reject**,
   % Medicare Part B.
3. **"Work the exceptions first."** The queue defaults to *flag-for-review* — the
   patients that actually need a human. Filter by decision or facility.
4. **"Every decision is explained, not guessed."** Open a patient: the three
   criteria with ✓/✗, the extracted wound (missing depth shown in red), and the
   **raw note + assessment + coverage** the extraction came from.
5. **"Act and hand off."** Mark billed / dismiss; export the worklist to CSV for
   the billing team.

See [DEMO.md](DEMO.md) for the full 10-minute runbook + pitch.

---

## API reference (this app)

| Method | Path | Purpose |
|---|---|---|
| GET  | `/meta` | dashboard labels, facilities, decision definitions |
| POST | `/sync` | pull a facility (`facility_ids`, `limit`, `since`), extract, route, store |
| GET  | `/sync/status` | what's loaded + API call/429 stats |
| GET  | `/patients` | eligibility output table (one row per patient) |
| GET  | `/patients/{id}` | full biller detail + raw source data |
| GET  | `/eligibility` | routing queue (filter `decision`, `facility_id`, `status`, `min_confidence`) |
| GET  | `/eligibility/stats` | headline counts by decision / facility / status |
| GET  | `/eligibility/export.csv` | biller worklist CSV |
| POST | `/eligibility/{id}/status` | mark billed / dismissed / open |
| POST | `/eligibility/{id}/explain` | AI narrative for the decision |

---

## Design choices (defensible to judges)

- **Graceful failure first.** 429s are expected, not exceptional — the client
  retries with `Retry-After` backoff and reports the count instead of dropping data.
- **Extraction is multi-source with provenance.** Structured assessment fields win;
  free-text notes backfill gaps. Every value shows its source, so a biller can
  verify — and missing measurements are surfaced, not silently guessed.
- **Routing = exactly the three stated criteria.** Wound + Part B + measurements/
  drainage. Stage is captured for context but never blocks a clean claim.
- **Evidence over black-box AI.** The decision and reasoning are deterministic;
  the LLM only phrases them, and degrades to a template with no API key.
- **Config-driven.** Wound vocab, ICD-10 prefixes, payer codes, and routing live in
  one [config.py](backend/app/config.py).

## To enable the live AI narrative
```bash
export ANTHROPIC_API_KEY=sk-ant-...   # PowerShell: $env:ANTHROPIC_API_KEY="sk-ant-..."
```
Without it, the deterministic reasoning shows instead — the demo never breaks.

## Bonus implemented
- ✅ Incremental sync (`since` param threaded through patients/notes/assessments)
- ✅ LLM-assisted narrative (optional, bounded, with fallback)
- ✅ CSV export of the biller worklist
