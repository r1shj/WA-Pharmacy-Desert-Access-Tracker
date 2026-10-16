-- Day 11 (DECISIONS.md 2026-10-16): stop storing individuals' names.
-- The ownership repetition fallback used to label pharmacies
-- "Unidentified chain (shared authorized official: FIRST LAST, N locations)".
-- Keep the signal (classification_method + the group size), drop the name.
-- Idempotent: rows already relabelled are untouched.
ALTER TABLE pharmacies ADD COLUMN IF NOT EXISTS shared_signer_npi_count INTEGER;

UPDATE pharmacies
SET shared_signer_npi_count = substring(parent_organization from ', ([0-9]+) locations\)$')::int,
    parent_organization = 'Likely chain: several locations share a registered signer'
WHERE classification_method = 'authorized_official_repetition'
  AND parent_organization LIKE 'Unidentified chain (shared authorized official:%';

-- Two pharmacies are registered in NPPES with an individual's name as the
-- legal organization_name (it equals the record's authorized official's
-- name). Flag them by NPI - no name stored here - so the API shows their
-- DBA (trading name) instead. The legal name stays in the source data.
ALTER TABLE pharmacies ADD COLUMN IF NOT EXISTS organization_name_is_individual BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE pharmacies SET organization_name_is_individual = TRUE
WHERE npi IN ('1649333105', '1760594675');

-- And don't keep the legal personal name at all: store the trading name,
-- as the regenerated day2/day3 CSVs now do. The flag stays as the record
-- that the legal name was withheld.
UPDATE pharmacies SET organization_name = dba_name
WHERE organization_name_is_individual AND dba_name IS NOT NULL AND organization_name IS DISTINCT FROM dba_name;
