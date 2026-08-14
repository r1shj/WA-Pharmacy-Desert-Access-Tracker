"""
Loads day8_prep/snapshots/pharmacies/2026-07-18.csv into pharmacy_snapshots
as snapshot_source='observed'.

That file is NPI-level (1,941 rows), but pharmacy_snapshots is
location-grain (one row per physical_location_id per date per source,
with npi_count_at_location/contributing_npis) - matching how the
enumeration backfill was already structured. So this aggregates the
NPI-level file up to one row per physical_location_id before inserting,
the same way pharmacy_enumeration_backfill.csv was built, rather than
inserting 1,941 raw rows into a table whose grain assumes one row per
location.
"""
import csv
import os
from collections import defaultdict
import psycopg2

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

with open(os.path.join(ROOT, "day8_prep", "snapshots", "pharmacies", "2026-07-18.csv")) as f:
    rows = list(csv.DictReader(f))

by_location = defaultdict(list)
for r in rows:
    by_location[r["physical_location_id"]].append(r["npi"])

conn = psycopg2.connect(dbname="pharmacy_tracker")
cur = conn.cursor()

inserted = 0
for loc_id, npis in by_location.items():
    cur.execute("""
        INSERT INTO pharmacy_snapshots (snapshot_date, physical_location_id, snapshot_source,
                                         npi_count_at_location, contributing_npis)
        VALUES ('2026-07-18', %s, 'observed', %s, %s)
    """, (loc_id, len(npis), ";".join(npis)))
    inserted += 1

conn.commit()
print(f"Aggregated {len(rows)} NPI-level rows -> {inserted} location-level 'observed' snapshot rows")
cur.close()
conn.close()
