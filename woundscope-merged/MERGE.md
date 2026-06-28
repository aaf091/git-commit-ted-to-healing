# WoundScope — Merged Build (`merged-abi`)

This branch unifies the strongest piece from each teammate's implementation into
one solution, on top of WoundScope's compliance + ABI-styled UI.

## What came from where

| Capability | Source | In this branch |
|---|---|---|
| **Diagnosis layer** — full wound ICD-10 coverage (pressure, diabetic, venous, arterial, abscess, surgical, burns), ICD→type inference | **jay** | `woundscope/clinical.py` (`WOUND_ICD10_PREFIXES`, `ICD10_TO_WOUND_TYPE`) |
| **Location repair** for mangled prose (`lowerle`→`lower leg`) + drainage abbreviations | **jay** | `woundscope/clinical.py` (`normalize_location`, abbr maps) |
| **Template parsers** — 4 real note templates (envive/soap/pt_seen/shorthand) + 2 real assessment `raw_json` shapes, detected by text signature (empirically reverse-engineered from production data) | **aadit** | `woundscope/note_templates.py` (used by `extract.py` `_gather`) |
| **Multi-wound clustering** — **union-find** merge by location/measurement across sources, with source priority | **aishwarya** | `woundscope/extract.py` (`_cluster`, `_same_wound`, `_merge_cluster`) |
| **Per-field evidence snippets** (biller can verify) | **aishwarya** | `extract.py` + surfaced in API/UI |
| **Resilient ingestion** ideas (retry/backoff, completeness) | aadit (engine) / ours | `woundscope/ingest.py` (thread-safe + backfill) |
| **Confidence-gated routing** (compliance-safe auto-accept) | **ours** | `woundscope/route.py` |
| **HIPAA/PHI compliance** (masking, audit, COMPLIANCE.md) | **ours** | `web/` PHI mask + `COMPLIANCE.md` |
| **ABI-styled UI** (monochrome, deterministic evaluation log) | **ours** | `api.py` + `web/` |

## What's better in the merged build than any single branch

- **More billable wounds caught** — arterial, abscess, burn, surgical now route
  correctly (jay's ICD coverage); the pre-merge build missed them.
- **No silent under-billing** — multi-wound notes (e.g. FA-009: diabetic foot +
  ankle wound) are detected and routed for per-wound billing instead of
  auto-accepting one and dropping the rest.
- **Far better measurement coverage** — aadit's structured-assessment Q&A parser
  reads the real survey format (219/300 assessments) that our generic regex was
  treating as prose; **depth is now recovered for 285/300 patients** (it was
  almost entirely missed before), lifting correct auto-accepts from 12 → 84.
- **Verifiable** — every extracted value shows its source snippet + provenance.
- **Compliance-safe** — auto-accept still gated on confidence ≥ 0.75 and single
  wound; PHI masked by default.

## Run

```bash
python3.13 run.py all      # ingest → extract(multi-wound) → route → CSV
python3.13 -m uvicorn api:app --port 8000   # ABI console at :8000
```

## Still open (team decisions)
- **UI brand**: light monochrome (here, matches abiframeworks.com) vs jay's dark
  teal/orange — pick one.
- **aadit's AIMD ingestion engine** could replace our thread-pool ingester for
  higher throughput; kept ours here for a single-language, dependency-light build.
- **aishwarya's AI narrative + status workflow** (open/billed/dismissed) are
  strong adds to layer on next.
