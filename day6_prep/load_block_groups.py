"""
Loads WA census_block_groups: CenPop2020 population-weighted centroids
(not tract geometric centroids), joined to a county-level income proxy
and a spatial urban/rural classification.

Income threshold methodology (see DECISIONS.md, 2026-07-26):
HUD's well-established standard defines "low income" as household income
below 80% of the Area Median Income (AMI) for the relevant area. We do
NOT have HUD's official published county AMI figures (their bulk file
could not be reliably fetched this session - see DECISIONS.md). Instead
we compute a PROXY AMI per WA county: the population-weighted mean of
median_household_income across that county's non-suppressed tracts
(from Day 4's audited ACS pull). A tract counts as "low_income" if its
own median_household_income is below 80% of ITS county's proxy AMI.
Suppressed tracts are marked "suppressed", never silently treated as
either low- or not-low-income.
"""
import csv
import os
import psycopg2
from collections import defaultdict

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
LOW_INCOME_PCT_OF_AMI = 0.80  # HUD "Low Income" standard

conn = psycopg2.connect(dbname="pharmacy_tracker")
cur = conn.cursor()

# --- Step 1: compute county-level proxy AMI from non-suppressed tracts ---
cur.execute("SELECT tract_geoid, median_income, population, income_suppressed FROM census_tracts")
tract_rows = cur.fetchall()

county_income_pop = defaultdict(list)  # county_fips -> [(income, population), ...]
tract_income_status = {}  # tract_geoid -> ('low_income'|'not_low_income'|'suppressed', county_fips)
for tract_geoid, median_income, population, income_suppressed in tract_rows:
    county_fips = tract_geoid[2:5]
    if not income_suppressed and median_income is not None and population:
        county_income_pop[county_fips].append((median_income, population))

county_proxy_ami = {}
for county_fips, pairs in county_income_pop.items():
    total_pop = sum(p for _, p in pairs)
    weighted_income = sum(inc * p for inc, p in pairs) / total_pop
    county_proxy_ami[county_fips] = weighted_income

print(f"Computed proxy AMI for {len(county_proxy_ami)} WA counties")

for tract_geoid, median_income, population, income_suppressed in tract_rows:
    county_fips = tract_geoid[2:5]
    if income_suppressed:
        tract_income_status[tract_geoid] = "suppressed"
    else:
        ami = county_proxy_ami[county_fips]
        threshold = ami * LOW_INCOME_PCT_OF_AMI
        tract_income_status[tract_geoid] = "low_income" if median_income < threshold else "not_low_income"

status_counts = defaultdict(int)
for s in tract_income_status.values():
    status_counts[s] += 1
print(f"Tract income_status distribution: {dict(status_counts)}")

# --- Step 2: load CenPop block groups, join tract income status, spatially classify urban/rural ---
with open(os.path.join(OUT_DIR, "cenpop_bg_53.txt"), encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    bg_rows = list(reader)

print(f"\nLoading {len(bg_rows)} WA block groups from CenPop...")
loaded = 0
missing_tract = 0
for r in bg_rows:
    geoid = f"{r['STATEFP']}{r['COUNTYFP']}{r['TRACTCE']}{r['BLKGRPCE']}"
    tract_geoid = f"{r['STATEFP']}{r['COUNTYFP']}{r['TRACTCE']}"
    income_status = tract_income_status.get(tract_geoid)
    if income_status is None:
        missing_tract += 1
        continue
    lat, lon = r["LATITUDE"], r["LONGITUDE"]
    cur.execute("""
        INSERT INTO census_block_groups (geoid, tract_geoid, population, geom, income_status)
        VALUES (%s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s)
    """, (geoid, tract_geoid, int(r["POPULATION"]), lon, lat, income_status))
    loaded += 1

conn.commit()
print(f"Loaded {loaded} block groups ({missing_tract} skipped - no matching tract in census_tracts)")

# --- Step 3: urban/rural via spatial join against the 2020 Census Urban Area boundaries ---
cur.execute("""
    UPDATE census_block_groups bg
    SET is_urban = EXISTS (
        SELECT 1 FROM urban_areas_raw ua WHERE ST_Within(bg.geom, ua.geom)
    )
""")
conn.commit()

cur.execute("SELECT is_urban, count(*) FROM census_block_groups GROUP BY 1")
print(f"\nUrban/rural distribution: {cur.fetchall()}")

cur.execute("SELECT income_status, count(*) FROM census_block_groups GROUP BY 1")
print(f"Block-group income_status distribution: {cur.fetchall()}")

cur.close()
conn.close()
