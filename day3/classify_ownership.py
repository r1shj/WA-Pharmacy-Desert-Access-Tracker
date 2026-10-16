"""
Day 3, part 1: ownership classification.

Applies chain_lookup.py patterns against DBA (other_names) and
organization_name first. Where no name pattern matches, falls back to the
Day 1 "shared authorized official across many NPIs" signal as a weaker,
medium-confidence chain indicator. Everything else stays "unknown" -
absence of a match is never treated as evidence of independence (see
DECISIONS.md, 2026-07-18 entry: "Unmatched != independent").

Only records in scope for the access analysis (included=True or
flagged REVIEW) get a real classification attempt; definitively-excluded
records (long_term_care, mail_order, etc.) are marked not_applicable and
passed through untouched.
"""
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, OUT_DIR)
from chain_lookup import (  # noqa: E402
    CHAIN_PATTERNS,
    HEALTH_SYSTEM_PATTERNS,
    HEALTH_SYSTEM_GENERIC_FALLBACK_PATTERNS,
    GOVERNMENT_TRIBAL_PATTERNS,
    INDEPENDENT_FRANCHISE_PATTERNS,
)

DAY2_DIR = os.path.join(OUT_DIR, "..", "day2")

# A shared authorized official across this many or more distinct NPIs is
# treated as a medium-confidence chain signal when no DBA/org-name pattern
# matched. Set >1 deliberately: two locations sharing an official name is
# too easily a common-name coincidence (e.g. "JOHN SMITH") to trust alone;
# three or more sharing the exact same first+last name is a much stronger
# signal, consistent with the Day 1 example (one official across 15+
# Albertsons-family locations). See DECISIONS.md.
AUTH_OFFICIAL_CHAIN_THRESHOLD = 3
SHARED_SIGNER_LABEL = "Likely chain: several locations share a registered signer"


def normalize_text(org_name, dba):
    return re.sub(r"[^A-Z0-9' ]", " ", f"{dba or ''} {org_name or ''}".upper())


def match_patterns(text, patterns):
    for regex, parent in patterns:
        if regex.search(text):
            return parent
    return None


def _try_all_categories(text):
    parent = match_patterns(text, CHAIN_PATTERNS)
    if parent:
        return ("chain", parent, "high", "dba_name_match")
    parent = match_patterns(text, HEALTH_SYSTEM_PATTERNS)
    if parent:
        return ("health_system", parent, "high", "dba_name_match")
    parent = match_patterns(text, GOVERNMENT_TRIBAL_PATTERNS)
    if parent:
        return ("government_or_tribal", parent, "high", "dba_name_match")
    parent = match_patterns(text, INDEPENDENT_FRANCHISE_PATTERNS)
    if parent:
        return ("independent_confirmed", parent, "medium", "franchise_brand_match")
    return None


def classify_by_name(org_name, dba):
    # Three tiers, checked in order. Fixes a real mislabeling found while
    # spot-checking Day 5 (some Albertsons-family stores are legally
    # registered under a DIFFERENT banner's entity than the one painted on
    # the door - e.g. organization_name="SAFEWAY INC" for a location whose
    # dba_name is "HAGGEN PHARMACY #3498") WITHOUT reintroducing a second
    # bug that a DBA-always-wins-outright version of this fix caused: for
    # two Yakima Valley Farm Workers Clinic records, the DBA
    # ("Unify Community Health...") only carries the generic
    # "community health" signal, while the specific identifying text
    # ("Farm Workers") lives in organization_name. Neither field is
    # universally more trustworthy - it depends on the record - so:
    #   1. DBA alone, against the SPECIFIC patterns only.
    #   2. Combined dba+org text, against the SPECIFIC patterns only.
    #   3. DBA alone, then combined text, against the generic
    #      catch-all fallback (currently only HEALTH_SYSTEM's
    #      "COMMUNITY HEALTH"). Only reached once no specific pattern
    #      matched either field.
    dba_only_text = normalize_text("", dba)
    result = _try_all_categories(dba_only_text)
    if result:
        return result
    combined_text = normalize_text(org_name, dba)
    result = _try_all_categories(combined_text)
    if result:
        return result
    for text in (dba_only_text, combined_text):
        parent = match_patterns(text, HEALTH_SYSTEM_GENERIC_FALLBACK_PATTERNS)
        if parent:
            return ("health_system", parent, "high", "dba_name_match")
    return None


