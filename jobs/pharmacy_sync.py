"""
Daily NPPES re-sweep: records which known WA pharmacy locations still
have an active NPI today, as a real `observed` pharmacy_snapshots row.

This replaces day8_prep/snapshot_pharmacies_today.py, which re-saved the
static Day 3 CSV every day and so never observed anything (DECISIONS.md
2026-10-15). Here every run re-queries the NPPES registry from scratch,
using the same population definition as Day 2:

  - every 5-digit ZIP in WA's USPS range (98001-99403), because one
    statewide query caps at 1,200 results
  - taxonomy "Pharmacy", organization NPIs (NPI-2)
  - kept only if the LOCATION address is in WA (the postal_code filter
    also matches mailing addresses - DAY2_ADDENDUM)

Each known NPI (the `pharmacies` table) is then classified:

  active       found, WA LOCATION, same ZIP, pharmacy taxonomy -> counts
  deactivated  missing from the sweep AND a direct lookup by number
               returns nothing (the API only serves active NPIs)
  relocated    active but its LOCATION moved to another ZIP or out of WA
  retaxonomied active, same place, but no longer a pharmacy taxonomy

A location appears in today's snapshot if at least one of its NPIs is
active. Brand-new NPIs aren't classified or geocoded automatically - they
go to npi_review_queue (DECISIONS.md 2026-10-15).

Never writes a partial picture: any ZIP that fails after retries, a ZIP
over the API's 1,200 cap, or a suspicious mass disappearance aborts the
run before anything is written.
"""
import concurrent.futures
import http.client
import json
import os
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "day3"))
from normalize_address import normalize_address  # noqa: E402

NPPES_URL = "https://npiregistry.cms.hhs.gov/api/"
ZIP_LOW, ZIP_HIGH = 98001, 99403  # inclusive; USPS-assigned WA range
PAGE_SIZE = 200
MAX_SKIP = 1000  # API maximum: skip 1000 + limit 200 = 1,200 results
MAX_WORKERS = 8

# Known NPIs missing from the sweep each need a direct lookup. More than
# this fraction missing means the sweep itself is broken (e.g. the API
# returning empty pages), not that pharmacies vanished - abort instead of
# making thousands of lookups.
MAX_MISSING_FRACTION = 0.10
# Pharmacy locations close slowly. A day where more than this fraction of
# the previous snapshot's locations disappear is a data problem until a
# human says otherwise (--allow-large-drop after review).
MAX_LOCATION_DROP_FRACTION = 0.03


class SweepFailed(Exception):
    pass


class SuspiciousSweep(Exception):
    pass


def _get(params, retries=4):
    url = NPPES_URL + "?" + urllib.parse.urlencode({"version": "2.1", **params})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except (OSError, http.client.HTTPException, json.JSONDecodeError):
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)


def _query_zip(zip_code):
    results, skip = [], 0
    while True:
        page = _get({
            "postal_code": zip_code,
            "taxonomy_description": "Pharmacy",
            "enumeration_type": "NPI-2",
            "limit": PAGE_SIZE,
            "skip": skip,
        })
        if "Errors" in page:
            raise SweepFailed(f"zip {zip_code}: {page['Errors']}")
        batch = page.get("results", [])
        results.extend(batch)
        if len(batch) < PAGE_SIZE:
            return results
        skip += PAGE_SIZE
        if skip > MAX_SKIP:
            raise SweepFailed(f"zip {zip_code} exceeds the API's 1,200-result cap")


def location_address(record):
    return next((a for a in record.get("addresses", [])
                 if a.get("address_purpose") == "LOCATION"), {})


def has_pharmacy_taxonomy(record):
    return any("Pharmacy" in (t.get("desc") or "") for t in record.get("taxonomies", []))


def sweep():
    """All pharmacy-taxonomy organization NPIs with a WA LOCATION address,
    keyed by NPI. Raises SweepFailed if any ZIP couldn't be fully read."""
    zips = [str(z) for z in range(ZIP_LOW, ZIP_HIGH + 1)]
    by_npi, failures = {}, []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_query_zip, z): z for z in zips}
        for fut in concurrent.futures.as_completed(futures):
            try:
                for r in fut.result():
                    by_npi[str(r["number"])] = r
            except Exception as e:  # noqa: BLE001 - every failure aborts the run
                failures.append(f"{futures[fut]}: {e}")
    if failures:
        raise SweepFailed(f"{len(failures)} of {len(zips)} ZIPs failed, e.g. {failures[:3]}")
    return {npi: r for npi, r in by_npi.items()
            if location_address(r).get("state") == "WA"}, len(zips)


def lookup_npis(npis):
    """Direct lookup by number. Returns {npi: record or None}; None means
    NPPES no longer serves it (deactivated). Raises if a lookup fails -
    a failed lookup must not be mistaken for a deactivation."""
    def one(npi):
        page = _get({"number": npi})
        if "Errors" in page:
            raise SweepFailed(f"lookup {npi}: {page['Errors']}")
        results = page.get("results", [])
        return npi, (results[0] if results else None)
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        return dict(pool.map(one, npis))


def load_known(cur):
    cur.execute("""
        SELECT p.npi, p.physical_location_id, l.postal_code, l.address_1
        FROM pharmacies p JOIN physical_locations l USING (physical_location_id)
    """)
    return {r[0]: {"location_id": r[1], "postal5": (r[2] or "")[:5], "address_1": r[3]}
            for r in cur.fetchall()}


