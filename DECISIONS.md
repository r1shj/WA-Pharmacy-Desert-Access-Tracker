# Decisions log

Methodological judgment calls made on this project, in the order they were
made. Each entry should stand alone — a future reader shouldn't need to
re-derive the reasoning from the raw data or old conversations. New
judgment calls get a new entry appended here as they happen, not just
logged retroactively.

---

## Current state (as of 2026-10-18)

*A snapshot for orientation, kept up to date; the dated entries below are
the permanent record.*

**Live:** https://wa-pharmacy-desert-access-tracker.onrender.com - a
landing page plus `/map/pharmacy` and `/map/shortages`.

**What's deployed:**
- **Web app (`webapp/`)** on Render's free tier. It auto-deploys from
  `main` when files under `webapp/` change, because Render's root
  directory is `webapp/`. The latest such change, the Day 10 copy and
  layout pass, went live on 2026-10-16. Commits that only touch docs, `jobs/` or
  the workflow don't redeploy. The instance sleeps after 15 idle
  minutes, so the first visit after that takes about a minute.
- **Database:** Supabase Postgres + PostGIS, reached through its
  session pooler (15-client limit; the app uses a 4-connection pool).
  Every table has row-level security and no grants for the API roles.
  Supabase, not the local `pharmacy_tracker` database, is the source of
  truth.
- **Caching:** the slider data is served from capped in-memory caches,
  so new snapshot data appears on the site within 5 minutes (entry:
  "Slider cache caps...").

**Daily data (GitHub Actions, `.github/workflows/daily-snapshot.yml`):**
both jobs - the openFDA shortage sync and the full NPPES pharmacy
re-sweep - run at **14:17 and 20:43 UTC**. Both times are always the same
Pacific date, and the second run overwrites that day's snapshot rather
than adding to it. Every run is logged in `snapshot_runs`. **Analyses
should use the latest successful (`ok`) run per `(run_date, job)`.**
Shortage change counts can be summed across a day's runs, but the
pharmacy totals are state counts and must not be. The old local launchd
job is disabled.

**Done - Days 1-9:**
1. Data exploration (NPPES, Census ACS).
2. The complete WA pharmacy population (ZIP sweep past the 1,200 cap,
   WA `LOCATION` filter, type classification).
3. Ownership classification and address dedup.
4. Geocoding and the ACS suppression audit.
5. PostgreSQL + PostGIS schema and load.
6. Pharmacy desert classification, including OR/ID border pharmacies.
7. The Pharmacy Access Map.
8. The Shortage Context Map and the vulnerability index.
9. Deployment: GitHub, the Supabase migration with observed shortage
   history, the landing page, the twice-daily Actions job with a real
   NPPES re-sweep, Render. Plus the post-deploy fixes: vulnerability
   colors on the continuous score, the slider 500s (connection pool,
   caching, load-safe slider), no-cache pages, and a full-history
   secret scan with no findings.

**Day 10 - documentation (done 2026-10-16):** README.md, a one-page
policy brief (`policy_brief.md` / `.docx`), and a consistency pass on the
site copy.

**Day 11 - final audit (2026-10-16):** the audit was run and its fixes
are applied: no individuals' names in the app or in tracked files, the
176-237 range on every page, national-context wording. What's left is
the owner decisions below.

**Known open items:**
- **Owner check pending: map gestures on a real phone.** They were tested
  only with Chrome's touch emulation: one finger scrolls the page, two
  fingers move the map, the slider drags by finger. iOS Safari and
  Android Chrome are unverified (entry 2026-10-18).
- **Owner decision pending:** whether to rewrite git history to purge
  individuals' names, which are still in the initial commit. See the
  Day 11 fixes entry for what it involves. The current tree has none.
- **The desert count is a range, 176-237 block groups,** until the 474
  REVIEW-bucket pharmacies are resolved (LIMITATIONS.md).
- **11 newly registered pharmacies** are in `npi_review_queue` and not on
  the map until they're classified, deduplicated and geocoded.
- **No validation against WA DOH licensing records** - closures and
  licensing status are unconfirmed (LIMITATIONS.md).
- **Rotate the Census API key.** It was pasted in chat and passed on a
  command line on Day 1. It's not in any file or commit, but it is in
  the local session transcript.
- **`jobs/db.py` is outside Render's root directory but imported by the
  app.** A change to it alone won't redeploy the site - trigger a manual
  deploy in Render.
- **Free-tier timers:** GitHub disables the schedule after 60 days with
  no pushes, and Supabase pauses after 7 days of inactivity
  (LIMITATIONS.md).

---

## 2026-07-18 — Study population inclusion rule (pharmacy_type)

**Decision:** Of the taxonomy-coded WA pharmacy records, `community_retail`,
`clinic`, and `compounding` are `included_in_access_analysis=True`.
`long_term_care`, `mail_order`, `specialty`, `home_infusion`, `military`,
`managed_care_org`, and `non_pharmacy` are excluded. `unspecified` (generic
"Pharmacy" taxonomy code), `institutional`, and
`unclassified_has_pharmacy_taxonomy` are flagged REVIEW rather than
decided either way. Nothing is deleted — every record keeps its
`pharmacy_type`/`walk_in_access`/`exclusion_reason` regardless of the
inclusion call.

**Why:** The access/desert analysis is about physical, walk-in medication
access points for the general population. Long-term-care and mail-order
pharmacies are closed-door or delivery-only by design. Military pharmacies
serve a restricted beneficiary population. Specialty/home-infusion
pharmacies are typically appointment- or delivery-based, though some do
have storefronts — excluded by default rather than assumed, with the
uncertainty noted in `exclusion_reason`. Generic/institutional codes carry
no sub-type information on their own and genuinely need a human or a
secondary signal (address type, DBA name) to resolve, so they're routed to
REVIEW instead of guessed.

**Evidence:** Full taxonomy distribution of the corrected 1,941-record WA
pull (see `day2/wa_pharmacies_final.csv` and
`day2/DAY2_ADDENDUM_complete_population.md`). Result: 1,363 included, 104
excluded, 474 review.

---

## 2026-07-18 — "Unmatched ≠ independent" rule for ownership classification

**Decision:** When Day 3's ownership/chain classification can't match a
pharmacy's `organization_name`/DBA to a known chain, its ownership status
must be recorded as `unknown` — never defaulted to `independent`.
"Independent" is a positive claim that requires actual evidence (e.g., a
DBA with no match against a maintained chain-name list *and* an
authorized official who doesn't recur across other NPIs in the dataset,
or some other corroborating signal) — not just the absence of a chain
match.

**Why:** Failing to match a chain-name list proves the list is incomplete
at least as often as it proves the pharmacy is independent. Silently
defaulting unmatched records to "independent" would systematically inflate
independent-pharmacy counts by exactly the size of whatever chains happen
to be missing from the match list, which is an easy and hard-to-detect way
to bias the whole downstream desert analysis. This decision is made now,
ahead of Day 3, so the classification logic is built around it from the
start rather than retrofitted after noticing the bias.

**Evidence:** Day 1 findings already established that `organization_name`
is frequently a generic corporate/holding-company name (e.g. Albertsons's
"1918 WINTER STREET OPERATING CO LLC" spanning Safeway, QFC, Haggen, and
Sav-On banners) rather than the consumer-facing brand — so a naive
"no obvious chain name → independent" heuristic was already known to be
unreliable before any matching logic was written.

---

## 2026-07-18 — Classification precedence fix (primary-code rules vs. secondary pharmacy taxonomy)

**Decision:** `classify()` in `day2/classify_pharmacy_type.py` now checks
"does this record have a pharmacy taxonomy anywhere (primary or
secondary)?" *before* applying the primary-code-only rule tables
(`RULES`, `NON_PHARMACY_FALSE_POSITIVES`). If a pharmacy taxonomy exists
only as a secondary code, the record is routed to
`unclassified_has_pharmacy_taxonomy` (REVIEW) regardless of what its
primary code's own rule would have said. Primary-code rules only get the
final word when no pharmacy taxonomy is present anywhere on the record.

**Why:** The verification pass run before Day 3 found that a record whose
*primary* taxonomy matched a definitive rule (e.g. a DME supplier, or a
military pharmacy) was being classified off that primary code alone and
never reached the "has a pharmacy taxonomy somewhere" fallback — even when
a secondary taxonomy entry was genuinely pharmacy-related. This is the
same failure mode as the Day 2 "AMS HOMECARE USA INC" example (DME
primary, Pharmacy secondary), just not yet fixed in code at that point.

**Evidence:** Rerunning classification on the full 1,941-row corrected
dataset after the fix: all 42 true secondary-taxonomy records now land in
REVIEW (up from 18 before the fix). Included count unchanged at 1,363
(these 24 records were already excluded either way); excluded dropped
128→104, review rose 450→474. Bartell Drugs (65 records) and the
no-duplicate-NPI check were confirmed unaffected. Full detail in
`day2/CLASSIFICATION_FIX.md`.

---

## 2026-07-18 — WA-state filtering must check LOCATION.state explicitly

**Decision:** Every NPPES pull must filter on the `LOCATION` address
object's `state` field client-side. The API's own `state=` and
`postal_code=` query parameters are not trustworthy for "physically
located here" — they match against *any* address on the record, including
`MAILING`.

**Why:** Discovered while building the county rollup: an out-of-state
pharmacy chain with a Washington billing/mailing address matches a
`state=WA` query even with zero WA storefronts. This wasn't a rare edge
case — it retroactively invalidated over half of the original Day 2 pull.

**Evidence:** Of the original 1,200-capped `state=WA` sample, 640 records
(53%) had a non-WA `LOCATION` address (concrete examples: a Florida-based
Genoa Healthcare pharmacy, an Astoria OR pharmacy with a Vancouver WA
mailing address, a Monterey CA military pharmacy). Of the full 3,364-record
zip sweep, 1,423 (42%) were non-WA-located. Filtering to
`LOCATION.state == 'WA'` cut the zip-sweep set to 1,941 confirmed
WA-located records — validated against Bartell Drugs' known real-world
footprint (65 WA stores found, matching public knowledge of the chain,
vs. only 5 visible in the old contaminated sample). Full detail in
`day2/DAY2_ADDENDUM_complete_population.md`.

---

## 2026-07-18 — NPPES 1,200-result API ceiling and the ZIP-partition workaround

**Decision:** A single NPPES API query (any combination of filters) caps
out at 1,200 total results (`limit` max 200 × `skip` max 1000, in pages of
200). To get the true WA population, the pull is partitioned across every
possible WA ZIP code (98001–99403, the full USPS-assigned range for the
state — 1,403 candidate codes) using the `postal_code` parameter, since it
requires an exact 5-digit match (no prefix support — confirmed by testing
`postal_code=980` before committing to this approach), and results are
deduped by NPI across partitions.

**Why:** ZIP code partitioning was chosen over city- or county-name
partitioning because it's a finite, enumerable, USPS-defined key — not
dependent on any external city/place-name list being complete. A gap in a
city list would silently under-count; a gap in the ZIP range is a
visible, checkable assumption (and was in fact double-checked: no
individual ZIP in the sweep hit its own 1,200 sub-cap, so no further
sub-partitioning was needed).

**Evidence:** The full 1,403-ZIP sweep was run twice, independently, from
a cold cache. Both runs returned exactly the same 3,364 unique NPIs (zero
difference either direction), confirming the pull is complete and stable
rather than an artifact of API flakiness or an incomplete ZIP range. See
`day2/pull_wa_pharmacies_by_zip.py` and
`day2/DAY2_ADDENDUM_complete_population.md`.

---

## 2026-07-18 — Deferred WA DOH facility-license validation rather than automate past a CAPTCHA

**Decision:** Do not attempt to bypass the reCAPTCHA on WA DOH's HELMS
facility-license lookup to complete the planned 30-50-pharmacy spot-check.
Document the gap instead of working around it.

**Why:** Bypassing CAPTCHAs is a hard line, not a judgment call to weigh
case-by-case. The only downloadable DOH dataset (`qxh8-f4bd` on
data.wa.gov) covers individual practitioner credentials only — confirmed
by enumerating all 310 distinct `credentialtype` values in it, none of
which is a facility/business pharmacy license — so there was no bulk data
path around the CAPTCHA either.

**Evidence:** See `LIMITATIONS.md` for the full writeup, including the
one available imperfect proxy (NPPES `last_updated` staleness: 82 of
1,200 sampled records untouched since before 2015).

---

## 2026-07-25 — Ownership classification: officer-repetition threshold and match precedence

**Decision:** A shared `authorized_official` name is only treated as a
chain signal when it recurs across **3 or more** distinct NPIs (not 2),
and only after DBA/org-name matching against the chain/health-system/
government lookup tables has already failed to classify the record. When
it fires, the result is `ownership_category=chain`,
`ownership_confidence=medium` (vs. `high` for a direct name match), with
`parent_organization` naming the shared officer rather than inventing a
brand name we don't actually know.

**Why:** Two locations sharing an official name is too easily a
common-name coincidence to trust alone (e.g. a common surname). Three or
more sharing the exact same first+last name is a much stronger signal,
consistent with the Day 1 example (one official across 15+
Albertsons-family locations). Running this check only after name-based
matching keeps it from ever overriding a confident, evidence-backed
classification - it only fills gaps.

**Evidence:** Applied to the 1,837 included/review records: 1,004
classified by direct name match (high confidence), 124 more by officer
repetition (medium confidence) across 28 distinct unidentified groups
(sizes 3-23 locations). Full detail in `day3/DAY3_REPORT.md`.

---

## 2026-07-25 — Officer-repetition fallback must not default to "chain" over known health systems/government orgs

