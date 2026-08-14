"""
Day 3, part 2: address-based dedup.

Groups NPIs by normalized address. Within any address shared by 2+ NPIs,
proposes collapsing to one physical_location_id only for the subset of
records that are BOTH "substantially similar" in name/DBA AND share the
same pharmacy_type - never for a whole address group just because the
address matches. Everything not auto-collapsed keeps its own
physical_location_id and gets manual_review_required=True, along with
every other NPI at that same address (even the ones that did auto-collapse
with something else), since a split at one address is itself worth a
human's attention.

"Substantially similar" = exact match, or one contains the other, after
normalizing case/punctuation/store-numbers/legal suffixes. Deliberately
NOT using fuzzy-ratio matching (e.g. difflib ratio): calibrating against
real address groups in this dataset (see DECISIONS.md) showed that
templated names like "KAISER PERMANENTE BELLEVUE INFUSION PHARMACY" vs
"KAISER PERMANENTE FACTORIA PHARMACY" score a deceptively high fuzzy
ratio (~0.71-0.89) despite being different pharmacies sharing a
registration address - a real false-merge risk. Plain containment
correctly rejected all three Kaiser test pairs while still catching every
genuine same-store case (Bartell, 14th Avenue, Haggen-by-DBA, QFC
short-name-vs-branded-name).
"""
import csv
import os
import re
import sys

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, OUT_DIR)
from normalize_address import normalize_address  # noqa: E402

_SUFFIX_RE = re.compile(r"\b(INC|LLC|LLP|LP|CO|CORP|CORPORATION|LTD|PLLC|PC|THE|COMPANY)\b\.?")
_STORE_NUM_RE = re.compile(r"#\d+")


