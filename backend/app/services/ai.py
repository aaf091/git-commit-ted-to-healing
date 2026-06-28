"""
Optional LLM layer — drafts a plain-English explanation + suggested action for
a flag. The DETERMINISTIC rule/dedupe result and its evidence remain the source
of truth; the LLM only phrases the "why" and proposes a next step. The UI labels
this clearly as assistive so a reviewer never mistakes it for the evidence.

Graceful by design: if ANTHROPIC_API_KEY is unset or the call fails, we return a
deterministic templated suggestion so the demo never breaks (no API dependency).

Model: claude-haiku-4-5 — cheapest/fastest tier, ideal for short per-flag text.
"""
from __future__ import annotations

import json
import os
from typing import Any

MODEL = "claude-haiku-4-5"

SYSTEM = (
    "You are a healthcare revenue-cycle / compliance assistant embedded in a "
    "review dashboard. You are given a SINGLE issue that a deterministic rules "
    "engine already flagged, plus its evidence fields. Do NOT re-judge whether "
    "the issue is real — the evidence is the source of truth. Your job is only "
    "to (1) explain the issue in one or two plain sentences a billing/ops staffer "
    "can act on, and (2) suggest one concrete next action. Be specific and "
    "reference the evidence. Never invent facts not present in the evidence. "
    'Respond ONLY with JSON: {"explanation": "...", "suggested_action": "..."}'
)


def explain_flag(flag: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """Returns {explanation, suggested_action, source: 'llm'|'fallback', model?}."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return _fallback(flag, "No ANTHROPIC_API_KEY set — showing a templated suggestion.")

    try:
        import anthropic  # imported lazily so the app runs without the package
    except ImportError:
        return _fallback(flag, "anthropic package not installed — templated suggestion.")

    prompt = _build_prompt(flag, record)
    try:
        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
        resp = client.messages.create(
            model=MODEL,
            max_tokens=400,
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        text = next((b.text for b in resp.content if b.type == "text"), "")
        data = _parse_json(text)
        return {
            "explanation": data.get("explanation") or flag.get("explanation", ""),
            "suggested_action": data.get("suggested_action") or _default_action(flag),
            "source": "llm",
            "model": MODEL,
        }
    except anthropic.AuthenticationError:
        return _fallback(flag, "Invalid ANTHROPIC_API_KEY — templated suggestion.")
    except Exception as e:  # noqa: BLE001 - never let the AI layer break the demo
        return _fallback(flag, f"AI call failed ({type(e).__name__}) — templated suggestion.")


def _build_prompt(flag: dict[str, Any], record: dict[str, Any]) -> str:
    evidence = "\n".join(f"  - {e['field']}: {e['value']}" for e in flag.get("evidence", []))
    name = f"{record.get('first_name','')} {record.get('last_name','')}".strip()
    return (
        f"Issue type: {flag.get('label')}\n"
        f"Category: {flag.get('category')}  |  Severity: {flag.get('severity')}  "
        f"|  Confidence: {flag.get('confidence')}%\n"
        f"Rule explanation: {flag.get('explanation')}\n"
        f"Patient/record: {name or record.get('patient_id') or flag.get('row_id')}\n"
        f"Evidence fields:\n{evidence}\n"
    )


def _fallback(flag: dict[str, Any], note: str) -> dict[str, Any]:
    return {
        "explanation": flag.get("explanation", ""),
        "suggested_action": _default_action(flag),
        "source": "fallback",
        "note": note,
    }


def _default_action(flag: dict[str, Any]) -> str:
    """Deterministic, defensible next step per category — no model needed."""
    return {
        "revenue": "Route to billing to submit/correct the claim and capture the charge.",
        "compliance": "Verify eligibility for the date of service before billing; document the check.",
        "duplicate": "Open the matched records side by side and merge into a single patient record.",
        "data_quality": "Return to intake to complete the missing required fields.",
    }.get(flag.get("category"), "Assign to a reviewer to confirm and resolve.")


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    # Tolerate a fenced code block or surrounding prose.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return {}