def classify(known, swept, lookups):
    """Pure decision step, no I/O. Returns active NPIs per location plus
    every known NPI that isn't counted, with the reason."""
    active_by_location, outcomes = {}, {
        "deactivated": [], "relocated": [], "retaxonomied": [], "address_changed_same_zip": []}
    for npi, k in known.items():
        rec = swept.get(npi) or lookups.get(npi)
        if rec is None:
            outcomes["deactivated"].append(npi)
            continue
        loc = location_address(rec)
        if loc.get("state") != "WA" or (loc.get("postal_code") or "")[:5] != k["postal5"]:
            outcomes["relocated"].append({
                "npi": npi, "from_location": k["location_id"],
                "to": f"{loc.get('address_1')}, {loc.get('city')}, {loc.get('state')} {(loc.get('postal_code') or '')[:5]}"})
            continue
        if not has_pharmacy_taxonomy(rec):
            outcomes["retaxonomied"].append(npi)
            continue
        if normalize_address(loc.get("address_1")) != normalize_address(k["address_1"]):
            # Same ZIP, different street text: usually a formatting edit,
            # sometimes a move down the street. Counted, but surfaced.
            outcomes["address_changed_same_zip"].append(npi)
        active_by_location.setdefault(k["location_id"], []).append(npi)
    return active_by_location, outcomes


def _previous_observed(cur, obs_date):
    cur.execute("""
        SELECT snapshot_date, count(*) FROM pharmacy_snapshots
        WHERE snapshot_source = 'observed' AND snapshot_date < %s
        GROUP BY snapshot_date ORDER BY snapshot_date DESC LIMIT 1
    """, (obs_date,))
    row = cur.fetchone()
    return (row[0].isoformat(), row[1]) if row else (None, None)


def run(cur, obs_date, allow_large_drop=False, log=print):
    """Sweep NPPES and write today's observed snapshot + review queue.
    Returns a summary dict. Caller commits; raises before writing if
    anything looks incomplete."""
    t0 = time.time()
    swept, n_zips = sweep()
    log(f"  sweep: {len(swept)} WA-located pharmacy NPIs across {n_zips} ZIPs ({time.time() - t0:.0f}s)")

    known = load_known(cur)
    missing = sorted(set(known) - set(swept))
    if known and len(missing) / len(known) > MAX_MISSING_FRACTION:
        raise SuspiciousSweep(
            f"{len(missing)} of {len(known)} known NPIs missing from the sweep "
            f"(> {MAX_MISSING_FRACTION:.0%}) - sweep is likely incomplete")
    lookups = lookup_npis(missing)
    log(f"  direct lookups for {len(missing)} known NPIs missing from the sweep")

    active_by_location, outcomes = classify(known, swept, lookups)
    prev_date, prev_count = _previous_observed(cur, obs_date)
    if prev_count and not allow_large_drop:
        drop = (prev_count - len(active_by_location)) / prev_count
        if drop > MAX_LOCATION_DROP_FRACTION:
            raise SuspiciousSweep(
                f"{len(active_by_location)} locations active vs {prev_count} on {prev_date} "
                f"({drop:.1%} drop > {MAX_LOCATION_DROP_FRACTION:.0%}) - review, then rerun "
                f"with --allow-large-drop if real")

    new_npis = sorted(set(swept) - set(known))

    # Idempotent: a rerun on the same day replaces that day's snapshot.
    cur.execute("DELETE FROM pharmacy_snapshots WHERE snapshot_source = 'observed' AND snapshot_date = %s",
                (obs_date,))
    for loc_id, npis in sorted(active_by_location.items()):
        cur.execute("""
            INSERT INTO pharmacy_snapshots (snapshot_date, physical_location_id, snapshot_source,
                npi_count_at_location, contributing_npis)
            VALUES (%s, %s, 'observed', %s, %s)
        """, (obs_date, loc_id, len(npis), ";".join(sorted(npis))))

    for npi in new_npis:
        r = swept[npi]
        loc = location_address(r)
        primary = next((t for t in r.get("taxonomies", []) if t.get("primary")),
                       (r.get("taxonomies") or [{}])[0])
        other = r.get("other_names") or [{}]
        cur.execute("""
            INSERT INTO npi_review_queue (npi, organization_name, dba_name, address_1, city,
                postal_code, primary_taxonomy_code, primary_taxonomy_desc,
                first_seen_date, last_seen_date)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (npi) DO UPDATE SET
                organization_name = EXCLUDED.organization_name, dba_name = EXCLUDED.dba_name,
                address_1 = EXCLUDED.address_1, city = EXCLUDED.city,
                postal_code = EXCLUDED.postal_code,
                primary_taxonomy_code = EXCLUDED.primary_taxonomy_code,
                primary_taxonomy_desc = EXCLUDED.primary_taxonomy_desc,
                last_seen_date = EXCLUDED.last_seen_date
        """, (npi, r.get("basic", {}).get("organization_name"), other[0].get("organization_name"),
              loc.get("address_1"), loc.get("city"), (loc.get("postal_code") or "")[:5],
              primary.get("code"), primary.get("desc"), obs_date, obs_date))

    return {
        "zips_swept": n_zips,
        "wa_npis_in_sweep": len(swept),
        "known_npis": len(known),
        "known_npis_active": sum(len(v) for v in active_by_location.values()),
        "locations_active": len(active_by_location),
        "previous_observed_date": prev_date,
        "previous_locations_active": prev_count,
        "direct_lookups": len(missing),
        "deactivated": outcomes["deactivated"],
        "relocated": outcomes["relocated"],
        "retaxonomied": outcomes["retaxonomied"],
        "address_changed_same_zip": outcomes["address_changed_same_zip"],
        "new_npis_queued": len(new_npis),
        "seconds": round(time.time() - t0),
    }