**Decision:** Before trusting the officer-repetition fallback, the
DBA/org-name lookup tables must have reasonable coverage of large
non-retail multi-location entities (hospitals, health systems, community
health centers, government/tribal orgs) - otherwise the fallback
mislabels them as generic "chain," which is simply wrong (a hospital
system is not a retail chain, even though both are "multi-location single
ownership").

**Why:** Caught concretely: Seattle Children's Hospital and University of
Washington Medical Center records were falling through to the officer-
repetition fallback and getting labeled "Unidentified chain" purely
because `HEALTH_SYSTEM_PATTERNS` didn't yet include their names.

**Evidence:** Added explicit patterns for Seattle Children's, UW
Medicine, a broad `COMMUNITY HEALTH` catch-all (covers several
differently-named WA community health centers/FQHCs at once), and
`PUBLIC HOSPITAL DIST(RICT)` (WA's special-purpose hospital districts are
legally government entities). Rerunning moved 65 records from `chain` to
`health_system`/`government_or_tribal` and shrank the officer-repetition
fallback group from 38 to 28. This is very likely still incomplete for
the long tail of WA's ~25+ independently-named regional community health
centers - remaining unmatched ones are left `unknown` rather than
guessed, consistent with the "unmatched != independent/anything" rule
above. See `day3/DAY3_REPORT.md`.

---

## 2026-07-25 — Address dedup: containment-only name matching, not fuzzy ratio

**Decision:** Two records at the same normalized address are only
considered "substantially similar" in name/DBA if one name is an exact
match or a full substring of the other (after stripping legal suffixes,
store numbers, and punctuation) - not a fuzzy similarity score like
difflib's ratio.

**Why:** Calibrated both approaches against this dataset's own real
multi-NPI address groups before choosing. Fuzzy ratio scored deceptively
high (0.71-0.89) on genuinely different pharmacies that happen to share a
templated name and a campus address - e.g. "Kaiser Permanente Bellevue
Infusion Pharmacy" vs. "Kaiser Permanente Factoria Pharmacy." Plain
containment correctly rejected every risky pair tested while still
catching every real same-store case (Bartell Drugs re-registrations, the
Day 1 14th Avenue Pharmacy trio, Haggen locations re-registered under
three different corporate names over the years, "QFC" matching "QFC
Pharmacy #0860").

**Evidence:** See the calibration table and full pairwise test results in
`day3/DAY3_REPORT.md` and `day3/dedup_addresses.py`'s module docstring.

---

## 2026-07-25 — Address dedup: organization_name is not trustworthy evidence for health systems/government orgs

**Decision:** When comparing two records at the same address for the
dedup collapse rule, `organization_name` equality is only used as
evidence of "same physical location" when neither record's
`ownership_category` is `health_system` or `government_or_tribal`. For
those two categories, only a DBA match counts.

**Why:** Caught concretely while calibrating the dedup logic: "KAISER
FOUNDATION HEALTH PLAN OF WASHINGTON" is the identical legal
`organization_name` for a Bellevue infusion pharmacy and an unrelated
Factoria pharmacy - comparing org_name alone would have merged two
genuinely different locations. This is the same underlying pattern Day 1
already flagged for `organization_name` generally (it's the legal
registrant, not the consumer-facing identity), just showing up again in a
new context. Health systems and government/tribal orgs routinely run
several distinct pharmacy departments (inpatient, outpatient, infusion,
LTC) from one nominal campus address; retail chains don't have this
failure mode, so the restriction is scoped to just those two categories
rather than applied everywhere.

**Evidence:** Verified the fix resolves the Kaiser Bellevue/Factoria case
(now 3 separate locations, was 1 merged) without breaking the legitimate
Bartell Drugs, QFC, or Haggen collapses, which all link via DBA
regardless. See `day3/DAY3_REPORT.md`.

---

## 2026-07-25 — Shortage timeline backfill: two tiers, not one, because "resolved" covers almost nothing

**Decision:** Reconstructed historical shortage-slider depth from openFDA's
current-state drug shortages data using two separate tiers instead of the
single "resolved records only" approach originally planned:
- **Tier 1 (resolved, bounded interval)**: only records with
  `status=="Resolved"`, dated `initial_posting_date` -> `update_date`.
- **Tier 2 (ongoing, open-ended)**: records still `"Current"` or
  `"To Be Discontinued"`, dated `initial_posting_date` -> today (pull
  date), explicitly not a closed interval yet.

**Why:** Checked before assuming the "resolved records" approach would
work. It doesn't, in practice: openFDA's shortages endpoint has no
`start_date`/`resolution_date` fields at all (the real fields are
`initial_posting_date` and `update_date`; `update_date` is only a
meaningful end-date proxy when `status=="Resolved"`), and only 25 of
1,614 rows carry that status - which collapse to just **3 distinct
shortages** once package/NDC-level duplication is removed. A resolved-only
backfill would have given the slider a real range of only
2023-03-17 to 2026-02-24, on 3 drugs. Tier 2 isn't what was originally
asked for (it has no confirmed end date), but it's the only way to get
real depth out of this data, and 231 of 234 distinct tracked shortages are
still open, with `initial_posting_date` values as far back as 2012.

**Evidence:** Confirmed empirically, not just from docs: pulled the full
live dataset (1,614 records) and the official bulk-download manifest
(`api.fda.gov/download.json`) - the download file has exactly 1,614
records, identical to the live API, confirming there is no separate
historical archive to fall back on. Combined tier 1 + tier 2 gives the
slider a real range of **2012-01-01 to 2026-07-18**; tier 1 alone would
have given only a ~3-year window on 3 drugs. Both tiers assume a shortage
was continuously active between its bounding dates (no visibility into
possible lapses/reopenings in between). Full numbers in
`day8_prep/build_shortage_backfill.py` output and its module docstring.

---

## 2026-07-25 — Pharmacy growth backfill uses physical_location_id, not raw NPI, and treats pre-2008 dates as unreliable

**Decision:** The pharmacy-existence backfill is keyed on Day 3's
`physical_location_id` (using the *earliest* `enumeration_date` among all
NPIs registered at that location), not on each NPI's own
`enumeration_date` directly. Separately: `enumeration_date` values before
~2008 are flagged as an unreliable growth signal, not just an early data
point.

**Why:** Two independent problems would have corrupted a naive per-NPI
version of this backfill. First, Day 3 already established that the same
physical store can carry multiple NPIs over time (ownership/banner
changes - e.g. a Haggen store re-registered under three different
corporate names). Using each NPI's own `enumeration_date` would make a
long-standing store look like a "new" pharmacy every time it changed
ownership. Second, checking the actual month-level distribution of 2006
`enumeration_date` values (958 of 1,941 records - basically half the
entire WA dataset) showed 80% of that year's registrations landing in a
sharp four-month window, May-August 2006. That's not organic pharmacy
growth; it lines up with NPPES/NPI system rollout and the HIPAA NPI
compliance deadline, meaning a large share of pharmacies that already
existed all registered for their first NPI in the same short window. The
pre-2008 portion of the backfill should be read as "this many pharmacies
already existed by the time NPI registration became mandatory," not as a
growth curve.

**Evidence:** 1,941 of 1,941 WA pharmacy NPIs have a usable
`enumeration_date` (100%, since it's a mandatory NPPES field) - so
completeness isn't the limiting factor, interpretability is. Collapsing
to the 1,811 `physical_location_id`s and taking the earliest date per
location changes the result for 124 locations that have 2+ NPIs. Full
date range: 2005-05-24 to 2026-06-30 at the location level. As documented
in `LIMITATIONS.md`, this can only ever show growth (new
`physical_location_id`s appearing) - NPPES's public API does not expose
deactivation dates, so it can never show a location disappearing. See
`day8_prep/pharmacy_enumeration_backfill.csv`.

---

## 2026-07-25 — Forward snapshot jobs scheduled via launchd, not cron

**Decision:** Started the two forward snapshot scripts on a real daily
schedule now, ahead of Day 8's formal scheduling step, using a macOS
LaunchAgent (`~/Library/LaunchAgents/com.pharmacytracker.dailysnapshot.plist`,
6:00 AM daily) rather than a crontab entry.

**Why:** This machine is macOS, where legacy cron's background execution
is commonly blocked or restricted by the OS permission model unless the
`cron` daemon is separately granted Full Disk Access - a manual System
Settings step outside anything a terminal command can do, and easy to
silently fail without the user noticing. launchd is Apple's native
scheduler and doesn't have that same silent-failure mode for jobs that
only touch files in the user's own home directory.

**Caveat this creates**: the LaunchAgent is registered with
`LimitLoadToSessionType=Aqua`, meaning it only fires while the user is
logged into a GUI session. If the machine is asleep, powered off, or at
the login screen at 6:00 AM, that day's snapshot won't run until the next
time the user logs back in (launchd generally catches up on a missed
`StartCalendarInterval` job rather than skipping it outright, but this
isn't a hard guarantee). A gap in the forward-observed snapshot history is
most likely explained by this, not a script failure - check
`day8_prep/snapshot_log.txt` first.

**Evidence:** Verified the actual scheduled-invocation path end-to-end,
not just the underlying scripts in isolation - ran `launchctl start`
manually to fire the job through launchd (not a direct `python3` call),
confirmed `LastExitStatus=0` and today's snapshot files were written by
both scripts via `day8_prep/snapshot_log.txt`. Cannot verify the actual
6:00 AM unattended fire within this session; that's confirmed by checking
tomorrow's `day8_prep/snapshots/*/` directories for a new dated file.

---

## 2026-07-25 — Geocoder benchmark/vintage, and treating "Tie" as its own category, not a Match subtype

**Decision:** Geocoded the 1,811 Day 3 physical locations via the Census
Batch Geocoder's `geographies/addressbatch` endpoint using
`benchmark=Public_AR_Current`, `vintage=Census2020_Current` - current
address ranges, but Census-2020-vintage tract boundaries, matching the
tract geography our ACS 2022 5-year pull already uses. Verified this
parameter pair against a live 3-row test call before committing the full
batch, rather than assuming remembered values were still correct.
Separately: `match_indicator` has three possible values -
`Match`/`No_Match`/`Tie` - not two. `Tie` (multiple equally-plausible
candidates, geocoder can't pick one) is its own category with zero
coordinate data, not a subtype of `Match` alongside `Exact`/`Non_Exact`.
Caught this by inspecting the real response distribution before writing
the parser, rather than assuming a two-way Match/No_Match split.

**Why:** Getting the benchmark/vintage pair wrong would have silently
misaligned every location's tract assignment against the ACS tract
boundaries used elsewhere in this project. Getting the Tie/Match
conflation wrong would have either inflated the "matched" count (if Tie
were miscounted as Non_Exact) or dropped 15 addresses from the unmatched
export entirely (if Tie weren't recognized as needing manual review at
all, since a naive parser checking only for `"No_Match"` would silently
pass Tie rows through as if they had usable data).

**Evidence:** 1,511 Exact + 211 Non_Exact + 15 Tie + 74 No_Match = 1,811
(reconciles exactly). Overall usable-coordinate match rate: 95.1%. Both
Tie and No_Match rows are exported together to `geocode_unmatched.csv`
with a `reason` column distinguishing which failure mode each hit -
neither is silently dropped. See `day4/parse_geocode_results.py`.

---

## 2026-07-25 — Two separate manual_review_required flags, not merged

**Decision:** The Day 5-facing `day4/physical_locations.csv` table
carries `dedup_manual_review_required` (from Day 3's address/name
collapse logic) and `geocode_manual_review_required` (from Day 4's
geocode match confidence) as two distinct columns, never combined into
one boolean.

**Why:** They flag different, independent problems - one is an
ownership/identity ambiguity (are these NPIs really the same store?),
the other is a geocoding confidence issue (do we trust this location's
coordinates?). A location can be flagged by either, both, or neither, and
collapsing them into one field would destroy that distinction for anyone
querying "why does this location need review."

**Evidence:** 35 of 1,811 locations are flagged by both; 564 by at least
one. Confirmed before rolling up that Day 3's `manual_review_required` is
already identical across every NPI sharing a `physical_location_id` (0
locations found with inconsistent values), so the location-level rollup
loses no information. See `day4/build_physical_locations.py`.

---

## 2026-07-25 — ACS suppression: checked all known sentinel codes, only one appeared

**Decision:** The suppression audit scans WA's 1,784 ACS tracts against
the full set of known ACS sentinel codes (-666666666, -222222222,
-333333333, -444444444, -555555555, -888888888, -999999999), not just
the one we expected to find, even though only -666666666 actually
appears in this pull.

**Why:** The other sentinel codes are typically used on margin-of-error
fields rather than the estimate fields we pulled (median household income
and total population), so their absence here is expected, not a gap in
the check. Checking the full set anyway costs nothing and means a future
re-pull that happens to include MOE fields, or a Census methodology
change, won't silently slip past this audit.

**Evidence:** 20 of 1,784 tracts (1.1%) have `income_suppressed=True`,
all via -666666666. 0 tracts have missing population (population is a
full count, not sample-based, so it's essentially never suppressed the
same way). Spot-checked the 20 suppressed tracts: the large majority show
population=0, consistent with non-residential tracts (water, industrial,
special-purpose tract numbers) rather than a data quality problem.
Suppressed tracts are never coerced to 0 and are never dropped from the
table - they stay present with `income_suppressed=True` and
`excluded_from_income_classification=True`, so population-based analysis
on those tracts is unaffected. See `day4/acs_suppression_audit.py`.

---

## 2026-07-25 — Day 5 schema: mapped column-name mismatches, fetched a genuinely new dataset for tract geometry

**Decision:** Loaded Day 5's PostgreSQL/PostGIS database from the actual
files on disk, resolving several column-name mismatches against the
schema as originally described, and fetching one dataset that didn't
exist anywhere in the project yet:
- `physical_locations.normalized_address` <- `matched_address` (geocoder-
  standardized) when matched, else the raw `address_1`. No column named
  `normalized_address` exists in `day4/physical_locations.csv`.
- `geocode_status`/`geocode_quality` <- `match_indicator`/`match_type`.
  No columns with those exact names exist either.
- `physical_locations` and `pharmacy_snapshots`/`shortages`' `id` <- used
  `physical_location_id` (e.g. `LOC-00001`) directly as the primary key
  for `physical_locations` rather than adding a redundant surrogate,
  since it's already the natural key referenced everywhere else in the
  project; added real `BIGSERIAL id` columns for `pharmacies`,
  `pharmacy_snapshots`, and `shortages` since those were explicitly
  listed as separate from any natural key.
- `pharmacies.dba_name` <- `other_names`.
- `pharmacies.enumeration_date`/`last_updated` <- **not present in
  `wa_pharmacies_deduped.csv` at all** - joined in from
  `day8_prep/pharmacy_enumeration_dates.csv` by `npi` instead.
- `pharmacies.source_name`/`retrieved_at` <- not a column anywhere;
  populated as known constants (`'NPPES'`, `2026-07-18`) rather than
  pretending they were derived from a file.
- `census_tracts.median_income` <- `median_household_income`.
- `census_tracts.geometry` <- **did not exist anywhere in the project.**
  Fetched the real 2020 TIGER/Line WA tract shapefile
  (`tl_2020_53_tract.zip`, 1,784 features, matching our ACS tract count
  exactly) and loaded it via `ogr2ogr`, reprojecting NAD83 (its native
  SRID, EPSG:4269) to EPSG:4326 to match the geocoder's output SRID.

**Why:** The task explicitly asked to flag mismatches rather than force
them, so each of the above got resolved with a clearly-reasoned mapping
rather than silently renamed or invented. The tract geometry gap was
different in kind from the naming mismatches - it wasn't a rename, it was
data that plain didn't exist yet - so it's called out as a real scope
addition, not folded in silently.

**Evidence:** All 5 tables loaded with row counts matching their source
files exactly (physical_locations 1,811; pharmacies 1,941; census_tracts
1,784; pharmacy_snapshots 1,811; shortages 234). Zero FK integrity
violations. Zero rows failed the `enumeration_date` join. As a strong
independent check on the whole pipeline (geocoding + shapefile load +
reprojection all being mutually consistent): ran a live PostGIS
`ST_Within` spatial join between `physical_locations.geom` and the newly-
loaded `census_tracts.geometry`, and compared the result against each
location's `tract_geoid` already supplied by the geocoder. **100%
agreement across all 1,722 geocoded locations, zero disagreements, zero
boundary-edge failures.** See `day5_prep/schema.sql` and
`day5_prep/load_data.py`.

---

## 2026-07-25 — Fixed: chain-pattern list order was mislabeling the banner sub-label; the first fix attempt introduced its own regression, caught before shipping

**Decision:** Fixed `classify_by_name()` in `day3/classify_ownership.py`
to try three tiers in order: (1) DBA text alone against every SPECIFIC
pattern, (2) combined dba+org text against every SPECIFIC pattern, (3)
DBA-then-combined text against a small GENERIC fallback tier
(`HEALTH_SYSTEM_GENERIC_FALLBACK_PATTERNS`, currently just the broad
"COMMUNITY HEALTH" catch-all, moved out of `HEALTH_SYSTEM_PATTERNS` into
its own list). User chose "fix now" over "defer as known limitation" when
asked.

**Why this happened (original bug):** the original single-pass matcher
checked `CHAIN_PATTERNS` in list order against combined dba+org text.
`SAFEWAY`/`ALBERTSON'S` are earlier in the list than `HAGGEN`/`SAV-ON`. A
record like `organization_name='SAFEWAY INC'` + `dba_name='HAGGEN
PHARMACY #3498'` (Albertsons registers some Haggen storefronts under a
Safeway Inc legal entity - a pattern already known from Day 3's dedup
work) matched SAFEWAY first and never reached HAGGEN.

**First fix attempt regressed something else - caught by rerunning the
full regression check, not assumed clean:** making DBA always win
outright (no tiers) fixed the 34 chain records correctly, but
demoted 2 Yakima Valley Farm Workers Clinic records from their correct,
specific classification to the generic "Community Health Center
(specific org not auto-identified)" bucket. Their DBA
("Unify Community Health...") only carries the generic signal; the
specific identifying text ("Farm Workers") lives in `organization_name`.
Neither field is universally more trustworthy than the other - it's
record-dependent - so a blanket DBA-first rule was the wrong level of
fix. The three-tier version (generic patterns only as an absolute last
resort, after BOTH fields have been tried against every specific pattern)
resolves both cases correctly without a blanket field-priority rule.

**Bonus finding from the same fix, present in the ORIGINAL code too, not
introduced by any fix attempt:** demoting the generic pattern to tier 3
also corrected 3 more records that were never part of the original bug
report - 2 "Community Health Care" Puyallup pharmacies and 1 "New Health
Programs Association" Colville pharmacy were being caught by the generic
"COMMUNITY HEALTH" pattern (checked as part of `HEALTH_SYSTEM_PATTERNS`,
which is checked before `GOVERNMENT_TRIBAL_PATTERNS`) before ever reaching
the specific `PUYALLUP`/`COLVILLE` patterns in `GOVERNMENT_TRIBAL_PATTERNS`.
All 3 now correctly show `government_or_tribal` / the specific tribe.

**Evidence:** Full regression check comparing every one of 1,941 rows
before vs. after, not just the originally-reported cases: 0 changes to
`physical_location_id`, `manual_review_required`, or any other unrelated
field (confirms the dedup pipeline is fully insulated from ownership
classification changes). Exactly 37 `parent_organization` text changes
(34 chain banner fixes + 3 tribal category fixes), and separately
confirmed the 2 Yakima Valley records are byte-for-byte identical
before/after (the near-regression was caught and fixed within this same
pass, never shipped). Post-reload spot-check via the live database: 46/46
Haggen records and 26/26 Sav-On records now correctly banded, 0 remaining
cross-banner mismatches, QFC/Safeway unaffected (0 mismatches, as
before). `pharmacies` table reloaded (`day5_prep/reload_pharmacies.py`),
other 4 tables untouched. See `day3/chain_lookup.py` and
`day3/classify_ownership.py`.

---

## 2026-07-26 — Pharmacy desert income threshold: HUD's 80% AMI standard, applied to a proxy AMI (not HUD's official figure)

**Decision:** A tract is classified `low_income` if its ACS median
household income is below 80% of its own county's Area Median Income
(AMI). The 80%-of-AMI cutoff is HUD's standard, well-established "Low
Income" definition, used across federal housing/community-development
programs (LIHTC, Section 8, CDBG) - see
https://www.huduser.gov/portal/datasets/il.html. The county AMI figure
itself is a **proxy**, not HUD's officially published number: the
population-weighted mean of `median_household_income` across that
county's non-suppressed ACS tracts (Day 4's audited pull).

**Why a proxy instead of HUD's real figures:** tried to fetch HUD's bulk
Income Limits dataset directly - every candidate URL either 404'd or
returned an empty/placeholder file (HTTP 202 with zero bytes), not real
data, and HUD's actual bulk-file naming/path couldn't be confirmed
cleanly within a reasonable time budget this session. Rather than keep
guessing at brittle URLs, used a proxy that's fully reproducible from
data already on hand and clearly labeled as such, rather than silently
presenting a self-computed number as if it were HUD's official figure.

**Why this matters:** HUD's real AMI uses family income (not household
income) and a different, non-ACS-tract-average methodology, so this
proxy will diverge from HUD's actual published county AMI by some
unknown margin. `income_status` should be read as directionally
informative, not a precise HUD program-eligibility determination. Also
logged in `LIMITATIONS.md`.

**Evidence:** Computed proxy AMI for all 39 WA counties. Tract-level
result: 512 low_income, 1,252 not_low_income, 20 suppressed (unchanged
from Day 4 - never defaulted either way). Block-group level (after
joining each block group to its parent tract): 1,523 low_income, 3,767
not_low_income, 21 suppressed. See
`day6_prep/desert_classification_config.json` and
`day6_prep/load_block_groups.py`.

---

## 2026-07-26 — Urban/rural classification: 2020 Census Urban Area delineation, not the older 2010 one

**Decision:** A block group is `is_urban=true` if its CenPop
population-weighted centroid falls within a 2020 Census Urban Area
polygon (`cb_2020_us_ua20_500k`, the cartographic boundary version of
that delineation); otherwise rural.

**Why the 2020 vintage specifically:** two Urban Area delineations exist
for roughly this era - the older 2010-based Urban Area/Urban Cluster
boundaries, and a newer 2020-based delineation finalized via Federal
Register notices in March and December 2022. Checked Census's own "Urban
and Rural" methodology page before choosing: it explicitly confirms the
2020 delineation is what the Census Bureau itself used to classify 2020
Census geography as urban vs. rural, so using anything else would be
inconsistent with the vintage of every other geography in this project
(2020 tracts, 2020 CenPop block groups).

**Why this determines the distance threshold:** urban block groups use a
1-mile pharmacy-access threshold, rural use 10 miles - the same 1mi
urban/10mi rural pattern as the widely-used USDA food-desert definition,
adapted here for pharmacies rather than groceries.

**Evidence:** 4,244 of 5,311 WA block groups (79.9%) classified urban,
1,067 (20.1%) rural - a plausible split given WA's population
concentration in the Puget Sound corridor. See
`day6_prep/desert_classification_config.json`.

---

## 2026-07-26 — Border handling: 20-mile OR/ID pharmacy buffer, verified to actually change outcomes (not just theoretically present)

**Decision:** Pulled and geocoded pharmacy-taxonomy NPPES records for
every OR/ID ZIP code whose centroid falls within 20 miles of the WA
state boundary (99 OR + 33 ID zips, found by buffering the union of all
WA census tract geometries and filtering the 2023 Census ZCTA
gazetteer). These border-buffer locations are used ONLY to compute
nearest-pharmacy distance for WA block groups near the state line -
never counted as WA population, WA pharmacy inventory, or in any
WA-facing report.

**Why:** without this, a WA block group a few miles from a real pharmacy
just across the Columbia River in Oregon (or the Idaho border near
Spokane) would have its nearest-pharmacy distance measured only against
other WA locations, artificially inflating the distance and risking a
false "desert" classification for a place that, in reality, has
reasonably close pharmacy access.

**Evidence, not just the theoretical case:** applied the same
`LOCATION.state` verification lesson from the original WA pull (Day 2 -
never trust the API's own `state`/`postal_code` params alone) to this
OR/ID pull: 566 raw NPIs, 524 confirmed true OR/ID `LOCATION` addresses,
42 false positives dropped. Geocoded via the same Census batch geocoder;
485 matched. **Directly verified the buffer changes real outcomes**, not
just adds theoretical coverage: computed nearest distance for every WA
block group twice (WA-only vs. WA+border) and compared. Several Klickitat/
Benton/Wahkiakum County block groups dropped from a WA-only distance that
would have exceeded the 10-mile rural threshold (16-19 miles) to a true
distance under it (2-8 miles) once the real Oregon pharmacy across the
river is counted - these would have been false desert flags. Just as
importantly, confirmed the buffer does **not** over-correct: several
Skamania County block groups remain correctly classified `desert` even
after the border buffer is applied, because their true nearest pharmacy
(WA or OR) is still genuinely beyond 10 miles. See
`day6_prep/pull_border_pharmacies.py` and
`day6_prep/desert_classification_config.json`.

---

## 2026-07-26 — Distance is straight-line geographic proximity, not travel distance (explicit scope decision)

**Decision:** `nearest_pharmacy_miles` is computed as PostGIS geography
`ST_Distance` (straight-line/great-circle) between a block group's CenPop
centroid and the nearest included pharmacy point - not road-network
travel distance or drive time.

**Why:** explicitly scoped this way per the task description; real
road-network distance is a documented future improvement, not attempted
now. Straight-line distance systematically understates real travel
distance, especially around water bodies (the Columbia River gorge
border counties above, Puget Sound islands, etc.) and mountainous
terrain (the Cascades) - both very relevant to WA specifically.

**Evidence / limitation:** logged in `LIMITATIONS.md` rather than left
implicit - every distance-based field and the `pharmacy_desert_status`
classification itself should be read as "geographic proximity," not
confirmed travel access.

---

## 2026-07-26 — Desert result plausibility check against an externally-cited figure (with a citation gap flagged, not papered over)

**Decision:** Computed total population in the 237 `desert`-classified
block groups (346,334) and compared it against a ~450,000 figure the user
described as coming from a "UW CHOICE Institute study... cited earlier in
this project." Searched this project's files and saved memory directly
for that citation before treating it as established fact - found no
record of it anywhere (every text match on "CHOICE" or "450" was a false
positive: the word "choices" in an unrelated sentence, and this project's
own unrelated count of 450 confirmed Oregon border pharmacies). Proceeded
with the comparison anyway, using the user-supplied 450,000 as a given
external reference point rather than something independently verified.

**Why proceed despite the citation gap:** the comparison itself was
explicitly requested as a rough plausibility check, not a pass/fail test,
and computing our own number is straightforward and valuable regardless
of where the comparison figure originated. But the gap is worth surfacing
plainly rather than silently treating an unverified figure as confirmed
prior art.

**Result:** 346,334 (77% of 450,000) for the compound low-income-AND-
low-access definition. For additional context, low-access ALONE
(dropping the income condition) covers 2,188,152 - about 4.9x the cited
figure. The cited number sits between our two figures, closer to the
stricter (compound) one, consistent with a study using some form of
compound desert definition rather than pure distance - though nothing
stronger than that can be concluded without knowing their actual
methodology. Order-of-magnitude plausible; not proof of correctness
either way.

---

## 2026-07-26 — Border-buffer pharmacies (OR/ID) shown on the Day 7 map, but visually distinct and explicitly labeled reference-only

**Decision:** The 524 OR/ID border-buffer locations will be rendered on
the Day 7 map using a visually distinct marker style from WA pharmacies
(e.g. outlined/greyed rather than solid), with an explicit label (tooltip
or legend text) stating they are reference-only and not part of the WA
pharmacy dataset.

**Why not backend-only:** a viewer looking at a WA border block group
correctly classified `not_desert` because of a nearby Oregon pharmacy
would see no pharmacy on the map at all and have no way to tell the
classification is right rather than broken. That's a real explainability
gap for exactly the border cases this project already went out of its
way to get right (see the Klickitat/Benton/Wahkiakum verification
above).

**Why not shown identically to WA pharmacies:** these 524 locations only
went through the taxonomy-based `pharmacy_type` inclusion filter (Day 2's
`classify()`), NOT the ownership/chain classification or address-dedup
collapsing that every WA `physical_location` went through (Days 3-5).
Rendering them with the same marker style would visually imply the same
data quality and completeness, which isn't true - e.g. two OR/ID NPIs at
the same physical address would show as two separate markers there,
something that would have been collapsed to one `physical_location_id`
had it happened on the WA side.

**How to apply:** any Day 7 map layer, legend, or tooltip logic touching
`border_buffer_locations` should carry this distinction forward - never
merge them into the same visual/data category as `physical_locations`.

---

## 2026-07-27 — Day 7 build: block-group polygons didn't exist yet, fetched them; historical view shows current attributes for locations that existed, not historical attributes

**Decision 1 - fetched WA block-group polygon boundaries.**
`census_block_groups.geom` (CenPop) is a population-weighted POINT, not an
area - there was no polygon anywhere in the project to render "Washington
block groups colored by desert status" as an actual choropleth. Fetched
the 2020 TIGER/Line block-group shapefile (`tl_2020_53_bg.zip`, 5,311
features - matches the table's row count exactly), joined by `geoid`
(100% match, 0 unmatched), and serve it simplified
(`ST_SimplifyPreserveTopology`, ~50m tolerance) - 46MB raw down to 4.3MB,
measured directly rather than guessed before picking a tolerance.

**Decision 2 - the historical slider shows CURRENT pharmacy attributes for
locations that existed by the selected date, not historical attributes.**
`pharmacy_snapshots` only tells us WHEN a location started existing
(`MIN(snapshot_date)` per `physical_location_id`) - we have no historical
record of what a location's `ownership_category` or `pharmacy_type` was on
some past date, only what they are today. So moving the slider back
changes *which* locations are shown, never *how* a shown location is
described. This is a real, separate limitation from the growth-only one
and is surfaced in the API design (`/api/pharmacy/pharmacies?date=X` joins
existence-by-date to always-current `pharmacies` attributes) - worth
calling out explicitly if it's not already obvious to a viewer.

**Decision 3 - desert choropleth colors follow the dataviz skill's status
palette, not its categorical one; ownership uses the categorical palette,
validated before shipping.** `desert`/`indeterminate`/`not_desert` are
states of the world (bad/unknown/fine), not identities, so they use the
skill's reserved status colors (critical red / warning amber / a
near-invisible neutral fill) rather than a categorical hue - this also
avoids color collision with the ownership-category point layer on the
same map. `not_desert` (95% of block groups) is intentionally rendered as
a barely-there neutral tint rather than a solid "good" green, so the
minority `desert`/`indeterminate` areas are what actually draws the eye -
the entire point of the map. Ran `scripts/validate_palette.js` against
the 4 ownership hues actually used (chain/health_system/government_or_
tribal/independent_confirmed) before committing to them: all checks pass
(worst adjacent CVD ΔE 24.2). `unknown` ownership deliberately uses the
palette's muted ink color instead of a 5th vivid categorical hue - it's
an absence-of-information bucket, not a peer identity category, so giving
it equal visual weight to the other four would overstate what's known.

**Evidence this actually works, not just compiles:** tested in-browser,
not just read the code. Moving the slider to 2012-03-28 dropped the
pharmacy count from 1,177 (today) to 848, with the mode note correctly
switching to "Backfilled estimate" language; the one real observed date
(2026-07-18) correctly shows "Observed snapshot" language; clicking a
point (verified via direct marker inspection after pixel-coordinate
clicks proved unreliable at this zoom level) returns the expected name/
ownership_category/pharmacy_type popup content. Zero console errors
across the whole test pass. See `webapp/main.py`,
`webapp/static/js/{date-slider,pharmacy-map}.js`.

---

## 2026-07-27 — Fixed: the pharmacy map was silently dropping all 474 REVIEW-bucket pharmacies, violating the standing carry-forward rule

**Decision:** `/api/pharmacy/pharmacies` now includes locations where
`included_in_access_analysis = TRUE OR walk_in_access = 'unknown'`
(previously `included_in_access_analysis = TRUE` only), and every
returned feature carries a `review_only` flag plus each individual
pharmacy's own `walk_in_access`, so the frontend can render REVIEW-bucket
locations visibly flagged rather than either dropping them or blending
them in as if confirmed.

**Why this was a real bug, not a stylistic gap:** `included_in_access_
analysis` is `FALSE` for BOTH definitively-excluded pharmacies (long_term_
care, mail_order, etc.) AND REVIEW-bucket ones (unspecified, institutional,
unclassified_has_pharmacy_taxonomy) - they're only distinguishable via
`walk_in_access = 'unknown'`. Filtering on `included_in_access_analysis
= TRUE` alone conflated the two and silently excluded every REVIEW
record, directly contradicting the rule established back in Day 2
("don't delete excluded records - flag them") and reinforced every time
since (Day 2.5, Day 5's banner-bug verification, etc.).

**Scope of the bug:** 470 of 1,811 physical locations (26%) had *only*
REVIEW-bucket pharmacies and zero confirmed-included ones - these were
completely absent from the map, not just under-flagged. Frontend
treatment: REVIEW-bucket markers keep their ownership-category fill
color (still real information) but get a dashed warning-amber
(`#fab219` - the same reserved status color used for `indeterminate_
income_suppressed` on the choropleth) stroke instead of white, and an
explicit ⚠ warning line in the popup, both at the per-pharmacy and
per-location level.

**Evidence:** pharmacy count on the map went from 1,177 to 1,624 after
the fix. Verified the arithmetic against the database directly rather
than trusting the UI number alone: 1,177 confirmed-included +
447 review-only-with-a-successful-geocode = 1,624 exactly (the
remaining 23 of the 470 review-only locations lack a geocode match,
consistent with the ~4.9% no-match rate found during Day 4 geocoding).
Spot-checked a real example via direct marker inspection: a Haggen
location (`unspecified` pharmacy_type, the exact taxonomy-coding pattern
flagged in Day 2) now shows both the location-level and pharmacy-level
warning text, with `parent_organization` still correctly resolving to
"Albertsons Companies (Haggen banner)" from the Day 5 banner-labeling
fix. See `webapp/main.py`.

---

## 2026-07-27 — Health system vs. independent-confirmed marker colors: checked, not actually a collision

**Decision:** Kept `#1baf7a` (health_system) and `#008300` (independent_
confirmed) unchanged after a specific check, rather than changing them on
an unverified hunch that they looked "identical or near-identical."

**Why:** ran the palette validator on this exact pair in isolation
(`validate_palette.js "#1baf7a,#008300"`) rather than reasoning about it:
CVD ΔE 35.9 (protan) / 18.6 (tritan) / 37.6 (normal vision), all
comfortably clear of the 12 floor - not a colorblind-safety issue.
Followed up with a direct visual check at two sizes (the legend's actual
render, and an enlarged side-by-side swatch) rather than trusting the
abstract number alone, since the concern was specifically about small-
marker legibility, a different question than CVD confusability: at both
sizes the two read clearly as teal/mint vs. forest green, not as the same
color. Both are legitimately in the "green family" in a loose sense, which
likely prompted the concern, but family resemblance isn't the same as
indistinguishability.

**Evidence:** independent_confirmed is also extremely rare (15 of 1,941
WA pharmacies statewide - see Day 3), so the practical collision
exposure on the live map is low regardless. No code changed for this
item.

---

## 2026-07-27 — Vulnerability index protocol, defined before any Day 8 code (pre-registered, same discipline as Day 6's config)

**Decision:** The full protocol below, computed per WA block group
(5,311 rows - the same population unit Day 6 established, chosen again
here so the shortage layer combines with, rather than duplicates, the
existing access/income work).

### 1. Chronic-condition therapeutic categories (7, out of 21 distinct tokens in the real data)

Included: **Endocrinology/Metabolism, Cardiovascular, Pulmonary/Allergy,
Psychiatry, Analgesia/Addiction, Renal, Rheumatology.**

Chosen by matching CDC's own leading-chronic-disease framework (diabetes,
heart disease, chronic respiratory disease, mental health conditions,
chronic kidney disease, arthritis/autoimmune disease) to the specific FDA
`therapeutic_category` tags actually present in `shortages`, not invented
independently of the data. `Analgesia/Addiction` is included on the
specific grounds that chronic pain management and opioid-use-disorder
maintenance therapy are now clinically treated as chronic conditions
requiring ongoing pharmacy access - concretely evidenced by our own data
(Naltrexone, an OUD maintenance drug, is one of only 3 tier-1
resolved shortages in the whole dataset).

**Explicitly excluded, with reasons, not just omitted:**
- `Anti-Infective` (33) and `Antiviral` (12) - majority acute short-course
  use (antibiotics, flu/COVID antivirals); the minority chronic exception
  (HIV/Hepatitis B suppressive therapy) can't be isolated from the acute
  majority at this data's granularity.
- `Oncology` (22) - most active cancer treatment is infusion/hospital-
  administered, not retail-pharmacy walk-in relevant, which is this
  project's whole frame (`community_retail` is the dominant included
  `pharmacy_type`).
- `Pediatric` (19) - an age modifier that cuts across every other
  category, not a condition category itself.
- Everything else (`Anesthesia`, `Hematology`, `Ophthalmology`,
  `Dermatology`, `Gastroenterology`, `Medical Imaging`, `Urology`,
  `Transplant`, `Total Parenteral Nutrition`, `Reproductive`, `Other`) -
  each is either small-N in this data or doesn't map to a CDC top-tier
  chronic condition without real interpretive stretching.

**Real counts, not estimated:** 108 of 234 total shortages (46%) match
these 7 categories; 105 of those are currently active (`tier=2`) as of
this writing.

### 2. Formula: 0-100, weighted 40/40/20, not equal

```
vulnerability_score = access_points + income_points + shortage_points

access_points   = 40 if is_low_access = TRUE, else 0
income_points   = 40 if income_status = 'low_income'
                    0 if income_status = 'not_low_income'
                  undefined if income_status = 'suppressed' -> see §3
shortage_points = min(20, round(20 * active_chronic_shortage_count / 150))
```

`active_chronic_shortage_count` = count of `shortages` rows with
`tier = 2` (currently active - resolved tier-1 shortages don't count
toward a CURRENT snapshot) whose `therapeutic_category` matches any of
the 7 categories above. This is a **single national number, identical
for every WA block group** - shortage data has no sub-state geographic
granularity, so unlike access/income it cannot vary by block group. All
of the index's geographic variation comes from the access/income
components; the shortage component uniformly raises or lowers the whole
state's floor as national conditions change. Recomputed fresh each time
the index is (re)built from the latest shortage data, not frozen at
protocol-definition time - the same block group's score can move over
time purely from national shortage conditions shifting, even with
unchanged access/income.

**Not weighted equally (40/40/20), because:** access and income are the
two already-validated, block-group-precise components of Day 6's desert
classification - the most direct, individually-verified vulnerability
signals we have. Shortage exposure is explicitly a *national context*
signal, not a local-availability measurement - this project's own
framing, stated as far back as Day 2: "a national drug-shortage context
layer... not a tool that claims to know local medication availability."
Weighting it lower is a direct continuation of that established
distinction, not a new arbitrary call.

**150 (the shortage saturation reference) is an acknowledged judgment
call, stated as one, not hidden as if externally validated.** Chosen as
a round number meaningfully above today's real count (105) specifically
so the index isn't pre-saturated at its ceiling on day one - it needs
headroom to register things getting worse. Revisit if the active count
trends persistently toward or past 150.

**Deliberately NOT severity-weighted** (e.g. by `n_package_variants` or
`source_status`) - a raw count of active matching shortages, to avoid
stacking a second layer of invented sub-weights on top of the first.
Noted here as a reasonable future refinement, not done now.

### 3. Scale and suppressed-income handling - flagged, given a partial score, never defaulted

**Complete records** (`income_status` is `low_income` or
`not_low_income`, 5,290 of 5,311 block groups): `vulnerability_score`
0-100, `vulnerability_score_basis = 'complete'`, banded into
`vulnerability_band`:
- 0-33 -> `low`, 34-66 -> `medium`, 67-100 -> `high`
(equal-width thirds - the neutral default absent any external banding
standard, same reasoning as choosing equal-width over an invented
skew).

**Suppressed-income records** (21 block groups - the exact same 21 Day 6
already flagged `indeterminate_income_suppressed`, not a new or
different set): income_points is **undefined, not defaulted to 0 or 40**.
`vulnerability_score_basis = 'partial_income_suppressed'`,
`vulnerability_score` computed on a **0-60 scale** (`access_points +
shortage_points` only) - a different denominator, not a truncated
version of the 0-100 scale, so it is never directly comparable or
co-sortable with complete scores without accounting for the missing 40
points. These records get **no `vulnerability_band`** - assigning
low/medium/high would itself assert a confidence the data doesn't
support. Consumers (the Day 8 map, any future ranking) must handle
`partial_income_suppressed` explicitly, not silently rank or average it
alongside complete scores. This mirrors Day 6's own handling of the same
21 block groups and Day 7's fix for REVIEW-bucket pharmacies - carry
forward with a flag, never drop, never silently coerce.

**Evidence this protocol is grounded in real numbers, not invented in
the abstract:** every count above (108/234 total, 105 active, 21
suppressed, 1,458/5,311 low-access) was queried from the live database
before this entry was written, not assumed. No Day 8 code has been
written against this protocol yet - this entry exists specifically so
the formula is fixed and auditable before implementation starts, the
same discipline Day 6 applied via
`day6_prep/desert_classification_config.json`.

---

## 2026-07-28 — Day 8 build: shortages shown as a list, never as map points; sequential color for vulnerability, not status colors; a real race-condition bug caught by testing

**Decision 1 - shortages are a browsable list, never plotted as map
points.** The task's "list/overlay" phrasing was read as a UI panel, not
shortages-as-markers, because the latter is impossible to do honestly:
openFDA shortage data has no sub-state location field at all, so placing
a shortage pin anywhere on the map would assert a geographic precision
that doesn't exist - directly against this build's framing requirement.
Only the vulnerability choropleth (built from Day 6's already-geographic
access/income data) varies by location; the shortage list and the
national shortage-count-derived score component are identical regardless
of where on the map you look.

**Decision 2 - vulnerability uses the dataviz skill's sequential blue
ramp, not the status colors used for desert status on the pharmacy map.**
Vulnerability low/medium/high is a true ordinal severity scale (a
continuum discretized into three bands), which the skill's own rule
("sequential = one hue, light->dark" for magnitude data) calls for -
different in kind from desert status's three qualitatively different
situations (bad/unknown/fine), which correctly used the reserved status
colors on the pharmacy map. Also deliberately avoids reusing red for a
different meaning than "desert" carries on the other page, since a user
may have both open.

**Decision 3 - block-group polygon geometry is fetched once and restyled
in place as the slider moves, not re-fetched per date change.** The
polygon coordinates (~4MB simplified) don't change with date, only the
per-geoid score does - so geometry loads once into a keyed layer map
(`blockGroupLayersByGeoid`), and a separate lightweight
`/api/shortages/vulnerability-scores?date=X` endpoint (no geometry,
just geoid + score) drives `layer.setStyle()` calls on every slider
move. Avoids repeatedly transferring the full polygon payload for what
is, from the user's perspective, just a color change.

**Bug caught by testing, not shipped:** the initial version fired the
geometry fetch and the first vulnerability-score fetch in parallel with
no ordering guarantee. When the score response arrived first (timing-
dependent - it did on first real load), every `blockGroupLayersByGeoid[geoid]`
lookup found nothing yet and silently no-opped, leaving the whole
choropleth on its neutral default style with no error anywhere. Fixed by
sequencing explicitly (`Promise.all` gating the slider setup and first
score render on geometry being loaded first). Caught by actually loading
the page and looking, not by reading the code - the map rendered without
any console error, so this would not have surfaced without a real
browser check.

**Evidence the fix (and the formula end-to-end) actually works:**
verified in-browser, not just re-read the code. Sidebar shortage list:
231 items rendered (matches `open_ended_count` from `/api/shortages/config`
exactly), 105 carry the `chronic` badge (matches
`active_chronic_shortage_count` for today exactly). Clicked into a real
block group's popup and confirmed the formula arithmetic directly:
`40 (low_income) + 0 (not low-access) + 14 (today's shortage_points) = 54,
medium`. Moved the slider to 2015-01-01 and confirmed the SAME block
group recomputed to `40 + 0 + 0 = 40` (shortage count for that date was 2,
correctly rounding to 0 points) - access/income held exactly constant,
only the national shortage component moved, precisely as the protocol
specifies. Zero console errors across the full test pass. Confirmed the
Day 7 pharmacy map is unaffected by the shared `map.css` additions. See
`webapp/main.py`, `webapp/static/js/shortage-map.js`,
`webapp/static/shortage_map.html`.

---

## 2026-10-15 — Found: the daily pharmacy snapshot job never observed anything; 85 copies not loaded

**Decision:** Did not load the 86 accumulated pharmacy snapshot files into
`pharmacy_snapshots`. The table keeps its 1,811 backfilled rows plus the
single 2026-07-18 observed snapshot (3,622 rows). The GitHub Actions job
replaces the old script with a real daily NPPES re-sweep (see the GitHub
Actions entry below). User chose this over loading the files as-is or under
a separate label.

**Why:** `day8_prep/snapshot_pharmacies_today.py` (built in Day 8 prep)
copied the local file `day3/wa_pharmacies_deduped.csv` every day and never
queried NPPES. Of 86 files (2026-07-18 to 2026-10-15), 85 are byte-
identical once the date column is ignored; the one that differs (07-18)
does so only because the local file was reclassified between 07-18 and
07-19 (the Day 5 banner fix), not because anything changed in the real
world. Loading them as `observed` would have added ~155,000 rows claiming
86 days of observation that never happened.

**Evidence:** content hashes of every file with the date column stripped:
85 share one hash, 1 differs. Coverage: 86 of 90 calendar days; missing
2026-08-17, 08-27, 10-01, 10-10 - consistent with the launchd caveat
(machine asleep or logged out), and part of why the job moves to GitHub
Actions.

---

## 2026-10-15 — Shortage snapshots folded into the interval table; dropouts labeled "last observed", never "resolved"

**Decision:** Replayed the 85 daily shortage snapshot files after the
2026-07-18 baseline, in date order, through
`jobs/shortage_sync.apply_observation()` - the same function the daily
GitHub Actions job uses, so the backfill and the forward job can't diverge.
Added `last_observed_date` and `end_date_basis` to `shortages`, and a third
tier: tier 1 = confirmed resolved (status flipped to Resolved), tier 2 =
open, tier 3 = left openFDA's feed without ever being marked Resolved,
`end_date` = last day seen, `end_date_basis = 'last_observed_in_feed'`.
User chose this over leaving the July data as-is.

**Why the separate label matters (and turned out to matter a lot):** all
35 dropouts were "To Be Discontinued" entries, and all 35 left the feed
364-369 days after their FDA posting date. That pattern fits
discontinuation notices expiring from FDA's list about a year after
posting - i.e. the product was discontinued, the opposite of a shortage
resolving. Older To Be Discontinued entries (posted as far back as 2012)
are still listed, so this is an observed pattern, not a confirmed FDA
rule. Labeling dropouts "resolved" would have been wrong for every one.

**Safeguards (both in the shared function):** refuses a feed whose row
count doesn't match openFDA's own reported total, and refuses to close
intervals if more than 25% of open shortages vanish in one day (far more
likely a broken feed than real change). Sanity-checked the history first:
daily distinct counts ranged smoothly from 231 to 245 with no dips, and 0
shortages ever dropped out and came back.

**Gap closed:** the old snapshot script never saved `dosage_form` or
`therapeutic_category`. The 40 shortages new since July were all still in
the live feed, so their categories came from a fresh openFDA pull - 0
rows left uncategorized. The new job saves categories every day.

**Evidence:** replay result matched an independent first-vs-last diff
exactly: 40 added, 5 newly resolved, 35 dropped out, 0 reappeared. Table:
234 -> 274 rows (231 open, 8 confirmed resolved, 35 last observed).
Active chronic-condition shortages today: 105 -> 103, so current
vulnerability scores fall slightly once stale entries close. Pre-replay
backup kept locally. See `day9/schema_day9.sql`,
`day9/backfill_shortage_snapshots.py`, `jobs/shortage_sync.py`.

---

## 2026-10-15 — Supabase migration: include-list of 9 tables, PostGIS in `extensions`, API roles locked out

**Decision:** Migrated only the 9 tables the app and daily job read or
write (`physical_locations`, `pharmacies`, `census_tracts`,
`census_block_groups`, `pharmacy_snapshots`, `shortages`,
`border_buffer_locations`, `npi_review_queue`, `snapshot_runs`) via an
explicit `pg_dump -t` include-list, `--no-owner --no-privileges`,
restored in a single transaction. Left behind ~65 MB of raw build-staging
tables (`bg_polygons_raw`, `tiger_tracts_raw`, `urban_areas_raw`,
`all_included_pharmacy_points`, border-zip helpers) and GDAL's own
`ogr_system_tables.metadata` - all regeneratable, none read at runtime.

**PostGIS in `extensions`, not `public`:** Supabase recommends it, and in
`public` PostGIS's `spatial_ref_sys` would be exposed through Supabase's
auto-generated REST API. The dump had exactly 5 `public.geometry(...)`
column types (one per geometry column), rewritten to
`extensions.geometry(...)`; nothing else referenced a PostGIS object. The
app's unqualified `ST_*` calls still resolve because Supabase's default
`search_path` includes `extensions`. Local PostGIS is 3.6, Supabase 3.3 -
every PostGIS function the app uses exists in 3.3.

**API roles locked out:** Supabase exposes every `public` table through a
REST API reachable with the project's anon key, which is public by design.
Enabled RLS on all 9 tables (no policies) and revoked every privilege from
`anon` and `authenticated` (they still held `REFERENCES`/`TRIGGER`/
`TRUNCATE` from Supabase's default grants; `TRUNCATE` isn't governed by
RLS). The app and job connect as the table owner, which bypasses RLS.

**Evidence:** row counts match on all 7 data tables; all 5 geometry
columns are SRID 4326, correct type, same populated counts, 100% valid;
the Day 5 `ST_Within` tract cross-check run on Supabase gives 1,722/1,722
agree, 0 disagree - identical to local; all 5 GIST indexes present. As
`anon`: permission denied. As the app role: all 1,941 pharmacies.
Password read from the environment per command, never printed or written
to a file.

---

## 2026-10-15 — Email alerts dropped from scope (future work)

**Decision:** No subscribe form, no SendGrid, no subscriber table, and no
mention of alerts or notifications on any page. Confirmed nothing of the
kind exists in `webapp/`, `jobs/`, or `day9/`.

**Future work - email alerts for newly posted national shortages:** the
data for it already exists. The daily shortage sync records every
shortage's first appearance (`added` in `jobs/shortage_sync.py`'s run
summary, logged to `snapshot_runs`), so a "newly posted" digest needs no
new data source - only a subscriber store, a sender, and unsubscribe
handling. Any copy must keep this project's framing: "a national shortage
was newly reported - check with your local pharmacy for availability,"
never a claim about any specific pharmacy's stock.

---

## 2026-10-15 — Landing page: static, no live numbers, limitations up front

**Decision:** `/` serves a static page (`webapp/static/landing.html`)
with a short project description, one entry card each for
`/map/pharmacy` and `/map/shortages`, a four-part "How it works"
(pharmacies, deserts, shortage context, and the two timeline sliders),
a "What this can't tell you" box, data attribution, and the GitHub
link. Each map's nav gained an "About" link back to it.

**Why no live counts on the landing page:** every number on it would
need either a DB round-trip on the one page that should load instantly
(and survive a paused Supabase free-tier project) or a hardcoded value
that goes stale the next time the daily jobs change a count - the exact
"231 of 234" problem fixed on the shortage map earlier today. The maps
already show live counts. The page states only the fixed methodology
(1 mi urban / 10 mi rural, 80%-of-AMI proxy, OR/ID border pharmacies,
slider ranges back to 2005 and 2012), each checked against the data and
DECISIONS entries before publishing.

**Why these four limitations:** they're the ones a first-time visitor
is most likely to get wrong: thinking a shortage means their pharmacy is
out of stock, that a registered pharmacy is confirmed open, that
distances are driving distances, or that the income line is HUD's
official figure. The page links to LIMITATIONS.md and DECISIONS.md for
the rest rather than restating them. No mention of alerts or
notifications (see the entry above).

---

## 2026-10-15 — Daily pharmacy snapshot is a real NPPES re-sweep, not a file copy

**Decision:** `jobs/pharmacy_sync.py` replaces
`day8_prep/snapshot_pharmacies_today.py` (which re-saved the static Day 3
CSV daily). Every run re-queries NPPES with exactly the Day 2 population
definition: every ZIP 98001-99403, taxonomy "Pharmacy", NPI-2, kept only
if the `LOCATION` address is in WA. Each of the 1,941 known NPIs is then
**active** (counts), **deactivated** (missing from the sweep *and* a
direct lookup by number returns nothing - the API only serves active
NPIs), **relocated** (LOCATION moved to another ZIP or out of WA), or
**retaxonomied** (no pharmacy taxonomy any more). A location gets an
`observed` row for the day if at least one NPI is active, with that
day's active NPIs as `contributing_npis`. Same-ZIP street-text changes
still count but are listed for review. New NPIs go to `npi_review_queue`
instead of the map.

**Why a direct lookup before calling anything deactivated:** a known NPI
can drop out of the sweep for reasons other than deactivation (taxonomy
or address change). Only an empty lookup by number is evidence of
deactivation, and a lookup that *fails* aborts the run rather than being
read as "gone."

**Why new NPIs go to a queue, not the map:** a map location needs
pharmacy type, walk-in status, ownership, address dedup against existing
locations, and a Census geocode. Each of those took a reviewed day of
work (Days 2-4) with manual-review flags. Auto-adding would put
unclassified points on the map with no ownership color and possibly
duplicate an existing storefront.

**Safeguards (any one aborts the run before anything is written):** any
ZIP failing after 4 retries or exceeding the 1,200-result cap; more than
10% of known NPIs missing from the sweep (a broken sweep, not mass
closure); more than 3% of the previous snapshot's locations disappearing
(override with `--allow-large-drop` only after reviewing). Re-running on
the same day replaces that day's rows.

**Evidence (first real run, 2026-10-15):** 1,403 ZIPs in ~30s; 1,952
WA-located pharmacy NPIs = all 1,941 known + 11 new (registered
2026-07-20 to 2026-10-06, e.g. three Fred Meyer stores on 2026-08-06);
154 known records updated since August; 0 deactivated, relocated or
retaxonomied. Proof that the sweep is live, and a measure of how slowly
NPPES records closures (see LIMITATIONS). The deactivated, relocated,
retaxonomied and address-changed branches were tested on synthetic
records. Both abort safeguards were tested by simulating a 4.4% location
drop and a 20% sweep gap: both aborted and wrote 0 rows. A same-day
rerun left exactly 1,811 rows.

---

## 2026-10-15 — GitHub Actions runs both daily jobs against Supabase

**Decision:** `.github/workflows/daily-snapshot.yml` runs
`jobs/daily_snapshot.py` daily at 14:17 UTC (7:17 Pacific in summer),
plus manual runs (`workflow_dispatch`, optionally one job, optionally
`allow_large_drop`). It connects through libpq's `PG*` variables:
host, port, user and database are in the workflow file (not secret - the
project ref is part of any Supabase URL), and only `PGPASSWORD` comes from
the `SUPABASE_DB_PASSWORD` repository secret. The secret was set by piping
the local environment variable straight into `gh secret set`, never
printed.

**Why these choices:**
- **Each job gets its own transaction and `snapshot_runs` row**
  (`ok`/`aborted`/`failed` + summary or error), so an openFDA outage
  doesn't block the pharmacy sweep, and every day's outcome is queryable.
  Any non-ok job exits non-zero so the run shows red.
- **"Today" is Pacific time**, not the runner's UTC clock. This is a WA
  dataset, and a UTC date would be a day ahead every evening.
- **Off the top of the hour**, because GitHub delays scheduled runs most
  at :00.
- **Pinned dependencies** (`jobs/requirements.txt`,
  `webapp/requirements.txt`) so a Render or Actions rebuild can't pick up
  a breaking release.

**Supabase is now the source of truth.** The local `pharmacy_tracker`
database is a development copy and will drift from it. The local launchd
agent (`com.pharmacytracker.dailysnapshot`, running
`day8_prep/run_daily_snapshots.sh`) was redundant once Actions was live.
On 2026-10-16, at the owner's request, it was unloaded and disabled with
`launchctl bootout` + `launchctl disable`. The plist is kept in
`~/Library/LaunchAgents`, so `launchctl enable` + `bootstrap` restores it.
`day8_prep/snapshots/` ends at 2026-10-15.

---

## 2026-10-15 — Pharmacy map uses the latest observed snapshot on or before each date

**Decision:** `/api/pharmacy/pharmacies` now picks a basis per date. On
or after the first observed snapshot, it shows the NPIs active in the most
recent observed snapshot on or before that date, so deactivations found
by the daily sweep actually disappear and the popup lists only active
NPIs. Before it, it uses the enumeration backfill as before. The response
carries `basis` and `observed_date`, and the mode note under the slider is
driven by those, so the note can't disagree with the points. The slider
gets one marker where observation begins, not one per day.
`/api/pharmacy/config` now returns every observed date (it previously
returned only the first).

**Why:** the old "existed since first snapshot" rule could never remove a
location, which would have made the new daily sweep invisible on the map.
Verified: today → "Observed snapshot" (1,624 locations shown);
2026-08-01 → "Most recent observed snapshot (2026-07-18)"; 2012 →
"Backfilled estimate" (1,179). The 2026-07-10 backfill count matches the
observed count, as expected with no deactivations.

**Also:** static JS/CSS is now served with `Cache-Control: no-cache`.
Testing showed the browser running the previous `pharmacy-map.js` against
the new API. With no build step to fingerprint filenames, revalidation
(an ETag 304) is the simplest way to make a redeploy reach returning
visitors. `db()` in `webapp/main.py` now goes through `jobs/db.py`
(`DATABASE_URL` → `PG*` → local), which Render needs.

---

## 2026-10-16 — Vulnerability map colors by the continuous 0-100 score, not the three bands (registered before implementation)

**Problem (LIMITATIONS.md, found testing the live site):** with access
and income each worth 0 or 40, every complete score falls in 0-20, 40-60
or 80-100, so the band cutoffs at 33 and 66 can never be crossed by the
0-20 shortage component. Coloring by band made the national-shortage
factor invisible on the map, and "high" was exactly the 237 deserts.

**Decision (chosen by the project owner from two options; the other was
re-weighting components or moving cutoffs):** the choropleth fill becomes
a continuous function of `vulnerability_score` for complete records.
**The scoring formula, weights, saturation reference (150) and band
definitions are unchanged.** Bands stay in the API response and in each
popup as labels; they just no longer drive the fill.

**Color rule, fixed here before any code:**
- Sequential single-hue blue, light to dark, with the three old band
  colors kept as anchors at the band cutoffs so the meaning carries over:
  0 → `#d6e6f9`, 33 → `#86b6ef`, 66 → `#2a78d6`, 100 → `#104281`.
- Interpolated in OKLab, not sRGB, so mid-tones stay clean blue instead
  of going grey, and equal score steps look roughly equally different.
- One color function drives both the map fill and the legend gradient,
  so they can't disagree.
- Legend: a 0-100 gradient bar with ticks at 0 / 33 / 66 / 100 marking
  where the low / medium / high labels apply.
- Suppressed-income block groups (partial 0-60 score) are **unchanged**:
  grey and dashed. Their score is on a different scale, so placing them on
  the 0-100 ramp would imply a comparability the protocol rules out.

**What this does and doesn't fix:** the shortage component now visibly
moves every block group's shade as the slider moves (by up to 20 points
of the 100-point ramp). Because it's a single statewide number, it
darkens or lightens the whole map uniformly. It can't change which block
groups are more vulnerable than others - that pattern still comes entirely
from access and income. That remaining limit is stated in LIMITATIONS.md,
not hidden by the new colors.

---

## 2026-10-16 — Daily snapshot runs twice a day; repeat runs audited and made safe

**What happened:** the workflow's first-ever scheduled slot (14:17 UTC
2026-10-16, the morning after it was added) never fired. There was no
run at all, not even skipped or failed. Nothing was misconfigured: the
file on `main` had a valid `schedule` trigger, Actions was enabled, the
workflow was `active`, and GitHub's status page showed no incident.
GitHub documents scheduled runs as best-effort (they can be delayed or
dropped under load), and new schedules are commonly reported to miss
their first slot. That day's snapshot was captured with a manual run.

