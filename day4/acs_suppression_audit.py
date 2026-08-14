"""
Day 4, part 2: scan the full 1,784-tract WA ACS pull (from Day 1) for
Census suppression/missing-data sentinels before any income math happens
downstream. Confirmed empirically (not assumed) which sentinel values
actually appear in this specific pull - see DECISIONS.md.

Suppressed values are NEVER coerced to 0 or dropped from the table -
every tract stays in the output, flagged instead, so population-based
analysis (which doesn't depend on income) isn't collateral damage from an
income suppression.
"""
import csv
import json
import os

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(OUT_DIR, "..")

# All known ACS sentinel codes for suppressed/inapplicable estimates,
# not just the one we happened to find, in case a future pull surfaces
# others.
ACS_SENTINELS = {-666666666, -222222222, -333333333, -444444444, -555555555,
                  -888888888, -999999999}


if __name__ == "__main__":
    data = json.load(open(os.path.join(PROJECT_ROOT, "acs_sample_raw.json")))
    header, rows = data[0], data[1:]
    idx = {name: i for i, name in enumerate(header)}

    out_rows = []
    income_suppressed_count = 0
    population_missing_count = 0
    sentinel_values_seen = {}

    for r in rows:
        income_raw = int(r[idx["B19013_001E"]])
        pop_raw = int(r[idx["B01003_001E"]])
        tract_geoid = f"{r[idx['state']]}{r[idx['county']]}{r[idx['tract']]}"

        income_suppressed = income_raw in ACS_SENTINELS
        population_missing = pop_raw in ACS_SENTINELS

        if income_suppressed:
            income_suppressed_count += 1
            sentinel_values_seen[income_raw] = sentinel_values_seen.get(income_raw, 0) + 1
        if population_missing:
            population_missing_count += 1

        out_rows.append({
            "tract_geoid": tract_geoid,
            "NAME": r[idx["NAME"]],
            "median_household_income": "" if income_suppressed else income_raw,
            "population": "" if population_missing else pop_raw,
            "income_suppressed": income_suppressed,
            "population_missing": population_missing,
            "excluded_from_income_classification": income_suppressed,
        })

    out_path = os.path.join(OUT_DIR, "acs_wa_tracts_audited.csv")
    fieldnames = ["tract_geoid", "NAME", "median_household_income", "population",
                  "income_suppressed", "population_missing", "excluded_from_income_classification"]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"Total WA tracts: {len(rows)}")
    print(f"Wrote {out_path}")
    print()
    print(f"income_suppressed: {income_suppressed_count} tracts ({income_suppressed_count/len(rows)*100:.1f}%)")
    print(f"  sentinel values found: {sentinel_values_seen}")
    print(f"population_missing: {population_missing_count} tracts ({population_missing_count/len(rows)*100:.1f}%)")
    print(f"excluded_from_income_classification: {income_suppressed_count} tracts "
          f"(same as income_suppressed - these tracts still appear in the table with population intact, "
          f"just excluded from any analysis keyed on income)")
