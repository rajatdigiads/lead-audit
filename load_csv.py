"""
Run the Lead-Quality Engine on YOUR real leads from a CSV file (command line).

USAGE
-----
    python3 load_csv.py leads.csv
    python3 load_csv.py leads.csv --config client_config.json

Auto-detects common column names. For unusual headers, add a "column_map" to
client_config.json. Outputs report.md and prints the summary.
"""

import sys
import csv
import json
import os

from lead_quality_engine import process_batch, summarize
from run_report import build_report
from core_io import build_column_map, rows_to_leads

DEFAULT_CLIENT_CONFIG = {
    "service_area_terms": ["sydney", "parramatta", "nsw", "2000"],
    "existing_customers": [
        {"email": "example.customer@gmail.com", "phone": "0400000000"}
    ],
    "business_hours": [8, 18],
    "column_map": {},
}


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 load_csv.py <leads.csv> [--config client_config.json]")
        if not os.path.exists("client_config.json"):
            with open("client_config.json", "w") as f:
                json.dump(DEFAULT_CLIENT_CONFIG, f, indent=2)
            print("\nWrote a sample client_config.json — edit it with the client's real")
            print("service suburbs/postcodes and existing-customer list, then re-run.")
        sys.exit(1)

    csv_path = sys.argv[1]
    cfg = dict(DEFAULT_CLIENT_CONFIG)
    if "--config" in sys.argv:
        with open(sys.argv[sys.argv.index("--config") + 1]) as f:
            cfg.update(json.load(f))
    elif os.path.exists("client_config.json"):
        with open("client_config.json") as f:
            cfg.update(json.load(f))
    if isinstance(cfg.get("business_hours"), list):
        cfg["business_hours"] = tuple(cfg["business_hours"])

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    headers = rows[0].keys() if rows else []
    col_map = build_column_map(headers, cfg.get("column_map", {}))

    print(f"Detected columns: {col_map}")
    missing = [c for c in ("email", "phone") if c not in col_map]
    if missing:
        print(f"WARNING: could not find column(s) for {missing}. "
              f"Add them to 'column_map' in client_config.json.")

    leads = rows_to_leads(rows, col_map)
    print(f"Loaded {len(leads)} leads from {csv_path}\n")

    results = process_batch(leads, cfg)
    s = summarize(results)
    report = build_report(results, s)
    with open("report.md", "w") as f:
        f.write(report)
    print(report)
    print(f"\n[written] report.md  ({s['lead_quality_pct']}% lead quality, "
          f"{s['qualified']} qualified of {s['total_leads']})")


if __name__ == "__main__":
    main()
