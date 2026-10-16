"""
Combine the complete zip-swept WA pharmacy pull (3,364 NPIs) with the Day 2
pharmacy_type classification rules and the zip->county crosswalk into one
final CSV. Also prints summary counts (overall, by pharmacy_type, by
county) so we can sanity-check the complete pull against the earlier
1,200-capped sample.
"""
import csv
import json
import os
import sys

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, OUT_DIR)
from classify_pharmacy_type import classify, output_organization_name  # noqa: E402

if __name__ == "__main__":
    with open(os.path.join(OUT_DIR, "wa_pharmacies_true_location_raw.json")) as f:
        records = json.load(f)
    with open(os.path.join(OUT_DIR, "wa_zip_to_county.json")) as f:
        zip_to_county = json.load(f)

    out_path = os.path.join(OUT_DIR, "wa_pharmacies_final.csv")
    fieldnames = [
        "npi", "organization_name", "other_names", "address_1", "city",
        "postal_code", "county",
        "primary_taxonomy_code", "primary_taxonomy_desc",
        "pharmacy_type", "walk_in_access", "included_in_access_analysis", "exclusion_reason",
    ]

    county_counts = {}
    type_counts = {}
    unmatched_zip = 0
    included_total = 0

    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            basic = r.get("basic", {})
            addresses = r.get("addresses", [])
            location = next((a for a in addresses if a.get("address_purpose") == "LOCATION"), {})
            taxonomies = r.get("taxonomies", [])
            primary = next((t for t in taxonomies if t.get("primary")), taxonomies[0] if taxonomies else {})
            other_names = r.get("other_names", [])
            dba = other_names[0].get("organization_name") if other_names else ""

            postal = (location.get("postal_code") or "")[:5]
            county = zip_to_county.get(postal, "")
            if not county:
                unmatched_zip += 1

            pharmacy_type, walk_in, included, reason = classify(r)
            if included:
                included_total += 1

            county_counts.setdefault(county or "UNKNOWN", {"total": 0, "included": 0})
            county_counts[county or "UNKNOWN"]["total"] += 1
            if included:
                county_counts[county or "UNKNOWN"]["included"] += 1

            type_counts[pharmacy_type] = type_counts.get(pharmacy_type, 0) + 1

            writer.writerow({
                "npi": r.get("number"),
                "organization_name": output_organization_name(r),
                "other_names": dba,
                "address_1": location.get("address_1"),
                "city": location.get("city"),
                "postal_code": postal,
                "county": county,
                "primary_taxonomy_code": primary.get("code"),
                "primary_taxonomy_desc": primary.get("desc"),
                "pharmacy_type": pharmacy_type,
                "walk_in_access": walk_in,
                "included_in_access_analysis": included,
                "exclusion_reason": reason,
            })

    print(f"Total records: {len(records)}")
    print(f"Included in access analysis: {included_total}")
    print(f"Records with unmatched zip->county (not found in crosswalk): {unmatched_zip}")
    print(f"\nDistinct counties represented: {len([c for c in county_counts if c != 'UNKNOWN'])}")
    print(f"\npharmacy_type distribution:")
    for t, c in sorted(type_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {c:4d}  {t}")
    print(f"\nCounty breakdown (total / included_in_access_analysis):")
    for county, counts in sorted(county_counts.items(), key=lambda kv: -kv[1]["total"]):
        print(f"  {counts['total']:4d} / {counts['included']:4d}  {county}")
    print(f"\nWrote {out_path}")
