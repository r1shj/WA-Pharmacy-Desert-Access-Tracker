"""
Reconstructs synthetic daily "active shortage" snapshots from openFDA's
current-state drug shortages data, since no separate historical archive
exists (confirmed: the bulk download is the identical 1,614-record
current snapshot, not a time series - see DECISIONS.md).

openFDA's actual field names differ from the start_date/resolution_date
assumed going in:
  - initial_posting_date: when FDA first posted the shortage notice
    (best available proxy for "start"). 100% populated (1,614/1,614).
  - status: "Current" | "To Be Discontinued" | "Resolved"
  - update_date: last time the record was touched. Only meaningful as a
    resolution-date proxy when status=="Resolved" - for the other two
    statuses it just reflects the last reverification, not an end date.
  - There is no field that is a clean, purpose-built "resolution_date."

This produces TWO backfill tiers rather than one, because a strict
resolved-only backfill (what was originally asked for) turned out to
cover almost nothing - see the tier 1 numbers below and DECISIONS.md.

TIER 1 - "resolved" (strict, bounded interval):
  Only records with status=="Resolved". Bounded start=initial_posting_date,
  end=update_date. Empirically: only 25 of 1,614 rows are Resolved, and
  those 25 rows collapse to just 3 DISTINCT drugs (package_ndc fragments
  one real shortage into several rows). Narrow date range, small n.

TIER 2 - "ongoing_since" (open-ended, NOT what was originally asked for,
  added because it's the only way to get real depth out of this data):
  Records with status in ("Current", "To Be Discontinued").
  start=initial_posting_date, end=the date this script ran (today) since
  they're confirmed not-yet-resolved as of the pull. This is NOT a bounded
  interval - it will keep needing to be extended by the forward snapshot
  job. But it's the only way to get the slider back to 2012 instead of
  2023, because 231 of 234 distinct shortages are still open.

Both tiers make the same "continuously active since first posting"
assumption for any given drug - we don't have a record of a shortage
possibly lapsing and reopening in between, and treat NDC-package variants
of the same generic_name as one shortage using its earliest posting date.
"""
import csv
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
PULL_DATE = datetime(2026, 7, 18)  # date this openFDA pull was taken


def parse_mdy(d):
    try:
        return datetime.strptime(d, "%m/%d/%Y")
    except (ValueError, TypeError):
        return None


def collapse_to_distinct_shortages(records):
    """One row per generic_name: earliest initial_posting_date, latest
    update_date, and the 'worst' status if they disagree across
    package_ndc variants (Resolved only counts if ALL variants resolved)."""
    by_generic = defaultdict(list)
    for r in records:
        by_generic[r.get("generic_name")].append(r)

    distinct = []
    for generic, rows in by_generic.items():
        postings = [parse_mdy(r.get("initial_posting_date")) for r in rows]
        postings = [d for d in postings if d]
        updates = [parse_mdy(r.get("update_date")) for r in rows]
        updates = [d for d in updates if d]
        statuses = {r.get("status") for r in rows}
        # Only call the whole shortage "Resolved" if every package variant is.
        status = "Resolved" if statuses == {"Resolved"} else (
            "To Be Discontinued" if "To Be Discontinued" in statuses else "Current"
        )
        if not postings:
            continue
        distinct.append({
            "generic_name": generic,
            "status": status,
            "initial_posting_date": min(postings),
            "last_update_date": max(updates) if updates else None,
            "n_package_variants": len(rows),
        })
    return distinct


def daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


if __name__ == "__main__":
    records = json.load(open(os.path.join(OUT_DIR, "shortages_all_raw.json")))
    distinct = collapse_to_distinct_shortages(records)
    print(f"{len(records)} raw rows -> {len(distinct)} distinct shortages (by generic_name)")

    resolved = [s for s in distinct if s["status"] == "Resolved" and s["last_update_date"]]
    ongoing = [s for s in distinct if s["status"] != "Resolved"]

    print(f"\nTIER 1 (resolved, bounded): {len(resolved)} distinct shortages")
    for s in resolved:
        print(f"   {s['generic_name'][:45]:45s} {s['initial_posting_date'].date()} -> {s['last_update_date'].date()}")

    print(f"\nTIER 2 (ongoing, open-ended since posting): {len(ongoing)} distinct shortages")
    print(f"   earliest initial_posting_date: {min(s['initial_posting_date'] for s in ongoing).date()}")
    print(f"   latest initial_posting_date:   {max(s['initial_posting_date'] for s in ongoing).date()}")

    # --- write the actual daily snapshot rows ---
    out_path = os.path.join(OUT_DIR, "shortage_backfill_snapshots.csv")
    row_count = 0
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["snapshot_date", "generic_name", "tier", "source_status", "n_package_variants"])
        for s in resolved:
            for d in daterange(s["initial_posting_date"], s["last_update_date"]):
                writer.writerow([d.date().isoformat(), s["generic_name"], "resolved_bounded",
                                  s["status"], s["n_package_variants"]])
                row_count += 1
        for s in ongoing:
            for d in daterange(s["initial_posting_date"], PULL_DATE):
                writer.writerow([d.date().isoformat(), s["generic_name"], "ongoing_open_ended",
                                  s["status"], s["n_package_variants"]])
                row_count += 1

    print(f"\nWrote {row_count} daily snapshot rows -> {out_path}")

    all_starts = [s["initial_posting_date"] for s in distinct]
    print(f"\nCombined (tier 1 + tier 2) date range achieved: "
          f"{min(all_starts).date()} to {PULL_DATE.date()}")
    print(f"Tier 1 ALONE date range: "
          f"{min(s['initial_posting_date'] for s in resolved).date()} to "
          f"{max(s['last_update_date'] for s in resolved).date()}" if resolved else "Tier 1 alone: no data")
