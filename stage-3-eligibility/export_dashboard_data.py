"""
Stage 5 helper -- exports eligibility results as the JSON shape the
dashboard.html file expects. Run this after run_eligibility() to refresh
the dashboard with real data, then paste the output into dashboard.html's
DATA constant (or wire it up to fetch from a small local server -- see
README for the no-build approach used here).
"""
import json
import eligibility


def export_for_dashboard(path: str = "dashboard_data.json") -> str:
    results = eligibility.run_eligibility()
    data = []
    for r in results:
        data.append({
            "patient_id": r.patient_id_str,
            "name": f"{r.first_name} {r.last_name}",
            "facility_id": r.facility_id,
            "decision": r.decision,
            "reason": r.reason,
            "wound_type": r.best_wound_type,
            "location": r.best_wound_location,
            "stage": r.best_wound_stage,
            "length_cm": r.best_wound_length_cm,
            "width_cm": r.best_wound_width_cm,
            "depth_cm": r.best_wound_depth_cm,
            "drainage": r.best_wound_drainage,
            "confidence": r.best_wound_confidence,
            "wound_count": r.wound_count,
            "has_active_mcb": r.has_active_mcb,
            "has_lapsed_mcb": r.has_lapsed_mcb,
            "primary_payer": r.primary_payer_code,
        })
    with open(path, "w") as f:
        json.dump(data, f)
    return path


if __name__ == "__main__":
    path = export_for_dashboard()
    print(f"Dashboard data exported to: {path}")
    print("Paste this file's contents into dashboard.html's DATA constant,")
    print("or open dashboard.html and use the 'Load data file' button.")