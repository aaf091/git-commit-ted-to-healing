"""
Optional LLM layer — drafts a short, biller-facing narrative for a routing
decision. The DETERMINISTIC decision + reasoning (from route.py) is the source
of truth; the LLM only rephrases it for a non-technical reader and suggests the
next action. The UI labels it as assistive.

Graceful by design: with no ANTHROPIC_API_KEY (or any error), it returns the
deterministic reasoning, so the console never depends on a network call. This
keeps WoundScope's compliance posture intact — nothing goes off-box unless a key
is explicitly configured (and COMPLIANCE.md notes a BAA is required in prod).

Model: claude-haiku-4-5 (cheapest/fastest tier, ideal for short narratives).
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
    "deterministic decision and its reasoning — do NOT re-decide or contradict it. "
    "Explain it in 1-2 warm, clear sentences and state the single next action the "
    "biller should take. Reference the specifics (wound, payer, missing field). "
    'Respond ONLY with JSON: {"narrative": "...", "next_action": "..."}'
)


def explain_decision(p: dict[str, Any]) -> dict[str, Any]:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return _fallback(p, "No ANTHROPIC_API_KEY set — showing deterministic reasoning.")
    try:
        import anthropic
    except ImportError:
        return _fallback(p, "anthropic package not installed.")
    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=MODEL, max_tokens=400, system=SYSTEM,
            messages=[{"role": "user", "content": _prompt(p)}],
        )
        text = next((b.text for b in resp.content if b.type == "text"), "")
        data = _parse_json(text)
        return {
            "narrative": data.get("narrative") or p.get("reasoning", ""),
            "next_action": data.get("next_action") or _default_action(p),
            "source": "llm",
            "model": MODEL,
        }
    except anthropic.AuthenticationError:
        return _fallback(p, "Invalid ANTHROPIC_API_KEY.")
    except Exception as e:  # noqa: BLE001 - never let the AI layer break the demo
        return _fallback(p, f"AI call failed ({type(e).__name__}).")


def _prompt(p: dict[str, Any]) -> str:
    return (
        f"Decision: {p.get('decision')}\n"
        f"Patient: {p.get('name')} ({p.get('patient_id')}), facility {p.get('facility_id')}\n"
        f"Active wound dx: {bool(p.get('has_active_wound'))} | "
        f"Active Part B: {bool(p.get('has_active_mcb'))}\n"
        f"Wound: type={p.get('wound_type')} stage={p.get('wound_stage')} "
        f"size={p.get('length_cm')}x{p.get('width_cm')}x{p.get('depth_cm')}cm "
        f"drainage={p.get('drainage')} | confidence={p.get('confidence')}\n"
        f"Deterministic reasoning: {p.get('reasoning')}\n"
    )


def _fallback(p: dict[str, Any], note: str) -> dict[str, Any]:
    return {
        "narrative": p.get("reasoning", ""),
        "next_action": _default_action(p),
        "source": "fallback",
        "note": note,
    }


def _default_action(p: dict[str, Any]) -> str:
    return {
        "auto_accept": "Submit the Part B wound-care claim — documentation is complete.",
        "flag_for_review": "Have a nurse complete the missing documentation, then re-route.",
        "reject": "Do not bill as Part B wound care; confirm coverage/wound status with the facility.",
    }.get(p.get("decision"), "Review with a supervisor.")


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    s, e = text.find("{"), text.rfind("}")
    if s != -1 and e != -1:
        try:
            return json.loads(text[s:e + 1])
        except json.JSONDecodeError:
            pass
    return {}