**Decision:** add a second daily schedule at **20:43 UTC** (13:43 PDT /
12:43 PST) alongside 14:17 UTC. Both are always on the same Pacific date,
which is the job's "today", so the second run re-observes the same day
rather than starting a new one. Changing the workflow file also makes
GitHub re-register the schedule.

**Why a second run is safe - audited per table:**
- `pharmacy_snapshots`: the day's `observed` rows are deleted and
  re-inserted, so the last run of the day wins, with no duplicates.
  The 3% drop safeguard compares against the previous *date*, not an
  earlier run the same day.
- `npi_review_queue`: an upsert that refreshes `last_seen_date` and the
  address, and never resets `first_seen_date`.
- `shortages`: every change is computed against the table's current
  state, so a repeat run with the same feed changes nothing (tested).
  **One real gap was found and fixed:** with three or more runs in a day,
  a shortage seen → missed → seen again would have been closed with
  `end_date` = today and reopened as a new row *starting* today. That's
  two overlapping intervals, counting the shortage twice for that day in
  the list and the vulnerability score. Exactly two runs couldn't
  trigger it, but a manual run plus both scheduled ones can. A same-day
  dropout that comes back now reopens the original interval instead
  (`same_day_dropouts_reverted` in the run summary). Tested in a
  rolled-back transaction: see/miss/see on one day leaves 274 rows and
  the shortage counted once. A real cross-day dropout (missed 10-21,
  back 10-22) still produces a new interval with no overlap.
