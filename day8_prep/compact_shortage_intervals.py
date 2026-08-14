"""
Compacts shortage_backfill_snapshots.csv (one row per shortage per active
day - 177,901 rows) into one row per distinct shortage with a start/end
interval instead. This, not the exploded daily version, is what Day 5's
database should actually load - the daily expansion was only ever useful
for eyeballing/debugging the backfill logic, not as a storage format.
"""
import csv
import json
import os
import sys

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, OUT_DIR)
from build_shortage_backfill import collapse_to_distinct_shortages, parse_mdy  # noqa: E402

PULL_DATE = "2026-07-18"


def dedup_join(values):
    seen = []
    for v in values:
        if v and v not in seen:
            seen.append(v)
    return "; ".join(seen)


if __name__ == "__main__":
    records = json.load(open(os.path.join(OUT_DIR, "shortages_all_raw.json")))
    distinct = collapse_to_distinct_shortages(records)

    by_generic = {}
    for r in records:
        by_generic.setdefault(r.get("generic_name"), []).append(r)

    out_path = os.path.join(OUT_DIR, "shortage_intervals.csv")
    fieldnames = [
        "generic_name", "tier", "source_status", "start_date", "end_date",
        "n_package_variants", "dosage_form", "therapeutic_category",
    ]
    rows = []
    for s in distinct:
        raw_rows = by_generic[s["generic_name"]]
        is_resolved = s["status"] == "Resolved" and s["last_update_date"] is not None
        rows.append({
            "generic_name": s["generic_name"],
            "tier": 1 if is_resolved else 2,
            "source_status": s["status"],
            "start_date": s["initial_posting_date"].date().isoformat(),
            "end_date": s["last_update_date"].date().isoformat() if is_resolved else "",
            "n_package_variants": s["n_package_variants"],
            "dosage_form": dedup_join(r.get("dosage_form") for r in raw_rows),
            "therapeutic_category": dedup_join(
                cat for r in raw_rows for cat in (r.get("therapeutic_category") or [])
            ),
        })

    rows.sort(key=lambda r: r["start_date"])
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    tier1 = sum(1 for r in rows if r["tier"] == 1)
    tier2 = sum(1 for r in rows if r["tier"] == 2)
    print(f"Wrote {len(rows)} interval rows -> {out_path}")
    print(f"  tier 1 (resolved/bounded): {tier1}")
    print(f"  tier 2 (ongoing/open-ended, end_date blank): {tier2}")
    print(f"\nCompaction ratio: 177,901 daily rows -> {len(rows)} interval rows "
          f"({177901 / len(rows):.0f}x smaller)")
