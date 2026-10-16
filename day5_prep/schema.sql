-- Day 5 schema. See DECISIONS.md (2026-07-25, "Day 5 schema deviations")
-- for why several columns here don't literally match the names first
-- requested - each deviation is a real mismatch against the actual CSV
-- headers, not a stylistic choice.

CREATE EXTENSION IF NOT EXISTS postgis;

DROP TABLE IF EXISTS pharmacy_snapshots CASCADE;
DROP TABLE IF EXISTS pharmacies CASCADE;
DROP TABLE IF EXISTS physical_locations CASCADE;
DROP TABLE IF EXISTS census_tracts CASCADE;
DROP TABLE IF EXISTS shortages CASCADE;

-- One row per physical_location_id (1,811). Geocoding happens at the
-- LOCATION level, not per-NPI, since multiple NPIs can share one
-- physical location (Day 3 dedup).
CREATE TABLE physical_locations (
    physical_location_id       TEXT PRIMARY KEY,        -- natural key, e.g. 'LOC-00001'; no separate surrogate id
    address_1                  TEXT NOT NULL,            -- representative raw input address (extra: not explicitly requested, kept for readability)
    normalized_address         TEXT,                     -- matched_address (geocoder-standardized) if matched, else address_1
    city                       TEXT,
    postal_code                TEXT,
    county                     TEXT,
    npi_count                  INTEGER,                  -- extra: how many NPIs share this location
    geom                       geometry(Point, 4326),     -- NULL for the 89 Tie/No_Match locations
    geocode_status              TEXT,                     -- = match_indicator: 'Match' | 'No_Match' | 'Tie'
    geocode_quality              TEXT,                     -- = match_type: 'Exact' | 'Non_Exact' | NULL
    tract_geoid                 TEXT,                     -- extra: free from geocoder, avoids needing a spatial join for tract assignment
    geocoder_benchmark          TEXT,
    geocoder_vintage            TEXT,
    geocode_manual_review_required   BOOLEAN NOT NULL,     -- Day 4's OWN flag - kept separate from dedup's, per instruction
    dedup_manual_review_required     BOOLEAN NOT NULL      -- Day 3's flag - kept separate from geocode's
);

CREATE INDEX idx_physical_locations_geom ON physical_locations USING GIST (geom);

-- One row per NPI (1,941).
CREATE TABLE pharmacies (
    id                              BIGSERIAL PRIMARY KEY,
    npi                             TEXT NOT NULL UNIQUE,
    organization_name               TEXT,
    dba_name                        TEXT,                 -- = other_names
    parent_organization             TEXT,
    ownership_category              TEXT,
    ownership_confidence            TEXT,
    classification_method           TEXT,                 -- extra: how ownership_category was determined
    shared_signer_npi_count         INTEGER,              -- NPIs sharing one registered signer (repetition fallback); the signer's name is never stored
    primary_taxonomy_code           TEXT,                 -- extra
    primary_taxonomy_desc           TEXT,                 -- extra
    pharmacy_type                   TEXT,
    walk_in_access                  TEXT,
    included_in_access_analysis     BOOLEAN,
    exclusion_reason                TEXT,
    physical_location_id            TEXT REFERENCES physical_locations(physical_location_id),
    enumeration_date                DATE,                 -- NOT in wa_pharmacies_deduped.csv - joined from day8_prep/pharmacy_enumeration_dates.csv by npi
    last_updated                    DATE,                 -- same source as enumeration_date
    source_name                     TEXT NOT NULL DEFAULT 'NPPES',   -- constant - not a column in any source file
    retrieved_at                    DATE NOT NULL           -- constant (2026-07-18, the actual pull date) - not a column in any source file
);

CREATE INDEX idx_pharmacies_physical_location_id ON pharmacies(physical_location_id);
CREATE INDEX idx_pharmacies_ownership_category ON pharmacies(ownership_category);

-- One row per census tract (1,784).
CREATE TABLE census_tracts (
    tract_geoid                          TEXT PRIMARY KEY,
    name                                 TEXT,             -- extra: human-readable tract name
    geometry                             geometry(MultiPolygon, 4326),  -- NOT in any CSV - loaded separately from 2020 TIGER/Line, reprojected NAD83->4326
    population                           INTEGER,
    median_income                        INTEGER,          -- = median_household_income; NULL when income_suppressed
    income_suppressed                    BOOLEAN NOT NULL,
    population_missing                   BOOLEAN NOT NULL,
    excluded_from_income_classification  BOOLEAN NOT NULL
);

CREATE INDEX idx_census_tracts_geometry ON census_tracts USING GIST (geometry);

-- Seed rows from the enumeration-date backfill (1,811, one per location).
-- Forward "observed" snapshots from day8_prep/snapshots/pharmacies/ are
-- NOT loaded here - not part of what was asked for this pass.
CREATE TABLE pharmacy_snapshots (
    id                       BIGSERIAL PRIMARY KEY,
    snapshot_date            DATE NOT NULL,
    physical_location_id     TEXT NOT NULL REFERENCES physical_locations(physical_location_id),
    snapshot_source          TEXT NOT NULL CHECK (snapshot_source IN ('backfilled_enumeration', 'observed')),
    npi_count_at_location     INTEGER,          -- extra, from the backfill file
    contributing_npis        TEXT              -- extra, from the backfill file
);

CREATE INDEX idx_pharmacy_snapshots_location_date ON pharmacy_snapshots(physical_location_id, snapshot_date);

-- Loaded directly from shortage_intervals.csv, already in interval form.
CREATE TABLE shortages (
    id                       BIGSERIAL PRIMARY KEY,
    generic_name              TEXT NOT NULL,
    tier                      SMALLINT NOT NULL,
    source_status             TEXT NOT NULL,
    start_date                DATE NOT NULL,
    end_date                  DATE,             -- NULL for tier 2 (open-ended)
    n_package_variants        INTEGER,
    dosage_form               TEXT,
    therapeutic_category      TEXT
);
