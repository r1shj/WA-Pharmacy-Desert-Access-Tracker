"""
Pulls the live openFDA shortages endpoint and writes today's snapshot.
Run this daily (via cron or similar) from this point forward - each run
adds one real observed day to the shortage timeline, on top of the
reconstructed backfill in shortage_backfill_snapshots.csv.
"""
import os
import sys
import urllib.request
import json
from collections import defaultdict
from datetime import date

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, OUT_DIR)
from snapshot_infra import write_snapshot  # noqa: E402
from build_shortage_backfill import collapse_to_distinct_shortages, parse_mdy  # noqa: E402

FIELDNAMES = ["snapshot_date", "generic_name", "status", "initial_posting_date",
              "last_update_date", "n_package_variants"]


def fetch_all_shortages():
    records = []
    for skip in (0, 1000):
        url = f"https://api.fda.gov/drug/shortages.json?limit=1000&skip={skip}"
        with urllib.request.urlopen(url, timeout=30) as resp:
            records.extend(json.loads(resp.read().decode())["results"])
    return records


if __name__ == "__main__":
    records = fetch_all_shortages()
    distinct = collapse_to_distinct_shortages(records)
    today = date.today()
    rows = [{
        "snapshot_date": today.isoformat(),
        "generic_name": s["generic_name"],
        "status": s["status"],
        "initial_posting_date": s["initial_posting_date"].date().isoformat(),
        "last_update_date": s["last_update_date"].date().isoformat() if s["last_update_date"] else "",
        "n_package_variants": s["n_package_variants"],
    } for s in distinct]
    path = write_snapshot("shortages", FIELDNAMES, rows, today)
    print(f"Wrote {len(rows)} distinct-shortage rows -> {path}")
