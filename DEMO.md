# Demo Runbook & Pitch — ABI Ops Radar

Everything you say and click during the judging window. Practice it once end-to-end.

---

## 0. Before you present (60 sec of setup)

Two terminals, both already running:

```bash
# Terminal 1 — backend
cd backend && python -m uvicorn main:app --port 8000

# Terminal 2 — frontend
cd frontend && npm run dev          # http://localhost:5173
```

- Open **http://localhost:5173** on the empty upload screen.
- (Optional) `export ANTHROPIC_API_KEY=sk-ant-...` in Terminal 1 *before* starting
  uvicorn if you want the live AI suggestion instead of the templated fallback.
- Delete `backend/data/flag_status.json` if you want a clean slate (no prior resolves).

---

## 30-second pitch (say this first, before clicking)

> "Healthcare ops teams lose money and fail compliance because critical data is
> messy and the catching is manual. **ABI Ops Radar** takes messy patient data,
> structures it, and surfaces every revenue leak, compliance gap, and duplicate
> as a **prioritized, evidence-backed worklist** — so staff review the
> highest-confidence issues first, and never have to trust a black box.
> We built it config-driven, so it retargets to any data schema in minutes."

---

## The click-through (90 seconds, 5 beats)

| Beat | Click | Say |
|---|---|---|
| **1. Messy in** | **⚡ Load demo data** | "This is real-shape healthcare data — inconsistent casing, four date formats, duplicate patients, unbilled procedures, missing fields." |
| **2. Clean out** | (cards appear) | "Instantly structured. 94 records, ~140 issues, **$5,345 estimated recoverable**, 8 duplicate clusters — the numbers a manager cares about." |
| **3. Prioritized** | point at queue | "The queue is pre-sorted by severity then confidence. Staff work top-down — highest-impact first. Filter by revenue, compliance, duplicates." |
| **4. Evidence, not 'AI says so'** | click a **Missed billable event** | "Every flag shows the exact fields that triggered it — procedure code present, billed = N. A biller can act immediately. This is the trust layer." |
| **5. Act + AI** | click **✨ Suggest**, then **Resolve** | "Optional AI drafts a plain-English next action — but the deterministic evidence stays the source of truth. Reviewer resolves; the worklist updates live." |
| **Close** | **⤓ Export CSV** | "And the reviewed worklist exports straight to the billing team. Messy data in, money and compliance out." |

---

## If a judge asks "how is this not just a dashboard / ChatGPT wrapper?"

- **Deterministic core, explainable by construction.** Rules + fuzzy matching do
  the detection; every finding carries its triggering evidence and a confidence
  derived from rule certainty × evidence completeness — not a model's opinion.
- **The AI is assistive and bounded.** It only phrases and recommends; it's handed
  the evidence and told *not* to re-judge. Falls back to a deterministic template
  if there's no API key — zero hallucination risk in the core path.
- **Config-driven, not hardcoded.** Schema, rules, and matching weights live in
  one `config.py`. We proved it remaps to alternate column names live.

## If a judge asks "does it scale / is it real?"

- Dedupe **blocks before scoring** (first-initial + birth-year buckets), so it's
  not O(n²) over the whole dataset.
- Stateless API, config-driven pipeline — swap the in-memory store for Postgres
  and it's production-shaped.

---

## Backup plan if something breaks

- **Backend down** → the UI shows a red banner and auto-recovers; just restart uvicorn.
- **Frontend won't load data** → hit the API directly at http://localhost:8000/docs
  (Swagger) and run `/load-sample` → `/flagged-events` to show it working.
- **Live AI errors** → it silently falls back to the templated suggestion; the demo
  is unaffected.

---

## One-liner to leave them with

> "We didn't build one solution — we built the **infrastructure** that turns any
> messy ABI-style healthcare problem into a reviewable, evidence-backed worklist."
