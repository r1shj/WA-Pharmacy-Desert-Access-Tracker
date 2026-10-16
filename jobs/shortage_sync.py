"""
Keeps the `shortages` interval table in step with openFDA's live feed.

apply_observation() is the single source of truth for how one day's feed
changes the table. It is used both by the daily GitHub Actions job (today's
live pull) and by day9/backfill_shortage_snapshots.py (replaying the
locally collected daily files in date order), so history and the forward
job can never diverge.

Per distinct shortage (generic_name), one observation can:
  - add it (new in the feed)          -> tier 2 open, or tier 1 if already Resolved
  - mark it Resolved                  -> tier 1, end_date = its last_update_date
  - un-resolve it (status flips back) -> reopened as tier 2
  - see it missing (was open)         -> tier 3, end_date = last day it was seen,
                                         end_date_basis 'last_observed_in_feed'.
                                         Leaving the feed is NOT confirmation the
                                         shortage ended, so it's never called resolved.
  - see it reappear after dropping out -> new interval row starting that day,
                                         unless it dropped out the same day
                                         (a flap between same-day runs), which
                                         just reopens the original interval
Confirmed-resolved rows that later leave the feed are left alone. Running
more than once a day is safe: every change is relative to the table's
current state, so a repeat run with the same feed changes nothing.
"""
import datetime
import json
import urllib.request
from collections import defaultdict

OPENFDA_URL = "https://api.fda.gov/drug/shortages.json"

# A single day where more than this fraction of open shortages vanish is
# far more likely a broken/partial feed than real-world resolution. Abort
# rather than mass-close intervals. Day-to-day change in the 86 days of
# local snapshots never came close (0 reappearances, counts 231-245).
MAX_DROPOUT_FRACTION = 0.25


class SuspiciousFeed(Exception):
    pass


def _mdy_to_iso(d):
    if not d:
        return None
    m, day, y = d.split("/")
    return f"{y}-{int(m):02d}-{int(day):02d}"


def _dedup_join(values):
    seen = []
    for v in values:
        if v and v not in seen:
            seen.append(v)
    return "; ".join(seen) or None


def fetch_live_feed():
    """Full current openFDA shortages feed. Refuses to return a partial
    pull - the row count must match openFDA's own reported total."""
    records, skip, total = [], 0, None
    while total is None or skip < total:
        url = f"{OPENFDA_URL}?limit=1000&skip={skip}"
        with urllib.request.urlopen(url, timeout=60) as resp:
            payload = json.loads(resp.read().decode())
        total = payload["meta"]["results"]["total"]
        page = payload["results"]
        if not page:
            break
        records.extend(page)
        skip += len(page)
    if len(records) != total:
        raise SuspiciousFeed(f"openFDA returned {len(records)} of {total} reported records")
    return records


def collapse(raw_records):
    """Raw package-level records -> one entry per generic_name, same rule
    as Day 8: Resolved only if every package variant is Resolved."""
    by_generic = defaultdict(list)
    for r in raw_records:
        by_generic[r.get("generic_name")].append(r)
    out = {}
    for generic, rows in by_generic.items():
        statuses = {r.get("status") for r in rows}
        status = "Resolved" if statuses == {"Resolved"} else (
            "To Be Discontinued" if "To Be Discontinued" in statuses else "Current")
        postings = [_mdy_to_iso(r.get("initial_posting_date")) for r in rows]
        updates = [_mdy_to_iso(r.get("update_date")) for r in rows]
        out[generic] = {
            "status": status,
            "initial_posting_date": min(p for p in postings if p),
            "last_update_date": max((u for u in updates if u), default=None),
            "n_package_variants": len(rows),
            "dosage_form": _dedup_join(r.get("dosage_form") for r in rows),
            "therapeutic_category": _dedup_join(
                c for r in rows for c in (r.get("therapeutic_category") or [])),
        }
    return out


