# WoundScope — ABI Frameworks Hackathon

**Automated Medicare Part B wound-care billing eligibility for skilled nursing facilities.**

WoundScope reads a facility's patient records — insurance, diagnoses, and messy
free-text nurse notes — and tells a biller **which wound patients can be billed to
Medicare Part B, and why**, with the original evidence behind every decision and a
clean dashboard to act on.

> Built for the Pulse Foundry × ABI Frameworks healthcare-data hackathon.
> Runs on **synthetic** data — no real PHI.

---

## 👉 The project lives in [`woundscope-merged/`](./woundscope-merged)

That folder is the complete, runnable build. **Start with its
[README](./woundscope-merged/README.md).**

```bash
cd woundscope-merged
pip install -r requirements.txt
python run.py all                       # ingest → extract → route  (handles the API's 30% failures)
python -m uvicorn api:app --port 8000   # dashboard → http://localhost:8000  (deck at /slides.html)
```

## What it does (30 seconds)

1. **Collect** every patient record from the PointClickCare API, surviving its 30%
   random failures (zero records dropped).
2. **Read** wound details out of 4 real note formats + structured assessments
   (multi-wound aware, with text repair).
3. **Decide** per patient — **auto-accept / flag-for-review / reject** — against the
   three Part B rules, with a reason and confidence.
4. **Show** it in a dashboard: a review queue + a per-patient evaluation log, the
   exact source evidence, and a biller workflow.

Result on 300 synthetic patients: **135 auto-accept · 10 review · 155 reject.**

## Documentation (all inside `woundscope-merged/`)

| Doc | For |
|---|---|
| `README.md` | Getting started + repo map |
| `OVERVIEW.md` | Plain-English explanation (non-technical) |
| `TECHNICAL_AND_DEMO.md` | How each problem was solved + judge Q&A + demo script |
| `DESIGN.md` | Architecture, diagrams, edge cases |
| `COMPLIANCE.md` | EHR / PHI / HIPAA posture |
| `UI_GUIDE.md` | Dashboard walkthrough |
| `MERGE.md` | Who built what |

## Branches

`main` holds the integrated build. Each teammate's original work is preserved on their
own branch (`aadit`, `aishwarya`, `jayudoshi`, `om-merged-abi`).
