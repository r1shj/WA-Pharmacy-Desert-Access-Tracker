"""
Shared FastAPI backend for both map pages (Day 7: /map/pharmacy, Day 8:
/map/shortages). One app, one set of DB helpers, one static-file mount -
Day 8 adds routes here rather than starting a second backend.

Database access goes through a small connection pool and in-memory caches
(DECISIONS.md 2026-10-16). Supabase's session pooler refuses the 16th
simultaneous client outright, and opening a connection per request made
every fast slider drag fail with HTTP 500s. The data behind the date
sliders is small and changes at most twice a day, so it's loaded once,
kept in memory, and refreshed every few minutes; per-date responses are
computed from that and cached too.
"""
import bisect
import datetime
import json
import os
import re
import sys
import threading
import time
from collections import OrderedDict
from zoneinfo import ZoneInfo

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(APP_DIR))
from jobs.db import connect  # noqa: E402 - DATABASE_URL on Render, local DB otherwise


class RevalidatingStaticFiles(StaticFiles):
    """No build step fingerprints the JS/CSS filenames, so tell browsers to
    revalidate every time (a cheap ETag 304) - otherwise returning visitors
    keep running the previous deploy's scripts against the new API."""
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app = FastAPI(title="Washington Pharmacy Access & National Shortage Context")
app.mount("/static", RevalidatingStaticFiles(directory=os.path.join(APP_DIR, "static")), name="static")


# ---------------------------------------------------------------------------
# Database access: a small pool, sized for Supabase's session pooler
# ---------------------------------------------------------------------------

# The session pooler admits 15 simultaneous clients for this project
# (measured: the 16th gets "EMAXCONNSESSION max clients reached"). Those 15
# are shared with the daily GitHub Actions job, with a second app instance
# during a Render deploy, and with any local psql session - so the app
# holds at most 4. Requests queue for a free connection instead of failing.
DB_POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "4"))
DB_WAIT_SECONDS = 15


class DatabaseBusy(Exception):
    pass


class ConnectionPool:
    def __init__(self, size):
        self._slots = threading.BoundedSemaphore(size)
        self._idle = []
        self._lock = threading.Lock()

    def run(self, fn):
        """Run fn(cursor) on a pooled connection and return its result.
        Every endpoint is read-only, so a refused or dropped connection is
        safely retried once on a fresh one."""
        if not self._slots.acquire(timeout=DB_WAIT_SECONDS):
            raise DatabaseBusy("all database connections are busy")
        try:
            for attempt in range(2):
                conn = None
                try:
                    conn = self._checkout()
                    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                        result = fn(cur)
                except (psycopg2.OperationalError, psycopg2.InterfaceError):
                    if conn is not None:
                        conn.close()  # dead or refused - never back into the pool
                    if attempt:
                        raise
                    time.sleep(0.5)
                    continue
                except Exception:
                    self._checkin(conn)
                    raise
                self._checkin(conn)
                return result
        finally:
            self._slots.release()

    def _checkout(self):
        with self._lock:
            while self._idle:
                conn = self._idle.pop()
                if not conn.closed:
                    return conn
        conn = connect()
        conn.autocommit = True  # reads only; never leave a transaction open between requests
        return conn

    def _checkin(self, conn):
        if conn is not None and not conn.closed:
            with self._lock:
                self._idle.append(conn)


POOL = ConnectionPool(DB_POOL_SIZE)


def query(sql, params=None):
    def fn(cur):
        cur.execute(sql, params)
        return cur.fetchall()
    return POOL.run(fn)


@app.exception_handler(DatabaseBusy)
@app.exception_handler(psycopg2.Error)
async def database_unavailable(request: Request, exc: Exception):
    # JSON, not FastAPI's plain-text "Internal Server Error", so the
    # frontend can show "couldn't load this date" instead of a parse error.
    return JSONResponse({"error": "The database is busy or unreachable. Try again in a moment."},
                        status_code=503)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    # Still logged with a traceback by uvicorn; the client gets JSON.
    return JSONResponse({"error": "Unexpected server error."}, status_code=500)


# ---------------------------------------------------------------------------
# In-memory caches
# ---------------------------------------------------------------------------

