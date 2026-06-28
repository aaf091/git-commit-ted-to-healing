"""
Thin HTTP layer. Each function makes exactly one call and translates the
response into scheduler-understood signals (success dict / RateLimited /
PermanentError). No retry logic lives here -- that's the scheduler's job.
This separation is what lets the scheduler's AIMD+budget logic stay
endpoint-agnostic.
"""
import httpx

import config
from scheduler import PermanentError, RateLimited

ENDPOINTS = {
    "patients": "/pcc/patients",
    "diagnoses": "/pcc/diagnoses",
    "coverage": "/pcc/coverage",
    "notes": "/pcc/notes",
    "assessments": "/pcc/assessments",
}


async def fetch(task, client: httpx.AsyncClient):
    path = ENDPOINTS[task.kind]
    url = f"{config.BASE_URL}{path}"
    try:
        resp = await client.get(url, params=task.params, timeout=config.REQUEST_TIMEOUT_SECONDS)
    except httpx.TransportError as e:
        raise PermanentError(f"transport error: {e}") from e

    if resp.status_code == 429:
        retry_after_header = resp.headers.get("Retry-After")
        retry_after = float(retry_after_header) if retry_after_header else None
        raise RateLimited(retry_after)

    if resp.status_code == 422:
        raise PermanentError(f"422 invalid params: {resp.text[:200]}")

    if resp.status_code >= 500:
        # Server errors aren't the documented 429 contract -- treat as a
        # one-shot permanent failure for this task rather than spending
        # retry budget on a class of error the docs don't promise is transient.
        raise PermanentError(f"{resp.status_code} server error: {resp.text[:200]}")

    resp.raise_for_status()
    return resp.json()