def normalize_name(name):
    if not name:
        return ""
    t = name.upper()
    t = _STORE_NUM_RE.sub("", t)
    t = _SUFFIX_RE.sub("", t)
    t = re.sub(r"[^A-Z0-9 ]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


# Health systems and government/tribal orgs commonly run multiple
# genuinely distinct pharmacy departments (inpatient, outpatient/clinic,
# infusion, LTC...) from one nominal campus address, all registered under
# the identical legal organization_name. Confirmed concretely in this
# dataset: "KAISER FOUNDATION HEALTH PLAN OF WASHINGTON" is the org_name
# for both a Bellevue infusion pharmacy AND an unrelated Factoria pharmacy
# - matching on org_name equality alone would have merged them. Retail
# chains (Bartell, Safeway, QFC...) don't have this failure mode - a
# single-counter store re-registering under the same or a near-identical
# org_name at one address really is the same store. So: for health_system
# / government_or_tribal records, require a DBA match specifically:
# comparing org_name is not trusted as evidence on its own.
_CAMPUS_LIKE_CATEGORIES = {"health_system", "government_or_tribal"}


def names_similar(r1, r2):
    campus_like = (r1.get("ownership_category") in _CAMPUS_LIKE_CATEGORIES
                   or r2.get("ownership_category") in _CAMPUS_LIKE_CATEGORIES)
    if campus_like:
        names1 = {normalize_name(r1["other_names"])}
        names2 = {normalize_name(r2["other_names"])}
    else:
        names1 = {normalize_name(r1["organization_name"]), normalize_name(r1["other_names"])}
        names2 = {normalize_name(r2["organization_name"]), normalize_name(r2["other_names"])}
    for n1 in names1:
        if len(n1) < 3:
            continue
        for n2 in names2:
            if len(n2) < 3:
                continue
            if n1 == n2 or n1 in n2 or n2 in n1:
                return True
    return False


def same_type(r1, r2):
    return r1["pharmacy_type"] == r2["pharmacy_type"]


class UnionFind:
    def __init__(self, items):
        self.parent = {i: i for i in items}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


if __name__ == "__main__":
    with open(os.path.join(OUT_DIR, "wa_pharmacies_ownership.csv")) as f:
        rows = list(csv.DictReader(f))

    groups = {}
    for r in rows:
        key = (normalize_address(r["address_1"]), r["postal_code"])
        groups.setdefault(key, []).append(r)

    # --- summary stats on raw address groups (before any collapsing) ---
    size_dist = {}
    for members in groups.values():
        size_dist[len(members)] = size_dist.get(len(members), 0) + 1
    print("=== Address group size distribution (raw, pre-collapse) ===")
    for size in sorted(size_dist):
        print(f"  {size} NPI(s) at address: {size_dist[size]} addresses")
    print(f"  total unique normalized addresses: {len(groups)}  |  total NPIs: {len(rows)}")

    # --- apply the collapse rule within each address group ---
    npi_to_location = {}
    npi_to_reason = {}
    npi_to_review = {}
    location_counter = 0

    for key, members in groups.items():
        if len(members) == 1:
            location_counter += 1
            loc_id = f"LOC-{location_counter:05d}"
            npi = members[0]["npi"]
            npi_to_location[npi] = loc_id
            npi_to_reason[npi] = "single_npi_at_address"
            npi_to_review[npi] = False
            continue

        uf = UnionFind([m["npi"] for m in members])
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                if names_similar(members[i], members[j]) and same_type(members[i], members[j]):
                    uf.union(members[i]["npi"], members[j]["npi"])

        components = {}
        for m in members:
            root = uf.find(m["npi"])
            components.setdefault(root, []).append(m["npi"])

        group_is_fully_collapsed = len(components) == 1
        for comp_npis in components.values():
            location_counter += 1
            loc_id = f"LOC-{location_counter:05d}"
            for npi in comp_npis:
                npi_to_location[npi] = loc_id
                if group_is_fully_collapsed:
                    npi_to_reason[npi] = "collapsed_same_name_and_type"
                elif len(comp_npis) > 1:
                    npi_to_reason[npi] = "partial_match_subset_collapsed"
                else:
                    npi_to_reason[npi] = "no_match_kept_separate"
                # Any split at this address (more than one resulting
                # location) makes the whole address worth a human look,
                # even for the subset that did auto-collapse.
                npi_to_review[npi] = not group_is_fully_collapsed

    # --- write outputs ---
    dataset_path = os.path.join(OUT_DIR, "wa_pharmacies_deduped.csv")
    fieldnames = list(rows[0].keys()) + [
        "normalized_address_1", "physical_location_id", "collapse_reason", "manual_review_required",
    ]
    with open(dataset_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            out = dict(r)
            out["normalized_address_1"] = normalize_address(r["address_1"])
            out["physical_location_id"] = npi_to_location[r["npi"]]
            out["collapse_reason"] = npi_to_reason[r["npi"]]
            out["manual_review_required"] = npi_to_review[r["npi"]]
            writer.writerow(out)
    print(f"\nWrote {dataset_path}")

    bridge_path = os.path.join(OUT_DIR, "npi_to_physical_location_bridge.csv")
    with open(bridge_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["npi", "physical_location_id"])
        for r in rows:
            writer.writerow([r["npi"], npi_to_location[r["npi"]]])
    print(f"Wrote {bridge_path}")

    n_locations = len(set(npi_to_location.values()))
    n_review = sum(1 for v in npi_to_review.values() if v)
    n_collapsed_pairs = sum(1 for v in npi_to_reason.values() if v in
                             ("collapsed_same_name_and_type", "partial_match_subset_collapsed"))
    print(f"\n{len(rows)} NPIs -> {n_locations} distinct physical_location_ids")
    print(f"{n_collapsed_pairs} NPIs auto-collapsed into a shared location with at least one other NPI")
    print(f"{n_review} NPIs flagged manual_review_required (address shared by NPIs that didn't fully collapse)")

    print("\n=== Every raw address group with 3+ NPIs (full detail) ===")
    multi = [(k, v) for k, v in groups.items() if len(v) >= 3]
    for key, members in sorted(multi, key=lambda kv: -len(kv[1])):
        print(f"\n--- {key[0]}, {key[1]} ({len(members)} NPIs) ---")
        for m in members:
            print(f"    {m['npi']} | {m['organization_name']} | {m['other_names']} | "
                  f"{m['pharmacy_type']} | loc={npi_to_location[m['npi']]} | "
                  f"reason={npi_to_reason[m['npi']]} | review={npi_to_review[m['npi']]}")
