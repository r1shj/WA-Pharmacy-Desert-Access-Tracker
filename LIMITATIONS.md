# Known limitations

This file documents gaps in the data and methodology that a user of this
tool should understand. It's written to be dropped directly into the
project README's limitations section once one exists.

---

## We have not validated pharmacies against Washington State's own licensing records

**What this tool actually checks:** every pharmacy in this dataset comes
from NPPES (the federal National Plan and Provider Enumeration System).
A pharmacy is included if it has an "Active" NPI record. We have **not**
cross-checked any of these pharmacies against Washington State's own
pharmacy licensing data.

**Why not:** we looked for a way to do this and hit a real wall.
Washington DOH's only *downloadable* open dataset covers individual
practitioner credentials — pharmacists, pharmacy technicians, pharmacy
assistants — not pharmacy businesses/facilities. The facility-level
license lookup that would actually tell us "is this pharmacy currently
licensed to operate" only exists as an interactive search tool
(the HELMS "Facility and Services Search"), and that tool is protected by
a reCAPTCHA. We did not attempt to automate around it, and a one-off
manual check of 30-50 pharmacies through that interface was scoped but not
carried out.

**What this means concretely:** an "included" pharmacy in this dataset
has an active federal provider ID, which is a real but limited signal.
NPPES's "active" status only means nobody has told the federal government
the pharmacy died, disbanded, or committed fraud — it is not proof the
pharmacy is currently open, licensed, or operating. **Some unknown
fraction of the pharmacies marked `included_in_access_analysis=TRUE` in
this dataset could be closed, relocated, or have lost their state license,
and this tool would not currently catch that.** We don't have a number for
how large that fraction is — that's exactly the gap.

**The one imperfect proxy we do have:** each NPPES record carries a
`last_updated` date. As of the Day 2 pull, 82 of 1,200 sampled records
(6.8%) hadn't been touched since before 2015 — over a decade with no
registration activity. This is a weak "maybe look closer here" flag, not
evidence of closure. A pharmacy can legitimately go a decade without
touching its federal registration; conversely, a closed pharmacy's record
can sit untouched for years without anyone ever formally deactivating it.
Treat this as a hint for prioritizing manual review, not as a validation
signal.

**What would actually close this gap:**
- A human manually spot-checking a sample of pharmacies through the HELMS
  UI (solving the CAPTCHA themselves, since that's not something we
  automate around)
- A formal public-records request to WA DOH for a facility-license data
  extract, which would allow a real bulk cross-check instead of a manual
  sample

Until one of those happens, treat every "included" pharmacy in this
dataset as "registered with the federal government, not confirmed
currently open."

---

## We do not know which pharmacies are independently owned

**What this tool actually checks:** every in-scope pharmacy is checked
against a lookup table of known chain, health-system, and government/
tribal names, plus a secondary signal (the same corporate officer signing
for 3+ locations). If neither turns up a match, the pharmacy's ownership
is recorded as `unknown` — not as independent.

**Why not:** matching "independent" reliably would require either a
maintained, complete list of every chain/franchise operating in
Washington (we don't have one, and no such list is likely ever fully
complete) or an external source that positively confirms single-location
ownership (which we don't have — see the DOH gap above). Absence of a
chain match is not the same thing as proof of independence, so we don't
treat it that way.

**What this means concretely:** of the 1,837 pharmacies in scope for the
access analysis, **392 (21.3%) have `ownership_category=unknown`**. Most
of these are probably independent pharmacies in real life — but "probably"
isn't something we're willing to assert as data. **Do not read the
`independent_confirmed` count (15) as "the number of independent
pharmacies in Washington."** It reflects only the pharmacies where we
found positive evidence of independent ownership — specifically, DBA
branding under a franchise program (Health Mart, Medicine Shoppe, Good
Neighbor Pharmacy) that by definition means the location is individually
owned rather than corporately owned. Everything else that might be
independent, including probably most of the 392 `unknown` records, simply
isn't counted as either chain or independent.

**What would actually close this gap:** cross-referencing against a
business-ownership registry (e.g. WA Secretary of State corporate
filings) or a pharmacy trade-association membership list (e.g. NCPA) that
positively identifies single-location ownership, rather than inferring it
from the absence of a chain match.

---

## Physical-location counts are a conservative floor, not a final count

**What this tool actually checks:** pharmacies sharing a normalized
street address are only merged into one `physical_location_id` when their
name/DBA is a close match *and* they share the same pharmacy type. Records
that share an address but don't clear that bar are kept as separate
locations and flagged `manual_review_required` instead of being merged or
dropped.

**Why not:** we found real cases in this dataset where merging on address
alone would have been wrong — e.g. a hospital campus running an inpatient
pharmacy, an outpatient clinic pharmacy, and an infusion pharmacy under
one street address, which are three genuinely different services, not one
location registered three times. Rather than guess, ambiguous cases are
left unresolved and flagged for a human to look at.

**What this means concretely:** of 1,941 total NPIs, the dedup pass
produced **1,811 `physical_location_id`s, with 319 NPIs flagged
`manual_review_required`**. The 1,811 figure is a conservative,
auto-resolved subset — not a confirmed final count of how many physical
pharmacy locations exist in Washington. The true number of distinct
physical locations is somewhere at or below 1,941 and likely at or above
1,811, with the 319 flagged records being exactly where that number is
still uncertain.

**What would actually close this gap:** manually reviewing the flagged
records (a few hundred, not thousands — tractable for a human pass), or
geocoding to lat/lon and using physical coordinate proximity as an
additional signal alongside the name/type match already in place.

---

## The national shortage timeline is mostly reconstructed, not observed history

**What this tool actually checks:** the shortage layer comes from
openFDA's drug shortages data, which only returns current-state records —
each drug's latest known status (Current, To Be Discontinued, or
Resolved) plus the date it was first posted. We checked openFDA's own
bulk-download files directly and confirmed they contain the exact same
1,614 records as the live API, refreshed daily — it's the same snapshot
in a different format, not a separate historical archive.

