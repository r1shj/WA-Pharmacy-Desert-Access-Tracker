"""
One-time: replay the daily shortage snapshot files collected locally by
launchd (day8_prep/snapshots/shortages/, 2026-07-18 onward) through
jobs/shortage_sync.apply_observation(), in date order, so the shortages
table reflects ~3 months of real observed change before it's migrated to
Supabase. From here on the GitHub Actions job applies the same function to
each day's live pull.

The old snapshot script never saved dosage_form/therapeutic_category, so
those are filled from a fresh live openFDA pull. All 40 shortages that
appeared after 2026-07-18 are still in today's feed (checked before
writing this), so none is left uncategorized.

Runs in a single transaction: all of it applies, or none of it does.
Usage: python3 day9/backfill_shortage_snapshots.py [--dry-run]
"""
import csv
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
from jobs.db import connect  # noqa: E402
from jobs.shortage_sync import apply_observation, collapse, fetch_live_feed  # noqa: E402

SNAPSHOT_DIR = os.path.join(ROOT, "day8_prep", "snapshots", "shortages")
BASELINE_DATE = "2026-07-18"  # the pull the shortages table was originally built from


def read_snapshot(path, categories):
    records = {}
    for r in csv.DictReader(open(path)):
        g = r["generic_name"]
        cat = categories.get(g, {})
        records[g] = {
            "status": r["status"],
            "initial_posting_date": r["initial_posting_date"],
            "last_update_date": r["last_update_date"] or None,
            "n_package_variants": int(r["n_package_variants"]),
            "dosage_form": cat.get("dosage_form"),
            "therapeutic_category": cat.get("therapeutic_category"),
        }
    return records


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    live = collapse(fetch_live_feed())
    print(f"Live openFDA feed: {len(live)} distinct shortages (used only for categories)")

    dates = sorted(f[:-4] for f in os.listdir(SNAPSHOT_DIR) if f.endswith(".csv"))
    conn = connect()
    cur = conn.cursor()

    # Sanity check: the baseline file should describe exactly the rows already in the table.
    baseline = set(read_snapshot(os.path.join(SNAPSHOT_DIR, f"{BASELINE_DATE}.csv"), {}))
    cur.execute("SELECT generic_name FROM shortages")
    in_table = {r[0] for r in cur.fetchall()}
    if baseline != in_table:
        sys.exit(f"Baseline mismatch: {len(baseline ^ in_table)} names differ between "
                 f"{BASELINE_DATE}.csv and the shortages table - not replaying.")

    totals = {"added": 0, "reappeared": 0, "resolved": 0, "unresolved": 0, "dropped_out": 0}
    for d in dates:
        if d <= BASELINE_DATE:
            continue
        s = apply_observation(cur, d, read_snapshot(os.path.join(SNAPSHOT_DIR, f"{d}.csv"), live))
        for k in totals:
            totals[k] += s[k]

    cur.execute("""
        SELECT count(*) FILTER (WHERE therapeutic_category IS NULL) AS uncategorized,
               count(*) AS total,
               count(*) FILTER (WHERE end_date_basis IS NULL) AS still_open,
               count(*) FILTER (WHERE end_date_basis = 'confirmed_resolved') AS resolved,
               count(*) FILTER (WHERE end_date_basis = 'last_observed_in_feed') AS dropped
        FROM shortages
    """)
    uncategorized, total, still_open, resolved, dropped = cur.fetchone()
    print(f"Replayed {len([d for d in dates if d > BASELINE_DATE])} daily files after {BASELINE_DATE}")
    print(f"Changes: {totals}")
    print(f"Table now: {total} rows - {still_open} open, {resolved} confirmed resolved, "
          f"{dropped} last-observed (dropped from feed), {uncategorized} uncategorized")

    if dry_run:
        conn.rollback()
        print("DRY RUN - rolled back, nothing written")
    else:
        conn.commit()
        print("Committed")
    cur.close()
    conn.close()
