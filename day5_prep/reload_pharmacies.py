"""Reloads just the pharmacies table from the corrected wa_pharmacies_deduped.csv
after the banner-mislabeling fix (day3/classify_ownership.py). Other tables
are untouched."""
import csv
import os
import psycopg2

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RETRIEVED_AT = "2026-07-18"

conn = psycopg2.connect(dbname="pharmacy_tracker")
cur = conn.cursor()


def none_if_blank(v):
    return v if v not in (None, "") else None


with open(os.path.join(ROOT, "day8_prep", "pharmacy_enumeration_dates.csv")) as f:
    enum_dates = {r["npi"]: r for r in csv.DictReader(f)}

with open(os.path.join(ROOT, "day3", "wa_pharmacies_deduped.csv")) as f:
    rows = list(csv.DictReader(f))

missing_enum = 0
for r in rows:
    enum = enum_dates.get(r["npi"])
    if not enum:
        missing_enum += 1
    cur.execute("""
        INSERT INTO pharmacies (
            npi, organization_name, dba_name, parent_organization, ownership_category,
            ownership_confidence, classification_method, primary_taxonomy_code, primary_taxonomy_desc,
            pharmacy_type, walk_in_access, included_in_access_analysis, exclusion_reason,
            physical_location_id, enumeration_date, last_updated, source_name, retrieved_at,
            shared_signer_npi_count
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        r["npi"], r["organization_name"], none_if_blank(r["other_names"]), none_if_blank(r["parent_organization"]),
        r["ownership_category"], none_if_blank(r["ownership_confidence"]), r["classification_method"],
        r["primary_taxonomy_code"], r["primary_taxonomy_desc"],
        r["pharmacy_type"], r["walk_in_access"], r["included_in_access_analysis"] == "True",
        none_if_blank(r["exclusion_reason"]), r["physical_location_id"],
        enum["enumeration_date"] if enum else None, enum["last_updated"] if enum else None,
        "NPPES", RETRIEVED_AT,
        int(r["shared_signer_npi_count"]) if r.get("shared_signer_npi_count") else None,
    ))

conn.commit()
print(f"pharmacies: reloaded {len(rows)} rows ({missing_enum} missing an enumeration_date join)")
cur.close()
conn.close()