**Why not:** the timeline has two very different halves. **Before
2026-07-18** it is reconstructed from what a single pull of current
records happened to carry: a posting date, and an end date only for
shortages already marked "Resolved." **From 2026-07-18 on** the feed has
been captured daily, so a shortage leaving the feed or changing status is
seen within a day (except on 4 days in Aug-Oct 2026 when the collecting
machine was off).

**What this means concretely:** the slider reaches back to 2012, but
**most of that depth is the open-ended tier, not a confirmed
start-to-finish period** — a shortage posted in 2015 and still listed is
shown as active the whole time, though it may have lapsed and returned in
between. An end date means one of two things, and the map never mixes
them up:
- **Confirmed resolved** — FDA marked it Resolved.
- **Last listed by FDA** — it left openFDA's feed without being marked
  Resolved. That is not confirmation the shortage ended. In the first
  three months of daily observation, every one of these (35) was a
  "To Be Discontinued" notice that left the feed about a year after
  posting — the product was discontinued, which is the opposite of
  resolved. Once FDA stops listing such a product, it also stops counting
  toward the vulnerability score's shortage exposure, even though the
  product remains unavailable from that manufacturer.

Shortages that were resolved and dropped from openFDA before 2026-07-18
are gone from the record entirely; nothing here can recover them.

**What would actually close this gap:** for the past, nothing available —
openFDA keeps no history. Going forward, the daily job (now on GitHub
Actions, so it no longer depends on any one machine being on) keeps
adding observed days, so the reconstructed share of the timeline shrinks
every day and never grows.

---

## The pharmacy timeline before 2026-10-15 can only show growth, and closures after it show up only if the registry records them

The pharmacy slider has two halves with different weaknesses.

**Before the first observed snapshot (2026-07-18): reconstructed from
registration dates.** Each NPI's `enumeration_date` is when it was first
registered with the federal government; a location counts as existing on
a past date if it was registered by then. NPPES's public API exposes no
deactivation dates (the same gap as the WA licensing entry above), so
this half can only add locations as time moves forward, never remove
them. It is biased in **two opposite directions at once**, so past counts
are neither a floor nor a ceiling:

- **Overcount:** a pharmacy that closed but never deactivated its NPI
  appears present on every date after it registered.
- **Undercount:** the API only serves *active* NPIs, so a pharmacy that
  closed *and* deactivated before the July 2026 pull isn't in the dataset
  at all - it's missing from every past date it actually existed on.

(An earlier version of this entry called past counts "a floor"; that
ignored the undercount and was wrong.)

The earliest years have a separate problem: **49% of WA pharmacy records
show a 2006 enumeration date, and 80% of those cluster in a single
four-month window (May–August 2006)**, matching the NPI system's
mandatory-registration rollout rather than real openings. **Treat any
date before roughly 2008 as "this many pharmacies already existed by the
registration deadline," not as a growth trend.**

