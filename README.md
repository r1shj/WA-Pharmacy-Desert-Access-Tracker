# Washington Pharmacy Access & Shortage Tracker

**Live site: https://wa-pharmacy-desert-access-tracker.onrender.com**

An interactive map of where Washingtonians live relative to a pharmacy. It
finds the state's pharmacy deserts at the neighborhood (census block group)
level and puts them next to the FDA's national drug-shortage list. Built
end to end:
- a Python data pipeline over federal registry, Census and FDA data;
- a PostGIS database;
- a FastAPI + Leaflet web app;
- a GitHub Actions job that re-pulls the pharmacy registry and the shortage
  feed every day.

It maps 1,811 pharmacy locations and 5,311 block groups covering all
7,705,281 Washington residents in the 2020 Census. Every methodological
judgment call is written down in [DECISIONS.md](DECISIONS.md), and every
known gap in [LIMITATIONS.md](LIMITATIONS.md).

It is a **pharmacy access and desert explorer with national shortage
context**. It does **not** know what any pharmacy has in stock: no public
source anywhere reports pharmacy-level or Washington-specific drug
availability.

| Page | Current view | Timeline slider |
|---|---|---|
| [Pharmacy Access Map](https://wa-pharmacy-desert-access-tracker.onrender.com/map/pharmacy) | Every mapped pharmacy location, colored by ownership, over block groups shaded by desert status (with OR/ID border pharmacies shown for reference) | Which locations had registered by a date, back to 2005. From 2026-07-18 on, which were active in an observed registry snapshot |
| [Shortage Context Map](https://wa-pharmacy-desert-access-tracker.onrender.com/map/shortages) | **National** context: FDA's national shortage list beside a 0-100 vulnerability index per block group. The index's geographic pattern comes entirely from the desert classification's access and income measures; the shortage part is one national number, the same everywhere | Which national shortages were active on a date, back to 2012, with the index recomputed for that date |

The first load after a quiet period can take 30-60 seconds while the free
hosting tier wakes up.

---

## At a glance (as of 2026-10-16)

| | |
|---|---|
| Pharmacy NPIs in Washington (organization NPIs with a WA physical address and a pharmacy taxonomy) | 1,941 |
| Physical pharmacy locations after deduplication | 1,811 |
| Locations on the map | 1,624 (1,177 with a confirmed walk-in pharmacy + 447 still in review) |
| Block groups / residents (2020 Census) | 5,311 / 7,705,281 |
| Block groups beyond the distance threshold ("low access") | 1,458 (2,188,152 residents) |
| **Pharmacy-desert block groups** (low access **and** low income) | **237 (346,334 residents)**; between 176 and 237 depending on unresolved review records ([why](#methodology)) |
| National shortages tracked / active today / active in the 7 chronic-condition categories | 274 / 231 / 103 |

---

## Data sources

| Source | Used for |
|---|---|
| [NPPES NPI Registry API](https://npiregistry.cms.hhs.gov/) (CMS) | The pharmacy population: organization NPIs with a pharmacy taxonomy. Re-swept daily |
| [Census ACS](https://www.census.gov/programs-surveys/acs) 2022 5-year | Tract median household income and population |
| [TIGER/Line](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html) 2020 | Tract and block-group boundaries |
| [CenPop 2020](https://www.census.gov/geographies/reference-files/time-series/geo/centers-population.html) block-group centers of population | Where residents actually live in each block group, plus its 2020 population |
| [2020 Census Urban Areas](https://www.census.gov/programs-surveys/geography/guidance/geo-areas/urban-rural.html) (cartographic boundary file) | The urban/rural split |
| [Census Geocoder](https://geocoding.geo.census.gov/) (batch; `Public_AR_Current` / `Census2020_Current`) | Pharmacy coordinates and tract assignment |
| Census ZCTA Gazetteer 2023 | Finding Oregon and Idaho ZIP codes within 20 miles of the border |
| [openFDA Drug Shortages](https://open.fda.gov/apis/drug/drugshortages/) | The national shortage list. Pulled daily |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) | Map tiles |

---

## Methodology

Written for someone who wants to check the work. The reasoning behind each
choice, with the evidence, is in [DECISIONS.md](DECISIONS.md).

### Pharmacy population

**Pulling the population.** NPPES caps any query at 1,200 results, so the
pull is partitioned across every Washington ZIP code (98001-99403; 1,403
codes) and deduplicated by NPI. The API's `state` and `postal_code`
filters also match *mailing* addresses: 42% of the raw sweep was physically
out of state. So every record is kept only if its `LOCATION` address is in
Washington. Result: 1,941 NPIs.

**Classifying pharmacy type** from taxonomy codes:

| Bucket | NPIs | Types |
|---|---|---|
| Included (walk-in) | 1,363 | 1,249 community retail, 81 clinic, 33 compounding |
| Excluded | 104 | long-term care, specialty, home infusion, mail order, other |
| **Review** | 474 | mostly the generic "Pharmacy" code (413), which carries no subtype |

Review records are never dropped. They're shown on the map with a warning
outline, but they are not counted when measuring distance.

### Deduplication: NPIs to physical locations

One storefront often carries several NPIs, for example after an ownership
change. NPIs are grouped into a `physical_location_id`:
- **Same normalized street address, plus one of two conditions:**
  - the names match by containment (one name contains the other once legal
    suffixes and store numbers are stripped). Fuzzy ratios were tested and
    rejected because they merged different pharmacies with templated
    names.
  - the pharmacy type matches.
- **Health systems and government/tribal organizations need a DBA match.**
  Their legal `organization_name` is shared across genuinely different
  pharmacies on one campus, so it doesn't count as evidence.

**Result:**
- 1,941 NPIs became 1,811 locations, 124 of them with two or more NPIs.
- 299 locations (319 NPIs) carry `dedup_manual_review_required` instead of
  being force-merged, so 1,811 is a conservative count. The NPI-to-location
  mapping is in `day3/npi_to_physical_location_bridge.csv`.
- **Geocoding:** 1,722 locations (95.1%) got usable coordinates from the
  Census Geocoder (1,511 exact, 211 non-exact). The 15 "tie" and 74
  unmatched addresses are flagged separately (`geocode_manual_review_required`)
  and are not mapped.

### Ownership classification

**How a pharmacy is classified:**
- **Chain, health system, government/tribal:** matched by DBA, then legal
  name, against curated name patterns.
- **Officer repetition (fallback):** the same authorized official signing
  for 3 or more NPIs counts as a medium-confidence chain signal.
- **Unmatched pharmacies stay `unknown`, never "independent."** Failing to
  match a list proves the list is incomplete at least as often as it proves
  independence.
- **`independent_confirmed` requires positive evidence only:** a
  franchise-program DBA (Health Mart, Medicine Shoppe, Good Neighbor
  Pharmacy), which by definition means individually owned.

**Result** across the 1,837 included and review NPIs: 1,128 chain, 253
health system, 49 government/tribal, **15 independent_confirmed, 392
unknown**. The 15 is not the number of independent pharmacies in Washington;
most of the 392 unknowns are probably independents too.

### Pharmacy desert classification (block group level)

- **Unit:** all 5,311 Washington block groups. Each is measured from its
  CenPop 2020 **population-weighted center** (where residents actually live),
  not its geometric centroid.
- **Urban vs. rural:** a block group is urban if that center falls inside a
  2020 Census Urban Area (4,244 urban, 1,067 rural).
- **Low access:** the nearest counted pharmacy is more than **1 mile (urban)
  or 10 miles (rural)** away, the same pattern as USDA's food-desert
  definition.
- **Distance is straight-line and means geographic proximity, NOT travel
  access.** It understates real trips across water and mountains, both
  common in Washington.
- **Border correction:** pharmacies in Oregon and Idaho ZIP codes within 20
  miles of the state line (99 OR and 33 ID ZIP codes; 524 locations, of which
  334 are geocoded walk-in pharmacies) count toward distance only. They are
  never part of Washington's pharmacy counts. This changes real outcomes: a
  Klickitat County block group (tract 9502) goes from 16.17 miles (Washington pharmacies
  only) to 2.37 miles once the pharmacy across the Columbia River is counted.
  Several Skamania County block groups remain deserts even with it.
- **Low income:**
  - A tract is low-income if its ACS median household income is below
    **80% of its county's area median income**. The 80% rule is HUD's
    standard.
  - **The county median used is a proxy we computed from our own ACS data**:
    the population-weighted average of the county's tract medians. It is
    **not HUD's published figure**, which uses family income and its own
    method. HUD's file couldn't be retrieved.
  - Block groups take their tract's status. The 20 tracts with suppressed
    income (21 block groups) are marked indeterminate, never defaulted.
- **Desert = low access AND low income.**

| Result | Block groups | Residents |
|---|---|---|
| Desert | 237 (207 urban, 30 rural) | 346,334 |
| Indeterminate (income suppressed) | 21 | 11,697 |
| Not a desert | 5,053 | 7,347,250 |

**Why 237 is an upper end.** Distance counts only the 1,177 Washington
locations with a confirmed walk-in pharmacy (plus the border pharmacies).
61 of the 237 desert block groups (91,478 residents) lie within their
threshold of one of the 447 review-bucket locations. Many of those are
plausibly real grocery-store pharmacies under the generic taxonomy code. So
under this method the desert count is **between 176 and 237 block groups
(about 255,000 to 346,000 residents)**.

### Vulnerability index (Shortage Context Map)

Defined in advance of any code ([DECISIONS.md](DECISIONS.md), 2026-07-27):

```
score = access (0 or 40) + income (0 or 40) + shortage (0-20)
shortage = min(20, round(20 × active chronic-condition shortages / 150))
```

- **Access and income** come from the desert classification above, and
  they are the **only** source of the map's geographic pattern.
- **The shortage term is ONE national number, identical for every block
  group.**
  - It counts the openFDA shortages active on the selected date in 7
    chronic-condition categories: Endocrinology/Metabolism, Cardiovascular,
    Pulmonary/Allergy, Psychiatry, Analgesia/Addiction, Renal and
    Rheumatology. Today that's 103 shortages, worth 14 points.
  - Moving the slider shifts the whole map together. **Geographic
    differences come only from access and income.**
- **The 150-shortage saturation constant is a judgment call.** It was chosen
  to leave headroom above the count at design time (105), not derived from
  any external standard.
- **Suppressed-income block groups** (21) get a **partial 0-60 score
  (access + shortage) and no band**, shown in grey. They are never ranked
  against complete scores.
- **The map is colored by the continuous 0-100 score.** It used to be
  colored by three bands (low ≤33, medium ≤66, high), but with access and
  income each worth 0 or 40, scores fell only in 0-20, 40-60 or 80-100. The
  band cutoffs sit in the gaps, so **the three-band coloring could never
  respond to shortage changes**, and "high" was exactly the 237 deserts. On
  the continuous scale, the shortage term visibly lightens or darkens the
  map as the slider moves. Bands remain as labels in the popups.

---

## Timeline caveats

**Pharmacy timeline**
- **Pharmacy history shows growth only, never closures.** Before observed
  snapshots exist, a location counts as present from its earliest NPI
  registration date. NPPES does not publicly expose deactivation dates, and
  the API serves only active NPIs. So past counts both include pharmacies
  that closed without deactivating and miss ones that closed and
  deactivated. They're neither a floor nor a ceiling.
- **"NPI no longer active" is not confirmation that a pharmacy closed.**
  Pharmacies often don't deactivate promptly, and deactivation can happen
  for other reasons. The first daily re-sweep found zero deactivations among
  1,941 NPIs after three months.
- **Dates before ~2008 reflect the NPI registration deadline, not real
  openings.** 49% of records show a 2006 registration date, 80% of those in
  May-August 2006.
- **Real observed snapshots begin 2026-07-18.**
  - Daily re-sweeps of the whole registry started 2026-10-15; dates in
    between show the 2026-07-18 state, labelled as such.
  - The daily snapshot files collected locally between those dates were
    byte-identical copies of one static file. They were never loaded as
    observations.
- **Newly registered pharmacies** (11 so far) wait in a review list and
  aren't on the map until they're classified and geocoded.

**Shortage timeline**
- **Shortage history is two-tier.**
  - **Before 2026-07-18:** reconstructed from openFDA's current records.
    openFDA keeps no history, so a shortage counts as active from its
    posting date until it's marked Resolved or, if still listed, until today.
  - **From 2026-07-18:** the feed is observed daily.
- **For a shortage that left the feed, the end date means "last observed,"
  not "resolved."** Of the 274 tracked shortages, 231 are open, 8 have a
  confirmed resolution and 35 left the feed without one. All 35 were
  discontinuation notices that dropped off about a year after posting.

**The run log** (`snapshot_runs`)
- Each scheduled run logs one row per job. Analyses should use the **latest
  successful run per day**.
- Pharmacy totals in the log are state counts and **must not be summed
  across a day's runs**.

---

## Operations and performance

- **Daily data:** a GitHub Actions workflow runs twice daily (14:17 and
  20:43 UTC) on GitHub's best-effort scheduler.
  - A scheduled run has been confirmed working, with observed delays of up
    to about four hours. A slot can occasionally be skipped, so a day is lost
    only if both runs miss.
  - Each run re-sweeps NPPES and re-pulls openFDA. A second run the same day
    overwrites that day's snapshot rather than adding to it.
  - Safeguards abort a run before any snapshot data is written. Each job
    runs in its own transaction, so a run that fails mid-way also writes
    nothing; only its `snapshot_runs` log row is kept. A run aborts if:
    - openFDA returns fewer records than its own reported total;
    - more than 25% of open shortages vanish from one day's feed;
    - any NPPES ZIP query still fails after 4 attempts or exceeds the
      API's 1,200-result cap;
    - more than 10% of known NPIs are missing from the sweep;
    - a direct lookup of a missing NPI fails (a failure is never read as a
      deactivation);
    - more than 3% of the pharmacy locations in the previous observed
      snapshot would disappear (overridable only with `--allow-large-drop`
      after review).
- **Caching:** Both date sliders are served from in-memory caches with fixed
  size caps (the whole app peaks at about 140 MB of the host's 512 MB),
  refreshed every 5 minutes and backed by a 4-connection database pool kept
  under Supabase's 15-connection limit, so dragging a slider never overloads
  the database and new daily data appears on the site within 5 minutes.
- **Hosting:** the web app runs on Render's free tier, which sleeps when
  idle, so the first load after a quiet period can take 30-60 seconds. The
  database is Supabase Postgres + PostGIS. Row-level security is on, and the
  public API roles have no access.
- **Free-tier timers:** GitHub disables scheduled workflows after 60 days
  without a push to the repo. Supabase pauses a free project after 7 days of
  inactivity (the daily job should keep it active).
- **Redeploys:** Render redeploys when files under `webapp/` change.
  `jobs/db.py` is outside Render's `webapp/` root but the app imports it, so
  a change to that file alone will not redeploy the site. A manual deploy is
  needed.

---

## Related work

As far as I could tell in October 2026, the closest existing resource is an
ArcGIS Online web map, ["Pharmacy care in rural Washington"](https://www.arcgis.com/home/item.html?id=a0472a0adb594ca38e0e1d2e55ce3e1a).
It's published from a Washington State University account and appears to be
associated with WSU's Rural Health Initiative (its rotation-site layer is
labelled "RHI WSU"). Its item metadata shows it was created in December 2023
and last updated in February 2024. It has five layers:

- **Washington Pharmacy Deserts:** 86 towns, each with a 2019 population, a
  "miles to a pharmacy" figure (10.2 to 27.7 miles) and the name of that
  pharmacy. Five of the towns list an Oregon pharmacy (in Astoria or The
  Dalles), so cross-border pharmacies are taken into account. The layer
  doesn't say how the miles were measured.
- **Critical Access Hospitals / Acute Care:** 39 hospitals, with address,
  phone and website.
- **RHI WSU Pharmacy Student Rotation Sites:** 13 sites.
- **MUA / MUP (Medically Underserved Areas and Populations):** shown as a
  static image overlay, not data. As far as I could tell, these are the
  federal HRSA designations, which weigh poverty alongside provider supply
  and other health factors.
- **Rural Counties:** a drawn overlay.

It pairs rural pharmacy distance with health-care context this project
doesn't include: hospitals, rotation sites and underserved-area designations.

What this project adds, as far as I could tell from those layers:
- **Statewide block-group coverage**, urban as well as rural, measured from
  population-weighted centers, with the same 20-mile Oregon/Idaho border
  buffer applied to every block group.
- **An income condition built into the desert definition** (low income
  AND low access). The WSU desert layer is distance-only. Income-related
  need appears there only through the separate MUA/MUP overlay, which isn't
  combined with distance.
- **Ownership classification** with an explicit "unknown" category. The
  WSU layer names the nearest pharmacy but doesn't classify it.
- **National shortage context** and a vulnerability index.
- **Two timeline sliders** backed by a twice-daily registry re-sweep. The
  WSU map is a static snapshot.

---

## Future work

- **Email alerts for newly posted national shortages.** The daily shortage
  snapshots already record each shortage's first appearance, so this needs
  only a subscriber list, a sender and unsubscribe handling. Any message
  would say a national shortage was reported, not that a local pharmacy is
  out.
- **CMS State Drug Utilization Data** as a possible *correlational* signal
  of dispensing changes. It would never be presented as confirmed local
  unavailability.
- **WA Department of Health facility-license validation**, to confirm which
  registered pharmacies are licensed and open. The facility lookup is behind
  a CAPTCHA; a public-records request is the realistic route.
- **NPPES bulk deactivation data**, to date closures that the API can't show.
- **Road-network distance or drive time** instead of straight-line distance.
- **Adding the 11 newly registered pharmacies** waiting in the review list,
  and resolving the 474-record review bucket (which would also narrow the
  176-237 desert range).

Pharmacy-level shortage data is not public anywhere: pharmacy inventory is
proprietary, and no state or federal agency publishes it. This project
deliberately does not scrape, infer or proxy local availability.

---

## Limitations

The full write-ups, with numbers and what would close each gap, are in
[LIMITATIONS.md](LIMITATIONS.md). In short:

- **Doesn't know what's in stock.** Shortages are national; nothing here is
  local availability.
- **Registered isn't confirmed open.** Pharmacies come from NPPES and haven't
  been validated against WA Department of Health licensing.
- **Distances are straight-line**, not travel access.
- **Income uses a proxy for HUD's area median income**, computed from ACS
  tract data, at the tract level.
- **The desert count is a range (176-237)** until the review bucket is
  resolved.
- **Ownership is undercounted for independents** (392 unknown; 15 confirmed).
- **Physical-location counts are conservative**; 299 locations are flagged
  for dedup review.
- **Border coverage is a 20-mile Oregon/Idaho strip.** Canada isn't covered.
- **Timelines:**
  - pharmacy growth only before observed snapshots, and the pre-2008
    registration artifact;
  - shortage history reconstructed before 2026-07-18;
  - "last observed" is not "resolved."
- **The shortage factor can't vary by place**, so it shifts the whole
  vulnerability map uniformly.
- **The daily data depends on free tiers** that can stop if the repo or
  database goes idle.

---

## Running locally

Requirements: Python 3.9+ (the site runs 3.12) and PostgreSQL with PostGIS.

1. **Create the database.** The schema is `day5_prep/schema.sql`, then
   `day6_prep/schema_day6.sql` and `day9/schema_day9.sql`. The scripts in
   the `day*` folders rebuild the data from the public sources, and
   DECISIONS.md walks through each step.
2. **Point the app at it** with environment variables. Only the names are
   listed here; never commit values. The app checks, in order:
   - `DATABASE_URL`, a full Postgres URL (used on Render);
   - otherwise the standard libpq variables `PGHOST`, `PGPORT`, `PGUSER`,
     `PGPASSWORD`, `PGDATABASE` and `PGSSLMODE`, so a password with special
     characters needs no URL encoding;
   - otherwise a local database named `pharmacy_tracker`.

   `DB_POOL_SIZE` is optional (default 4).
3. **Run the web app:**

   ```bash
   pip install -r webapp/requirements.txt
   uvicorn main:app --app-dir webapp --port 8000
   ```

4. **Run the daily job.** `--dry-run` does the full pull, then rolls back:

   ```bash
   pip install -r jobs/requirements.txt
   python jobs/daily_snapshot.py --dry-run
   ```

In GitHub Actions the database password comes from the repository secret
`SUPABASE_DB_PASSWORD`, which the workflow passes in as `PGPASSWORD`.

### Repository layout

| Path | What's there |
|---|---|
| `webapp/` | FastAPI app (`main.py`) and the static landing page and map pages |
| `jobs/` | Daily snapshot jobs: shortage sync, NPPES re-sweep and the shared DB connection |
| `.github/workflows/daily-snapshot.yml` | The twice-daily schedule |
| `day2/` - `day9/` | The pipeline as built, step by step (pulls, classification, dedup, geocoding, schema, desert classification) |
| `DECISIONS.md` / `LIMITATIONS.md` | Every judgment call, and every known gap |
| `policy_brief.md` / `policy_brief.docx` | One-page summary of findings |

---

## Disclaimer

Informational only, not medical advice. Check with your pharmacy about
medication availability. This project is not affiliated with or endorsed by
the FDA, CMS, or the State of Washington.

## Attribution

- Pharmacy data: CMS NPPES NPI Registry.
- Demographic and geographic data: U.S. Census Bureau (ACS, TIGER/Line,
  Centers of Population, Urban Areas, ZCTA Gazetteer, Geocoder).
- Drug shortage data: openFDA (U.S. Food and Drug Administration). Use of
  openFDA data does not imply FDA endorsement.
- Map tiles © [OpenStreetMap](https://www.openstreetmap.org/copyright)
  contributors. Mapping library: [Leaflet](https://leafletjs.com/).