- `snapshot_runs`: one row per run, so two (or more) per day. The
  shortage deltas (`added`, `resolved`, `dropped_out`, ...) are relative
  to the previous run, so summing them across a day is still correct. The
  pharmacy fields (`locations_active`, `new_npis_queued`) are *state*
  counts and must not be summed - read the latest `ok` run per
  `(run_date, job)`. This matters for the future email-alerts idea, which
  would key off shortage `added`.

The workflow's `concurrency` group already keeps two runs from
overlapping. A run that fires while another is in progress waits.

---

## 2026-10-16 — Security audit: full git history and Actions logs scanned for credentials, nothing found

(This is the "security-audit entry" `.gitignore` refers to. The
pre-publication audit before the first commit was reported in chat but
never written down here.)

**What was scanned:** every object in the git database, reachable or
not: 136 objects, including 6 commits. One of those commits is the
pre-amend initial commit, which was never pushed; every other object is
on the public `origin/main`. Also scanned: all commit messages, the
public GitHub Actions run logs (2 runs), and the working tree including
untracked and ignored files (300 files, local only).

**What was searched for, without ever printing a value:**
- **The Census API key** pasted on Day 1, matched exactly. The value was
  taken in memory from the session transcript and confirmed as the key
  used in the Day 1 Census API calls.