**From 2026-10-15: observed daily, but only as well as NPPES records
closures.** A GitHub Actions job re-sweeps the full registry every day
(`jobs/pharmacy_sync.py`) and a location drops off the map once none of
its NPIs are active. Between 2026-07-18 and 2026-10-15 there are no
observations at all (the earlier local job saved copies of a static file
and observed nothing - DECISIONS.md 2026-10-15), so those dates show the
2026-07-18 state, labelled as such. Remaining gaps:

- **Closures lag or never appear.** Pharmacies often don't deactivate
  promptly when they close. The first real sweep found **zero**
  deactivations among the 1,941 known NPIs after three months, while
  finding 11 new registrations and 154 updated records - so the sweep is
  live; the registry is simply slow to record closures.
- **New pharmacies don't appear on the map automatically.** New NPIs go
  to `npi_review_queue` (11 on the first run) because they need type and
  ownership classification, address dedup and geocoding first. Until
  someone works the queue, the map undercounts openings since July 2026.
- **A relocated NPI is dropped from its old location and not added at
  its new one** (it's listed in that day's `snapshot_runs` details).
- **A failed or aborted day has no snapshot**; the map shows the most
  recent earlier one and says so.

**What would actually close this gap:** for closures, the same state
licensing cross-check described in the WA DOH entry. For openings,
working the review queue through the Day 2-4 classification and
geocoding steps.

---

## The pharmacy desert "low income" cutoff uses a self-computed proxy, not HUD's official income limits

**What this tool actually checks:** a tract counts as low-income if its
median household income (ACS 2022 5-year) is below 80% of its county's
Area Median Income (AMI) - the same 80%-of-AMI rule HUD uses across
federal housing/community-development programs. Income is classified at
the tract level; each block group takes its parent tract's status.

**Why not the real HUD figures:** we tried to fetch HUD's official
published county AMI data directly and could not get a working download
in this session - candidate URLs either didn't exist or returned empty
placeholder responses rather than real data. Instead, we compute a proxy
AMI per county: the population-weighted average of median household
income across that county's own (non-suppressed) census tracts.

**What this means concretely:** the 80% threshold itself is a
well-established standard, but the number it's being compared against is
**not** HUD's real number. HUD's actual AMI uses family income (a
different concept from household income) and its own methodology, not a
simple average of ACS tract data. Some tracts near the edge of the 80%
cutoff could be classified differently under HUD's real figures than
under this proxy. Treat `income_status` as a reasonable, transparent
approximation - not a number you could use to determine actual program
eligibility.

**What would actually close this gap:** obtaining HUD's official Income
Limits dataset (huduser.gov) through a working download and substituting
the real county AMI figures for the proxy.

---

## Pharmacy desert distances are straight-line, not travel distances

**What this tool actually checks:** `nearest_pharmacy_miles` is the
straight-line ("as the crow flies") distance between where people
actually live in a block group (the population-weighted centroid) and
the nearest pharmacy counted in this analysis.

**Why not travel distance:** computing real road-network distance or
drive time requires a routing engine and road network data, which is
explicitly out of scope for this pass (a documented future improvement,
not attempted now).

**What this means concretely:** straight-line distance systematically
*understates* how far someone actually has to travel, especially across
water (the Columbia River gorge counties, Puget Sound islands) or
mountainous terrain (the Cascades) - all directly relevant to Washington.
A block group could show as "1.2 miles from a pharmacy" by straight-line
distance while the real drive is considerably longer if a river, strait,
or mountain pass is in the way. **Every distance figure and the
`pharmacy_desert_status` classification itself should be read as
"geographic proximity," not confirmed travel access.**

**What would actually close this gap:** road-network routing (e.g. via
OSRM, Valhalla, or a commercial routing API) between the same
population-weighted centroids and pharmacy locations already computed
here.

---

## Border-buffer pharmacies fix a real gap but don't cover the whole neighboring states

**What this tool actually checks:** to avoid falsely flagging WA border
areas as pharmacy deserts just because we didn't look across the state
line, we pulled and geocoded pharmacies in every Oregon/Idaho ZIP code
within 20 miles of the WA border, and include those (and only those)
locations when computing how far a WA block group is from its nearest
pharmacy.

**Why a 20-mile buffer specifically:** chosen to comfortably cover the
1-mile urban / 10-mile rural access thresholds used elsewhere in this
classification, with margin. It is not based on any specific commuting
or travel-shed study for these particular border communities.

**What this means concretely:** this fixes the specific, verified
problem it was built for (confirmed several real Klickitat/Benton/
Wahkiakum County block groups would have been misclassified without it -
see DECISIONS.md). But it only covers pharmacies within that 20-mile
strip. A WA border resident whose closest real pharmacy happens to be
slightly further than 20 miles into Oregon or Idaho (unlikely given the
threshold distances involved, but not impossible in very sparse areas)
would still not have that pharmacy counted. Also, Canada is not covered
at all - any WA resident near the northern border whose nearest real
option is across that border is not accounted for here.