class Cached:
    """A value loaded from the database on first use and reloaded after
    `ttl` seconds. If a reload fails, the previous value keeps being served
    and the reload is retried in 30s, so a database blip doesn't break
    pages that were working."""

    def __init__(self, ttl, loader):
        self._ttl, self._loader = ttl, loader
        self._value, self._loaded_at = None, 0.0
        self._lock = threading.Lock()

    def get(self):
        if self._value is not None and time.monotonic() - self._loaded_at < self._ttl:
            return self._value
        with self._lock:
            if self._value is not None and time.monotonic() - self._loaded_at < self._ttl:
                return self._value
            try:
                self._value = self._loader()
                self._loaded_at = time.monotonic()
            except Exception:
                if self._value is None:
                    raise
                self._loaded_at = time.monotonic() - self._ttl + 30
            return self._value


class LRU:
    """Small thread-safe cache of computed responses, keyed per date."""

    def __init__(self, maxsize):
        self._items, self._max = OrderedDict(), maxsize
        self._lock = threading.Lock()

    def get_or_compute(self, key, compute):
        with self._lock:
            if key in self._items:
                self._items.move_to_end(key)
                return self._items[key]
        value = compute()
        with self._lock:
            self._items[key] = value
            self._items.move_to_end(key)
            while len(self._items) > self._max:
                self._items.popitem(last=False)
        return value


def _json_bytes(obj):
    return json.dumps(obj, separators=(",", ":")).encode()


def _json_response(body_bytes):
    return Response(content=body_bytes, media_type="application/json")


def _today():
    # Pacific, matching jobs/daily_snapshot.py - Render's clock is UTC.
    return datetime.datetime.now(ZoneInfo("America/Los_Angeles")).date()


def _parse_date(date):
    if date is None:
        return _today()
    try:
        return datetime.date.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD")


def _miles(v):
    return float(v) if v is not None else None


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

# no-cache: browsers must revalidate (cheap ETag 304), so a deploy never
# pairs an old cached page with new scripts - which broke the shortage map's
# legend for at least one visitor (DECISIONS.md 2026-10-16).
PAGE_HEADERS = {"Cache-Control": "no-cache"}


@app.get("/")
def landing_page():
    return FileResponse(os.path.join(APP_DIR, "static", "landing.html"), headers=PAGE_HEADERS)


@app.get("/map/pharmacy")
def map_pharmacy_page():
    return FileResponse(os.path.join(APP_DIR, "static", "pharmacy_map.html"), headers=PAGE_HEADERS)


@app.get("/map/shortages")
def map_shortages_page():
    return FileResponse(os.path.join(APP_DIR, "static", "shortage_map.html"), headers=PAGE_HEADERS)


# ---------------------------------------------------------------------------
# API - pharmacy map (Day 7)
# ---------------------------------------------------------------------------

def _load_pharmacy_data():
    """Everything the pharmacy date slider needs except observed snapshot
    membership, which is loaded per observed date on demand. Refreshed every
    5 minutes so a new daily snapshot appears without a redeploy."""
    locations = {r["physical_location_id"]: r for r in query("""
        SELECT physical_location_id, address_1, city, ST_X(geom) AS lon, ST_Y(geom) AS lat
        FROM physical_locations WHERE geom IS NOT NULL
    """)}
    # Same eligibility as before: confirmed-included OR still in the REVIEW
    # bucket (walk_in_access='unknown'). Excluded-only locations never show.
    pharmacies_by_location = {}
    # A few pharmacies are legally registered under an individual's name;
    # show their trading name (DBA) instead (DECISIONS.md 2026-10-16).
    for r in query("""
        SELECT physical_location_id, npi,
               CASE WHEN organization_name_is_individual THEN dba_name ELSE organization_name END AS organization_name,
               CASE WHEN organization_name_is_individual THEN NULL ELSE dba_name END AS dba_name,
               ownership_category, parent_organization, pharmacy_type,
               included_in_access_analysis, walk_in_access
        FROM pharmacies
        WHERE included_in_access_analysis = TRUE OR walk_in_access = 'unknown'
        ORDER BY npi
    """):
        pharmacies_by_location.setdefault(r.pop("physical_location_id"), []).append(r)
    first_dates = sorted(
        (r["first_date"], r["physical_location_id"]) for r in query("""
            SELECT physical_location_id, MIN(snapshot_date) AS first_date
            FROM pharmacy_snapshots GROUP BY physical_location_id
        """))
    sources = {r["snapshot_source"]: r for r in query("""
        SELECT snapshot_source, min(snapshot_date) AS min_date, max(snapshot_date) AS max_date
        FROM pharmacy_snapshots GROUP BY snapshot_source
    """)}
    observed_dates = [r["d"] for r in query("""
        SELECT DISTINCT snapshot_date AS d FROM pharmacy_snapshots
        WHERE snapshot_source = 'observed' ORDER BY d
    """)]
    return {
        "locations": locations,
        "pharmacies_by_location": pharmacies_by_location,
        "first_dates": first_dates,
        "first_date_keys": [d for d, _ in first_dates],
        "sources": sources,
        "observed_dates": observed_dates,
        "observed_npis": LRU(8),   # observed_date -> {location_id: set(active NPIs)}
        "responses": LRU(24),      # (basis, key) -> serialized feature list
    }


