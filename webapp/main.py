"""
Shared FastAPI backend for both map pages (Day 7: /map/pharmacy, Day 8:
/map/shortages). One app, one set of DB helpers, one static-file mount -
Day 8 adds routes here rather than starting a second backend.
"""
import datetime
import json
import os

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

APP_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="Pharmacy Access & Shortage Tracker")
app.mount("/static", StaticFiles(directory=os.path.join(APP_DIR, "static")), name="static")


def db():
    return psycopg2.connect(dbname="pharmacy_tracker", cursor_factory=psycopg2.extras.RealDictCursor)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.get("/map/pharmacy")
def map_pharmacy_page():
    return FileResponse(os.path.join(APP_DIR, "static", "pharmacy_map.html"))


@app.get("/map/shortages")
def map_shortages_page():
    return FileResponse(os.path.join(APP_DIR, "static", "shortage_map.html"))


# ---------------------------------------------------------------------------
# API - pharmacy map (Day 7)
# ---------------------------------------------------------------------------

@app.get("/api/pharmacy/config")
def pharmacy_config():
    """Slider bounds + the backfill/observed transition point, computed
    from the real data rather than hardcoded, so this stays correct once
    Day 8 starts loading more observed dates."""
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT snapshot_source, min(snapshot_date) AS min_date, max(snapshot_date) AS max_date
        FROM pharmacy_snapshots GROUP BY snapshot_source
    """)
    rows = {r["snapshot_source"]: r for r in cur.fetchall()}
    cur.close()
    conn.close()

    backfill = rows.get("backfilled_enumeration")
    observed = rows.get("observed")
    return {
        "slider_min_date": backfill["min_date"].isoformat() if backfill else None,
        "slider_max_date": datetime.date.today().isoformat(),
        "last_backfilled_date": backfill["max_date"].isoformat() if backfill else None,
        "observed_dates_available": [observed["min_date"].isoformat()] if observed else [],
    }


@app.get("/api/pharmacy/block-groups")
def block_groups_geojson():
    """Static desert-classification choropleth - does not change with the
    date slider (ACS/geocoded data doesn't change day to day)."""
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT geoid, pharmacy_desert_status, is_urban, income_status,
               population, nearest_pharmacy_miles, distance_threshold_miles,
               ST_AsGeoJSON(ST_SimplifyPreserveTopology(polygon_geom, 0.0005)) AS geom
        FROM census_block_groups
        WHERE polygon_geom IS NOT NULL
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    features = []
    for r in rows:
        features.append({
            "type": "Feature",
            "geometry": json.loads(r["geom"]),
            "properties": {
                "geoid": r["geoid"],
                "pharmacy_desert_status": r["pharmacy_desert_status"],
                "is_urban": r["is_urban"],
                "income_status": r["income_status"],
                "population": r["population"],
                "nearest_pharmacy_miles": float(r["nearest_pharmacy_miles"]) if r["nearest_pharmacy_miles"] is not None else None,
                "distance_threshold_miles": float(r["distance_threshold_miles"]) if r["distance_threshold_miles"] is not None else None,
            },
        })
    return JSONResponse({"type": "FeatureCollection", "features": features})


@app.get("/api/pharmacy/pharmacies")
def pharmacies_geojson(date: str = Query(default=None, description="YYYY-MM-DD; defaults to today")):
    """
    WA pharmacy points, filtered to locations that (a) existed by the
    requested date per pharmacy_snapshots and (b) have at least one
    pharmacy that is either confirmed-included OR still in the REVIEW
    bucket (walk_in_access='unknown'). Definitively-excluded-only
    locations (long_term_care, mail_order, etc. with no included/review
    pharmacy) are the only ones left out - per the standing project rule,
    REVIEW records are carried forward with a flag, never silently
    dropped (see DECISIONS.md - a location-only-has-REVIEW-pharmacies bug
    was found and fixed here). `review_only` tells the frontend to render
    these visually distinct rather than blend them into confirmed
    markers. Attributes shown (ownership_category, pharmacy_type, etc.)
    are always CURRENT values - we don't have historical attribute
    snapshots, only historical existence. That's a real, separate
    limitation surfaced in the UI, not just here.
    """
    query_date = date or datetime.date.today().isoformat()

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        WITH existed AS (
            SELECT physical_location_id, MIN(snapshot_date) AS first_date
            FROM pharmacy_snapshots
            GROUP BY physical_location_id
        ),
        loc_pharmacies AS (
            SELECT physical_location_id,
                   json_agg(json_build_object(
                       'npi', npi,
                       'organization_name', organization_name,
                       'dba_name', dba_name,
                       'ownership_category', ownership_category,
                       'parent_organization', parent_organization,
                       'pharmacy_type', pharmacy_type,
                       'included_in_access_analysis', included_in_access_analysis,
                       'walk_in_access', walk_in_access
                   ) ORDER BY npi) AS pharmacies,
                   COALESCE(
                       (array_agg(ownership_category ORDER BY npi) FILTER (WHERE included_in_access_analysis))[1],
                       (array_agg(ownership_category ORDER BY npi))[1]
                   ) AS primary_ownership_category,
                   NOT bool_or(included_in_access_analysis) AS review_only
            FROM pharmacies
            WHERE included_in_access_analysis = TRUE OR walk_in_access = 'unknown'
            GROUP BY physical_location_id
        )
        SELECT l.physical_location_id, l.address_1, l.city,
               ST_X(l.geom) AS lon, ST_Y(l.geom) AS lat,
               lp.pharmacies, lp.primary_ownership_category, lp.review_only
        FROM physical_locations l
        JOIN existed e ON e.physical_location_id = l.physical_location_id
        JOIN loc_pharmacies lp ON lp.physical_location_id = l.physical_location_id
        WHERE e.first_date <= %s AND l.geom IS NOT NULL
    """, (query_date,))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    features = [{
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
        "properties": {
            "physical_location_id": r["physical_location_id"],
            "address_1": r["address_1"],
            "city": r["city"],
            "ownership_category": r["primary_ownership_category"],
            "pharmacies": r["pharmacies"],
            "review_only": r["review_only"],
        },
    } for r in rows]
    return JSONResponse({"type": "FeatureCollection", "features": features, "as_of_date": query_date})


@app.get("/api/pharmacy/border-pharmacies")
def border_pharmacies_geojson():
    """Static reference layer - OR/ID pharmacies used only to make WA
    border desert classification explainable. Not tracked with history,
    not part of the WA dataset - see DECISIONS.md 2026-07-26."""
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT state, npi, organization_name, dba_name, address_1, city,
               ST_X(geom) AS lon, ST_Y(geom) AS lat
        FROM border_buffer_locations
        WHERE geom IS NOT NULL AND included_in_access_analysis = TRUE
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    features = [{
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
        "properties": {
            "state": r["state"], "npi": r["npi"],
            "organization_name": r["organization_name"], "dba_name": r["dba_name"],
            "address_1": r["address_1"], "city": r["city"],
        },
    } for r in rows]
    return JSONResponse({"type": "FeatureCollection", "features": features})


# ---------------------------------------------------------------------------
# API - shortage map (Day 8)
#
# FRAMING: every endpoint here reports NATIONAL shortage context and a
# community-level VULNERABILITY score (capacity to adapt), never a
# claim about what's on the shelf at a specific pharmacy or in a
# specific block group right now - no public source for that exists
# (researched and deliberately out of scope, see DECISIONS.md). No
# endpoint here returns a shortage tied to a point/pharmacy/tract as if
# observed locally.
# ---------------------------------------------------------------------------

# The 7-category chronic-condition list and the full scoring formula are
# pre-registered in DECISIONS.md (2026-07-27, "Vulnerability index
# protocol") BEFORE this code was written - nothing here invents new
# weights or category choices.
CHRONIC_CATEGORIES_REGEX = (
    r"(Endocrinology/Metabolism|Cardiovascular|Pulmonary/Allergy|"
    r"Psychiatry|Analgesia/Addiction|Renal|Rheumatology)"
)
SHORTAGE_SATURATION_REFERENCE = 150  # see DECISIONS.md for why 150, not tuned to today's count
VULNERABILITY_DISCLAIMER = (
    "This identifies communities that may have reduced capacity to adapt "
    "when national shortages occur - it does not measure local pharmacy "
    "inventory."
)


def _active_chronic_shortage_count(cur, query_date):
    cur.execute("""
        SELECT count(*) AS n FROM shortages
        WHERE therapeutic_category ~ %s
        AND start_date <= %s AND (end_date IS NULL OR end_date >= %s)
    """, (CHRONIC_CATEGORIES_REGEX, query_date, query_date))
    return cur.fetchone()["n"]


@app.get("/api/shortages/config")
def shortages_config():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT min(start_date) AS min_date FROM shortages")
    min_date = cur.fetchone()["min_date"]
    cur.execute("SELECT count(*) AS n FROM shortages WHERE end_date IS NULL")
    open_ended = cur.fetchone()["n"]
    cur.execute("SELECT count(*) AS n FROM shortages")
    total = cur.fetchone()["n"]
    cur.close()
    conn.close()
    return {
        "slider_min_date": min_date.isoformat(),
        "slider_max_date": datetime.date.today().isoformat(),
        "open_ended_count": open_ended,
        "total_count": total,
    }


@app.get("/api/shortages/active")
def shortages_active(date: str = Query(default=None, description="YYYY-MM-DD; defaults to today")):
    """
    Shortages active on the given date: start_date <= date <=
    (end_date or unbounded). Tier is irrelevant to this boundary check -
    a tier-1 (resolved) shortage is simply one whose end_date happens to
    be populated and in the past relative to `date`; a tier-2 shortage
    has no end_date, so it counts as active for every date from its
    start through today. This list is NOT filtered to the chronic
    categories - that filter only applies to the vulnerability score's
    shortage component, computed separately. `counts_toward_vulnerability`
    tells the frontend which rows do, for transparency.
    """
    query_date = date or datetime.date.today().isoformat()
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, generic_name, tier, source_status, start_date, end_date,
               n_package_variants, dosage_form, therapeutic_category,
               (therapeutic_category ~ %s) AS counts_toward_vulnerability
        FROM shortages
        WHERE start_date <= %s AND (end_date IS NULL OR end_date >= %s)
        ORDER BY generic_name
    """, (CHRONIC_CATEGORIES_REGEX, query_date, query_date))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    shortages = [{
        "id": r["id"],
        "generic_name": r["generic_name"],
        "tier": r["tier"],
        "source_status": r["source_status"],
        "start_date": r["start_date"].isoformat(),
        "end_date": r["end_date"].isoformat() if r["end_date"] else None,
        "n_package_variants": r["n_package_variants"],
        "dosage_form": r["dosage_form"],
        "therapeutic_category": r["therapeutic_category"],
        "counts_toward_vulnerability": r["counts_toward_vulnerability"],
    } for r in rows]
    return JSONResponse({"as_of_date": query_date, "count": len(shortages), "shortages": shortages})


