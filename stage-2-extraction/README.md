# Stage 2 — Wound Data Extraction (rebuilt against real data)

**This version replaces an earlier draft that was built against the API
docs' example note format. Once tested against the real `pcc_data.db`, that
example format turned out not to occur in production data at all — see
"What changed and why" below.**

Reads `pcc_data.db` (produced by Stage 1) and extracts the 5 required wound
fields from every progress note and assessment, then groups them into
distinct wounds per patient.

## Run it

Drop these files into the same folder as your Stage 1 output (`pcc_data.db`,
`storage.py`, `config.py` must already be there), then:

```bash
python3 run_stage2.py
```

This adds two new tables to `pcc_data.db` — nothing in Stage 1's tables is
touched.

## What changed and why

The first version of this extractor assumed `note_type` indicated format
(`"Wound (SPN)"` = structured labeled fields, everything else = narrative
prose), based on the API documentation's example. Running it against the
real database showed **100% of "structured" notes flagged as missing every
measurement field** — the real text didn't match the documented
`Location:`/`Length:`/`Width:`/`Depth:` label format at all.

Inspecting real samples revealed the real API has **4 note_type values**
(`Wound (SPN)`, `Wound (IDT)`, `Wound Care Progress Note`, `HP Skin & Wound
Note`) that **do not correlate with text format at all** — each note_type
contains a mix of 4 actual prose templates:

1. **`envive`** — `"Wound Status: {type} to {location} / Measures {L} cm x
   {W} cm / Stage: {N or N/A}"` then `"Drainage present - {type}, {level}."`
   — structurally never reports depth.
2. **`soap`** — `Subjective:/Objective:/Assessment:/Plan:` sections with
   `"{type} {type repeated} {location} measures {L} cm x {W} cm x {D} cm"`
   and `Drainage: {level}.`
3. **`pt_seen`** — `"Pt seen for wound eval. {type} {location} measures
   aprx {L} x {W}cm, depth {D}cm."` — can describe **two distinct wounds
   in one note** (a second `"{location} wound also eval - ..."` clause).
4. **`shorthand`** — `"Wound note - {location}. Meas {L}x{W}x{D}cm.
   {level} {type} drainage..."` — never states a wound type explicitly.

The extractor now detects template by **structural signature in the text
itself**, ignoring `note_type` entirely, since `note_type` carries no
reliable format information in the real data.

## Files

| File | Role |
|---|---|
| `extraction.py` | Field-level parsers: structured `assessments.raw_json` (direct field mapping) + 4 real note templates (`envive`, `soap`, `pt_seen`, `shorthand`), detected by text signature |
| `extraction_storage.py` | Schema + upserts for `extracted_wounds` (audit trail) and `wounds` (one row per distinct wound) |
| `run_stage2.py` | Orchestrator — reads Stage 1's data, runs extraction, groups into wounds |

## Output schema

**`extracted_wounds`** — one row per wound mentioned in a note/assessment.
Most notes produce exactly one row; the `pt_seen` template can produce two
(distinguished by `wound_index`), since it sometimes documents two separate
wounds in a single note. Nothing is overwritten or dropped — every
extraction attempt is kept, keyed on `(source_table, source_record_id,
wound_index)`.

**`wounds`** — one row per distinct wound, derived by grouping a patient's
extractions by normalized `location` (the API has no wound ID field, so
location is the proxy: same location across records = same wound tracked
over time; different location = different wound). A patient with a left
foot ulcer and a left ankle wound — as seen directly in the real `pt_seen`
template — gets two rows here, not one blended row.

Each wound's displayed fields come from its single best contributing
record (ranked by confidence, then recency), with `best_source_table` /
`best_source_record_id` showing exactly which document they trace to.

## Design notes

**Laterality is preserved, not stripped.** "Right hip" and "Left hip" are
genuinely different wounds for a patient who has both — collapsing them to
a bare "hip" would silently merge two real wounds into one. Location
normalization canonicalizes the body-part word (hip/hips → hip, plantar →
plantar foot) and the laterality spelling (R/Right → right) but keeps them
combined: `"R hip"` and `"Right hip"` match as the same wound; `"Right
hip"` and `"Left hip"` do not.

**Clinical abbreviations are recognized for drainage.** Real notes use
`"Min"`, `"Mod"`, `"slight"` as shorthand for minimal/moderate/light —
these are mapped to the canonical 4-level scale with word-boundary
matching (not bare substring checks) to avoid false positives from short
abbreviations matching inside unrelated words.

**The `envive` template structurally never reports depth.** Rather than
treating a missing depth as a parse failure, the extractor flags it as a
template limitation — `"depth (not reported in this note template)"` — so
downstream consumers understand this is a property of the documentation
style, not a hole in the extraction logic.

**The `pt_seen` template's second wound doesn't restate wound type.** When
a note covers two wounds, the second mention is terse and doesn't repeat
the clinical wound type — the extractor leaves `wound_type=None` rather
than guessing it matches the first wound, and flags this explicitly.

**`shorthand` notes never state a wound type at all** — every one of these
falls back to the patient's active ICD-10 diagnosis description, flagged
as `diagnosis_fallback` so it's clear the value didn't come from the note
itself.

**Unknown future formats are never silently dropped.** If a note's text
doesn't match any of the 4 known template signatures, it's stored with
`source_type="unrecognized_template"` and flagged for manual review rather
than being skipped or guessed at.

**Billing scope.** This stage extracts clinical wound characteristics only.
No service/procedure/CPT-level data exists anywhere in the API, so no
per-service billing structure is built — that would be invented on top of
the dataset, not extracted from it. `treatment_note` (where present, e.g.
the `envive` template's `Treatment:` field) is kept as descriptive context
only, never as a billing line item.

## What was tested

Built and verified against the **actual 4 real note templates** (11 sample
notes spanning all 4 templates and all 4 `note_type` values, assembled into
a synthetic test database matching the real schema):

- All 4 templates parse correctly, including laterality preservation
  (`"Right hip"`, `"Left foot"`, `"Right plantar foot"`, etc.) and clinical
  abbreviation recognition (`"Min"` → light, `"Mod"` → moderate).
- The `pt_seen` template's two-wounds-in-one-note case correctly produces 2
  wound records, not 1 (verified: patient with `"Diabetic Left foot"` +
  `"Heel wound also eval - L ankle"` correctly yields 2 separate wounds:
  `left foot` and `left ankle`).
- `envive` template's structural depth gap is correctly flagged as a
  template limitation rather than a parse failure.
- `shorthand` template's missing wound type correctly falls back to the
  diagnosis record with an honest flag.
- Storage layer correctly handles multi-wound notes via the
  `(source_table, source_record_id, wound_index)` composite key — no
  primary-key collisions, no data loss.

**Caught and fixed during this rebuild** (the value of testing against real
data instead of the documented example):
1. The documented `Location:`/`Length:`/`Width:`/`Depth:` label format does
   not occur in the real dataset at all — `note_type` carries no format
   signal; all 4 real templates were reverse-engineered from actual samples.
2. Initial location matching dropped laterality ("Right hip" → "hip"),
   which would have silently merged genuinely distinct bilateral wounds.
3. Clinical abbreviations ("Min", "Mod") weren't recognized, causing
   correctly-present drainage data to register as missing.