PHARMACY_DATA = Cached(300, _load_pharmacy_data)


def _observed_npis(data, observed_date):
    def load():
        out = {}
        for r in query("""
            SELECT physical_location_id, contributing_npis FROM pharmacy_snapshots
            WHERE snapshot_source = 'observed' AND snapshot_date = %s
        """, (observed_date,)):
            out[r["physical_location_id"]] = set((r["contributing_npis"] or "").split(";"))
        return out
    return data["observed_npis"].get_or_compute(observed_date, load)


def _location_features(data, active):
    """active: {location_id: set(NPIs) or None (= all eligible NPIs)}."""
    features = []
    for loc_id, npis in active.items():
        loc = data["locations"].get(loc_id)
        eligible = [p for p in data["pharmacies_by_location"].get(loc_id, [])
                    if npis is None or p["npi"] in npis]
        if loc is None or not eligible:
            continue
        included = [p for p in eligible if p["included_in_access_analysis"]]
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [loc["lon"], loc["lat"]]},
            "properties": {
                "physical_location_id": loc_id,
                "address_1": loc["address_1"],
                "city": loc["city"],
                "ownership_category": (included or eligible)[0]["ownership_category"],
                "pharmacies": eligible,
                "review_only": not included,
            },
        })
    return _json_bytes(features)


@app.get("/api/pharmacy/config")
def pharmacy_config():
    """Slider bounds + the backfill/observed transition point, computed
    from the real data rather than hardcoded, so this stays correct as
    the daily NPPES sweep adds observed dates."""
    data = PHARMACY_DATA.get()
    backfill = data["sources"].get("backfilled_enumeration")
    observed = [d.isoformat() for d in data["observed_dates"]]
    return {
        "slider_min_date": backfill["min_date"].isoformat() if backfill else None,
        "slider_max_date": _today().isoformat(),
        "last_backfilled_date": backfill["max_date"].isoformat() if backfill else None,
        "first_observed_date": observed[0] if observed else None,
        "observed_dates_available": observed,
    }


BLOCK_GROUPS_GEOJSON = Cached(6 * 3600, lambda: _feature_collection_bytes(query("""
    SELECT geoid, pharmacy_desert_status, is_urban, income_status,
           population, nearest_pharmacy_miles, distance_threshold_miles,
           ST_AsGeoJSON(ST_SimplifyPreserveTopology(polygon_geom, 0.0005)) AS geom
    FROM census_block_groups
    WHERE polygon_geom IS NOT NULL
"""), lambda r: {
    "geoid": r["geoid"],
    "pharmacy_desert_status": r["pharmacy_desert_status"],
    "is_urban": r["is_urban"],
    "income_status": r["income_status"],
    "population": r["population"],
    "nearest_pharmacy_miles": _miles(r["nearest_pharmacy_miles"]),
    "distance_threshold_miles": _miles(r["distance_threshold_miles"]),
}))


def _feature_collection_bytes(rows, properties):
    # ST_AsGeoJSON already returns JSON text - splice it in rather than
    # parsing and re-serializing ~5,000 polygons.
    parts = [b'{"type":"Feature","geometry":' + r["geom"].encode()
             + b',"properties":' + _json_bytes(properties(r)) + b"}" for r in rows]
    return b'{"type":"FeatureCollection","features":[' + b",".join(parts) + b"]}"