- **The Supabase database password**, matched exactly in its raw,
  percent-encoded and plus-encoded forms. It was read in memory from the
  local environment variable.
- **Any `postgres://` / `postgresql://` URL with a non-placeholder
  password.**
- **Generic credential patterns:** AWS access keys, GitHub tokens,
  SendGrid keys, private-key blocks, Supabase JWTs, `key=` plus 40 hex
  characters, and literal `PASSWORD=` assignments.

**Result: zero hits everywhere.** No connection URL with a password
exists anywhere in history. The only database references are the
pooler hostname and user in the workflow's `PG*` variables (not secret
by design) and the variable *name* `DATABASE_URL`. The patterns were
checked against planted fake credentials and caught each one (connection
string, Census `key=`, `PGPASSWORD=`, AWS, GitHub), while correctly
skipping the `[PASSWORD]` placeholder. So "no hits" is a real negative,
not a broken scan.

**No rotation is needed for anything in the repo.** Separately, rotating
the Census key is still recommended, as advised on Day 1. It was passed
as a literal command-line argument then, so it exists in the local
session transcript, though not in any file or commit.

---

## 2026-10-16 — Slider 500s: Supabase's 15-client pooler limit; fixed with a connection pool, caching, and a slider that owns its load cycle

**Symptom (reported from the live site):** dragging either slider produced
HTTP 500s from `/api/pharmacy/pharmacies`, `/api/shortages/active` and
`/api/shortages/vulnerability-scores` (18 + 84 console errors in one
session), then `Unexpected token 'I', "Internal S"... is not valid JSON`.
On the pharmacy map, the slider read 2026-10-16 while the note under it
described 2018-09-25.

