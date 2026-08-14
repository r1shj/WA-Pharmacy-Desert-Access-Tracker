"""
Build a WA 5-digit ZIP -> county lookup from the Census Bureau's 2020
ZCTA-to-county relationship file. Some ZCTAs span more than one county;
for those, assign the county with the larger land-area overlap
(AREALAND_PART), which is the standard approach for a single-valued
zip->county crosswalk.
"""
import csv
import json
import os

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

if __name__ == "__main__":
    best = {}  # zip -> (arealand_part, county_name)
    with open(os.path.join(OUT_DIR, "zcta_county.txt"), encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter="|")
        for r in reader:
            if not r["GEOID_COUNTY_20"].startswith("53"):  # WA FIPS
                continue
            z = r["GEOID_ZCTA5_20"]
            if not z:
                continue
            area = int(r["AREALAND_PART"] or 0)
            county = r["NAMELSAD_COUNTY_20"]
            if z not in best or area > best[z][0]:
                best[z] = (area, county)

    crosswalk = {z: county for z, (area, county) in best.items()}
    out_path = os.path.join(OUT_DIR, "wa_zip_to_county.json")
    with open(out_path, "w") as f:
        json.dump(crosswalk, f, indent=2, sort_keys=True)
    print(f"Wrote {len(crosswalk)} zip->county mappings -> {out_path}")
    counties = sorted(set(crosswalk.values()))
    print(f"{len(counties)} distinct WA counties covered")