**What would actually close this gap:** widening the buffer if a specific
uncovered case is found, or adding a similar buffer against the Canadian
border for northern WA counties.

---

## The daily data depends on two free-tier services that can quietly stop

**What can stop it:**

- **GitHub disables scheduled workflows in a public repository after 60
  days with no repository activity.** The daily job doesn't commit
  anything, so it doesn't count as activity. Two months without a push
  means the snapshots silently stop (GitHub emails the owner when it
  disables the schedule).
- **Supabase's free tier pauses a project after a week of inactivity.**
  The daily job's writes count as activity, so the two keep each other
  alive. But once the GitHub schedule is disabled, the database pauses a
  week later and the live site's maps stop loading until it's resumed in
  the Supabase dashboard.

GitHub's scheduler is also best-effort: it can delay or drop a scheduled
run, and the very first slot after the workflow was added (2026-10-16)
never fired. The job therefore runs twice a day (14:17 and 20:43 UTC).
A day is lost only if both runs are dropped or fail (an API outage, or a
safeguard refusing suspicious data). A failed run turns the workflow red,
and every run, successful or not, is logged in `snapshot_runs`. Missed
days can't be recovered later - neither openFDA nor NPPES serves past
states. The site keeps the data in memory and reloads it every 5 minutes, so a
new snapshot can take up to 5 minutes to appear after a run.

**What would close this gap:** any push to the repository resets
GitHub's 60-day clock, and re-enabling the workflow in the Actions tab
restores it. A paid Supabase tier doesn't pause.

---

## The shortage factor shifts the whole vulnerability map uniformly; it can't change which places look most vulnerable

**History:** until 2026-10-16 the map colored block groups by the
low/medium/high band, and **no block group ever changed color as the
shortage slider moved** (found while testing the live site). Access and
income are each worth 0 or 40, so before shortages every complete score
is 0, 40 or 80. Shortage points add at most 20, and the band cutoffs at
33 and 66 fall in the gaps. "High" was exactly the 237 pharmacy deserts.
**Fixed** by coloring on the continuous 0-100 score instead (DECISIONS.md
2026-10-16): the shade now moves with the slider. For example, the
lightest group goes from `#d4e5f9` at 1 shortage point (2017-10-28) to
`#b4d2f5` at 14 points (2026-10-16).

**What's still true:** shortage points are one statewide number, so they
darken or lighten *every* block group by the same amount. The map's
spatial pattern - which places look more vulnerable than others - comes
entirely from access and income, and the shortage factor moves shades by
at most 20 of 100 points. The low/medium/high labels in the popups still
can't change with the slider, for the arithmetic reason above. This
follows from the source data (openFDA has no sub-state geography), not
from the color choice.

**What would close it:** a shortage measure that varies by place, which
no public source provides (see the "doesn't know what's in stock" notes),
or re-weighting so shortage points can cross a band boundary. Either is a
methodology change to register in DECISIONS.md first.

---

## The desert count depends on review-bucket pharmacies that aren't counted yet: 176 to 237 block groups

**What this tool actually checks:** distance to the nearest pharmacy
counts only locations with at least one pharmacy confirmed as walk-in
(`included_in_access_analysis = TRUE`): 1,177 WA locations plus 334
geocoded OR/ID border locations. The 447 geocoded WA locations whose
pharmacies are all still in the REVIEW bucket (walk-in status unknown)
are shown on the map with a warning outline, but they are **not** used
when measuring distance.

**What this means concretely:** measured 2026-10-16, **61 of the 237
desert block groups (91,478 of 346,334 residents) lie within their
1-mile or 10-mile threshold of a REVIEW-only location.** If those
locations turn out to be walk-in pharmacies, those 61 block groups are
not deserts. Counting REVIEW locations can only shorten distances, so
under this method **the desert count is somewhere between 176 and 237
block groups (about 255,000 to 346,000 residents)**. 237 is the
conservative upper end. Most REVIEW records carry NPPES's generic
"Pharmacy" taxonomy code (413 of 474), which includes real grocery-store
pharmacies (e.g. Haggen stores), so the true figure is plausibly below
237. The 176 block groups not near any REVIEW location are robust to
this question.

**What would actually close this gap:** resolving the REVIEW bucket -
confirming walk-in status for those 474 records (store type, hours,
DBA) - then recomputing distances.