@app.get("/api/pharmacy/block-groups")
def block_groups_geojson():
    """Static desert-classification choropleth - does not change with the
    date slider (ACS/geocoded data doesn't change day to day)."""
    return _json_response(BLOCK_GROUPS_GEOJSON.get())


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

    Which pharmacies "existed" on a date:
      - on/after the first observed snapshot: the NPIs active in the most
        recent observed snapshot on or before that date (so deactivations
        found by the daily NPPES sweep actually disappear)
      - before it: the enumeration-date backfill, which can only add
    `basis` / `observed_date` in the response say which one was used.
    """
    query_date = _parse_date(date)
    data = PHARMACY_DATA.get()
    i = bisect.bisect_right(data["observed_dates"], query_date)
    observed_date = data["observed_dates"][i - 1] if i else None

    if observed_date:
        def compute():
            return _location_features(data, _observed_npis(data, observed_date))
        features = data["responses"].get_or_compute(("observed", observed_date), compute)
    else:
        # Backfill: locations whose first snapshot is on or before the date.
        # The sorted prefix length identifies the result, so dates in the
        # same gap between first-registration dates share one cached entry.
        n = bisect.bisect_right(data["first_date_keys"], query_date)

        def compute():
            return _location_features(data, {loc: None for _, loc in data["first_dates"][:n]})
        features = data["responses"].get_or_compute(("backfill", n), compute)

    head = _json_bytes({
        "type": "FeatureCollection", "as_of_date": query_date.isoformat(),
        "basis": "observed" if observed_date else "backfilled_enumeration",
        "observed_date": observed_date.isoformat() if observed_date else None,
    })
    return _json_response(head[:-1] + b',"features":' + features + b"}")


BORDER_PHARMACIES_GEOJSON = Cached(6 * 3600, lambda: _json_bytes({
    "type": "FeatureCollection",
    "features": [{
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
        "properties": {
            "state": r["state"], "npi": r["npi"],
            "organization_name": r["organization_name"], "dba_name": r["dba_name"],
            "address_1": r["address_1"], "city": r["city"],
        },
    } for r in query("""
        SELECT state, npi, organization_name, dba_name, address_1, city,
               ST_X(geom) AS lon, ST_Y(geom) AS lat
        FROM border_buffer_locations
        WHERE geom IS NOT NULL AND included_in_access_analysis = TRUE
    """)],
}))


@app.get("/api/pharmacy/border-pharmacies")
def border_pharmacies_geojson():
    """Static reference layer - OR/ID pharmacies used only to make WA
    border desert classification explainable. Not tracked with history,
    not part of the WA dataset - see DECISIONS.md 2026-07-26."""
    return _json_response(BORDER_PHARMACIES_GEOJSON.get())


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
CHRONIC_CATEGORIES = re.compile(CHRONIC_CATEGORIES_REGEX)
SHORTAGE_SATURATION_REFERENCE = 150  # see DECISIONS.md for why 150, not tuned to today's count
# First day the shortage feed was snapshotted daily. A fixed historical
# fact - not derivable from last_observed_date, which records each row's
# most recent sighting.
DAILY_SHORTAGE_OBSERVATION_START = "2026-07-18"
VULNERABILITY_DISCLAIMER = (
    "This identifies communities that may have reduced capacity to adapt "
    "when national shortages occur - it does not measure local pharmacy "
    "inventory."
)


def _load_shortages():
    """The whole shortage interval table (a few hundred rows), in the
    database's own generic_name order. Refreshed every 5 minutes so the
    twice-daily sync shows up without a redeploy."""
    rows = query("""
        SELECT id, generic_name, tier, source_status, start_date, end_date, end_date_basis,
               n_package_variants, dosage_form, therapeutic_category
        FROM shortages ORDER BY generic_name
    """)
    for r in rows:
        r["counts_toward_vulnerability"] = bool(
            r["therapeutic_category"] and CHRONIC_CATEGORIES.search(r["therapeutic_category"]))
    return {"rows": rows, "responses": LRU(256)}


SHORTAGES = Cached(300, _load_shortages)


def _active_on(rows, d):
    # Active if start_date <= date <= (end_date or unbounded) - same rule
    # as the original SQL.
    return [r for r in rows if r["start_date"] <= d and (r["end_date"] is None or r["end_date"] >= d)]


def _shortage_points(rows, d):
    active_count = sum(1 for r in _active_on(rows, d) if r["counts_toward_vulnerability"])
    return active_count, min(20, round(20 * active_count / SHORTAGE_SATURATION_REFERENCE))


@app.get("/api/shortages/config")
def shortages_config():
    rows = SHORTAGES.get()["rows"]
    return {
        "slider_min_date": min(r["start_date"] for r in rows).isoformat(),
        "slider_max_date": _today().isoformat(),
        "daily_observation_since": DAILY_SHORTAGE_OBSERVATION_START,
        "total_count": len(rows),
        "open_ended_count": sum(r["end_date_basis"] is None for r in rows),
        "confirmed_resolved_count": sum(r["end_date_basis"] == "confirmed_resolved" for r in rows),
        "dropped_from_feed_count": sum(r["end_date_basis"] == "last_observed_in_feed" for r in rows),
    }


@app.get("/api/shortages/active")
def shortages_active(date: str = Query(default=None, description="YYYY-MM-DD; defaults to today")):
    """
    Shortages active on the given date: start_date <= date <=
    (end_date or unbounded). Tier is irrelevant to this boundary check -
    an end_date comes either from a confirmed resolution (tier 1) or from
    the last day the shortage was seen in openFDA's feed (tier 3,
    end_date_basis='last_observed_in_feed' - not a resolution); a tier-2
    shortage has no end_date, so it counts as active for every date from
    its start through today. This list is NOT filtered to the chronic
    categories - that filter only applies to the vulnerability score's
    shortage component, computed separately. `counts_toward_vulnerability`
    tells the frontend which rows do, for transparency.
    """
    query_date = _parse_date(date)
    data = SHORTAGES.get()

    def compute():
        shortages = [{
            **r,
            "start_date": r["start_date"].isoformat(),
            "end_date": r["end_date"].isoformat() if r["end_date"] else None,
        } for r in _active_on(data["rows"], query_date)]
        return _json_bytes({"as_of_date": query_date.isoformat(), "count": len(shortages),
                            "shortages": shortages})
    return _json_response(data["responses"].get_or_compute(("active", query_date), compute))


BLOCK_GROUP_GEOMETRY = Cached(6 * 3600, lambda: _feature_collection_bytes(query("""
    SELECT geoid, ST_AsGeoJSON(ST_SimplifyPreserveTopology(polygon_geom, 0.0005)) AS geom
    FROM census_block_groups
    WHERE polygon_geom IS NOT NULL