if __name__ == "__main__":
    with open(os.path.join(DAY2_DIR, "wa_pharmacies_final.csv")) as f:
        final_rows = list(csv.DictReader(f))
    with open(os.path.join(DAY2_DIR, "wa_pharmacies_true_location_raw.json")) as f:
        raw_by_npi = {r["number"]: r for r in json.load(f)}

    def in_scope(row):
        return row["included_in_access_analysis"] == "True" or row["walk_in_access"] == "unknown"

    scope_rows = [r for r in final_rows if in_scope(r)]

    # Pass 1: name-based classification, and collect authorized_official
    # for every record that DIDN'T match a name pattern, so we can measure
    # repetition among only the unmatched ones.
    name_results = {}
    unmatched_official = defaultdict(list)  # (first,last) -> [npi,...]
    for row in scope_rows:
        result = classify_by_name(row["organization_name"], row["other_names"])
        if result:
            name_results[row["npi"]] = result
        else:
            raw = raw_by_npi.get(row["npi"], {})
            basic = raw.get("basic", {})
            official = (basic.get("authorized_official_first_name", "") or "",
                        basic.get("authorized_official_last_name", "") or "")
            if official != ("", ""):
                unmatched_official[official].append(row["npi"])

    # Pass 2: apply the authorized-official repetition fallback. The
    # signer's name is used only to group NPIs here and is never written
    # out (DECISIONS.md 2026-10-16) - the output keeps a generic label and
    # the group size.
    final_results = {npi: r + ("",) for npi, r in name_results.items()}
    for official, npis in unmatched_official.items():
        if len(npis) >= AUTH_OFFICIAL_CHAIN_THRESHOLD:
            for npi in npis:
                final_results[npi] = (
                    "chain",
                    SHARED_SIGNER_LABEL,
                    "medium",
                    "authorized_official_repetition",
                    len(npis),
                )

    # Anything still unclassified stays unknown.
    for row in scope_rows:
        if row["npi"] not in final_results:
            final_results[row["npi"]] = ("unknown", "", "n/a", "no_match", "")

    out_path = os.path.join(OUT_DIR, "wa_pharmacies_ownership.csv")
    fieldnames = list(final_rows[0].keys()) + [
        "ownership_category", "parent_organization", "ownership_confidence", "classification_method",
        "shared_signer_npi_count",
    ]
    category_counts = Counter()
    method_counts = Counter()
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in final_rows:
            out_row = dict(row)
            if row["npi"] in final_results:
                category, parent, confidence, method, signer_count = final_results[row["npi"]]
            else:
                category, parent, confidence, method, signer_count = ("not_applicable", "", "n/a", "excluded_from_scope", "")
            out_row["ownership_category"] = category
            out_row["parent_organization"] = parent
            out_row["ownership_confidence"] = confidence
            out_row["classification_method"] = method
            out_row["shared_signer_npi_count"] = signer_count
            category_counts[category] += 1
            method_counts[method] += 1
            writer.writerow(out_row)

    print(f"Wrote {out_path}")
    print(f"\nScope: {len(scope_rows)} included/review records classified; "
          f"{len(final_rows) - len(scope_rows)} excluded records marked not_applicable")
    print("\nownership_category frequency (all 1,941 rows):")
    for cat, c in category_counts.most_common():
        print(f"  {c:5d}  {cat}")
    print("\nclassification_method frequency:")
    for m, c in method_counts.most_common():
        print(f"  {c:5d}  {m}")
