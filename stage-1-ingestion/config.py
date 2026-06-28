"""Configuration for the PCC wound-care eligibility pipeline."""
import os

BASE_URL = os.environ.get("PCC_API_BASE_URL", "https://hackathon.prod.pulsefoundry.ai")
FACILITY_IDS = [101, 102, 103]

DB_PATH = os.environ.get("PCC_DB_PATH", "pcc_data.db")
SYNC_STATE_PATH = os.environ.get("PCC_SYNC_STATE_PATH", "sync_state.json")

# Known failure rate from API docs — used to provision the retry budget
# analytically rather than guessing: expected retries per task = p/(1-p)
KNOWN_FAILURE_RATE = 0.30
RETRY_BUDGET_MULTIPLIER = 2.5  # safety margin over the analytic expectation

REQUEST_TIMEOUT_SECONDS = 15.0

# AIMD concurrency control bounds
MIN_CONCURRENCY = 1
MAX_CONCURRENCY = 20
INITIAL_CONCURRENCY = 5
ADDITIVE_INCREASE = 1            # on success streaks
MULTIPLICATIVE_DECREASE = 0.5    # on 429

# Fallback spacing if a 429 arrives without a Retry-After header
DEFAULT_RETRY_AFTER_SECONDS = 3.0

TARGET_PAYER_CODE = "MCB"