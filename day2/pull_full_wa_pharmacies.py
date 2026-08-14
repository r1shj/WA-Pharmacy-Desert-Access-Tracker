"""
Day 2, step 1: pull as much of the WA "Pharmacy" NPPES population as the
public API allows, and tabulate what pharmacy_type values actually exist.

The NPPES API caps total retrievable results per query at 1200
(skip max 1000 + limit max 200). This script paginates to that ceiling,
reports whether it was hit (i.e. WA has >1200 matching orgs and a
different pull strategy is needed), and writes every record plus a
taxonomy-code frequency table.
"""
import csv
import json
import os
import time
import urllib.parse
import urllib.request

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_URL = "https://npiregistry.cms.hhs.gov/api/"


def fetch_json(url):
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode())


def pull_all(taxonomy_description="Pharmacy", state="WA", enumeration_type="NPI-2"):
    all_results = []
    skip = 0
    limit = 200
    while True:
        params = {
            "version": "2.1",
            "state": state,
            "taxonomy_description": taxonomy_description,
            "enumeration_type": enumeration_type,
            "limit": limit,
            "skip": skip,
        }
        url = BASE_URL + "?" + urllib.parse.urlencode(params)
        data = fetch_json(url)
        results = data.get("results", [])
        all_results.extend(results)
        print(f"  skip={skip}: got {len(results)} (running total {len(all_results)})")
        if len(results) < limit:
            break
        skip += limit
        if skip > 1000:  # API hard ceiling: skip max 1000
            break
        time.sleep(0.2)
    hit_ceiling = skip > 1000 and len(results) == limit
    return all_results, hit_ceiling


if __name__ == "__main__":
    print("Pulling all WA org NPIs matching taxonomy_description='Pharmacy' ...")
    results, hit_ceiling = pull_all()
    print(f"\nTotal pulled: {len(results)}")
    if hit_ceiling:
        print("WARNING: hit the API's 1200-result ceiling. True population is larger; "
              "would need to partition by taxonomy code or county to get the rest.")

    raw_path = os.path.join(OUT_DIR, "wa_pharmacies_full_raw.json")
    with open(raw_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Wrote raw -> {raw_path}")

    # Taxonomy code/description frequency table
    tax_counts = {}
    for r in results:
        taxonomies = r.get("taxonomies", [])
        primary = next((t for t in taxonomies if t.get("primary")), taxonomies[0] if taxonomies else {})
        key = (primary.get("code", ""), primary.get("desc", ""))
        tax_counts[key] = tax_counts.get(key, 0) + 1

    print("\nPrimary taxonomy distribution:")
    for (code, desc), count in sorted(tax_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {count:4d}  {code:12s} {desc}")

    tax_path = os.path.join(OUT_DIR, "wa_pharmacy_taxonomy_counts.csv")
    with open(tax_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["taxonomy_code", "taxonomy_desc", "count"])
        for (code, desc), count in sorted(tax_counts.items(), key=lambda kv: -kv[1]):
            writer.writerow([code, desc, count])
    print(f"\nWrote taxonomy counts -> {tax_path}")

    # Full flattened CSV for downstream use
    flat_path = os.path.join(OUT_DIR, "wa_pharmacies_full_flat.csv")
    fieldnames = [
        "npi", "organization_name", "other_names", "address_1", "city", "state",
        "postal_code", "telephone_number", "primary_taxonomy_code",
        "primary_taxonomy_desc", "taxonomy_license",
        "authorized_official_first_name", "authorized_official_last_name",
        "last_updated_epoch", "enumeration_date", "certification_date", "status",
    ]
    with open(flat_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            basic = r.get("basic", {})
            addresses = r.get("addresses", [])
            location = next((a for a in addresses if a.get("address_purpose") == "LOCATION"), {})
            taxonomies = r.get("taxonomies", [])
            primary_tax = next((t for t in taxonomies if t.get("primary")), taxonomies[0] if taxonomies else {})
            other_names = r.get("other_names", [])
            dba = other_names[0].get("organization_name") if other_names else ""
            writer.writerow({
                "npi": r.get("number"),
                "organization_name": basic.get("organization_name"),
                "other_names": dba,
                "address_1": location.get("address_1"),
                "city": location.get("city"),
                "state": location.get("state"),
                "postal_code": location.get("postal_code"),
                "telephone_number": location.get("telephone_number"),
                "primary_taxonomy_code": primary_tax.get("code"),
                "primary_taxonomy_desc": primary_tax.get("desc"),
                "taxonomy_license": primary_tax.get("license"),
                "authorized_official_first_name": basic.get("authorized_official_first_name"),
                "authorized_official_last_name": basic.get("authorized_official_last_name"),
                "last_updated_epoch": basic.get("last_updated_epoch"),
                "enumeration_date": basic.get("enumeration_date"),
                "certification_date": basic.get("certification_date"),
                "status": basic.get("status"),
            })
    print(f"Wrote flattened -> {flat_path}")

    # Dump the raw "basic" block of the first record so we can see every
    # field NPPES actually returns (looking for status/deactivation fields).
    if results:
        print("\nFull 'basic' block of first record (checking for status/deactivation fields):")
        print(json.dumps(results[0].get("basic", {}), indent=2))
