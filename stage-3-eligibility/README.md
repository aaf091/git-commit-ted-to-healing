# Stage 3, 4, 5 — Eligibility, Presentation, Dashboard

Built from scratch against your own Stage 1 (`patients`, `coverage`) and
Stage 2 (`wounds`) tables — no dependency on anyone else's code.

## Setup

Drop these files into the same folder as your Stage 1 (`storage.py`,
`config.py`) and Stage 2 (`extraction_storage.py`) files, alongside your
real `pcc_data.db`:

```
your-folder/
├── config.py              (yours, Stage 1)
├── storage.py               (yours, Stage 1)
├── extraction_storage.py     (yours, Stage 2)
├── pcc_data.db                 (yours, built by Stage 1 + 2)
│
├── eligibility.py                ← Stage 3
├── eligibility_storage.py         ← Stage 3
├── presentation.py                  ← Stage 4
├── export_dashboard_data.py          ← Stage 5 helper
└── dashboard.html                      ← Stage 5
```

## Run it

```bash
python3 eligibility.py       # Stage 3: routes every patient, prints + persists + CSV
python3 presentation.py       # Stage 4: plain-English summary for a biller
python3 export_dashboard_data.py  # Stage 5: refreshes dashboard_data.json
```

Then open `dashboard.html` in a browser and click **"Load data file"** to
load the fresh `dashboard_data.json` — the dashboard updates instantly with
your real patient population. (It ships with the 7-patient test scenario
pre-loaded so it's never blank on first open.)

## Stage 3 — `eligibility.py`

Produces one row per patient. Routing rule, in priority order:

1. **No active Medicare Part B coverage → `reject`.** Wrong payer is a hard
   stop regardless of wound documentation quality. Distinguishes a patient
   who never had Part B from one whose Part B *lapsed* — these get
   different, accurate wording (`has_lapsed_mcb` field) rather than a
   confusing "no active Part B... payer on file: MCB" contradiction.
2. **Active MCB, zero wounds extracted → `reject`.** Nothing to bill.
3. **Active MCB, at least one wound with every required field present
   (type, location, all 3 measurements, drainage) and not flagged by
   Stage 2 → `auto_accept`.** A patient can have several wounds; one
   clean, fully-documented wound is enough to bill on even if their other
   wounds are messier.
4. **Active MCB, has wound(s), but none meet that bar → `flag_for_review`.**

Every decision carries a reason built from the actual data — payer name,
which fields are missing, the original Stage 2 flag note where relevant —
not a fixed template string.

Results land in a new `eligibility` table in the same `pcc_data.db`, and
export to `eligibility_output.csv`.

## Stage 4 — `presentation.py`

Turns Stage 3's table into what a biller reads first: total counts and
percentages per bucket, *why* people were rejected or flagged (broken down
by specific reason, not just a number), and a sorted worklist per bucket
(flagged patients sorted by fewest missing fields first, so the quickest
fixes surface at the top).

## Stage 5 — `dashboard.html`

A single self-contained HTML file (no server, no build step, no
dependencies) — open it directly in any browser:

- Stat cards: total / ready to bill / needs review / doesn't qualify
- Filter by decision, facility, or free-text search (name or patient ID)
- Sortable columns
- Click any patient to see full reasoning + wound detail in a side panel
- "Load data file" button to swap in a fresh `dashboard_data.json` without
  editing the HTML

## What was tested

A 7-patient scenario set was built covering every routing branch:
clean auto-accept, multiple wounds where all are flagged, multiple wounds
where one is clean (still auto-accepts), wrong payer, zero wounds,
**lapsed** Part B coverage (caught and fixed a real bug here — the reason
text and category breakdown initially mislabeled "lapsed" patients as
"wrong payer: MCB", which is self-contradictory), and a single flagged
wound.

The dashboard itself was tested headlessly with jsdom, not just visually:
verified stat cards compute correctly, all 7 rows render, clicking a row
populates the detail panel, decision/facility/search filters work
individually and combined, and column sorting works — all assertions
passed with zero JS errors.