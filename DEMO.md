# Demo Runbook & Pitch — ABI Wound-Care Eligibility Radar

~10-minute presentation: pipeline architecture → output table → example routing
decisions, framed for a non-technical biller.

---

## 0. Before you present

```bash
# Terminal 1 — backend
cd backend && python -m uvicorn main:app --port 8000
# Terminal 2 — frontend
cd frontend && npm run dev          # http://localhost:5173
```

- Open **http://localhost:5173** (the sync screen).
- (Optional) `export ANTHROPIC_API_KEY=sk-ant-...` in Terminal 1 *before* uvicorn
  to get the live AI narrative; otherwise it shows the deterministic fallback.
- Decide your sync size: **30 patients = fast** (good for the live click). Bump to
  100 / multiple facilities if you want volume on screen.

---

## 30-second pitch (say this first)

> "Post-acute billers waste hours figuring out which wound patients can be billed
> under Medicare Part B — the data is spread across coverage records, ICD-10
> diagnoses, and messy free-text nurse notes. **Our pipeline pulls it all from
> PointClickCare, extracts the wound details, and routes every patient to
> auto-accept, flag-for-review, or reject — with the exact reasoning and the raw
> evidence behind it.** A biller works the flagged exceptions first and trusts
> every decision, because nothing is a black box."

---

## Pipeline architecture (30 sec — say while on the sync screen)

> "Five stages: **ingest** from the API with retry logic for its 30% rate-limiting;
> **extract** wound fields from both structured assessments and free-text notes;
> apply the **eligibility rules** — active wound, active Part B, complete
> measurements and drainage; **route**; and present it all with evidence. It's
> config-driven, so the rules and vocabulary live in one file."

---

## The click-through (5 beats)

| Beat | Click | Say |
|---|---|---|
| **1. Ingest** | pick **Facility A**, **Run sync** | "It's pulling patients, diagnoses, coverage, notes, assessments — and look, it absorbed **N rate-limits** by retrying. No data lost." |
| **2. Decisions out** | (cards) | "30 patients: **X auto-accept, Y flag, Z reject**, ~60% Medicare Part B — matching the real payer mix." |
| **3. Work exceptions** | queue (defaults to flag-for-review) | "We surface the patients that need a human first. Here's one flagged because depth wasn't documented." |
| **4. Explain + evidence** | click that patient | "Three criteria, ✓/✗. Part B active, wound diagnosis active, but **depth is missing** — shown in red. And here's the **actual nurse note** it extracted from. Nothing guessed." |
| **5. Act** | ✨ Explain for biller → **Mark billed** on an auto-accept | "Optional plain-English summary for staff. Biller bills it, status updates." |
| **Close** | **⤓ Export** | "And the whole worklist exports to CSV for the billing team." |

---

## Show one of each decision (the "example routing decisions" ask)

Click the **Reject / Flag / Auto-accept** filter and open one of each:
- **auto_accept** — "All three criteria met, complete L×W×D + drainage. Clean to bill."
- **flag_for_review** — "Eligible, but missing a measurement. One nurse note away from billable."
- **reject** — "Has a wound, but primary payer is HMO — not Part B. Can't bill this as Part B wound care."

---

## Judge Q&A — likely questions

- **"How do you handle the rate-limiting?"** → Every request retries with backoff
  honoring the `Retry-After` header; the sync reports how many 429s it absorbed.
  Per-patient fetches run concurrently so one patient's 429 doesn't stall the rest.
- **"How accurate is the extraction?"** → Multi-source with provenance: structured
  assessment fields first, free-text notes backfill. All four note styles handled
  (SPN, Progress Note, HP Skin & Wound, IDT). We don't hallucinate missing fields —
  we surface them as gaps, which is exactly what drives flag-for-review.
- **"What about patients with more than one wound?"** → Handled. We segment the note
  per measurement and cluster wound mentions by location/size across notes and
  assessments, so a sacral ulcer and a heel wound are both captured and shown; we
  route on the best-documented wound. (~30% of patients have two wounds — open one to
  show the wounds list.)
- **"Why these routing rules?"** → They're the three stated criteria: active wound,
  active Part B, documented measurements + drainage. We deliberately *don't* block a
  clean claim on a missing stage — stage is context, not a billing gate.
- **"Is the AI making the decision?"** → No. The decision and reasoning are
  deterministic and auditable; the LLM only rewrites it for a non-technical reader,
  and it falls back to a template with no API key. Zero hallucination in the routing.
- **"How would this scale / productionize?"** → Stateless API, config-driven rules,
  `since`-based incremental sync already wired. Swap the in-memory store for Postgres.

---

## Backup plan

- **Backend down** → red banner appears and auto-recovers; restart uvicorn.
- **Frontend issue** → drive it from http://localhost:8000/docs: `POST /sync` →
  `GET /eligibility` → `GET /patients/{id}` shows the whole pipeline working.
- **Live AI errors** → silently falls back to deterministic narrative; demo unaffected.

---

## One-liner to close

> "Messy EHR data in, billable Part B wound-care decisions out — every one
> explained, every one traceable to its source."
