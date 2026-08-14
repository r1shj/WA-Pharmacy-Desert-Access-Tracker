import csv
import os
import psycopg2

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

flat = {r["npi"]: r for r in csv.DictReader(open(os.path.join(OUT_DIR, "border_pharmacies_flat.csv")))}
geo_rows = list(csv.reader(open(os.path.join(OUT_DIR, "border_geocode_output.csv"))))

conn = psycopg2.connect(dbname="pharmacy_tracker")
cur = conn.cursor()

loaded = 0
for row in geo_rows:
    npi = row[0]
    match_indicator = row[2]
    flat_row = flat[npi]
    geom_sql = "NULL"
    match_type = None
    params = [
        flat_row["state"], npi, flat_row["organization_name"], flat_row["dba_name"] or None,
        flat_row["address_1"], flat_row["city"], flat_row["postal_code"],
    ]
    if match_indicator == "Match":
        match_type = row[3]
        lon, lat = row[5].split(",")
        geom_sql = f"ST_SetSRID(ST_MakePoint({lon}, {lat}), 4326)"
    params.extend([match_indicator, match_type, flat_row["included_in_access_analysis"] == "True"])
    cur.execute(f"""
        INSERT INTO border_buffer_locations
            (state, npi, organization_name, dba_name, address_1, city, postal_code,
             geom, match_indicator, match_type, included_in_access_analysis)
        VALUES (%s,%s,%s,%s,%s,%s,%s, {geom_sql}, %s,%s,%s)
    """, params)
    loaded += 1

conn.commit()
print(f"Loaded {loaded} border_buffer_locations rows")
cur.execute("SELECT state, match_indicator, count(*) FROM border_buffer_locations GROUP BY 1,2 ORDER BY 1,2")
for row in cur.fetchall():
    print(" ", row)
cur.close()
conn.close()
