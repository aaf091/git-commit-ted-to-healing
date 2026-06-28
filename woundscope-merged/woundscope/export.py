"""Export the results table to CSV for billing staff."""
from __future__ import annotations

import csv
from pathlib import Path

from .db import connect

OUT = Path(__file__).resolve().parent.parent / "wound_billing_review.csv"
COLS = ["patient_id", "name", "facility_id", "decision", "confidence",
        "has_active_wound", "has_active_mcb", "wound_type", "wound_stage",
        "wound_location", "length_cm", "width_cm", "depth_cm", "drainage",
        "reasoning"]


def export_csv(path: Path = OUT) -> Path:
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM results ORDER BY "
        "CASE decision WHEN 'auto_accept' THEN 0 WHEN 'flag_for_review' THEN 1 "
        "ELSE 2 END, confidence DESC").fetchall()
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLS)
        for r in rows:
            w.writerow([r[c] for c in COLS])
    conn.close()
    print(f"Wrote {len(rows)} rows -> {path}")
    return path


if __name__ == "__main__":
    export_csv()
