# Day 2 — Study population & active-status audit

## 1. Study population

Pulled all WA organizational NPIs matching `taxonomy_description=Pharmacy` via the
NPPES API. **Hit the API's hard pagination ceiling at 1,200 results** (skip max
1000 + limit max 200 = 1200). The true WA population is larger than 1,200 —
this pull is a large, representative sample, not a full census. Getting the
rest requires partitioning the query (e.g. by county or by narrower taxonomy
terms) — deferred to Day 3+ since the task said not to build the pipeline yet.

### Taxonomy distribution (n=1,200) and inclusion decision

| taxonomy_code | description | count | pharmacy_type | walk_in_access | included_in_access_analysis | exclusion_reason |
|---|---|---|---|---|---|---|
| 3336C0003X | Community/Retail Pharmacy | 1021 | community_retail | yes | **TRUE** | — |
| 183700000X* | (miscoded — see below) | 5 | community_retail | yes | **TRUE** | reclassified, see note |
| 3336C0002X | Clinic Pharmacy | 38 | clinic | yes, restricted | **TRUE** | walk-in but may be limited to that clinic's patient panel |
| 3336C0004X | Compounding Pharmacy | 10 | compounding | yes | **TRUE** | — |
| 3336L0003X | Long Term Care Pharmacy | 42 | long_term_care | no | FALSE | closed-door, serves facility residents not the public |
| 3336M0002X | Mail Order Pharmacy | 10 | mail_order | no | FALSE | no walk-in storefront |
| 3336S0011X | Specialty Pharmacy | 12 | specialty | no (default) | FALSE | typically appointment/mail-based; some do have storefronts — flagged uncertain |
| 3336H0001X | Home Infusion Therapy Pharmacy | 4 | home_infusion | no | FALSE | home delivery service, not a walk-in location |
| 332000000X | Military/Coast Guard Pharmacy | 2 | military | no | FALSE | restricted to military beneficiaries |
| 3336M0003X | Managed Care Organization Pharmacy | 1 | managed_care_org | no | FALSE | administrative/network entity, not a storefront |
| 333600000X | Pharmacy (generic/unspecified) | 40 | unspecified | unknown | **REVIEW** | generic code carries no sub-type info |
| 3336I0012X | Institutional Pharmacy | 3 | institutional | unknown | **REVIEW** | hospital outpatient pharmacies are often public; inpatient-only ones are closed-door — ambiguous without a per-record check |
| 332B00000X, 335E00000X, 291U00000X, 175F00000X, 183500000X, 261QM1300X, 261QH0100X | DME supplier, Prosthetic/Orthotic, Clinical Lab, Naturopath, individual Pharmacist, two Clinic/Center codes | 12 total | non_pharmacy | no | FALSE | false positives from the fuzzy `taxonomy_description` text search — not pharmacies |

**Result: 1,074 included / 83 excluded / 43 flagged for manual review**, out of
1,200 pulled. Nothing was deleted — every record keeps its `pharmacy_type`,
`walk_in_access`, `included_in_access_analysis`, and `exclusion_reason` in
`wa_pharmacies_classified.csv`. *(Note added 2026-10-16: that file is no longer
tracked in git. It was this superseded 1,200-record sample and predates the
2026-07-18 classification fix. Regenerate it with `classify_pharmacy_type.py`.
The analysis uses the full 1,941-record `wa_pharmacies_final.csv`.)*

### Two concrete data-quality findings (not hypothetical)

1. **Taxonomy coding errors exist in NPPES itself.** 5 Bartell Drugs
   locations (a real, operating WA chain) are coded under `183700000X`
   ("Pharmacy Technician" — an *individual* credential type), not any
   pharmacy code. A strict code-based filter would have silently dropped
   them. They were only caught because the API's `taxonomy_description=Pharmacy`
   search does fuzzy text matching against the description string (which
   contains the substring "Pharmacy"), not a rigid code match. **Recommendation:
   keep using the text-search approach, and treat "primary taxonomy" as
   necessary-but-not-sufficient — some real pharmacies need name-based rescue.**
