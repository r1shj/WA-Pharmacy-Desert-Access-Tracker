"""
SUPERSEDED by jobs/pharmacy_sync.py (DECISIONS.md 2026-10-15): this
re-saves the static Day 3 CSV, so every "snapshot" it wrote was a copy
and observed nothing. Kept only as a record of what ran before.

Writes today's snapshot of the full deduped/classified WA pharmacy
dataset, using the same shared snapshot_infra as the shortage layer.
Run this daily going forward (per pharmacy task #3) - real observed
pharmacy-dataset changes accumulate here with actual dates, separate
from the enumeration_date-based growth backfill in
pharmacy_enumeration_backfill.csv (which cannot see closures).
"""
import csv
import os
import sys
from datetime import date

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, OUT_DIR)
from snapshot_infra import write_snapshot  # noqa: E402

DAY3_DEDUPED = os.path.join(OUT_DIR, "..", "day3", "wa_pharmacies_deduped.csv")

if __name__ == "__main__":
    with open(DAY3_DEDUPED) as f:
        reader = csv.DictReader(f)
        fieldnames = ["snapshot_date"] + reader.fieldnames
        rows = []
        for row in reader:
            out_row = {"snapshot_date": date.today().isoformat()}
            out_row.update(row)
            rows.append(out_row)

    path = write_snapshot("pharmacies", fieldnames, rows, date.today())
    print(f"Wrote {len(rows)} pharmacy rows -> {path}")