**Reproduced against the live site:** sequential requests: 28/28 ok.
8 concurrent: all ok but up to 53s. 24 concurrent: 2 HTTP 500s and 2
60-second timeouts. 48 concurrent: 16 of 112 failed, on all three date
endpoints. Every date that failed succeeded when retried alone - **load,
not a date-specific bug.**

**Root cause:** the Supabase **session pooler admits 15 simultaneous
clients**. Measured directly: connections 1-15 succeed and the 16th
gets `FATAL: (EMAXCONNSESSION) max clients reached in session mode`. The
app opened a new connection for every request. FastAPI runs up to 40 sync
requests at once, and the slider fired a fetch on every `input` event
(two per step on the shortage map), so a quick drag blew through 15. The
unhandled `OperationalError` became FastAPI's plain-text "Internal Server
Error", and the frontend called `.json()` on it without checking the
status. Separately, nothing ordered the responses: the pharmacy note and
points were filled independently by whichever response arrived last.
That's how a late 2018-09-25 response ended up under 2026-10-16. Render's
own log traceback wasn't retrieved (no Render API access). The diagnosis
rests on reproducing the identical error against the same pooler.

**Fix - server (`webapp/main.py`):**
- **A connection pool of 4** (`DB_POOL_SIZE`). The 15 pooler slots are
  shared with the daily job, with a second instance during a Render
  deploy, and with local psql. Requests wait up to 15s for a free
  connection instead of failing. Connections are autocommit (read-only,
  no open transactions). A refused or dropped connection is retried once.
- **Database errors return JSON 503**, and anything else returns JSON
  500, never plain text. Bad dates get a 422.
- **In-memory caches.** The shortage table (274 rows) and the pharmacy
  locations, eligibility and backfill dates reload every 5 minutes, so a
  new snapshot shows up on the site within 5 minutes of a run. The
  vulnerability base reloads hourly, the static polygon and border layers
  every 6 hours. Per-date responses are cached on top, so dragging the
  slider almost never touches the database. Vulnerability scores depend
  on the date only through the 0-20 shortage points, so the 5,311-row
  list is serialized once per points value. If a reload fails, the
  previous data keeps being served.
- **Verified identical output:** for 25 dates (2005-2026), the new
  endpoints return exactly the old ones' data. Static layers match except
  feature order, which was never defined. With cold caches, 180 date
  requests from 48 threads against Supabase all succeeded in 3.1s using 2
  connections. With all 15 pooler slots held, the app retried and
  returned a JSON 503, then recovered when the slots freed.

**Fix - client (`date-slider.js`, shared by both maps):** the slider now
owns the whole load cycle, so the rule is enforced once:
- **The readout date and every date-dependent element always agree.**
  The moment the date changes, the page clears the old date's points,
  colors, popups, counts, list and note. `render` only ever receives
  data for the date in the readout, and each map also checks the
  response's `as_of_date`. A failure leaves the content cleared and shows
  "Couldn't load YYYY-MM-DD" with Retry. On the shortage map, both
  requests must succeed before anything is shown.
- **Debounced:** while dragging, it fetches only after a 250ms pause,
  and immediately on release. The previous date's request is aborted, and
  a late response for an abandoned date is discarded.
- `fetchJSON` rejects any non-2xx response, so an error body is never
  parsed as data.

Local results: a 401-event drag across the full pharmacy range sent 1
request (previously 401). A 301-event shortage drag sent 2 (one per
endpoint). Content was cleared, never stale, throughout. An injected 500
showed the error state with nothing left from the previous date, and
Retry recovered it. A slow response for 2010 overtaken by a fast one for
2020 showed 2020 only. Every check ended with readout = note date, count
= markers = API count, and 0 of 5,311 block-group colors mismatched.

**Also:** the three HTML pages now send `Cache-Control: no-cache` (the
cause of the stale three-color legend: an old cached page paired with the
new script). The legend code and the layer-error reporting now tolerate
missing elements, so a stale page still renders the map. Tested by
loading the shortage page with both elements removed: all 5,311 block
groups colored, 231 shortages listed, no errors.

**Live re-test after deploy (`25a103e` + `7431264`), 2026-10-16:**
- **Same concurrent load test that failed before:** 0 failures at every
  level (1/8/24/48 concurrent; 224 requests). The slowest request went
  from 60s (timeout) to 4.1s.
- **Both maps, fresh browser tab each, console open:** real mouse drags
  across the full range in both directions plus partial sweeps, then
  three synthetic fast drags (1,203 `input` events each).
  - **Console errors: 0 on both maps.** Every API request returned 200,
    apart from 3 (pharmacy) and 6 (shortage) `ERR_ABORTED` entries.
    Those are superseded requests the slider cancelled on purpose.
  - **Agreement:** 7 of 7 checks per map agreed. The readout date matched
    the note or summary date, the count matched the markers or list
    items, and both matched a fresh API response for that date. On the
    shortage map, 0 of 5,311 block-group colors mismatched at each check.
  - **During drags:** of 1,203 mid-drag samples per map, 1,201 were
    "loading, content cleared" and 2 were "loaded, consistent". Never a
    previous date's content.
  - **Requests:** 3 for the pharmacy map and 6 for the shortage map (two
    per date) across the three synthetic drags - previously one per
    `input` event.
- **The errors in the original report:** the browser's network log
  showed the 500s were all from the pre-deploy page firing one request
  pair per slider step, with the old `.json()`-on-500 parse errors.
- **One more fix found while testing:** the pharmacy mode note is
  cleared while a date loads and varies in length, so the slider jumped
  vertically under the cursor between drags. Its space is now reserved
  (`7431264`); the slider stays at the same position in every state.

---

## 2026-10-16 — Slider cache caps, memory budget, staleness window, and pool size

Details behind the caching in the entry above, measured rather than
estimated.

**Per-date caches are capped LRUs** (least-recently-used entry evicted
when full):

| Cache | Cap | Size per entry | Full |
|---|---|---|---|
| Pharmacy map responses (keyed by observed date, or by backfill prefix) | 24 | ≤ 0.9 MB | ~16 MB |
| Observed-snapshot NPI sets | 8 dates | small | < 5 MB |
| Shortage list responses | 256 dates | ≤ 70 KB | ~3 MB |
| Vulnerability scores, by shortage points | 21 (every possible value, 0-20) | 1.49 MB | ~31 MB |

Single-value caches are replaced on reload, never grown: the static
polygon and border layers (10.6 MB, refreshed every 6 hours), the
vulnerability base (hourly), and the shortage table and pharmacy data
(every 5 minutes).

**Memory, measured:** every cache was filled past its cap (400 and 600
distinct dates; both date-keyed caches stopped exactly at 24 and 256).
The whole process measured 133 MB, or **about 142 MB** with all 21
vulnerability entries. That's ~28% of Render's 512 MB, with headroom
for the pooled connections and for a reload, when old and new data
briefly coexist.

**Staleness window: 5 minutes.** A new snapshot reaches the site within
5 minutes of the job committing it. If a reload fails, the previous data
keeps being served and the reload is retried after 30 seconds.

**Pool: 4 connections.** Supabase's session pooler admits 15 clients
(measured). Those 15 are shared with the daily job, with a second app
instance while Render swaps deploys (another 4), and with local psql.

**Same output as before the caching:** old (one query per request) vs
new endpoints on the same database. Local: 2,394 comparisons covering
every pharmacy first-registration date and the day before it, every
shortage interval start and end ±1 day, both slider minimums ±1, the
backfill/observed boundary (2026-06-30 ±1, 2026-07-17..19, each observed
date ±1), today, and the no-date default. Supabase: 277 comparisons over
the same named boundaries with its three observed snapshots. **0
mismatches.**