2. **"Primary" taxonomy isn't always the meaningful one.** One record
   (AMS HOMECARE USA INC.) is a DME supplier whose *primary* taxonomy is
   Durable Medical Equipment, but it also carries a secondary "Pharmacy"
   taxonomy. 1,194 records have *some* pharmacy-related taxonomy vs. 1,181
   where it's specifically primary — a 13-record gap that primary-only
   logic would miss.

## 2. Active status

- The NPPES public API's `basic.status` field exists and returned **`"A"`
  (Active) for all 1,200 records** in this pull. Deactivated NPIs do not
  appear to surface through this lightweight API at all.
- Deactivation detail (`NPI Deactivation Date`, `NPI Deactivation Reason
  Code` — values are Death / Disbandment / Fraud / Other, `NPI Reactivation
  Date`) exists **only in CMS's full monthly bulk file** (multi-GB, all US
  providers), confirmed from the official
  [NPPES Data Dissemination code-values PDF](https://www.cms.gov/regulations-and-guidance/administrative-simplification/nationalprovidentstand/downloads/data_dissemination_file-code_values.pdf).
  It is not exposed per-record via the API.
- **This is the crux of the Day 1 finding**: an "Active" NPI only means CMS
  hasn't received formal notice of death/disbandment/fraud — it does *not*
  mean the pharmacy is currently open. A closed independent pharmacy that
  never notified CMS will show "Active" indefinitely.
- As a free, already-available (not a substitute for real validation) weak
  signal: `last_updated` on the org record ranges from 2007-07-20 to
  2026-07-xx. **82 of 1,200 records (6.8%) haven't been touched since before
  2015** — over a decade with no registration activity. This doesn't prove
  closure (an open pharmacy can go a decade without touching its NPI
  record), but it's a defensible "worth a second look" flag.

## 3. WA DOH validation — blocked, not completed

Per your direction, this is documented as a known limitation rather than
worked around:

- WA DOH's only **downloadable** dataset
  ([`qxh8-f4bd` on data.wa.gov](https://data.wa.gov/resource/qxh8-f4bd.json))
  covers **individual practitioner credentials only** — confirmed by pulling
  all 310 distinct `credentialtype` values. Pharmacist, Pharmacy Technician,
  Pharmacy Assistant, and Pharmacy Collaborative Drug Therapy Agreement all
  appear; a facility-level "Pharmacy License" type does not.
- The only place a pharmacy *facility* license actually lives is the
  **"Facility and Services Search" tab** of the new HELMS portal
  (`wahelms.my.site.com/s/license-search`), which is protected by reCAPTCHA.
  I stopped there rather than attempt to bypass it.
- **No automated or bulk cross-check against DOH facility licensing data
  exists for this project as of today.** If/when this matters more, the
  realistic paths are: a human manually spot-checking a sample through that
  UI, or a formal public-records request to DOH for a facility license
  extract.

## 4. Recommended inclusion rule going forward

- Use `taxonomy_description=Pharmacy` (fuzzy text search) as the pull
  filter, not a rigid taxonomy-code allowlist — it catches known coding
  errors like the Bartell case.
- Treat `included_in_access_analysis=TRUE` records (1,074 of 1,200: retail,
  clinic, compounding) as the default study population for the desert
  analysis.
- Carry the 43 "REVIEW" records (institutional + unspecified "Pharmacy")
  forward with their flag rather than silently excluding them — they need
  either an address-type check or manual eyeballing before Day 3.
- Do **not** treat NPPES "Active" as proof of "open." Frame this explicitly
  in the README/system language per the v2 project reframing — this tool
  reports registered access points and a national shortage context layer,
  not confirmed local availability.
- DOH validation remains an open gap — flag it plainly wherever operating
  status is discussed downstream.

## Files produced

- `wa_pharmacies_full_raw.json` — raw API response, 1,200 records
- `wa_pharmacies_full_flat.csv` — flattened, same 1,200 *(not tracked in git: it
  contains authorized officials' names and phone numbers)*
- `wa_pharmacy_taxonomy_counts.csv` — taxonomy frequency table
- `wa_pharmacies_classified.csv` — same 1,200 with `pharmacy_type`,
  `walk_in_access`, `included_in_access_analysis`, `exclusion_reason` added
  *(not tracked in git; superseded, see note above)*
