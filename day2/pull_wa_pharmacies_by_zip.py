"""
Day 2 follow-up: get past the NPPES API's 1,200-result cap for a single
state-wide query. WA's ZIP codes fall entirely in the range 98001-99403
(a USPS-assigned range, not something we're inferring from an incomplete
city list), so we partition the pull by every 5-digit code in that range
and dedupe by NPI. This is exhaustive by construction: if a pharmacy has a
WA ZIP code, some call in this sweep will hit it - not dependent on any
city-name list being complete, and not dependent on the "state" field
being filled in consistently on the org record.

The postal_code parameter requires an EXACT 5-digit match (confirmed:
prefix search returns 0 results), so we can't collapse this into fewer,
broader calls.

Checkpoints progress to disk so a partial run can resume instead of
re-querying zips already covered.
"""
import concurrent.futures
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_URL = "https://npiregistry.cms.hhs.gov/api/"
CHECKPOINT_PATH = os.path.join(OUT_DIR, "zip_sweep_checkpoint.json")
RESULTS_PATH = os.path.join(OUT_DIR, "wa_pharmacies_by_zip_raw.json")

ZIP_LOW, ZIP_HIGH = 98001, 99403  # inclusive; USPS-assigned WA range
MAX_WORKERS = 10

lock = threading.Lock()


def fetch_json(url, retries=3):
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as e:
            if attempt == retries - 1:
                raise
            time.sleep(0.5 * (attempt + 1))


def query_zip(zip_code):
    """Paginate a single ZIP fully. Returns (zip_code, results, hit_cap)."""
    all_results = []
    skip = 0
    limit = 200
    while True:
        params = {
            "version": "2.1",
            "postal_code": zip_code,
            "taxonomy_description": "Pharmacy",
            "enumeration_type": "NPI-2",
            "limit": limit,
            "skip": skip,
        }
        url = BASE_URL + "?" + urllib.parse.urlencode(params)
        data = fetch_json(url)
        results = data.get("results", [])
        all_results.extend(results)
        if len(results) < limit:
            break
        skip += limit
        if skip > 1000:
            return zip_code, all_results, True  # hit the cap - would need further splitting
    return zip_code, all_results, False


def load_checkpoint():
    if os.path.exists(CHECKPOINT_PATH):
        with open(CHECKPOINT_PATH) as f:
            return json.load(f)
    return {"done_zips": [], "results_by_npi": {}, "overflow_zips": []}


def save_checkpoint(state):
    with open(CHECKPOINT_PATH, "w") as f:
        json.dump(state, f)


if __name__ == "__main__":
    state = load_checkpoint()
    done = set(state["done_zips"])
    results_by_npi = state["results_by_npi"]
    overflow_zips = set(state["overflow_zips"])

    all_zips = [str(z) for z in range(ZIP_LOW, ZIP_HIGH + 1)]
    todo = [z for z in all_zips if z not in done]
    print(f"Total candidate zips: {len(all_zips)}  already done: {len(done)}  remaining: {len(todo)}")

    processed_since_save = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(query_zip, z): z for z in todo}
        for i, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            zip_code = futures[fut]
            try:
                zc, results, hit_cap = fut.result()
            except Exception as e:
                print(f"  ERROR on zip {zip_code}: {e} - will retry next run")
                continue
            with lock:
                for r in results:
                    results_by_npi[r["number"]] = r
                done.add(zc)
                if hit_cap:
                    overflow_zips.add(zc)
                    print(f"  WARNING: zip {zc} hit the 1200 cap itself - needs sub-partitioning")
                processed_since_save += 1
            if results:
                print(f"  [{i}/{len(todo)}] zip {zc}: {len(results)} results")
            if processed_since_save >= 50:
                with lock:
                    save_checkpoint({
                        "done_zips": sorted(done),
                        "results_by_npi": results_by_npi,
                        "overflow_zips": sorted(overflow_zips),
                    })
                processed_since_save = 0
                print(f"  --- checkpoint saved: {len(done)}/{len(all_zips)} zips done, {len(results_by_npi)} unique NPIs so far ---")

    save_checkpoint({
        "done_zips": sorted(done),
        "results_by_npi": results_by_npi,
        "overflow_zips": sorted(overflow_zips),
    })

    print(f"\nDone. {len(done)}/{len(all_zips)} zips covered. {len(results_by_npi)} unique pharmacy NPIs found.")
    if overflow_zips:
        print(f"Zips that hit the cap and need sub-partitioning: {sorted(overflow_zips)}")

    with open(RESULTS_PATH, "w") as f:
        json.dump(list(results_by_npi.values()), f, indent=2)
    print(f"Wrote {RESULTS_PATH}")
