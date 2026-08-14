"""
Exploratory pull from NPPES and Census ACS to see what fields are actually
available before building the real pipeline. Not the pipeline itself.

Usage:
    python3 explore_sources.py

Optional env var:
    CENSUS_API_KEY - Census works without a key for light use, but a free
    key (https://api.census.gov/data/key_signup.html) avoids rate limiting.
"""
import csv
import json
import os
import urllib.error
import urllib.parse
import urllib.request

OUT_DIR = os.path.dirname(os.path.abspath(__file__))


def fetch_json(url):
    with urllib.request.urlopen(url, timeout=30) as resp:
        body = resp.read().decode()
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        if "census.gov" in url and "missing_key" in body.lower() or "census.gov" in url and "<html" in body.lower():
            raise SystemExit(
                "Census API rejected the request - it now requires an API key.\n"
                "1. Get a free key: https://api.census.gov/data/key_signup.html\n"
                "2. Run again with: CENSUS_API_KEY=your_key python3 explore_sources.py"
            )
        raise


# ---------------------------------------------------------------------------
# 1. NPPES - pull a sample of WA pharmacies
# ---------------------------------------------------------------------------

def pull_nppes_sample(limit=20):
    params = {
        "version": "2.1",
        "state": "WA",
        "taxonomy_description": "Pharmacy",
        "enumeration_type": "NPI-2",  # organizations, not individual providers
        "limit": limit,
    }
    url = "https://npiregistry.cms.hhs.gov/api/?" + urllib.parse.urlencode(params)
    data = fetch_json(url)

    raw_path = os.path.join(OUT_DIR, "nppes_sample_raw.json")
    with open(raw_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"NPPES: wrote raw response ({data.get('result_count', 0)} results) -> {raw_path}")

    results = data.get("results", [])
    flat_path = os.path.join(OUT_DIR, "nppes_sample_flat.csv")
    fieldnames = [
        "npi",
        "organization_name",
        "other_names",  # DBA name, if any - potential chain signal
        "address_1",
        "city",
        "state",
        "postal_code",
        "telephone_number",
        "primary_taxonomy_code",
        "primary_taxonomy_desc",
        "taxonomy_license",
        "authorized_official_first_name",
        "authorized_official_last_name",
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
            })
    print(f"NPPES: wrote flattened sample -> {flat_path}")
    return results


# ---------------------------------------------------------------------------
# 2. Census ACS - pull income + population by tract for WA (state FIPS 53)
# ---------------------------------------------------------------------------

def pull_acs_sample(year=2022, sample_size=20):
    api_key = os.environ.get("CENSUS_API_KEY")
    params = {
        "get": "NAME,B19013_001E,B01003_001E",
        "for": "tract:*",
        "in": "state:53",
    }
    if api_key:
        params["key"] = api_key
    url = f"https://api.census.gov/data/{year}/acs/acs5?" + urllib.parse.urlencode(params)
    data = fetch_json(url)  # list of lists, first row is header

    raw_path = os.path.join(OUT_DIR, "acs_sample_raw.json")
    with open(raw_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"ACS: wrote raw response ({len(data) - 1} tracts total) -> {raw_path}")

    header, rows = data[0], data[1:]
    sample_rows = rows[:sample_size]

    flat_path = os.path.join(OUT_DIR, "acs_sample_flat.csv")
    with open(flat_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(sample_rows)
    print(f"ACS: wrote flattened sample ({len(sample_rows)} rows) -> {flat_path}")
    return header, sample_rows


if __name__ == "__main__":
    print("=== NPPES sample ===")
    pull_nppes_sample()
    print("\n=== ACS sample ===")
    pull_acs_sample()
