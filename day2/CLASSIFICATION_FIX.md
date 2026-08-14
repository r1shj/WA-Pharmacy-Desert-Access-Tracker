# Classification precedence fix

## Root cause

`classify()` checked the primary-code rule tables (`RULES`,
`NON_PHARMACY_FALSE_POSITIVES`) before checking whether the record had a
pharmacy taxonomy anywhere else on it. A record whose *primary* taxonomy
matched a definitive rule (e.g. `military`, or a DME/lab/naturopath false
positive) got that classification immediately and never reached the
"has a pharmacy taxonomy somewhere" fallback — even when a *secondary*
taxonomy entry was genuinely pharmacy-related.

## Fix

Inserted a check directly after the Bartell name-override and before the
`RULES`/`NON_PHARMACY_FALSE_POSITIVES` lookups: if the record has a
pharmacy taxonomy (`3336*`) anywhere in its taxonomy list but the *primary*
code isn't itself one, return `unclassified_has_pharmacy_taxonomy` (REVIEW)
immediately, regardless of what the primary code's own rule would have
said. Primary-code rules now only get the final word when no pharmacy
taxonomy is hiding as a secondary entry.

## Result of rerunning on the full 1,941-row dataset

All 42 secondary-taxonomy records (confirmed by rebuilding the secondary-only
set fresh from the raw data, not reusing the earlier count) now land in
`unclassified_has_pharmacy_taxonomy` / REVIEW — up from 18 before the fix.

| | before fix | after fix | change |
|---|---|---|---|
| Included | 1,363 | 1,363 | no change |
| Excluded (definitive) | 128 | 104 | -24 |
| Review | 450 | 474 | +24 |
| Total | 1,941 | 1,941 | — |

**Included/excluded counts don't change** — all 24 affected records were
already `included=False` before the fix (as `non_pharmacy` or `military`);
the fix only moves them from "definitively excluded" to "flagged for
human review," which is the correct behavior since their pharmacy status
is genuinely ambiguous (DME supplier with a secondary pharmacy taxonomy,
etc.) rather than a confident negative.

## Regression checks

- **Bartell Drugs**: still 65 total, 55 `community_retail`/included
  (including the 5 name-marker-recovered miscoded ones), 10 `unspecified`
  under REVIEW — identical to before the fix. The Bartell override runs
  before the new secondary-taxonomy check, so it's unaffected.
- **Duplicates**: 1,941 rows, 1,941 unique NPIs, zero duplicates.
