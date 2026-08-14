-- Day 6 schema additions. See config.json for every threshold value and
-- DECISIONS.md (2026-07-26 entries) for the reasoning behind each choice.

DROP TABLE IF EXISTS census_block_groups CASCADE;
DROP TABLE IF EXISTS border_buffer_locations CASCADE;

-- One row per WA block group (population unit for the desert
-- classification - CenPop population-weighted centroids, not tract
-- geometric centroids, so distance reflects where people actually live).
CREATE TABLE census_block_groups (
    geoid                   TEXT PRIMARY KEY,          -- 12-digit: state(2)+county(3)+tract(6)+blockgroup(1)
    tract_geoid             TEXT REFERENCES census_tracts(tract_geoid),
    population              INTEGER NOT NULL,          -- from CenPop2020 (block-group-level count, not ACS)
    geom                    geometry(Point, 4326),      -- CenPop population-weighted centroid
    is_urban                BOOLEAN,                    -- ST_Within a 2020 Census Urban Area polygon
    income_status           TEXT NOT NULL CHECK (income_status IN ('low_income', 'not_low_income', 'suppressed')),
    distance_threshold_miles NUMERIC,                   -- 1 (urban) or 10 (rural), per config.json
    nearest_pharmacy_miles   NUMERIC,                    -- straight-line geographic distance, NOT travel distance
    is_low_access            BOOLEAN,
    pharmacy_desert_status   TEXT CHECK (pharmacy_desert_status IN ('desert', 'not_desert', 'indeterminate_income_suppressed'))
);

CREATE INDEX idx_census_block_groups_geom ON census_block_groups USING GIST (geom);

-- Pharmacies within ~20mi of the WA border in OR/ID. Used ONLY to make
-- sure a WA border block group's "nearest pharmacy" search isn't
-- artificially cut off at the state line - never counted as WA
-- population or included in any WA-facing pharmacy count.
CREATE TABLE border_buffer_locations (
    id                      BIGSERIAL PRIMARY KEY,
    state                   TEXT NOT NULL CHECK (state IN ('OR', 'ID')),
    npi                     TEXT,
    organization_name       TEXT,
    dba_name                TEXT,
    address_1               TEXT,
    city                    TEXT,
    postal_code             TEXT,
    geom                    geometry(Point, 4326),
    match_indicator         TEXT,
    match_type              TEXT,
    included_in_access_analysis BOOLEAN NOT NULL DEFAULT TRUE  -- same pharmacy_type inclusion logic as WA, applied minimally - see DECISIONS.md
);

CREATE INDEX idx_border_buffer_locations_geom ON border_buffer_locations USING GIST (geom);
