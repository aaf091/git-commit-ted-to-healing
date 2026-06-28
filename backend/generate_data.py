"""
Generate a synthetic, deliberately MESSY healthcare dataset for the demo.

It seeds every problem the kit detects:
  - duplicate patients (typos, nickname, different formatting of same person)
  - missed billable events (procedure present, billed = N)
  - services rendered while eligibility inactive/expired
  - missing required identity fields
  - zero-charge procedures
  - inconsistent casing / whitespace / date formats / phone formats

Run:  python generate_data.py   ->  writes data/synthetic_patients.csv
Deterministic (fixed seed) so the demo is reproducible.
"""
from __future__ import annotations

import csv
import os
import random

random.seed(42)

FIRST = ["Robert", "Bob", "Maria", "María", "James", "Jim", "Linda", "Lin",
         "Michael", "Mike", "Patricia", "Pat", "John", "Jon", "Jennifer", "Jen",
         "William", "Will", "Elizabeth", "Liz", "David", "Dave", "Susan"]
LAST = ["Smith", "Smyth", "Johnson", "Jonson", "Garcia", "Garica", "Williams",
        "Brown", "Browne", "Davis", "Davies", "Miller", "Wilson", "Wilsen",
        "Martinez", "Anderson", "Andersen", "Taylor", "Thomas", "Moore"]
PLANS = ["PPO Gold", "HMO Basic", "PPO Silver", "Medicare A", "Medicaid"]
ELIG = ["Active", "active", "ACTIVE", "Inactive", "Expired", "Termed"]
PROCS = [("99213", "Office visit, established patient"),
         ("99204", "Office visit, new patient"),
         ("80053", "Comprehensive metabolic panel"),
         ("93000", "Electrocardiogram"),
         ("71046", "Chest X-ray"),
         ("36415", "Routine venipuncture")]
PROVIDERS = ["Dr. A. Patel", "Dr. R. Nguyen", "dr. s. kim", "Dr. L. Okafor ",
             "Dr. M. Rossi"]


def messy_phone() -> str:
    n = f"{random.randint(200,999)}{random.randint(200,999)}{random.randint(1000,9999)}"
    fmt = random.choice([
        f"({n[:3]}) {n[3:6]}-{n[6:]}",
        f"{n[:3]}-{n[3:6]}-{n[6:]}",
        f"{n[:3]}.{n[3:6]}.{n[6:]}",
        f"+1{n}", n,
    ])
    return fmt


def messy_date(y: int, m: int, d: int) -> str:
    fmt = random.choice([
        f"{y:04d}-{m:02d}-{d:02d}",
        f"{m:02d}/{d:02d}/{y:04d}",
        f"{m}/{d}/{y}",
        f"{d:02d}-{m:02d}-{y:04d}",
    ])
    return fmt


def make_row(pid: int) -> dict:
    f = random.choice(FIRST)
    l = random.choice(LAST)
    dob = messy_date(random.randint(1945, 2005), random.randint(1, 12),
                     random.randint(1, 28))
    proc_code, proc_desc = random.choice(PROCS)
    charge = random.choice([120, 250, 75, 340, 0, 95])
    billed = random.choices(["Y", "N", ""], weights=[6, 3, 1])[0]
    pad = random.choice(["", " ", "  "])  # stray whitespace
    return {
        "patient_id": f"P{pid:05d}",
        "first_name": pad + f,
        "last_name": l + pad,
        "dob": dob,
        "gender": random.choice(["M", "F", "Male", "Female", ""]),
        "phone": messy_phone(),
        "email": f"{f.lower()}.{l.lower()}@example.com" if random.random() > 0.2 else "",
        "address": f"{random.randint(1,999)} {random.choice(['Main St','Oak Ave','2nd St'])}",
        "insurance_id": f"INS{random.randint(100000,999999)}",
        "plan_type": random.choice(PLANS),
        "eligibility_status": random.choice(ELIG),
        "encounter_date": messy_date(2025, random.randint(1, 12), random.randint(1, 28)),
        "procedure_code": proc_code,
        "procedure_desc": proc_desc,
        "charge_amount": random.choice([f"${charge}", str(charge), f"{charge}.00"]),
        "billed": billed,
        "provider": random.choice(PROVIDERS),
    }


def dup_of(row: dict, pid: int) -> dict:
    """A near-duplicate of an existing patient (same person, messy variant)."""
    d = dict(row)
    d["patient_id"] = f"P{pid:05d}"          # different ID = the classic dup
    # nickname swap
    nick = {"Robert": "Bob", "James": "Jim", "Michael": "Mike", "William": "Will",
            "Jennifer": "Jen", "Elizabeth": "Liz", "David": "Dave"}
    fn = row["first_name"].strip()
    if fn in nick and random.random() > 0.5:
        d["first_name"] = nick[fn]
    # last-name typo
    if random.random() > 0.5:
        d["last_name"] = row["last_name"].strip() + ("e" if random.random() > 0.5 else "")
    d["phone"] = messy_phone()               # re-entered differently
    d["encounter_date"] = messy_date(2025, random.randint(1, 12), random.randint(1, 28))
    return d


def main() -> None:
    rows: list[dict] = []
    pid = 1
    for _ in range(80):
        row = make_row(pid); pid += 1
        rows.append(row)
        if random.random() < 0.18:           # ~18% get a duplicate
            rows.append(dup_of(row, pid)); pid += 1

    # Inject a few rows missing required fields.
    for _ in range(5):
        r = make_row(pid); pid += 1
        drop = random.choice(["first_name", "last_name", "dob", "patient_id"])
        r[drop] = ""
        rows.append(r)

    random.shuffle(rows)
    out_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "synthetic_patients.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows -> {path}")


if __name__ == "__main__":
    main()
