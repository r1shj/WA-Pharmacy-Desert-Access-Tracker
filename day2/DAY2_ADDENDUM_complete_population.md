# Day 2 addendum — complete WA population + county rollup

## What was done

1. Partitioned the NPPES pull across all 1,403 possible WA ZIP codes
   (98001-99403, the USPS-assigned range) since `postal_code` only supports
   exact match, not prefix. Chose ZIP over city/county partitioning because
   it's a finite, enumerable, USPS-defined key — not dependent on any
   external city-name list being complete.
2. Ran the full 1,403-zip sweep **twice, independently, from a cold cache**.
   Both runs returned exactly the same 3,364 unique NPIs (zero difference
   either direction) — the pull is complete and stable, not an artifact of
   API flakiness or an incomplete zip range. No individual zip hit its own
   200/page pagination cap, so no further sub-partitioning was needed.

## A critical correction this surfaced

While mapping results to county, ~42% of the 3,364 records had a physical
`LOCATION` address **outside Washington entirely** (e.g. a Florida-based
Genoa Healthcare pharmacy, an Astoria, OR pharmacy, a Monterey, CA military
pharmacy). Root cause: **NPPES's `postal_code` and `state` query
parameters match against *any* address on the record — including the
`MAILING` address — not specifically the physical `LOCATION` address.** An
out-of-state pharmacy chain with a Washington billing/mailing address will
match a WA-scoped query even though it has no WA storefront.

This affected the **original Day 1/Day 2 pull too**: of the original
1,200-capped `state=WA` sample, 640 records (53%) had a non-WA `LOCATION`
address. Those Day 2 numbers (1,074 included / 83 excluded / 43 review)
are **superseded** by this corrected pull — they were built on a sample
that was itself roughly half contaminated with out-of-state entities.

**Fix applied**: filter to `LOCATION.state == 'WA'` explicitly, rather than
trusting the API's own `state`/`postal_code` filters. This removed 1,423
false positives and left:

### Corrected total: 1,941 pharmacy-taxonomy NPIs with a true WA physical location

Sanity check: Bartell Drugs (a known Puget-Sound-area chain that
historically runs ~60-67 stores) now shows **65 WA-located records** in
this corrected pull — consistent with public knowledge of the chain's
footprint, versus only 5 visible in the old capped sample.

## Corrected pharmacy_type breakdown (n=1,941)

| pharmacy_type | count | included_in_access_analysis |
|---|---|---|
| community_retail | 1249 | TRUE |
| unspecified (generic "Pharmacy" code) | 413 | REVIEW |
| clinic | 81 | TRUE |
| long_term_care | 59 | FALSE |
| compounding | 33 | TRUE |
| non_pharmacy (false positive from fuzzy text search) | 24 | FALSE |
| specialty | 20 | FALSE (default) |
| unclassified_has_pharmacy_taxonomy | 18 | REVIEW |
| institutional | 16 | REVIEW |
| home_infusion | 15 | FALSE |
| mail_order | 8 | FALSE |
| unclassified | 3 | REVIEW |
| military | 1 | FALSE |
| managed_care_org | 1 | FALSE |

**1,363 included / 578 excluded+review**, out of 1,941.

Notably, `long_term_care` dropped from 777 (contaminated count) to 59 (true
WA count) — most LTC-pharmacy taxonomy hits were large regional/national
long-term-care pharmacy operators (e.g. Omnicare-style chains) serving WA
facilities from an out-of-state distribution hub, not physically located
in WA.

## County rollup (total pharmacy-taxonomy NPIs / included_in_access_analysis)

All 39 WA counties are represented. Built via a Census Bureau 2020
ZCTA-to-county relationship file; for the 84 WA ZIPs that straddle two
counties, assigned the county with the larger land-area overlap. Only 2 of
1,941 records didn't resolve to a county (edge-case ZIPs).

| County | Total | Included | County | Total | Included |
|---|---|---|---|---|---|
| King | 607 | 392 | Kittitas | 19 | 16 |
| Pierce | 204 | 136 | Franklin | 19 | 16 |
| Snohomish | 195 | 134 | Okanogan | 17 | 15 |
| Spokane | 158 | 106 | Island | 16 | 11 |
| Clark | 95 | 68 | Mason | 15 | 13 |
| Thurston | 64 | 51 | Douglas | 15 | 13 |
| Kitsap | 64 | 47 | Walla Walla | 14 | 12 |
| Yakima | 62 | 47 | Jefferson | 12 | 11 |
| Benton | 61 | 50 | Whitman | 12 | 11 |
| Whatcom | 55 | 35 | Stevens | 10 | 8 |
| Skagit | 47 | 32 | Pacific | 9 | 7 |
| Cowlitz | 25 | 18 | Asotin | 8 | 7 |
| Lewis | 25 | 13 | San Juan | 4 | 3 |
| Grant | 22 | 20 | Skamania | 4 | 2 |
| Clallam | 21 | 16 | Lincoln | 4 | 4 |
| Grays Harbor | 20 | 16 | Klickitat | 3 | 3 |
| Chelan | 20 | 17 | Pend Oreille | 3 | 3 |
| | | | Ferry | 3 | 3 |
| | | | Adams | 3 | 2 |
| | | | Garfield | 2 | 2 |
| | | | Wahkiakum | 1 | 1 |
| | | | Columbia | 1 | 1 |

Rural low-population counties (Garfield, Columbia, Wahkiakum, Ferry) show
1-3 pharmacies each — expected given their population sizes, and exactly
the kind of number a desert analysis will need to weigh against ACS
population/income per tract.

## Standing rule for Day 3+

Any future NPPES pull must explicitly filter on the `LOCATION` address
object's `state`/`postal_code` fields client-side — never trust the API's
own `state=`/`postal_code=` query parameters to mean "physically located
here." They mean "has *an* address here."

## Files produced

- `wa_pharmacies_by_zip_raw.json` — all 3,364 records matched by the zip
  sweep, pre-filter (kept for transparency/audit trail)
- `wa_pharmacies_true_location_raw.json` — the 1,941 records with a
  confirmed WA `LOCATION` address
- `wa_zip_to_county.json` — WA ZIP -> county crosswalk (606 zips, 39
  counties)
- `wa_pharmacies_final.csv` — the deliverable: 1,941 records with
  `county`, `pharmacy_type`, `walk_in_access`, `included_in_access_analysis`,
  `exclusion_reason`
