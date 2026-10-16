"""
Day 2, step 2: apply a documented pharmacy_type / walk_in_access /
included_in_access_analysis rule set to the full WA pull. Nothing is
deleted - excluded and ambiguous records are flagged, not dropped, so a
human can review the judgment calls later.
"""
import csv
import json
import os

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

# code -> (pharmacy_type, walk_in_access, included, exclusion_reason)
# "REVIEW" means: don't auto-decide, a human should look at the record.
RULES = {
    "3336C0003X": ("community_retail", "yes", True, ""),
    "3336C0002X": ("clinic", "yes_restricted", True,
                   "walk-in but may be limited to that clinic's patient panel"),
    "3336C0004X": ("compounding", "yes", True, ""),
    "3336L0003X": ("long_term_care", "no", False,
                   "closed-door pharmacy serving facility residents, not the general public"),
    "3336M0002X": ("mail_order", "no", False, "mail-order only, no walk-in storefront"),
    "3336M0003X": ("managed_care_org", "no", False,
                   "administrative/network pharmacy benefit entity, not a physical storefront"),
    "3336S0011X": ("specialty", "no_default", False,
                   "typically appointment/mail-based specialty dispensing; some have storefronts - REVIEW if precision matters"),
    "3336H0001X": ("home_infusion", "no", False, "home delivery/infusion service, not a walk-in location"),
    "3336I0012X": ("institutional", "REVIEW", None,
                   "ambiguous: hospital OUTPATIENT pharmacies are often public walk-in, inpatient-only pharmacies are closed-door - needs per-record check"),
    "333600000X": ("unspecified", "REVIEW", None,
                   "generic 'Pharmacy' code carries no sub-type info - needs per-record check (address type, DBA name)"),
    "332000000X": ("military", "no", False, "restricted to military beneficiaries, not general population"),
}

NON_PHARMACY_FALSE_POSITIVES = {
    "332B00000X": "Durable Medical Equipment & Medical Supplies - matched only via a secondary taxonomy entry, primary business is not dispensing medication",
    "335E00000X": "Prosthetic/Orthotic Supplier - false positive from fuzzy taxonomy_description text match",
    "291U00000X": "Clinical Medical Laboratory - false positive from fuzzy taxonomy_description text match",
    "175F00000X": "Naturopath - individual-style provider, false positive from fuzzy taxonomy_description text match",
    "183500000X": "Pharmacist - individual credential type, not an organizational pharmacy location",
    "261QM1300X": "Clinic/Center, Multi-Specialty - not a pharmacy",
    "261QH0100X": "Clinic/Center, Health Services - not a pharmacy",
}

# NPPES data-entry errors: known retail chains coded under an individual
# credential taxonomy (183700000X, Pharmacy Technician) instead of a real
# pharmacy code. Recovered by organization_name match, not by taxonomy code.
MISCODED_RETAIL_NAME_MARKERS = ["BARTELL"]


def output_organization_name(record):
    """The organization name written to the CSVs. NPPES's legal
    organization_name, unless it is the record's own authorized official's
    personal name (a pharmacy registered under an individual's name) - then
    the trading name (first DBA) instead, matching what the site shows
    (DECISIONS.md 2026-10-16). Classification still runs on the raw record."""
    basic = record.get("basic", {})
    legal = (basic.get("organization_name") or "").strip()
    official = " ".join(filter(None, [(basic.get("authorized_official_first_name") or "").strip(),
                                      (basic.get("authorized_official_last_name") or "").strip()]))
    other_names = record.get("other_names") or []
    dba = (other_names[0].get("organization_name") or "").strip() if other_names else ""
    if official and dba and legal.upper() == official.upper():
        return dba
    return basic.get("organization_name")