def apply_observation(cur, obs_date, records, enforce_dropout_limit=True):
    """Apply one day's distinct-shortage observation. `records` maps
    generic_name -> dict with status, initial_posting_date,
    last_update_date, n_package_variants, and optionally dosage_form /
    therapeutic_category. Returns a summary dict. Caller commits."""
    obs = datetime.date.fromisoformat(str(obs_date))
    cur.execute("""
        SELECT DISTINCT ON (generic_name) id, generic_name, tier, end_date_basis, last_observed_date
        FROM shortages ORDER BY generic_name, id DESC
    """)
    current = {r[1]: {"id": r[0], "tier": r[2], "basis": r[3], "last_observed": r[4]}
               for r in cur.fetchall()}

    open_names = {g for g, r in current.items() if r["basis"] is None}
    dropouts = open_names - set(records)
    if enforce_dropout_limit and open_names and len(dropouts) / len(open_names) > MAX_DROPOUT_FRACTION:
        raise SuspiciousFeed(
            f"{len(dropouts)} of {len(open_names)} open shortages missing from the {obs_date} feed "
            f"(> {MAX_DROPOUT_FRACTION:.0%}) - refusing to close them")

    summary = {"added": 0, "reappeared": 0, "resolved": 0, "unresolved": 0, "dropped_out": 0,
               "same_day_dropouts_reverted": 0}
    for g, rec in records.items():
        row = current.get(g)
        resolved = rec["status"] == "Resolved"
        if (row and row["basis"] == "last_observed_in_feed"
                and row["last_observed"] is not None and row["last_observed"] >= obs):
            # Seen earlier today, missed by a later run today, and back now: a
            # feed flap between same-day runs, not a real dropout. Reopen the
            # interval - a new row starting today would overlap the old one
            # (which ends today) and count this shortage twice for the day.
            cur.execute("""UPDATE shortages SET tier = 2, end_date = NULL,
                end_date_basis = NULL WHERE id = %s""", (row["id"],))
            row = dict(row, tier=2, basis=None)
            summary["same_day_dropouts_reverted"] += 1
        if row is None or row["basis"] == "last_observed_in_feed":
            # New shortage, or one that had dropped out and is back: new interval.
            start = rec["initial_posting_date"] if row is None else obs_date
            cur.execute("""
                INSERT INTO shortages (generic_name, tier, source_status, start_date, end_date,
                    end_date_basis, n_package_variants, dosage_form, therapeutic_category,
                    last_observed_date)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (g, 1 if resolved else 2, rec["status"], start,
                  rec["last_update_date"] if resolved else None,
                  "confirmed_resolved" if resolved else None,
                  rec["n_package_variants"], rec.get("dosage_form"),
                  rec.get("therapeutic_category"), obs_date))
            summary["reappeared" if row else "added"] += 1
            continue

        cur.execute("""
            UPDATE shortages SET source_status = %s, n_package_variants = %s,
                last_observed_date = %s,
                dosage_form = COALESCE(%s, dosage_form),
                therapeutic_category = COALESCE(%s, therapeutic_category)
            WHERE id = %s
        """, (rec["status"], rec["n_package_variants"], obs_date,
              rec.get("dosage_form"), rec.get("therapeutic_category"), row["id"]))
        if resolved and row["basis"] is None:
            cur.execute("""UPDATE shortages SET tier = 1, end_date = %s,
                end_date_basis = 'confirmed_resolved' WHERE id = %s""",
                        (rec["last_update_date"] or obs_date, row["id"]))
            summary["resolved"] += 1
        elif not resolved and row["basis"] == "confirmed_resolved":
            cur.execute("""UPDATE shortages SET tier = 2, end_date = NULL,
                end_date_basis = NULL WHERE id = %s""", (row["id"],))
            summary["unresolved"] += 1

    for g in dropouts:
        cur.execute("""UPDATE shortages SET tier = 3, end_date = last_observed_date,
            end_date_basis = 'last_observed_in_feed' WHERE id = %s""", (current[g]["id"],))
    summary["dropped_out"] = len(dropouts)
    summary["feed_size"] = len(records)
    return summary
