# WoundScope — EHR / PHI / HIPAA Compliance Posture

WoundScope handles Protected Health Information (PHI) sourced from an EHR
(PointClickCare). This document states how the system aligns with HIPAA and EHR
data-handling best practices — what is implemented now, and what production
deployment additionally requires.

> **Hackathon data note:** the Pulse Foundry mock API serves **synthetic**
> patients — no real PHI is processed in this demo. The architecture is
> nonetheless built to be compliance-ready so it can be pointed at a live EHR
> under a BAA without redesign.

---

## 1. Minimum Necessary (HIPAA §164.502(b))

- The UI **masks PHI by default** — patient names show as initials, IDs are
  digit-masked. A reviewer explicitly toggles PHI visibility ("break-glass"),
  modeling role-based, least-privilege access.
- Billing decisions only ever require **clinical eligibility facts** (wound type,
  measurements, payer, dates) — not full demographics. The pipeline never pulls
  or displays more PHI than the billing decision needs.

## 2. Access Control (§164.312(a))

- Implemented (demo): PHI-masked default view + explicit reveal action.
- Production: SSO/IdP integration, per-role authorization (billing vs. clinical
  vs. admin), and per-user access scoping on every API route.

## 3. Audit Controls (§164.312(b))

- **Every decision is fully audit-logged**: the eligibility evaluation log records
  each condition (active wound, active Part B, extraction reliability,
  measurement completeness, drainage, confidence), the outcome, and a
  plain-English reason.
- **Provenance** records the source of every extracted field, so any value can be
  traced back to its origin record — essential for billing audits and CMS review.
- Production: append-only access logs (who viewed which patient, when, and whether
  PHI was unmasked), retained per policy.

## 4. Integrity (§164.312(c))

- Raw EHR payloads are stored verbatim; extraction/routing are deterministic and
  re-runnable, so a decision can always be reproduced from source.
- `is_current` / `sync_version` fields are respected so superseded records don't
  drive decisions.

## 5. Transmission Security (§164.312(e))

- Core pipeline runs **locally**; no PHI is transmitted to third parties.
- The EHR (PointClickCare) is accessed over HTTPS/TLS.
- Production: TLS everywhere, encryption at rest (DB/disk), secrets in a managed
  vault, network isolation.

## 6. Third-party / LLM handling

- The deterministic extractor sends **no data off-box**.
- The optional LLM extraction tier is **off by default**. If enabled in
  production it must run under a **Business Associate Agreement (BAA)** with the
  model provider (e.g., Azure OpenAI / Bedrock with a signed BAA), or against a
  self-hosted model — never a non-BAA public API. Output is schema-validated and
  low-confidence results fall back to human review, so the model can never
  silently drive a bill.

## 7. EHR data-handling best practices

- **Read-only** consumption of the source EHR — WoundScope never mutates PCC data.
- Two-layer patient identity (`patient_id` ↔ internal `id`) resolved correctly so
  records are never cross-linked to the wrong patient.
- Resilient ingestion guarantees **completeness** (no silently dropped patients) —
  a data-integrity safeguard, since a dropped record could mean a missed or wrong
  billing decision.
- Incremental `since` sync supports delta loads without re-pulling full PHI sets.

## 8. De-identification option (§164.514)

- Because decisions depend only on clinical/eligibility attributes, the pipeline
  can run on a **de-identified** dataset (Safe Harbor: strip names, MRNs, dates to
  year, etc.) for analytics/QA, with re-identification kept behind access control
  only where billing requires it.

## 9. Compliance responsibilities NOT in scope of this demo

Documented for honesty; required before production with real PHI:

- Signed **BAAs** with hosting, the EHR, and any LLM provider.
- Encryption at rest + in transit across all components.
- Authenticated, role-based access with full access audit logging + retention.
- Formal risk assessment, breach-notification procedures, workforce training.
- Data retention / disposal policy.

---

### Summary

WoundScope is built **compliance-first**: minimum-necessary PHI exposure,
deterministic + auditable decisions with full provenance, local processing with
no off-box PHI, and a clear, documented path to a production HIPAA deployment
under BAAs. The demo runs entirely on synthetic data.
