"""
Day 4, part 1: parse the Census Batch Geocoder's variable-width CSV
response into a clean table with match_type, matched_address, lat/lon,
tract_geoid, and the geocoder's own benchmark/vintage - kept as a
separate manual_review_required flag from Day 3's dedup flag of the same
name, since they mean different things (dedup ambiguity vs. geocode
failure) and shouldn't be collapsed into one column.
"""
import csv
import os

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
BENCHMARK = "Public_AR_Current"
VINTAGE = "Census2020_Current"

if __name__ == "__main__":
    with open(os.path.join(OUT_DIR, "geocode_output_raw.csv")) as f:
        reader = csv.reader(f)
        raw_rows = list(reader)

    print(f"Parsed {len(raw_rows)} response rows")

    # match_indicator (field 3) has THREE possible values, not two -
    # "Match", "No_Match", "Tie". Confirmed empirically before writing this
    # parser (see DECISIONS.md): "Tie" means the geocoder found multiple
    # equally-plausible candidates and could not pick one - it is not a
    # subtype of "Match" and, like No_Match, carries no address/coordinate/
    # geography fields at all (only 3 columns in that row, same shape as
    # No_Match). match_type ("Exact" vs "Non_Exact") only exists on rows
    # where match_indicator=="Match".
    parsed = []
    for row in raw_rows:
        physical_location_id = row[0]
        input_address = row[1]
        match_indicator = row[2]

        if match_indicator == "Match":
            match_type = row[3]           # "Exact" or "Non_Exact"
            matched_address = row[4]
            lon, lat = row[5].split(",")
            state_fips, county_fips, tract, block = row[8], row[9], row[10], row[11]
            tract_geoid = f"{state_fips}{county_fips}{tract}"
            parsed.append({
                "physical_location_id": physical_location_id,
                "input_address": input_address,
                "match_indicator": match_indicator,
                "match_type": match_type,
                "matched_address": matched_address,
                "lat": lat,
                "lon": lon,
                "tract_geoid": tract_geoid,
                "county_fips": county_fips,
                "geocoder_benchmark": BENCHMARK,
                "geocoder_vintage": VINTAGE,
                "geocode_manual_review_required": match_type != "Exact",
            })
        else:
            # No_Match or Tie - neither has usable geography/coordinates.
            parsed.append({
                "physical_location_id": physical_location_id,
                "input_address": input_address,
                "match_indicator": match_indicator,
                "match_type": "",
                "matched_address": "",
                "lat": "",
                "lon": "",
                "tract_geoid": "",
                "county_fips": "",
                "geocoder_benchmark": BENCHMARK,
                "geocoder_vintage": VINTAGE,
                "geocode_manual_review_required": True,
            })

    fieldnames = ["physical_location_id", "input_address", "match_indicator", "match_type",
                  "matched_address", "lat", "lon", "tract_geoid", "county_fips",
                  "geocoder_benchmark", "geocoder_vintage", "geocode_manual_review_required"]

    out_path = os.path.join(OUT_DIR, "physical_locations_geocoded.csv")
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(parsed)
    print(f"Wrote {out_path}")

    exact = sum(1 for p in parsed if p["match_type"] == "Exact")
    non_exact = sum(1 for p in parsed if p["match_type"] == "Non_Exact")
    tie = sum(1 for p in parsed if p["match_indicator"] == "Tie")
    no_match = sum(1 for p in parsed if p["match_indicator"] == "No_Match")
    total = len(parsed)

    print(f"\nTotal submitted: {total}")
    print(f"  Exact matches:     {exact:5d} ({exact/total*100:.1f}%)")
    print(f"  Non-exact matches: {non_exact:5d} ({non_exact/total*100:.1f}%)  (geocoder resolved to one best candidate, not a perfect string match)")
    print(f"  Tie:               {tie:5d} ({tie/total*100:.1f}%)  (multiple equally-plausible candidates, geocoder could not pick one - NOT a subtype of Match)")
    print(f"  No match:          {no_match:5d} ({no_match/total*100:.1f}%)")
    print(f"  Overall match rate (Exact + Non_Exact, i.e. any usable coordinates): {(exact+non_exact)/total*100:.1f}%")

    # Both Tie and No_Match carry zero usable coordinates - export both,
    # not just No_Match, with a reason column so the two failure modes
    # stay distinguishable rather than being silently merged.
    unmatched = [p for p in parsed if p["match_indicator"] in ("No_Match", "Tie")]
    unmatched_path = os.path.join(OUT_DIR, "geocode_unmatched.csv")
    with open(unmatched_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["physical_location_id", "input_address", "reason"])
        writer.writeheader()
        for p in unmatched:
            writer.writerow({"physical_location_id": p["physical_location_id"],
                              "input_address": p["input_address"],
                              "reason": p["match_indicator"]})
    print(f"\nWrote {len(unmatched)} unmatched/tied addresses ({no_match} No_Match + {tie} Tie) -> {unmatched_path}")
