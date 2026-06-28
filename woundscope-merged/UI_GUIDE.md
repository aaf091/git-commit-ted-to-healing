# WoundScope UI — What It Does & How to Demo It

The dashboard is the biller-facing front end. It turns 300 patients of messy EHR
data into a clean work list with a defensible, audit-ready decision for each one.

Run it: `python3.13 -m uvicorn api:app --port 8000` → open **http://localhost:8000**

---

## Built-in guidance (no manual needed)

The UI explains itself:
- A **3-step onboarding strip** at the top ("Filter → Click a patient → Read the log
  & evidence"), dismissible (remembered per browser).
- A **"? How it works"** button (top bar) opens a panel explaining the three
  decisions, how to read the evaluation log, and the privacy posture.
- The **empty detail panel** shows numbered steps until a patient is selected.
- Tooltips on the PHI toggle, confidence bars, and filters.

---

## What's on the screen (top to bottom)

**1. Header.** ABI logo + "WoundScope", a live count with a pulsing dot ("X live"),
a **🔒 PHI toggle**, and **Export CSV**.

**2. HIPAA banner.** States the privacy posture: PHI minimized by default,
processed locally, every decision audit-logged, synthetic data in the demo.

**3. KPI cards (the 5-second read for a billing manager):**
- **Patients evaluated** — total processed
- **Auto-Accept** — clean to bill
- **Flag for Review** — needs a human
- **Reject** — not Part B billable
- **Medicare Part B %** — how much of the population is even eligible (e.g. 48%)

**4. Toolbar (filters):** search by name/ID, decision chips (toggle each on/off),
facility, **status** (open/billed/dismissed), and a **min-confidence** slider.

**5. Review queue (left).** One row per patient: name, ID, wound type/stage, a
**confidence bar**, a **decision pill**, a **"2 wounds" badge** when relevant, and
a status tag once a biller acts. Click any row to open it.

**6. Detail panel (right) — the heart of the product:**
- **Eligibility evaluation log** — the decision shown step-by-step with ✓/✕:
  active wound → active Part B → reliably extracted → complete measurements →
  drainage → confidence threshold. *This is the "show your work" view.*
- **Plain-English reason** for the decision.
- **Wound measurements** — Length / Width / Depth chips; anything missing turns
  **red** so the gap is obvious at a glance.
- **Wounds detected (N)** — when a note documents two wounds, each is listed with
  "bill separately."
- **Biller action** — mark the patient **Open / Billed / Dismissed** (persists; the
  "billed" count updates live).
- **Evidence** — the actual source sentence behind each extracted value.
- **Provenance** — which record each field came from (assessment / note / diagnosis).

---

## What the UI is really doing (in one line)

It makes every automated billing decision **transparent and verifiable** — a biller
can see *what* was decided, *why*, *from which source text*, and then *act on it* —
so they trust it and work only the exceptions.

---

## How to give the demo (~6–8 minutes)

**0. Setup (before you talk):** make sure the data is loaded
(`python3.13 run.py all`) and the server is running. Open
**http://localhost:8000**. Keep PHI masked to start.

**1. The hook (30 sec).** "Billers waste hours figuring out which wound patients
can be billed under Medicare Part B — the data is scattered across coverage
records, diagnoses, and messy nurse notes. WoundScope reads all of it and routes
every patient, with the reasoning and the raw evidence behind each call."

**2. The numbers (30 sec).** Point at the KPI row: "300 patients processed
automatically. Only 48% even have Part B. The tool sorted them into bill / review /
skip — so the biller works the **review** pile, not all 300."

**3. An Auto-Accept (90 sec).** Click the **Auto-Accept** chip, open a clean one
(e.g. **FA-003** or **FA-009's** counterpart with full data). Walk the **evaluation
log** top to bottom — every check is green. Show the **measurement chips** (all
present) and scroll to **Evidence**: "here's the exact line in the record this came
from — nothing is a black box."

**4. A Flag-for-Review (90 sec).** Filter to **Flag for Review**, open one that's
**missing depth** — show the red Depth chip and the failed step in the log. "It's
eligible on diagnosis and Part B, but the depth wasn't documented, so instead of
risking a bad Medicare claim, it routes to a human."

**5. The standout — a multi-wound patient (60 sec).** Open **FA-009**. "This note
documents **two** wounds — a diabetic foot ulcer *and* an ankle wound. A naïve tool
bills the first and silently misses the second. We detect both and flag it so each
wound gets billed." Show the "2 wounds" list.

**6. A Reject (30 sec).** Filter to **Reject**, open one on an **HMO** — the log
shows the Part B check failing. "Correctly not billable, and it tells you why."

**7. Act + trust (45 sec).** On any reviewed patient, click **Mark billed** — the
billed count updates. Toggle **🔒 PHI** to show names hide/reveal: "PHI is masked by
default — minimum-necessary access, in line with HIPAA." Click **Export CSV** for
the biller worklist.

**8. Close (20 sec).** "So: messy records in, a trustworthy work list out — every
decision explained, evidenced, and ready for a biller to act on."

---

## Demo cheat-sheet (patients to have ready)

| Show | Pick |
|---|---|
| Auto-Accept (clean) | filter Auto-Accept → top row (e.g. FA-003) |
| Flag — missing depth | filter Flag for Review → any with a red Depth chip |
| Multi-wound | **FA-009** |
| Reject — wrong payer | filter Reject → any (reason names HMO/Medicaid) |

**If something looks off:** filters stack (decision + facility + status + confidence)
— click all three decision chips back on and clear the status filter to see
everyone again.