**README-ready summary:** Both date sliders are served from in-memory
caches with fixed size caps (the whole app peaks at about 140 MB of the
host's 512 MB), refreshed every 5 minutes and backed by a 4-connection
database pool kept under Supabase's 15-connection limit, so dragging a
slider never overloads the database and new daily data appears on the
site within 5 minutes.

---

## 2026-10-16 — Desert count reported as a range (176-237) because REVIEW-bucket pharmacies aren't counted in distances

**Finding (while pulling numbers for the Day 10 README):** the Day 6
nearest-pharmacy search counts only locations with a confirmed walk-in
pharmacy (`desert_classification_config.json`,
`nearest_pharmacy_search`). That was the conservative choice, but its
effect was never measured. Measured now against Supabase: 61 of the 237
desert block groups (91,478 residents) are within their urban or rural
threshold of one of the 447 geocoded REVIEW-only locations. Counting
REVIEW locations can only shorten distances, so the desert count under
this method lies between **176 and 237** block groups (254,856 to
346,334 residents).

**Decision:** keep 237 as the published classification, because it is
what the pre-registered method produces and REVIEW status is genuinely
unresolved. But report it everywhere with the range and the reason
(README, policy brief, LIMITATIONS.md), never as a bare point estimate.
Rankings in the policy brief flag which deserts are review-sensitive. No
change to the classification code: resolving the REVIEW bucket is the
real fix, not counting unconfirmed pharmacies by fiat.

**Evidence:** PostGIS `ST_DWithin` between each desert block group's
CenPop centroid and every REVIEW-only location (geography, threshold
1 mi urban / 10 mi rural). 413 of the 474 REVIEW NPIs carry the generic
"Pharmacy" taxonomy (`pharmacy_type = unspecified`). By county, the
review-sensitive deserts are concentrated in King (25 of 78), Pierce
(10 of 33), Snohomish (10 of 15) and Clark (9 of 16).

---

## 2026-10-16 — Day 10 documentation: README, policy brief, and a copy consistency pass

**README.md** is written for two readers: a recruiter in the first
paragraph, and a skeptical methodologist further down. Every number comes
from a query against Supabase or from these docs, not from memory.
Nothing external is cited as a population comparison. The ~450,000
figure from the Day 6 plausibility check was never sourced, so it's left
out. The Related Work section describes the WSU "Pharmacy care in rural
Washington" ArcGIS web map from its own item metadata and layer data:
86 rural towns with a 2019 population, the miles to the nearest pharmacy
(10.2-27.7) and that pharmacy's name, some across the Oregon border; plus
hospitals, rotation sites, MUA/MUP areas and rural counties. The web
map's owner field is a personal email address and is deliberately not
reproduced.

**policy_brief.md / .docx:** one page. County and block-group rankings
carry a "review-sensitive" flag (see the 176-237 entry above). Skamania's
top share, for instance, rests on 2 block groups that are both
review-sensitive. Growth is framed as "today's locations by
first-registration year": the dataset only contains NPIs active in 2026,
so a per-year count is not openings that year. No local-shortage or
ownership-burden claims. The .docx is generated directly as
WordprocessingML (no pandoc or python-docx available, and macOS
`textutil` flattened the table). It is validated as well-formed and
rendered to confirm it fits one page.

**Consistency pass (site copy vs. README):**
- Landing page: ownership listed as "(chain, health system, independent)"
  -> now names government/tribal, says independent only with positive
  evidence, otherwise unknown. Deserts step now says straight-line,
  confirmed walk-in, and geographic proximity not travel time. Shortage
  step says the shortage term is one national number. The timeline gives
  the 2026-07-18 observed start. "Checked every day" -> "twice a day". A
  "Some deserts may not be" limitation was added. The footer lists Urban
  Areas.
- Pharmacy map: the growth-only note said "Before October 2026"; it now
  says before 2026-07-18, notes the undercount from closed-and-deactivated
  pharmacies, and that an inactive NPI isn't proof of closure. The 2006
  note said "roughly half … in a few months"; it now gives the measured
  49% / 80% May-August. A new note says desert status is straight-line
  proximity to confirmed walk-in pharmacies, the income cutoff is a proxy,
  and REVIEW locations aren't counted. The REVIEW legend label says "not
  counted in desert status".
- Both maps: block-group popups said "Nearest pharmacy: X mi"; they now
  say "nearest confirmed walk-in pharmacy … (straight line)". The figure
  never included REVIEW locations, so the old label invited "but there's
  a pharmacy right there."

**Layout fix found during the pass:** at a 557x662 window the notes
panel took 625px and the pharmacy map's height was **0**. Even before
the new note, small windows left the map ~130px tall. The notes panel
is now capped at 45% of the viewport and scrolls, with the slider pinned
(sticky) at its top. Measured after: map 298px at 557x662 and 365px at
375x812, with the slider at the same position whether or not the notes
are scrolled.

---

## 2026-10-16 — Map pages on phones: stacked, scrolling layout below 800px

**Problem:** both map pages put a fixed 300px sidebar beside the map, so
at phone width (375px) the map was ~75px wide.

**Decision:** below 800px wide, the page scrolls instead of being a
fixed-height app, and stacks: the map (full width, 55vh, at least
300px), then the slider with its load status and the mode note, then
the legend/sidebar (the shortage list scrolls within 50vh), then the
remaining notes. CSS only (`display: contents` on the two wrapper divs
plus `order`), so both pages keep their shared HTML. Above 800px nothing
changes.

**Verified locally at 375x812:** the pharmacy and shortage maps both
render 375x447, with no horizontal scroll and the slider directly under
the map. On the shortage map the label, list and all 5,311 colors agree
with the API. Real mouse drags on the phone-width slider land
correctly (e.g. 2018-02-02 shows 1,414 locations, matching the API). At
768x1024 (tablet) the layout is stacked too, with the map 753x563. At
1280x800 the desktop layout is unchanged: map 980x395 with the 300px
sidebar, the notes panel capped and scrolling, the slider sticky, and
no page scroll.

---

## 2026-10-16 — Day 10 review: WSU comparison corrected, safeguards stated precisely, shortage-map framing made explicit

**WSU map, re-read layer by layer from its ArcGIS data:**
- Washington Pharmacy Deserts: 86 towns, 2019 population, "miles to a
  pharmacy" (10.2-27.7), nearest pharmacy name. 5 towns list an Oregon
  pharmacy.
- Critical Access Hospitals / Acute Care: 39.
- RHI WSU Pharmacy Student Rotation Sites: 13.
- MUA/MUP: a static PNG overlay at 40% opacity, not data.
- Rural Counties: one drawn feature.

The README's Related Work implied two things it lacks that it partly has:
- a **border correction** - contradicted, since its desert layer names
  Oregon pharmacies for 5 towns;
- an **income dimension** - partly contradicted, since its MUA/MUP
  overlay reflects HRSA underservice designations that (as far as I could
  tell) weigh poverty.

Rewritten to state what each layer contains. "What this project adds" is
now scoped to what the layers show, under "as far as I could tell in
October 2026". The publisher attribution (WSU Rural Health Initiative,
inferred from a wsu.edu owner and the "RHI WSU" layer name), "federally
designated", "rural towns" and "practitioner-oriented" were uncertain or
editorial, and are now hedged or removed. The landing page and the
policy brief don't mention the WSU map.

**Safeguards in the README now match the code exactly:**
- openFDA record count vs. its reported total;
- `MAX_DROPOUT_FRACTION = 0.25` of open shortages;
- NPPES `_get` 4 attempts with 1/2/4s backoff, and the 1,200-result cap
  (`MAX_SKIP = 1000`);
- `MAX_MISSING_FRACTION = 0.10`;
- a failed direct NPI lookup aborts;
- `MAX_LOCATION_DROP_FRACTION = 0.03`, measured against the **previous
  observed snapshot**, not "a day". The README previously said "in a
  day".

**Shortage map framing:** the README's pages table and the landing page
now say plainly that the map is national context and that its
geographic pattern comes entirely from the desert classification's
access and income measures. Previously the README said so only in
Methodology, and the landing page said "access and income" without tying
it to the desert classification.

---

## 2026-10-16 — Day 11 fixes: no individuals' names in the app or in tracked files; range on the landing page; national-context wording

**1. Officer names removed from the ownership output and the live
popups.** The officer-repetition fallback labelled 124 pharmacies
"Unidentified chain (shared authorized official: FIRST LAST, N
locations)", naming 28 individuals on the live site. It now says
**"Likely chain: several locations share a registered signer"**. The
signal is kept as `classification_method = authorized_official_repetition`
plus a new `shared_signer_npi_count` (group sizes: 17 groups of 3, 6 of 4,
2 of 5, 1 each of 7, 9 and 23). Names are used only to group NPIs inside
`day3/classify_ownership.py` and are never written out.
- **Proof the code and the files agree:** re-running the updated
  generator and dedup step reproduced the patched day3 CSVs byte for byte.
- **Databases:** Supabase and the local database were migrated with
  `day11/remove_personal_names.sql`, which checks itself: 124 rows
  relabelled, 0 names left, 0 mismatches with the CSV. The schema and both
  load scripts carry the new column.
- **A second case found while verifying:** two pharmacies are registered
  in NPPES with an individual's name as the legal `organization_name`.
  It equals the record's authorized official. They're flagged
  `organization_name_is_individual` by NPI, and the API shows their trading
  name (DBA) instead. Their legal names remain in four committed CSVs
  (`day2/wa_pharmacies_classified.csv`, `day2/wa_pharmacies_final.csv`
  and both day3 CSVs) as NPPES source data. Removing them is the owner's
  call.
- **Verified:** every endpoint (5 static, plus the 3 date endpoints at 4
  dates) and every page and script was scanned. Matched against 731
  authorized officials' names and 4,214 phone/fax numbers from the raw
  NPPES pulls, plus the word "official": 0 of 23 had any match. The same
  matcher found 31 names in the old committed CSV (positive control). One
  remaining substring match, in a taxonomy description, is junk NPPES
  data ("MANAGED CARE" entered as an official's name), not a person.

**2. Personal-data files untracked, not deleted.**
`day2/wa_pharmacies_full_flat.csv` (1,200 officials' names and phone
numbers), `nppes_sample_flat.csv` and `nppes_sample_raw.json` (officials'
names, titles, credentials, phone and fax numbers) are removed from
tracking with `git rm --cached`. They're added to `.gitignore` and kept
locally. This reverses the 2026-10-15 choice to keep the Day 1 samples.
The day3 CSVs had no separate name or phone columns; the names were inside
`parent_organization`, now relabelled (above).

**History was NOT rewritten - what it would take, for the owner to decide.**
The names remain in git history: the three files and the old day3 CSVs
were all added in the initial commit (`50fed2e`). Any clone of the public
repository, and GitHub's own copy, still has them.

*What a rewrite involves:*
1. A fresh clone, then `git filter-repo`:
   - `--invert-paths` on the three files;
   - plus `--replace-text` (or a blob callback) to replace the officer-name
     labels in every historical version of the two day3 CSVs.
2. Re-scan every blob in the rewritten history (the 2026-10-16 audit
   scanner) to confirm zero names.
3. Re-add the remote and `git push --force-with-lease origin main`.
4. Ask GitHub Support to purge cached views and garbage-collect. Until
   then, old commits stay viewable by their SHA.
5. Replace every local working copy with a fresh clone.

*Risks:*
- **Every commit hash changes,** all of them, because the initial commit
  is rewritten. Hashes cited in DECISIONS.md (e.g. `7431264`, `25a103e`,
  `32e9549`, `c965c0c`, `e64ae4b`, `a994189`, `3550526`, `463b999`) go
  stale. filter-repo writes a commit map that could be used to update
  them.
- **The force push rewrites public history.** Forks and existing clones
  keep the old history and can't be recalled.
- **Render** auto-deploys the new HEAD (same content, a brief redeploy and
  cold start); its deploy history keeps the old SHAs. **GitHub Actions**
  run history also references old SHAs. The schedule itself is
  unaffected.
- **Limited benefit:** this is public NPPES data, and the repository has
  been public since 2026-10-15. A rewrite reduces future casual exposure;
  it can't guarantee removal.

**3. Desert range everywhere.**
- **Landing page:** the "Pharmacy deserts" step now states "Between 176
  and 237 of Washington's 5,311 block groups are deserts", with what each
  end means. These are classification outputs, not live counts, so the
  earlier no-live-numbers rule still holds.
- **The standalone mentions now read "237 (the upper end of a 176-237
  range)":** the README methodology, the policy brief (.md and .docx,
  still one page), and the same sentence in LIMITATIONS.md.

**4. Wording.**
- The shortage sidebar heading is now "Active national shortages (N)".
- The summary line says "a single national number, the same for every
  block group" instead of "a single statewide number". The same phrase
  was fixed in the brief and LIMITATIONS.md.
- The site title is now "Washington Pharmacy Access & National Shortage
  Context": landing `<title>` and `<h1>`, README heading, FastAPI title.
  The GitHub repository description is empty, and the resume bullets
  never used the title.

---

## 2026-10-16 — Legal personal names removed from the committed CSVs; MIT license added

**Personal legal names.** Two pharmacies are registered in NPPES under
an individual's name as the legal `organization_name` (NPIs 1649333105
and 1760594675).
- **The rule:** `output_organization_name()` in
  `day2/classify_pharmacy_type.py`, also used by
  `day2/build_final_dataset.py`. When the legal organization name equals
  the record's own authorized official's name, the CSV gets the trading
  name (first DBA) instead. That's what the site already showed. It's a
  rule over NPPES's own fields, not a list of names, and classification
  still runs on the raw record.
- **Databases:** both now store the trading name too, so a rebuild from
  the CSVs and the live data agree.
- **Unchanged:** the `organization_name_is_individual` flag stays, and the
  API output is unchanged.

**Regenerate-from-source check.** All four day2/day3 CSVs were
regenerated in pipeline order (`classify_pharmacy_type.py` ->
`build_final_dataset.py` -> `classify_ownership.py` ->
`dedup_addresses.py`).
- `wa_pharmacies_final.csv`, `wa_pharmacies_ownership.csv` and
  `wa_pharmacies_deduped.csv` differ from the previous commit in exactly
  those two `organization_name` cells. The bridge file is unchanged.
- **`day2/wa_pharmacies_classified.csv` regenerates with 13 further
  differences,** all from before this change. That file is the original
  1,200-record Day 2 sample and was never regenerated after the
  2026-07-18 classification-precedence fix. 11 `non_pharmacy` and 2
  `military` rows now move to `unclassified_has_pharmacy_taxonomy`.
