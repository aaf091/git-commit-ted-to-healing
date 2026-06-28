"""WoundScope end-to-end runner.

Usage:
    python run.py ingest            # full concurrent ingest of all 300 patients
    python run.py ingest 12         # ingest first 12 (quick demo)
    python run.py process           # extract + route from local DB (no API)
    python run.py export            # write wound_billing_review.csv
    python run.py all [N]           # ingest [N] -> process -> export
"""
import sys

from woundscope.ingest import ingest_parallel
from woundscope.pipeline import build_results, summarize
from woundscope.export import export_csv


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    arg = sys.argv[2] if len(sys.argv) > 2 else None
    limit = int(arg) if arg and arg.isdigit() else None

    if cmd in ("ingest", "all"):
        ingest_parallel(reset=True, limit=limit)
    if cmd in ("process", "all"):
        res = build_results()
        print("Routing summary:", summarize(res))
    if cmd in ("export", "all"):
        export_csv()


if __name__ == "__main__":
    main()
