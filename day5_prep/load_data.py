"""
Day 5 load script. Reads the ACTUAL files already on disk - no
re-derivation of anything. Column mappings and the reasoning behind each
deviation from the originally-described schema are documented in
schema.sql's comments and DECISIONS.md (2026-07-25 entry).
"""
import csv
import os
import psycopg2

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RETRIEVED_AT = "2026-07-18"  # known NPPES pull date; not a column in any source file

conn = psycopg2.connect(dbname="pharmacy_tracker")
cur = conn.cursor()


def none_if_blank(v):
    return v if v not in (None, "") else None


# ---------------------------------------------------------------------
# physical_locations
# ---------------------------------------------------------------------
with open(os.path.join(ROOT, "day4", "physical_locations.csv")) as f:
    rows = list(csv.DictReader(f))

for r in rows:
    normalized_address = r["matched_address"] or r["address_1"]
    geom_sql = None
    if r["lat"] and r["lon"]:
        geom_sql = f"ST_SetSRID(ST_MakePoint({r['lon']}, {r['lat']}), 4326)"
    cur.execute(f"""
        INSERT INTO physical_locations (
            physical_location_id, address_1, normalized_address, city, postal_code, county,
            npi_count, geom, geocode_status, geocode_quality, tract_geoid,
            geocoder_benchmark, geocoder_vintage,
            geocode_manual_review_required, dedup_manual_review_required
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, {geom_sql or 'NULL'}, %s, %s, %s, %s, %s, %s, %s)
    """, (
        r["physical_location_id"], r["address_1"], normalized_address, r["city"], r["postal_code"], r["county"],
        int(r["npi_count"]), r["match_indicator"], none_if_blank(r["match_type"]), none_if_blank(r["tract_geoid"]),
        r["geocoder_benchmark"], r["geocoder_vintage"],
        r["geocode_manual_review_required"] == "True", r["dedup_manual_review_required"] == "True",
    ))
print(f"physical_locations: loaded {len(rows)} rows")

# ---------------------------------------------------------------------
# pharmacies (join enumeration_date/last_updated from day8_prep - NOT
# present in wa_pharmacies_deduped.csv)
# ---------------------------------------------------------------------
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
print(f"pharmacies: loaded {len(rows)} rows ({missing_enum} missing an enumeration_date join)")

# ---------------------------------------------------------------------
# census_tracts (ACS attributes + TIGER geometry, joined by tract_geoid)
# ---------------------------------------------------------------------
with open(os.path.join(ROOT, "day4", "acs_wa_tracts_audited.csv")) as f:
    rows = list(csv.DictReader(f))

unmatched_geom = 0
for r in rows:
    cur.execute("""
        INSERT INTO census_tracts (
            tract_geoid, name, geometry, population, median_income,
            income_suppressed, population_missing, excluded_from_income_classification
        )
        SELECT %s, %s, t.geom, %s, %s, %s, %s, %s
        FROM (SELECT geom FROM tiger_tracts_raw WHERE geoid = %s) t
    """, (
        r["tract_geoid"], r["NAME"],
        none_if_blank(r["population"]), none_if_blank(r["median_household_income"]),
        r["income_suppressed"] == "True", r["population_missing"] == "True",
        r["excluded_from_income_classification"] == "True",
        r["tract_geoid"],
    ))
    if cur.rowcount == 0:
        unmatched_geom += 1
        # tract exists in ACS but not in TIGER geometry (or vice versa) - insert without geometry rather than drop the tract
        cur.execute("""
            INSERT INTO census_tracts (
                tract_geoid, name, geometry, population, median_income,
                income_suppressed, population_missing, excluded_from_income_classification
            ) VALUES (%s,%s,NULL,%s,%s,%s,%s,%s)
        """, (
            r["tract_geoid"], r["NAME"],
            none_if_blank(r["population"]), none_if_blank(r["median_household_income"]),
            r["income_suppressed"] == "True", r["population_missing"] == "True",
            r["excluded_from_income_classification"] == "True",
        ))
print(f"census_tracts: loaded {len(rows)} rows ({unmatched_geom} without a TIGER geometry match)")

# ---------------------------------------------------------------------
# pharmacy_snapshots (seeded from the enumeration backfill only)
# ---------------------------------------------------------------------
with open(os.path.join(ROOT, "day8_prep", "pharmacy_enumeration_backfill.csv")) as f:
    rows = list(csv.DictReader(f))

for r in rows:
    cur.execute("""
        INSERT INTO pharmacy_snapshots (snapshot_date, physical_location_id, snapshot_source,
                                         npi_count_at_location, contributing_npis)
        VALUES (%s, %s, 'backfilled_enumeration', %s, %s)
    """, (r["first_seen_date"], r["physical_location_id"], int(r["npi_count_at_location"]), r["contributing_npis"]))
print(f"pharmacy_snapshots: loaded {len(rows)} rows (source=backfilled_enumeration)")

# ---------------------------------------------------------------------
# shortages (loaded as-is, no expansion)
# ---------------------------------------------------------------------
with open(os.path.join(ROOT, "day8_prep", "shortage_intervals.csv")) as f:
    rows = list(csv.DictReader(f))

for r in rows:
    cur.execute("""
        INSERT INTO shortages (generic_name, tier, source_status, start_date, end_date,
                                n_package_variants, dosage_form, therapeutic_category)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        r["generic_name"], int(r["tier"]), r["source_status"], r["start_date"],
        none_if_blank(r["end_date"]), none_if_blank(r["n_package_variants"]),
        none_if_blank(r["dosage_form"]), none_if_blank(r["therapeutic_category"]),
    ))
print(f"shortages: loaded {len(rows)} rows")

conn.commit()
cur.close()
conn.close()
print("\nCommitted.")