- To keep this change small, the committed file keeps its Day 2 contents
  with only the two names replaced. Regenerating it would update those 13
  rows to the current rules. It isn't used downstream: the full 1,941-row
  `wa_pharmacies_final.csv` is.

**Verified:** no tracked file contains any authorized official's full
name (matched against 731 names from the raw NPPES pulls). The only
remaining hits were two junk NPPES entries made of ordinary words
("MANAGED CARE", "CLOSE PHARMACY").

**License:** MIT, "Copyright (c) 2026 Rishabh Jain", in `LICENSE`. The
README has a one-line License section noting that the data sources
(CMS NPPES, U.S. Census Bureau, openFDA, OpenStreetMap) keep their own
terms.

---

## 2026-10-16 — Final polish: classified.csv untracked, repository metadata, README screenshots

**`day2/wa_pharmacies_classified.csv`: untracked, not regenerated.**
Regenerating was quick, but `day2/DAY2_REPORT.md` quotes that file's
exact Day 2 counts ("1,074 included / 83 excluded / 43 flagged" out of
1,200, and the per-taxonomy table). A regenerated file, which would
reflect the 2026-07-18 classification fix, would silently contradict the
report. The file is a superseded intermediate: the 1,200-record capped
sample, contaminated by out-of-state LOCATION records and not used
downstream. So it's removed from tracking (`git rm --cached`; local copy
kept; added to `.gitignore`). DAY2_REPORT.md gets a dated note where it
links the file, so the link doesn't silently break.

**GitHub metadata (via `gh repo edit`):**
- description "Washington pharmacy access and national drug-shortage
  context explorer";
- homepage set to the live site;
- topics postgis, fastapi, leaflet, public-health, geospatial, pharmacy.

**README screenshots (`docs/pharmacy-map.png`,
`docs/shortages-map.png`):** taken from the live site at 1440x1080
with headless Chrome, driven over the DevTools protocol. The script waits
in real time until the slider reports the date's data as loaded, then
for the tiles. Chrome's simpler `--screenshot --virtual-time-budget`
mode was tried first and rejected: fast-forwarded timers left a 22px band
with no tiles at the bottom of the pharmacy map that a real browser
doesn't show.

**Found while checking that, not fixed here (this commit excludes
`webapp/`):** Leaflet's idea of the map size can go stale after the page
finishes laying out.
- **Measured at 1440x1080:** on the shortage map, Leaflet's height is 904
  vs an 827px container in a real browser. On the pharmacy map, 695 vs
  653 in one real-time capture, while a real browser measured 653 vs 653,
  so it depends on load timing.
- **Effect:** the extra area is clipped, so nothing visibly breaks, but
  the map's center sits a little low and popups near the bottom edge can
  be clipped.
- **Cause:** both pages call `invalidateSize()` only on window load,
  after 150ms and on resize. They don't call it when the notes, slider or
  counts below the map change the container's height.
- **Fix (later):** a `ResizeObserver` on `#map` calling
  `map.invalidateSize()`.

---

## 2026-10-16 — Map size kept in sync with its container (ResizeObserver); open item closed

**Change (`6185f9c`, webapp only):** both map scripts replace their three
one-off `invalidateSize()` calls (on window load, after 150ms, on window
resize) with `new ResizeObserver(() => map.invalidateSize()).observe(#map)`.
Nothing else changed.

**Why:** Leaflet measures the map once at init. The slider, notes and
counts below the map fill in later and change the container's height,
so Leaflet's size went stale.

**Tested** in headless Chrome against the live site, before and after
the deploy, with an identical script:
- Leaflet's height vs the container's;
- the distance between the intended center (47.4, -120.6) and the middle
  of the visible map;
- a popup opened with its anchor 40 and 10 px above, and 20 and 50 px
  below, the visible bottom edge.

| | Before (desktop 1440x1080) | After (desktop) | Phone 375x812, before and after |
|---|---|---|---|
| Leaflet vs container height | 904 vs 827 (shortage), 695 vs 653 (pharmacy) | equal | equal |
| Off-center | 39 px / 22 px | 1 px | 1 px |
| Popup anchored 20 / 50 px below the visible edge | no auto-pan; clipped 7 / 37 px (shortage), 7 / 17 px (pharmacy) | auto-pans 31-32 / 61 px; clipped 0 | clipped 0 |
| Popup anchored inside the visible area | fully visible | fully visible | fully visible |

At phone width the stacked layout gives the map a fixed 55vh height, so
it never had the mismatch.

**Why the test ran headless:** the in-app browser pane was hidden while
testing and rendered no frames (0 animation frames in 500ms).
`ResizeObserver` only fires as part of rendering a frame, so a hidden
pane can't exercise it. Headless Chrome renders frames.

**Sliders re-tested** on the live site, both pages, desktop and phone, with
real mouse drags sent through Chrome's input pipeline
(`Input.dispatchMouseEvent`): full range, partial and back. Every check
agreed: readout = note/summary date, count = markers/items = a fresh API
response, 0 of 5,311 colors mismatched.
- **Console:** the only message in every run is a 404 for `/favicon.ico`,
  which the site doesn't have. It predates this change, and Chrome doesn't
  show favicon failures in the DevTools console. Not changed; this commit
  was scoped to the resize fix.

**README screenshots retaken:** the old ones were captured with the
stale size. Aligning old against new shows the maps were 38px
(shortage) and 21px (pharmacy) low, matching the measured off-center
error.

---

## 2026-10-16 — Favicon added; page loads now log zero console messages

**Change (`2177e58`, webapp only):** a favicon. Nothing else changed.
- **The icon:** a blue (`#2a78d6`, the site's chain-ownership blue) map pin
  with a white pharmacy cross, legible at 16px.
- **`webapp/static/favicon.svg`:** for current browsers.
- **`webapp/static/favicon.ico`:** 16/32/48px PNG images in an ICO
  container (2,434 bytes), rendered from the SVG with headless Chrome.
  It's served at `/favicon.ico` by a new route.
- **Links:** all three pages carry `<link rel="icon">` tags for both.

**Why:** browsers request `/favicon.ico` on their own. Without it,
every page load logged "Failed to load resource: 404" - the one console
message left after the slider and resize fixes.

**Verified on the live site** (headless Chrome, recording every console
message at every level plus uncaught exceptions):
- **Before:** each of the three pages logged 1 error (404 for
  `/favicon.ico`).
- **After:** each page logs **0 messages**, and both `/favicon.ico`
  (`image/x-icon`) and `/static/favicon.svg` return 200.
- **Sliders:** real mouse drags (`Input.dispatchMouseEvent`) on both maps
  at 1440x1080 and 375x812 - full range, partial and back - agreed with a
  fresh API response at every stop. 0 of 5,311 colors mismatched, and
  each run logged 0 console messages.

---

## 2026-10-18 — Taller maps on a normally scrolling page; the map no longer traps the scroll

**Change (webapp only; shared CSS plus one new shared script).** No data,
API, caching or slider logic changed; `date-slider.js` is untouched.

**Layout (`map.css`):**
- **Page scroll:** the page scrolls like a normal page. Gone: the
  one-screen layout, the 45vh notes box that scrolled on its own, and the
  sticky slider. Order: header, map (legend beside it on desktop), slider,
  notes.
- **Map height:** `clamp(420px, 100dvh - 200px, 900px)`, with `vh` lines
  as the fallback for browsers without `dvh`. The 200px keeps the header,
  the slider and the top of the notes on screen with the map.
  - **Not `70dvh`:** that was the suggested figure, but it would have made
    the shortage map *shorter* than before on desktop (844 -> 756px at
    1920x1080, 647 -> 630px at 1440x900), because that page's notes panel
    was short.
  - **What actually needs to stay on screen** below the map is roughly
    fixed (header + slider), so the height is the screen minus a fixed
    reserve, not a fraction of it.
- **Short screens** (`max-height: 540px`, e.g. a phone in landscape): the
  map is `100dvh - 120px`, at least 240px, so it fits on screen with the
  slider. This rule meets the main one at 420px when the screen is 540px
  tall.
- **Legend:** desktop keeps it beside the map. The legend column is the
  map's height and scrolls within it, as before. At 800px wide or less,
  it goes below the slider (as before), not between the map and the
  slider: on the shortage page the legend and list are most of a screen
  tall, and putting them first would push the slider a screen away from
  the map.
- **Header:** the gap between wrapped header rows is 4px (was 12px). This
  only matters on phones, where the header wraps. It's what lets the
  pharmacy page's slider fit on screen at 667x375.
- **Extra fix:** popup content is capped at the screen width minus 64px.
  Leaflet's 300px cap plus padding made popups 352px wide, wider than a
  320px phone's map, so they were clipped 16px on each side whatever the
  pan. This predates the change; screens 375px and up are unaffected.

**Gestures (`webapp/static/js/map-gestures.js`, loaded by both map pages;
each page calls `makeMapScrollFriendly(map)` once).** Plain Leaflet 1.9,
no plugin. I considered Leaflet.GestureHandling, the usual plugin for
this, but Leaflet's own handlers already do what's needed.
- **Desktop wheel:** a wheel or trackpad scroll over the map scrolls the
  page, and Ctrl/Cmd + wheel zooms the map.
  - A trackpad pinch also zooms, since browsers send it as Ctrl + wheel.
  - A capture-phase listener on the map container stops unmodified wheel
    events before they reach Leaflet's wheel-zoom listener. Nothing
    cancels them, so the browser scrolls the page.
  - Leaflet's own wheel zoom (smoothing, pinch) is kept for the modified
    events, and it cancels them, so the browser doesn't zoom the page.
  - A hint, "Use ⌘ + scroll to zoom the map" ("Ctrl" off Apple
    platforms), shows for 1.5s.
  - **Why not "click the map to enable wheel zoom":** after any click,
    such as opening a popup, the map would trap the page scroll again,
    and nothing would show it was armed.
  - Mouse drag, the +/- buttons and the keyboard work as before.
- **Touch** (`pointer: coarse`, i.e. phones and tablets): one finger
  scrolls the page, and two fingers pan and pinch-zoom the map.
  - This turns off Leaflet's one-finger dragging. Leaflet's own CSS then
    gives the map `touch-action: pan-x pan-y`, so the browser scrolls the
    page.
  - Leaflet's two-finger handler (`touchZoom`) both zooms and pans, so no
    custom touch code is needed.
  - The first one-finger swipe per page load shows "Use two fingers to
    move the map" for 2s.
  - A mouse-first device keeps one-finger/mouse dragging. The check
    re-runs if the primary input changes.
- **Slider:** `touch-action: pan-y` on the range input. A sideways finger
  drag moves the slider and never the page. A vertical swipe that starts
  on it still scrolls the page.
- **Why a new file rather than `date-slider.js`:** the gestures belong to
  the map, not the slider. Both pages load the same file, so there is
  still one implementation.

**Measured** in headless Chrome with real input events through Chrome's
input pipeline (`Input.dispatchMouseEvent` and `dispatchTouchEvent`,
`synthesizeScrollGesture` / `synthesizePinchGesture` with touch
emulation). Before = the live site, old layout. After = the new layout,
tested locally.

| Size | Map, pharmacy (before -> after) | Map, shortage (before -> after) | Slider visible without scrolling | Horizontal overflow |
|---|---|---|---|---|
| 1920x1080 | 1620x688 -> 1620x880 | 1620x844 -> 1620x880 | yes -> yes | none -> none |
| 1440x900 | 1140x473 -> 1140x700 | 1140x647 -> 1140x700 | yes -> yes | none -> none |
| 1280x720 | 980x351 -> 980x520 | 980x467 -> 980x520 | yes -> yes | none -> none |
| 768x1024 (touch) | 768x563 -> 768x824 | 768x563 -> 768x824 | yes -> yes | none -> none |
| 375x812 (touch) | 375x447 -> 375x612 | 375x447 -> 375x612 | yes -> yes | none -> none |
| 667x375 (touch) | 667x300 -> 667x255 | 667x300 -> 667x255 | **no -> yes** | none -> none |

- **667x375:** the map is shorter on purpose. Before, its 300px minimum
  put the map's bottom edge and the slider below the fold; now the whole
  map and the slider fit on screen together.
- **What scrolls** (same on both maps at every size):

| Input over the map | Before | After |
|---|---|---|
| Mouse wheel (desktop sizes) | zoomed the map out a level; the page never scrolled | page scrolls by all it can (e.g. 227 of 227px, pharmacy at 1440x900); map zoom unchanged; event not cancelled; hint shown |
| Ctrl + wheel / Cmd + wheel | zoomed | zooms in a level; event cancelled (no browser page zoom) |
| Mouse drag / + button | pans / zooms | pans 109px / zooms (unchanged) |
| One-finger swipe (touch sizes) | panned the map ~215px; page didn't move | page scrolls ~200px; map moves 0px; hint shown |
| Two-finger drag | panned the map 85px | pans the map 85-86px; page doesn't move |
| Two-finger pinch | zoomed in a level | zooms in a level; page zoom stays 1 |
| Finger drag along the slider | moved it; page scroll 0 | moves it; page scroll 0 vertical, 0 horizontal |
| Vertical swipe starting on the slider | scrolled the page ~120px | scrolls the page ~120px |

**Other checks on the new layout:**
- **Popups:** a popup opened with its anchor 12px from each of the four
  map edges, at all six sizes on both maps, opens fully visible (0px
  clipped). Leaflet's size matches the container everywhere, so the
  ResizeObserver fix still holds.
- **Sliders:** real mouse drags across the full range, partial and back,
  at all six sizes on both maps (12 runs). Every stop agrees with a fresh
  API response, with 0 color mismatches on the shortage map.
- **Console:** 0 messages on all three pages.

**Known gaps:**
- **Touch hardware:** touch was tested only through Chrome's touch
  emulation, not on a phone (see "Current state").
- **The slider jumps where you touch it (Chrome):** Chrome's native range
  input moves the thumb to the point a finger first touches. So on Chrome
  phones, a vertical swipe that starts on the slider track scrolls the
  page but also changes the date. Seen at 375 and 667 wide, identically
  before and after this change. It's built-in browser behavior, and
  avoiding it would mean changing the slider's logic, so it's left as is.
- **`dvh` on a real phone:** it follows the browser toolbar as it hides
  and shows. On a real phone the map may grow or shrink by the toolbar's
  height (~50px) once as you scroll. If that is distracting, `svh`
  instead of `dvh` fixes it at the cost of a slightly shorter map once
  the toolbar hides.
