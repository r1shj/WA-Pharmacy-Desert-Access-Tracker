#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
echo "=== $(date) ===" >> snapshot_log.txt
/usr/bin/python3 snapshot_shortages_today.py >> snapshot_log.txt 2>&1
/usr/bin/python3 snapshot_pharmacies_today.py >> snapshot_log.txt 2>&1
