"""
Daily snapshot entrypoint, run by .github/workflows/daily-snapshot.yml.

    python jobs/daily_snapshot.py [--only shortages|pharmacies] [--dry-run]
                                  [--allow-large-drop]

Runs each job in its own transaction: a failure in one doesn't block the
other, and a failed job writes nothing except its snapshot_runs row
(status 'aborted' when a safeguard refused the data, 'failed' on an
error). Exits non-zero if any job didn't succeed, so the workflow run
shows red.

--dry-run does everything (including the full NPPES sweep) and prints the
summary, then rolls back instead of committing.

Database: see jobs/db.py - no credentials in code.
"""
import argparse
import datetime
import json
import os
import sys
import traceback
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from jobs import pharmacy_sync, shortage_sync  # noqa: E402
from jobs.db import connect  # noqa: E402

# The dataset is about Washington, so "today" is Pacific time regardless
# of where the job runs (GitHub's runners use UTC).
TODAY = datetime.datetime.now(ZoneInfo("America/Los_Angeles")).date()


def run_shortages(cur, obs_date, args):
    records = shortage_sync.collapse(shortage_sync.fetch_live_feed())
    return shortage_sync.apply_observation(cur, obs_date, records)


def run_pharmacies(cur, obs_date, args):
    return pharmacy_sync.run(cur, obs_date, allow_large_drop=args.allow_large_drop)


JOBS = {"shortages": run_shortages, "pharmacies": run_pharmacies}
SAFEGUARDS = (shortage_sync.SuspiciousFeed, pharmacy_sync.SweepFailed, pharmacy_sync.SuspiciousSweep)


def log_run(conn, job, status, details):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO snapshot_runs (run_date, job, status, details) VALUES (%s, %s, %s, %s)",
                    (TODAY, job, status, json.dumps(details)))
    conn.commit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=sorted(JOBS))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-large-drop", action="store_true",
                        help="accept a pharmacy location drop above the safeguard after reviewing it")
    args = parser.parse_args()

    ok = True
    conn = connect()
    for name, fn in JOBS.items():
        if args.only and name != args.only:
            continue
        print(f"[{name}] {TODAY}{' (dry run)' if args.dry_run else ''}")
        try:
            with conn.cursor() as cur:
                summary = fn(cur, TODAY, args)
            if args.dry_run:
                conn.rollback()
            else:
                conn.commit()
                log_run(conn, name, "ok", summary)
            print(f"[{name}] ok: {json.dumps(summary, default=str)}")
        except Exception as e:  # noqa: BLE001 - logged, reported, and exits non-zero
            conn.rollback()
            ok = False
            status = "aborted" if isinstance(e, SAFEGUARDS) else "failed"
            print(f"[{name}] {status}: {e}", file=sys.stderr)
            traceback.print_exc()
            if not args.dry_run:
                log_run(conn, name, status, {"error": f"{type(e).__name__}: {e}"})
    conn.close()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
