# Day 3 — ownership classification & address dedup

## Part 1: Ownership classification

Applied to the 1,837 included+review records from `wa_pharmacies_final.csv`
(the 104 definitively-excluded records are passed through as
`ownership_category=not_applicable`). Method: match DBA/org-name against
a version-controlled lookup (`chain_lookup.py`, patterns grounded in
actual token frequency in this dataset - see `explore_names.py` output),
then fall back to Day 1's "shared authorized official across 3+ NPIs"
signal only when no name pattern matched. Unmatched stays `unknown` -
never defaulted to `independent_confirmed` (see DECISIONS.md).

### Ownership frequency table (n=1,837 in scope)

| ownership_category | count | % of scope | confidence |
|---|---|---|---|
| chain | 1,128 | 61.4% | 1,004 high (name match) + 124 medium (officer repetition) |
| unknown | 392 | 21.3% | n/a |
| health_system | 256 | 13.9% | high (name match) |
| government_or_tribal | 46 | 2.5% | high (name match) |
| independent_confirmed | 15 | 0.8% | medium (franchise-brand match) |

(Plus 104 `not_applicable` records outside the access-analysis scope,
1,941 total.)

**Read the `independent_confirmed` number carefully**: 15 is not "how many
independent pharmacies exist in WA" - it's how many we found *positive*
evidence for (Health Mart / Medicine Shoppe / Good Neighbor Pharmacy
franchise branding). Most of the 392 `unknown` records are very likely
independent in reality, but we don't have the evidence to say so
confidently - see DECISIONS.md "Unmatched != independent."

### A bug caught and fixed during this pass

The officer-repetition fallback initially mislabeled Seattle Children's
Hospital and UW Medicine records as generic "chain" because their
specific names weren't yet in `HEALTH_SYSTEM_PATTERNS`. Patched by adding
explicit patterns for both, plus a broad `COMMUNITY HEALTH` catch-all that
picked up several differently-named WA community health centers at once
(Community Health Center of Snohomish County, Tri-Cities Community
Health, Community Health Association of Spokane, etc.), plus a
`PUBLIC HOSPITAL DIST(RICT)` pattern for WA's special-purpose hospital
districts (legally government entities). This moved 65 records from
`chain` to `health_system`/`government_or_tribal` and shrank the
officer-repetition fallback group from 38 to 28. Full detail in
DECISIONS.md.

## Part 2: Address dedup

Grouped all 1,941 records by normalized address (`normalize_address.py`
canonicalizes case/punctuation/directional and street-suffix abbreviations
- does not strip suite/unit numbers, and doesn't touch the original
`address_1` column).

### Raw address group sizes (before any collapsing)

| NPIs sharing one normalized address | # of addresses |
|---|---|
| 1 | 1,408 |
| 2 | 210 |
| 3 | 31 |
| 4 | 2 |
| 6 | 2 |

1,653 unique normalized addresses across 1,941 NPIs.

### Collapse rule applied

Collapse two NPIs at the same address into one `physical_location_id`
only if their name/DBA is "substantially similar" (exact match, or one
contains the other, after normalizing case/punctuation/store-numbers/legal
suffixes) **and** they share the same `pharmacy_type`. Otherwise keep them
as separate locations and flag `manual_review_required=True` for every
NPI at that address (including ones that did successfully collapse with
something else at the same address, since a split there is itself worth a
human's attention).

Deliberately **not** using fuzzy-ratio text similarity (e.g. difflib):
calibrating against this dataset's own real address groups showed
templated names like "KAISER PERMANENTE BELLEVUE INFUSION PHARMACY" vs
"KAISER PERMANENTE FACTORIA PHARMACY" score a deceptively high fuzzy
ratio (0.71-0.89) despite being different pharmacies that happen to share
a campus mailing address - a real false-merge risk. Plain containment
rejected all the risky Kaiser pairs while still catching every genuine
same-store case in the dataset (Bartell Drugs re-registrations, the 14th
Avenue Pharmacy trio from Day 1, Haggen locations re-registered under
three different corporate names over time, short-name-vs-branded-name QFC
records).

### A second bug caught and fixed during this pass

Initial version also compared `organization_name` directly between
records. This over-merged: "KAISER FOUNDATION HEALTH PLAN OF WASHINGTON"
is the identical legal `organization_name` for both a Bellevue infusion
pharmacy and an unrelated Factoria pharmacy, so org-name equality alone
nearly merged two genuinely different locations. Fixed by disabling the
org-name comparison channel (requiring a DBA match instead) whenever
either record's `ownership_category` is `health_system` or
`government_or_tribal` - these are exactly the entity types that
legitimately run multiple distinct pharmacy departments from one nominal
campus address, unlike retail chains. Verified this didn't break the
legitimate Bartell/QFC/Haggen collapses, which all resolve independently
of the org-name channel.

### Dedup results (n=1,941)

| | count |
|---|---|
| Distinct `physical_location_id`s | 1,811 |
| NPIs auto-collapsed with >=1 other NPI | 254 |
| NPIs flagged `manual_review_required` | 319 |

| collapse_reason | count |
|---|---|
| single_npi_at_address | 1,408 |
| no_match_kept_separate | 279 |
| collapsed_same_name_and_type | 214 |
| partial_match_subset_collapsed | 40 |

Every NPI is traceable to its `physical_location_id` via
`npi_to_physical_location_bridge.csv` (simple two-column CSV, npi ->
physical_location_id). The full per-NPI detail (including
`ownership_category`, `normalized_address_1`, `collapse_reason`,
`manual_review_required`) is in `wa_pharmacies_deduped.csv`.

## Files produced

- `chain_lookup.py` - version-controlled DBA/org-name -> parent_organization pattern table
- `classify_ownership.py` - applies the lookup + officer-repetition fallback
- `wa_pharmacies_ownership.csv` - Part 1 output
- `normalize_address.py`, `dedup_addresses.py` - Part 2
- `wa_pharmacies_deduped.csv` - final Day 3 dataset (all Day 2 fields + ownership + dedup fields)
- `npi_to_physical_location_bridge.csv` - the traceability bridge table