def classify(record):
    basic = record.get("basic", {})
    org_name = (basic.get("organization_name") or "").upper()
    taxonomies = record.get("taxonomies", [])
    primary = next((t for t in taxonomies if t.get("primary")), taxonomies[0] if taxonomies else {})
    code = primary.get("code", "")
    desc = primary.get("desc", "")

    has_any_pharmacy_taxonomy = any((t.get("code") or "").startswith("3336") for t in taxonomies)
    primary_is_pharmacy_taxonomy = code.startswith("3336")

    if code == "183700000X" and any(marker in org_name for marker in MISCODED_RETAIL_NAME_MARKERS):
        return ("community_retail", "yes", True,
                "NPPES data-entry error: coded under individual 'Pharmacy Technician' taxonomy "
                "instead of a pharmacy code; reclassified by organization name match")

    # A pharmacy taxonomy present only as a SECONDARY code must not be
    # shadowed by a definitive primary-code rule (e.g. primary=DME,
    # primary=Military). Route straight to REVIEW before the primary-code
    # tables get a chance to make a final call. Primary-code rules only
    # apply once we know no pharmacy taxonomy is being hidden this way.
    if has_any_pharmacy_taxonomy and not primary_is_pharmacy_taxonomy:
        return ("unclassified_has_pharmacy_taxonomy", "unknown", False,
                f"primary taxonomy '{desc}' ({code}) is not itself pharmacy-related, but a "
                "secondary taxonomy is - REVIEW rather than trusting the primary code's rule")

    if code in RULES:
        pharmacy_type, walk_in, included, reason = RULES[code]
        if walk_in == "REVIEW":
            return (pharmacy_type, "unknown", False, reason)
        return (pharmacy_type, walk_in, included, reason)

    if code in NON_PHARMACY_FALSE_POSITIVES:
        return ("non_pharmacy", "no", False, NON_PHARMACY_FALSE_POSITIVES[code])

    if has_any_pharmacy_taxonomy:
        return ("unclassified_has_pharmacy_taxonomy", "unknown", False,
                f"primary taxonomy '{desc}' ({code}) has no rule, but a secondary taxonomy is pharmacy-related - REVIEW")

    return ("unclassified", "unknown", False,
            f"no rule for taxonomy '{desc}' ({code}) - REVIEW")


if __name__ == "__main__":
    with open(os.path.join(OUT_DIR, "wa_pharmacies_full_raw.json")) as f:
        records = json.load(f)

    out_path = os.path.join(OUT_DIR, "wa_pharmacies_classified.csv")
    fieldnames = [
        "npi", "organization_name", "other_names", "address_1", "city", "postal_code",
        "primary_taxonomy_code", "primary_taxonomy_desc",
        "pharmacy_type", "walk_in_access", "included_in_access_analysis", "exclusion_reason",
    ]
    counts = {"included": 0, "excluded": 0, "review": 0}
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            basic = r.get("basic", {})
            addresses = r.get("addresses", [])
            location = next((a for a in addresses if a.get("address_purpose") == "LOCATION"), {})
            taxonomies = r.get("taxonomies", [])
            primary = next((t for t in taxonomies if t.get("primary")), taxonomies[0] if taxonomies else {})
            other_names = r.get("other_names", [])
            dba = other_names[0].get("organization_name") if other_names else ""

            pharmacy_type, walk_in, included, reason = classify(r)
            if included:
                counts["included"] += 1
            elif walk_in == "unknown":
                counts["review"] += 1
            else:
                counts["excluded"] += 1

            writer.writerow({
                "npi": r.get("number"),
                "organization_name": output_organization_name(r),
                "other_names": dba,
                "address_1": location.get("address_1"),
                "city": location.get("city"),
                "postal_code": location.get("postal_code"),
                "primary_taxonomy_code": primary.get("code"),
                "primary_taxonomy_desc": primary.get("desc"),
                "pharmacy_type": pharmacy_type,
                "walk_in_access": walk_in,
                "included_in_access_analysis": included,
                "exclusion_reason": reason,
            })

    print(f"Wrote {out_path}")
    print(f"  included={counts['included']}  excluded={counts['excluded']}  needs_review={counts['review']}  total={len(records)}")
