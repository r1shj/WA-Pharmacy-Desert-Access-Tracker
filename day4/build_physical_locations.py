"""
Day 4: the canonical physical_locations table for Day 5 - one row per
physical_location_id (1,811 rows), combining Day 3's dedup rollup with
Day 4's geocoding results.

Two DISTINCT manual_review_required-style flags are kept, deliberately
not merged into one column, because they mean different things:
  - dedup_manual_review_required: from Day 3 - this address was shared by
    NPIs that didn't cleanly auto-collapse (an ownership/identity
    ambiguity).
  - geocode_manual_review_required: from Day 4 - the Census geocoder
    didn't return a clean Exact match for this address (a geocoding
    confidence issue). Also true for the 89 addresses with no usable
    coordinates at all (Tie or No_Match).
A location can be flagged by either, both, or neither independently.
"""
import csv
import os
from collections import defaultdict

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

if __name__ == "__main__":
    deduped = list(csv.DictReader(open(os.path.join(OUT_DIR, "..", "day3", "wa_pharmacies_deduped.csv"))))
    geocoded = {r["physical_location_id"]: r
                for r in csv.DictReader(open(os.path.join(OUT_DIR, "physical_locations_geocoded.csv")))}

    by_loc = defaultdict(list)
    for r in deduped:
        by_loc[r["physical_location_id"]].append(r)

    fieldnames = [
        "physical_location_id", "address_1", "city", "postal_code", "county",
        "npi_count", "dedup_manual_review_required",
        "match_indicator", "match_type", "matched_address", "lat", "lon",
        "tract_geoid", "county_fips", "geocoder_benchmark", "geocoder_vintage",
        "geocode_manual_review_required",
    ]
    out_rows = []
    for loc_id, members in by_loc.items():
        rep = members[0]
        g = geocoded.get(loc_id, {})
        out_rows.append({
            "physical_location_id": loc_id,
            "address_1": rep["address_1"],
            "city": rep["city"],
            "postal_code": rep["postal_code"],
            "county": rep["county"],
            "npi_count": len(members),
            "dedup_manual_review_required": rep["manual_review_required"],
            "match_indicator": g.get("match_indicator", ""),
            "match_type": g.get("match_type", ""),
            "matched_address": g.get("matched_address", ""),
            "lat": g.get("lat", ""),
            "lon": g.get("lon", ""),
            "tract_geoid": g.get("tract_geoid", ""),
            "county_fips": g.get("county_fips", ""),
            "geocoder_benchmark": g.get("geocoder_benchmark", ""),
            "geocoder_vintage": g.get("geocoder_vintage", ""),
            "geocode_manual_review_required": g.get("geocode_manual_review_required", ""),
        })

    out_path = os.path.join(OUT_DIR, "physical_locations.csv")
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    both_flagged = sum(1 for r in out_rows
                        if r["dedup_manual_review_required"] == "True" and r["geocode_manual_review_required"] == "True")
    either_flagged = sum(1 for r in out_rows
                          if r["dedup_manual_review_required"] == "True" or str(r["geocode_manual_review_required"]) == "True")
    print(f"Wrote {len(out_rows)} rows -> {out_path}")
    print(f"Locations flagged by BOTH dedup and geocode review: {both_flagged}")
    print(f"Locations flagged by EITHER: {either_flagged}")
