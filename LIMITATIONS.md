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

**Why not:** to give the timeline slider any depth before today, we
reconstructed history from what current records happen to carry. Only 3
distinct shortages in the entire dataset have both a confirmed start and
a confirmed end date (drugs marked "Resolved," with fewer than two dozen
total). Everything else that has historical depth — 231 other shortages —
is still ongoing, so we can only say "known active since its posting
date," not "active for exactly this duration."

**What this means concretely:** the slider's shortage range reaches back
to 2012, but **most of that depth is the open-ended tier, not a confirmed
start-to-finish period.** For the 3 resolved drugs, the active window
shown is real and bounded. For the other 231, the start date is real but
the "still active" status just reflects "as of our last data pull" — if
one of those shortages actually ended at some point without openFDA's
current snapshot reflecting it (or a shortage was resolved and later
dropped from the dataset entirely before we ever captured it), that
window would be wrong and we'd have no way to know.

**What would actually close this gap:** running the forward daily
snapshot job continuously from today onward. Every day that passes adds
one day of genuinely observed data instead of reconstructed data, so this
gap only ever shrinks relative to the total slider range, never grows.

---

## The pharmacy timeline can only show growth, never closures

**What this tool actually checks:** the pharmacy layer's historical view
is built from each NPI's `enumeration_date` — when it was first
registered with the federal government. A pharmacy location "counts" as
existing as of a given past date if it was already registered by then.

**Why not:** NPPES's public API does not expose deactivation dates (see
the earlier "we have not validated against WA licensing records" entry —
this is the same underlying gap showing up again). We can see when a
pharmacy first appears in the federal registry. We cannot see when one
closes. That means this backfill is structurally one-directional: it can
only add locations as you move forward in time, never remove them.

**What this means concretely:** **historical pharmacy counts from this
tool will always be a floor, not an accurate count** — every past date
will show at least as many pharmacies as actually existed, and any
pharmacy that closed before today will still appear as "present" on every
date up through today. On top of that directional bias, the earliest
part of the timeline has a separate, specific problem: **49% of WA
pharmacy records show a 2006 enumeration date, and 80% of those cluster
in a single four-month window (May–August 2006).** That lines up with the
federal NPI system's mandatory-registration rollout, not with when those
pharmacies actually opened. A pharmacy that had already been open for
twenty years by 2006 shows up in this data exactly the same way as one
that opened that same week. **Treat any date before roughly 2008 as "this
many pharmacies already existed by the registration deadline," not as a
real growth trend** — the actual growth signal only becomes meaningful
after the registration rollout settled down.

**What would actually close this gap:** there is no available fix for the
closure-blindness from NPPES data alone — it would require the same kind
of state-level licensing cross-check described in the WA DOH limitation
above, applied historically rather than just to current records. The
forward daily snapshot job (shared with the shortage layer) at least
ensures that from today onward, real openings *and* closures the dataset
happens to reflect are captured with accurate dates, rather than compounding
the growth-only bias indefinitely.

---

## The pharmacy desert "low income" cutoff uses a self-computed proxy, not HUD's official income limits

**What this tool actually checks:** a tract counts as low-income if its
median household income is below 80% of its county's Area Median Income
(AMI) - the same 80%-of-AMI rule HUD uses across federal
housing/community-development programs.

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
