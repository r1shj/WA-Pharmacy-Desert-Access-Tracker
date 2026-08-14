# Verification pass on wa_pharmacies_final.csv (post county/ZIP-partition fix)

## 1. Field population — PASS

All 1,941 rows have `pharmacy_type`, `walk_in_access`, and
`included_in_access_analysis` populated (0 empty). `exclusion_reason` is
blank on 1,277 rows, but that's expected — it's only populated for
excluded/review/caveated rows, and 0 non-included rows have a blank reason.
Confirms the Day 2 classification logic (`classify_pharmacy_type.py`) was
in fact rerun against the full corrected 1,941-record set via
`build_final_dataset.py`, not left stale from the original 1,200.

## 2. Data-quality bug regressions — PASS, with one caveat carried forward

**Bartell Drugs (miscoded taxonomy):** all 65 real WA Bartell stores are
present, zero duplicates. The 5 records coded under `183700000X`
("Pharmacy Technician" — an individual credential type) are still
correctly reclassified to `community_retail` / `included=True` by the
name-marker rule. (10 additional Bartell records carry the generic
`333600000X` "Pharmacy" code and land in the `unspecified`/REVIEW bucket —
same as Day 2, not a regression.)

**Secondary-taxonomy-only records:** 42 records in the full pull have a
pharmacy taxonomy (3336*) somewhere in their taxonomy list but not as
primary. All 42 are present in the final CSV — none were dropped, confirming
the fuzzy `taxonomy_description=Pharmacy` text search (not a
primary-taxonomy-only filter) is still what's pulling them in.

*Caveat worth flagging explicitly*: of those 42, only 18 land in the
`unclassified_has_pharmacy_taxonomy` REVIEW bucket as intended. The other
24 (23 `non_pharmacy` + 1 `military`) get classified purely off their
*primary* taxonomy code, because `classify()` checks the `RULES` and
`NON_PHARMACY_FALSE_POSITIVES` tables before falling back to the
"has any pharmacy taxonomy" check — so a record whose primary code is e.g.
DME or Military short-circuits before the secondary pharmacy taxonomy is
ever considered. **This is the same limitation Day 2 already flagged**
(the original AMS HOMECARE USA INC example — DME primary / Pharmacy
secondary), not a new regression from the county-partition fix. It scaled
up proportionally with the larger, corrected dataset (13-record gap at
n=1,200 -> 24-record gap at n=1,941). Still an open item for a future
classification pass, not something today's verification was asked to fix.

## 3. Integrity checks — PASS

- **Duplicates**: 1,941 rows, 1,941 unique NPIs. Zero duplicates from
  combining the 1,403 per-ZIP partition pulls.
- **LOCATION.state == 'WA'**: cross-referenced every CSV row's NPI back to
  `wa_pharmacies_true_location_raw.json` — all 1,941 resolve to a record
  whose actual `LOCATION` address (not mailing) has `state == 'WA'`, and
  every row's `postal_code` column matches that same LOCATION address's
  ZIP. Zero mismatches.

## 4. Final verified counts

| | count |
|---|---|
| Total rows | 1,941 |
| Included in access analysis | 1,363 |
| Excluded (definitive) | 128 |
| Flagged for review (unknown/ambiguous) | 450 |
| Excluded + review | 578 |

**Matches the previously reported 1,363 included / 578 excluded+review
exactly — no discrepancy.** (Previous report combined excluded+review into
one figure; this pass breaks it out: 128 definitively excluded, 450 still
flagged REVIEW rather than decided either way.)

## Bottom line

The Day 2 classification survived the Day 2.5 county/ZIP-partition fix
intact and correctly rerun against the full dataset. No dataset integrity
issues (no dupes, no non-WA leakage). One known limitation (secondary-only
taxonomy records with a non-pharmacy primary code) persists unchanged from
Day 2 — flagged again here for visibility, not treated as a surprise.