"""), lambda r: {"geoid": r["geoid"]}))


@app.get("/api/shortages/block-group-geometry")
def shortage_block_group_geometry():
    """Static polygon geometry only (no vulnerability data) - fetched
    once by the frontend and restyled in place as the slider moves,
    rather than re-fetching ~4MB of polygon coordinates on every date
    change. Same simplification tolerance as the Day 7 pharmacy map for
    consistency."""
    return _json_response(BLOCK_GROUP_GEOMETRY.get())


def _load_vulnerability_base():
    # Access/income come from Day 6's census_block_groups and don't change
    # with the date, so the per-block-group list depends on the date only
    # through the single statewide shortage_points value (0-20). It's
    # serialized once per value and reused for every date with that value.
    return {"rows": query("""
        SELECT geoid, is_low_access, income_status, pharmacy_desert_status, nearest_pharmacy_miles
        FROM census_block_groups
    """), "scores_by_points": LRU(21)}


VULNERABILITY_BASE = Cached(3600, _load_vulnerability_base)


def _scores_bytes(rows, shortage_points):
    scores = []
    for r in rows:
        access_points = 40 if r["is_low_access"] else 0
        common = {
            "geoid": r["geoid"],
            "is_low_access": r["is_low_access"],
            "income_status": r["income_status"],
            "pharmacy_desert_status": r["pharmacy_desert_status"],
            "nearest_pharmacy_miles": _miles(r["nearest_pharmacy_miles"]),
        }
        if r["income_status"] == "suppressed":
            scores.append({
                **common,
                "vulnerability_score": access_points + shortage_points,
                "vulnerability_score_max": 60,
                "vulnerability_score_basis": "partial_income_suppressed",
                "vulnerability_band": None,
            })
        else:
            income_points = 40 if r["income_status"] == "low_income" else 0
            score = access_points + income_points + shortage_points
            scores.append({
                **common,
                "vulnerability_score": score,
                "vulnerability_score_max": 100,
                "vulnerability_score_basis": "complete",
                "vulnerability_band": "low" if score <= 33 else ("medium" if score <= 66 else "high"),
            })
    return _json_bytes(scores)


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
    query_date = _parse_date(date)
    active_count, shortage_points = _shortage_points(SHORTAGES.get()["rows"], query_date)
    base = VULNERABILITY_BASE.get()
    scores = base["scores_by_points"].get_or_compute(
        shortage_points, lambda: _scores_bytes(base["rows"], shortage_points))
    head = _json_bytes({
        "as_of_date": query_date.isoformat(),
        "active_chronic_shortage_count": active_count,
        "shortage_points": shortage_points,
        "shortage_points_max": 20,
        "disclaimer": VULNERABILITY_DISCLAIMER,
    })
    return _json_response(head[:-1] + b',"scores":' + scores + b"}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
