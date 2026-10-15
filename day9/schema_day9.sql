-- Day 9 schema additions: real daily observation of both layers.
-- See DECISIONS.md (2026-10-15) for why each exists.

-- Shortages: track when each shortage was last seen in openFDA's feed,
-- and WHY an interval ended. tier 1 = confirmed resolved (status flipped
-- to Resolved), tier 2 = still open, tier 3 = dropped out of the feed
-- without ever being marked Resolved - "last observed", not "resolved".
ALTER TABLE shortages ADD COLUMN IF NOT EXISTS last_observed_date DATE;
ALTER TABLE shortages ADD COLUMN IF NOT EXISTS end_date_basis TEXT
    CHECK (end_date_basis IN ('confirmed_resolved', 'last_observed_in_feed'));

-- Every row in the July 18 pull was, by definition, observed that day.
UPDATE shortages SET last_observed_date = '2026-07-18' WHERE last_observed_date IS NULL;
UPDATE shortages SET end_date_basis = 'confirmed_resolved' WHERE tier = 1 AND end_date_basis IS NULL;

CREATE INDEX IF NOT EXISTS idx_shortages_generic_name ON shortages(generic_name);

-- NPIs the daily NPPES sweep finds that aren't in the curated pharmacies
-- table. Held for manual review, never auto-added to the map: a new NPI
-- needs pharmacy_type/ownership classification, geocoding, and a
-- physical_location assignment before it can be shown.
CREATE TABLE IF NOT EXISTS npi_review_queue (
    npi                     TEXT PRIMARY KEY,
    organization_name       TEXT,
    dba_name                TEXT,
    address_1               TEXT,
    city                    TEXT,
    postal_code             TEXT,
    primary_taxonomy_code   TEXT,
    primary_taxonomy_desc   TEXT,
    first_seen_date         DATE NOT NULL,
    last_seen_date          DATE NOT NULL
);

-- One row per job run, so job health is visible from the database itself
-- (GitHub Actions logs expire after 90 days).
CREATE TABLE IF NOT EXISTS snapshot_runs (
    id              BIGSERIAL PRIMARY KEY,
    run_date        DATE NOT NULL,
    job             TEXT NOT NULL CHECK (job IN ('shortages', 'pharmacies')),
    status          TEXT NOT NULL CHECK (status IN ('ok', 'aborted', 'failed')),
    details         JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