@app.get("/api/shortages/block-group-geometry")
def shortage_block_group_geometry():
    """Static polygon geometry only (no vulnerability data) - fetched
    once by the frontend and restyled in place as the slider moves,
    rather than re-fetching ~4MB of polygon coordinates on every date
    change. Same simplification tolerance as the Day 7 pharmacy map for
    consistency."""
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT geoid, ST_AsGeoJSON(ST_SimplifyPreserveTopology(polygon_geom, 0.0005)) AS geom
        FROM census_block_groups
        WHERE polygon_geom IS NOT NULL
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    features = [{
        "type": "Feature",
        "geometry": json.loads(r["geom"]),
        "properties": {"geoid": r["geoid"]},
    } for r in rows]
    return JSONResponse({"type": "FeatureCollection", "features": features})


@app.get("/api/shortages/vulnerability-scores")
def vulnerability_scores(date: str = Query(default=None, description="YYYY-MM-DD; defaults to today")):
    """
    Per-block-group vulnerability score, computed exactly per the
    protocol in DECISIONS.md (2026-07-27) - not re-derived here:
      score = access_points(0-40) + income_points(0-40) + shortage_points(0-20)
    access/income come from Day 6's census_block_groups (constant across
    dates - ACS/geocoded data doesn't change day to day). shortage_points
    is a SINGLE national number for the whole state, recomputed for the
    requested date, since shortage data has no sub-state geography.
    Suppressed-income block groups get a partial 0-60 score
    (access+shortage only) and no band - never defaulted to a number.
    """
    query_date = date or datetime.date.today().isoformat()
    conn = db()
    cur = conn.cursor()

    active_count = _active_chronic_shortage_count(cur, query_date)
    shortage_points = min(20, round(20 * active_count / SHORTAGE_SATURATION_REFERENCE))

    cur.execute("SELECT geoid, is_low_access, income_status, pharmacy_desert_status, nearest_pharmacy_miles FROM census_block_groups")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    scores = []
    for r in rows:
        access_points = 40 if r["is_low_access"] else 0
        common = {
            "geoid": r["geoid"],
            "is_low_access": r["is_low_access"],
            "income_status": r["income_status"],
            "pharmacy_desert_status": r["pharmacy_desert_status"],
            "nearest_pharmacy_miles": float(r["nearest_pharmacy_miles"]) if r["nearest_pharmacy_miles"] is not None else None,
        }
        if r["income_status"] == "suppressed":
            score = access_points + shortage_points
            scores.append({
                **common,
                "vulnerability_score": score,
                "vulnerability_score_max": 60,
                "vulnerability_score_basis": "partial_income_suppressed",
                "vulnerability_band": None,
            })
        else:
            income_points = 40 if r["income_status"] == "low_income" else 0
            score = access_points + income_points + shortage_points
            band = "low" if score <= 33 else ("medium" if score <= 66 else "high")
            scores.append({
                **common,
                "vulnerability_score": score,
                "vulnerability_score_max": 100,
                "vulnerability_score_basis": "complete",
                "vulnerability_band": band,
            })

    return JSONResponse({
        "as_of_date": query_date,
        "active_chronic_shortage_count": active_count,
        "shortage_points": shortage_points,
        "shortage_points_max": 20,
        "disclaimer": VULNERABILITY_DISCLAIMER,
        "scores": scores,
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
