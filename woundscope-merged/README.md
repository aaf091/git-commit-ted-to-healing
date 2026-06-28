# 🩹 WoundScope

**Automated Medicare Part B wound-care billing eligibility for post-acute care.**

WoundScope ingests fragmented EHR data from a mock PointClickCare API, extracts
wound details from messy multi-format clinical notes, and routes every patient
into one of three billing decisions — **auto-accept**, **flag for review**, or
**reject** — each with a plain-English reason and full provenance a billing
specialist can trust.

Built for the Pulse Foundry × ABI Frameworks Healthcare Data Hackathon.

---

## The problem

A post-acute care company can separately bill Medicare **Part B** for wound care
only when three things are true:

1. an **active wound** diagnosis (pressure ulcer, diabetic foot ulcer, venous ulcer, …)
2. **active Medicare Part B** coverage
3. **documented wound measurements** (length, width, depth) **and drainage**

That evidence is scattered across five API endpoints, two patient-ID systems, and
clinical notes written in inconsistent formats — and the source API fails 30% of
requests. WoundScope automates the whole judgment.

## Architecture

```
 PointClickCare mock API (5 endpoints, 30% rate-limited)
        │   resilient client: exp backoff + jitter, honors Retry-After
        ▼
 Ingestion  ──►  SQLite (raw payloads stored verbatim)
        │        resolves patient_id "FA-001"  →  internal id 1
        ▼
 Extraction engine  (tiered by reliability, with provenance + confidence)
   Tier 0  diagnosis ICD-10      → authoritative wound type + stage
   Tier 1  assessment raw_json   → structured numeric fields
   Tier 2  labeled note fields   → Length:/Width:/Depth:
   Tier 3  free-text prose       → "8.0x3.5x0.2cm", "Venous to R lower leg"
        ▼
 Routing engine  → auto_accept / flag_for_review / reject  + reasoning
        ▼
 Output: results table  ·  CSV  ·  Streamlit dashboard
```

## What makes it robust (the three differentiators)

1. **Provenance + confidence on every field.** Each extracted value records
   *which source* it came from and how reliable that source is. Billing staff see
   exactly why a decision was made — not a black box. This confidence score is
   what separates auto-accept from flag-for-review.
2. **Complete data despite a 30% failure rate.** The client retries with
   exponential backoff + jitter and respects `Retry-After`, so the pipeline never
   produces partial records. (Typical run: hundreds of 429s, **zero** dropped.)
3. **Handles every note format.** The real `raw_json` is *not* the clean schema
   the docs show — wound data hides in free-text "Wound narrative" answers. The
   tiered extractor parses structured fields, labeled fields, and prose, and
   backfills authoritative type/stage from the ICD-10 diagnosis.

## Routing logic

| Decision | When |
|----------|------|
| `auto_accept` | active wound dx **+** active Part B **+** complete L/W/D **+** drainage **+** confidence ≥ 0.75 **+** single wound |
| `flag_for_review` | eligible on dx + Part B, but a measurement is missing, drainage absent, multiple wounds, or confidence below threshold |
| `reject` | no active wound, no active Part B, or extraction too unreliable to bill |

## Quick start

```bash
pip install -r requirements.txt

python run.py all            # ingest all 300 patients → extract → route → CSV
# or, for a fast demo:
python run.py all 15

python api.py                # ABI-style web console at http://localhost:8000
```

Individual stages:

```bash
python run.py ingest         # API → SQLite  (concurrent, retry-safe)
python run.py process        # SQLite → results  (re-runnable, no API)
python run.py export         # results → wound_billing_review.csv
```

## Project layout

```
woundscope/
  api_client.py   resilient PCC client (retry/backoff, ID resolution)
  ingest.py       concurrent ingestion + retry + completeness backfill → SQLite
  extract.py      tiered wound-data extraction (provenance + confidence)
  route.py        eligibility + 3-way routing with reasoning
  pipeline.py     orchestrates extract → route → results table
  export.py       CSV for billing staff
  db.py           SQLite schema
api.py            FastAPI backend + serves the web console
web/              ABI-style frontend (index.html, styles.css, app.js)
run.py            end-to-end runner
```

See **DESIGN.md** (architecture, diagrams, guardrails, edge cases) and
**COMPLIANCE.md** (EHR / PHI / HIPAA posture).

## Output

`wound_billing_review.csv` — one row per patient: extracted wound fields,
Part B status, decision, confidence, and reasoning, sorted with auto-accepts
first. The dashboard adds filtering and a per-patient provenance view.

## Notes & next steps

- **LLM tier:** the extractor interface is built so an LLM pass can be slotted in
  for the messiest Envive prose, with schema validation + fallback to
  flag-for-review on low model confidence.
- **Incremental sync:** the client already supports the `since` parameter for
  delta loads.
