"""
Shared forward-snapshot infrastructure for Day 8+. Any dataset (drug
shortages, the pharmacy dataset, anything else added later) writes one
CSV per calendar day into snapshots/<dataset_name>/<YYYY-MM-DD>.csv.
Idempotent - re-running on the same day overwrites that day's file rather
than duplicating it, so it's safe to run manually more than once.

This is intentionally just the write-path. Actually scheduling it (cron,
Task Scheduler, a hosted job runner) is a deployment decision for later,
not something wired up automatically here.
"""
import csv
import os
from datetime import date

SNAPSHOT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshots")


def write_snapshot(dataset_name, fieldnames, rows, snapshot_date=None):
    snapshot_date = snapshot_date or date.today()
    dataset_dir = os.path.join(SNAPSHOT_ROOT, dataset_name)
    os.makedirs(dataset_dir, exist_ok=True)
    path = os.path.join(dataset_dir, f"{snapshot_date.isoformat()}.csv")
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def list_snapshot_dates(dataset_name):
    dataset_dir = os.path.join(SNAPSHOT_ROOT, dataset_name)
    if not os.path.isdir(dataset_dir):
        return []
    return sorted(f[:-4] for f in os.listdir(dataset_dir) if f.endswith(".csv"))
