"""
Optional LLM layer — drafts a plain-English, biller-facing narrative explaining
a patient's routing decision. The DETERMINISTIC eligibility result (decision +
pass/fail reasons + evidence) is the source of truth; the LLM only turns it into
a sentence a non-technical biller can read. The UI labels it as assistive.

Graceful: with no ANTHROPIC_API_KEY (or any error), returns the deterministic
reasoning so the demo never depends on a network call.

Model: claude-haiku-4-5 — cheapest/fastest tier, ideal for short narratives.
"""
from __future__ import annotations

import json
import os
from typing import Any

MODEL = "claude-haiku-4-5"

SYSTEM = (
    "You write one short, plain-English explanation for a non-technical medical "
    "biller, explaining why a patient was routed to a Medicare Part B wound-care "
    "billing decision (auto_accept, flag_for_review, or reject). You are given the "
    "deterministic decision and the exact pass/fail criteria — do NOT re-decide. "
    "Just explain it in 1-2 warm, clear sentences and state the single next action "
    "the biller should take. Reference the specifics (payer, wound, missing field). "
    'Respond ONLY with JSON: {"narrative": "...", "next_action": "..."}'
)


def explain_decision(row: dict[str, Any]) -> dict[str, Any]:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return _fallback(row, "No ANTHROPIC_API_KEY set — showing deterministic reasoning.")
    try:
        import anthropic
    except ImportError:
        return _fallback(row, "anthropic package not installed.")

    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=MODEL, max_tokens=400, system=SYSTEM,
            messages=[{"role": "user", "content": _prompt(row)}],
        )
        text = next((b.text for b in resp.content if b.type == "text"), "")
        data = _parse_json(text)
        return {
            "narrative": data.get("narrative") or row.get("reasoning", ""),
            "next_action": data.get("next_action") or _default_action(row),
            "source": "llm",
            "model": MODEL,
        }
    except anthropic.AuthenticationError:
        return _fallback(row, "Invalid ANTHROPIC_API_KEY.")
    except Exception as e:  # noqa: BLE001
        return _fallback(row, f"AI call failed ({type(e).__name__}).")


def _prompt(row: dict[str, Any]) -> str:
    wd = row["wound"]
    crit = "\n".join(f"  - [{'PASS' if r['ok'] else 'FAIL'}] {r['text']}" for r in row["reasons"])
    return (
        f"Decision: {row['decision']}\n"
        f"Patient: {row['name']} ({row['patient_id']}), facility {row['facility_id']}\n"
        f"Primary payer: {row['primary_payer_code']} | Part B active: {row['part_b_active']}\n"
        f"Wound: type={wd.get('wound_type')} stage={wd.get('stage')} "
        f"size={wd.get('length_cm')}x{wd.get('width_cm')}x{wd.get('depth_cm')}cm "
        f"drainage={wd.get('drainage_amount')}\n"
        f"Criteria:\n{crit}\n"
    )


def _fallback(row: dict[str, Any], note: str) -> dict[str, Any]:
    return {
        "narrative": row.get("reasoning", ""),
        "next_action": _default_action(row),
        "source": "fallback",
        "note": note,
    }


def _default_action(row: dict[str, Any]) -> str:
    return {
        "auto_accept": "Submit the Part B wound-care claim — documentation is complete.",
        "flag_for_review": "Have a nurse complete the missing documentation, then re-route.",
        "reject": "Do not bill as Part B wound care; confirm coverage/wound status with the facility.",
    }.get(row["decision"], "Review with a supervisor.")


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    s, e = text.find("{"), text.rfind("}")
    if s != -1 and e != -1:
        try:
            return json.loads(text[s:e + 1])
        except json.JSONDecodeError:
            pass
    return {}
