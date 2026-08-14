"""
Pulls pharmacy-taxonomy NPPES records for the 132 OR/ID zip codes within
~20mi of the WA border (or_id_border_zctas.csv), applying the same
lesson learned in Day 2: the API's postal_code param matches ANY address
on a record (including MAILING), so results are filtered to a genuine
LOCATION.state in ('OR','ID') before being trusted.
"""
import csv
import json
import os
import time
import urllib.parse
import urllib.request

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_URL = "https://npiregistry.cms.hhs.gov/api/"


def fetch_json(url, retries=3):
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                return json.loads(resp.read().decode())
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(0.5)


def query_zip(zip_code):
    all_results = []
    skip = 0
    while True:
        params = {"version": "2.1", "postal_code": zip_code, "taxonomy_description": "Pharmacy",
                  "enumeration_type": "NPI-2", "limit": 200, "skip": skip}
        data = fetch_json(BASE_URL + "?" + urllib.parse.urlencode(params))
        results = data.get("results", [])
        all_results.extend(results)
        if len(results) < 200:
            break
        skip += 200
    return all_results


if __name__ == "__main__":
    with open(os.path.join(OUT_DIR, "or_id_border_zctas.csv")) as f:
        zips = [r["zcta"] for r in csv.DictReader(f)]

    by_npi = {}
    for i, z in enumerate(zips, 1):
        results = query_zip(z)
        for r in results:
            by_npi[r["number"]] = r
        if results:
            print(f"[{i}/{len(zips)}] zip {z}: {len(results)} raw results")

    print(f"\n{len(by_npi)} unique raw NPIs across all border zips (before LOCATION.state filter)")

    filtered = []
    for r in by_npi.values():
        addresses = r.get("addresses", [])
        location = next((a for a in addresses if a.get("address_purpose") == "LOCATION"), {})
        if location.get("state") in ("OR", "ID"):
            filtered.append(r)

    print(f"{len(filtered)} confirmed true OR/ID LOCATION addresses (dropped {len(by_npi) - len(filtered)} false positives)")

    with open(os.path.join(OUT_DIR, "border_pharmacies_raw.json"), "w") as f:
        json.dump(filtered, f, indent=2)
    print(f"Wrote border_pharmacies_raw.json")
