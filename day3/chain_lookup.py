"""
Version-controlled ownership lookup table for WA pharmacy_type-included
records. Patterns were derived empirically from the actual DBA/org-name
token frequency in wa_pharmacies_final.csv (see day3/explore_names.py),
not guessed in advance - see DECISIONS.md for the 2026-07-25 entry.

Each pattern is a (regex, parent_organization) pair matched against the
combined, uppercased "other_names + organization_name" text. Patterns are
checked as ordered lists; the FIRST list a record matches in wins (see
classify_ownership.py for the precedence order). Use \\b word boundaries
on any token that isn't already distinctive enough to avoid false
positives (e.g. bare "MASON" or "NATION" would over-match).
"""
import re

def _pat(p):
    return re.compile(p)

# Large national/regional multi-location retail or PBM-owned pharmacy
# operators. "Chain" here means "multiple locations under one ownership
# umbrella" - it deliberately includes regionally-owned multi-location
# groups (e.g. Kelley-Ross, Rosauers) alongside national chains, since our
# 5-category schema has no separate bucket for "small local chain." See
# DECISIONS.md.
CHAIN_PATTERNS = [
    (_pat(r"\bSAFEWAY\b"), "Albertsons Companies (Safeway banner)"),
    (_pat(r"\bALBERTSON'?S?\b"), "Albertsons Companies"),
    (_pat(r"\bHAGGEN\b"), "Albertsons Companies (Haggen banner)"),
    (_pat(r"\bSAV.?ON\b"), "Albertsons Companies (Sav-On banner)"),
    (_pat(r"\bQFC\b"), "Kroger (QFC banner)"),
    (_pat(r"\bFRED MEYER\b"), "Kroger (Fred Meyer banner)"),
    (_pat(r"\bWALGREEN'?S?\b"), "Walgreens Boots Alliance"),
    (_pat(r"\bCVS\b"), "CVS Health"),
    (_pat(r"\bLONGS DRUGS?\b"), "CVS Health (Longs Drugs banner)"),
    (_pat(r"\bRITE AID\b"), "Rite Aid"),
    (_pat(r"\bTHRIFTY( PAY.?LESS)?\b"), "Rite Aid (legacy Thrifty/PayLess banner)"),
    (_pat(r"\bPAYLESS\b"), "Rite Aid (legacy PayLess banner)"),
    (_pat(r"\bBARTELL\b"), "Rite Aid (Bartell Drugs banner, acquired 2020)"),
    (_pat(r"\bWAL.?MART\b"), "Walmart Inc."),
    (_pat(r"\bCOSTCO\b"), "Costco Wholesale"),
    (_pat(r"\bSHOPKO\b"), "Shopko (legacy - chain defunct since 2019, record likely stale)"),
    (_pat(r"\bROSAUERS?\b"), "Rosauers Supermarkets"),
    (_pat(r"\bYOKE'?S\b"), "Yoke's Fresh Market"),
    (_pat(r"\bGROCERY OUTLET\b"), "Grocery Outlet"),
    (_pat(r"\bOPTUM\b"), "Optum (UnitedHealth Group)"),
    (_pat(r"\bMAXOR\b"), "Maxor National Pharmacy Services (third-party pharmacy management vendor)"),
    (_pat(r"\bKELLEY.?ROSS\b"), "Kelley-Ross Pharmacy Group (Seattle-based, regionally owned, multi-location)"),
    (_pat(r"\bOMNICARE\b"), "Omnicare (CVS Health long-term-care pharmacy division)"),
    (_pat(r"\bPHARMERICA\b"), "PharMerica"),
    (_pat(r"\bGENOA\b"), "Genoa Healthcare (specialty behavioral-health pharmacy chain)"),
]

# Hospital systems and nonprofit community health center (FQHC) networks.
# Community health centers are nonprofit, not government-run, but their
# embedded pharmacies function like a health-system pharmacy rather than a
# retail chain or a government facility, so they're grouped here.
HEALTH_SYSTEM_PATTERNS = [
    (_pat(r"\bMULTICARE\b"), "MultiCare Health System"),
    (_pat(r"\bPROVIDENCE\b"), "Providence Health & Services"),
    (_pat(r"\bSWEDISH\b"), "Swedish Health Services"),
    (_pat(r"\bFRANCISCAN\b"), "Virginia Mason Franciscan Health"),
    (_pat(r"\bVIRGINIA MASON\b"), "Virginia Mason Franciscan Health"),
    (_pat(r"\bHARBORVIEW\b"), "UW Medicine (Harborview)"),
    (_pat(r"\bUW MEDICINE\b"), "UW Medicine"),
    (_pat(r"\bPEACEHEALTH\b"), "PeaceHealth"),
    (_pat(r"\bLOURDES\b"), "PeaceHealth (Lourdes banner)"),
    (_pat(r"\bKAISER\b|\bPERMANENTE\b"), "Kaiser Permanente"),
    (_pat(r"\bCONFLUENCE HEALTH\b"), "Confluence Health"),
    (_pat(r"\bOVERLAKE\b"), "Overlake Medical Center"),
    (_pat(r"\bEVERGREENHEALTH\b"), "EvergreenHealth"),
    (_pat(r"\bSEA ?MAR\b"), "Sea Mar Community Health Centers"),
    (_pat(r"\bHEALTHPOINT\b"), "HealthPoint (Puget Sound community health centers)"),
    (_pat(r"\bCHAS\b"), "CHAS Health (Community Health Association of Spokane)"),
    (_pat(r"\bINTERNATIONAL COMMUNITY HEALTH\b|\bICHS\b"), "International Community Health Services"),
    (_pat(r"\bFARM WORKERS\b"), "Yakima Valley Farm Workers Clinic"),
    (_pat(r"\bNEIGHBORCARE\b"), "Neighborcare Health"),
    (_pat(r"\bMASON GENERAL\b"), "Mason General Hospital"),
    (_pat(r"\bSEATTLE CHILDREN'?S\b"), "Seattle Children's Hospital"),
    (_pat(r"\bUNIVERSITY OF WASHINGTON\b"), "UW Medicine"),
]

# Broad, low-specificity catch-all - deliberately NOT in HEALTH_SYSTEM_PATTERNS
# above. Checked only as a last resort, after every specific pattern (in
# both CHAIN/HEALTH_SYSTEM/GOVERNMENT_TRIBAL/INDEPENDENT_FRANCHISE, against
# both the DBA alone and the combined dba+org text) has already been tried
# and failed. Added after officer-repetition matching mislabeled several
# community health centers as generic "chain" (e.g. Community Health
# Center of Snohomish County, Tri-Cities Community Health, Community
# Health Association of Spokane). Kept separate from the specific patterns
# after a real regression: giving it equal priority to specific patterns
# caused it to preempt "Yakima Valley Farm Workers Clinic" (matched via
# FARM WORKERS in organization_name) for two records whose DBA -
# "Unify Community Health..." - only carries the generic signal, not the
# specific one. This is intentionally broad; it will not catch every WA
# CHC by name (e.g. "Yakima Neighborhood Health Services" doesn't contain
# this exact bigram) - remaining misses are left "unknown" rather than
# guessed. See DECISIONS.md.
HEALTH_SYSTEM_GENERIC_FALLBACK_PATTERNS = [
    (_pat(r"\bCOMMUNITY HEALTH\b"), "Community Health Center (specific org not auto-identified)"),
]

# Government (federal/state/county/city) and tribal health organizations.
# Kept as one bucket per the ownership_category schema given to us.
GOVERNMENT_TRIBAL_PATTERNS = [
    (_pat(r"\bSWINOMISH\b"), "Swinomish Indian Tribal Community"),
    (_pat(r"\bCOLVILLE\b"), "Confederated Tribes of the Colville Reservation"),
    (_pat(r"\bYAKAMA\b"), "Confederated Tribes and Bands of the Yakama Nation"),
    (_pat(r"\bLUMMI\b"), "Lummi Nation"),
    (_pat(r"\bPUYALLUP\b"), "Puyallup Tribe of Indians"),
    (_pat(r"\bTULALIP\b"), "Tulalip Tribes"),
    (_pat(r"\bMUCKLESHOOT\b"), "Muckleshoot Indian Tribe"),
    (_pat(r"\bSUQUAMISH\b"), "Suquamish Tribe"),
    (_pat(r"\bNISQUALLY\b"), "Nisqually Indian Tribe"),
    (_pat(r"\bCHEHALIS\b"), "Confederated Tribes of the Chehalis Reservation"),
    (_pat(r"\bSPOKANE TRIBE\b"), "Spokane Tribe of Indians"),
    (_pat(r"\bKALISPEL\b"), "Kalispel Tribe of Indians"),
    (_pat(r"\bMAKAH\b"), "Makah Tribe"),
    (_pat(r"\bQUINAULT\b"), "Quinault Indian Nation"),
    (_pat(r"S'KLALLAM"), "S'Klallam Tribe (Jamestown or Port Gamble)"),
    (_pat(r"\bSNOQUALMIE TRIBE\b"), "Snoqualmie Indian Tribe"),
    (_pat(r"\bSTILLAGUAMISH\b"), "Stillaguamish Tribe"),
    (_pat(r"\bSKOKOMISH\b"), "Skokomish Indian Tribe"),
    (_pat(r"\bSHOALWATER\b"), "Shoalwater Bay Indian Tribe"),
    (_pat(r"\bSAMISH\b"), "Samish Indian Nation"),
    (_pat(r"\bCOWLITZ INDIAN\b"), "Cowlitz Indian Tribe"),
    (_pat(r"\bNOOKSACK\b"), "Nooksack Indian Tribe"),
    (_pat(r"\bUPPER SKAGIT\b"), "Upper Skagit Indian Tribe"),
    (_pat(r"\bHOH TRIBE\b"), "Hoh Indian Tribe"),
    (_pat(r"\bQUILEUTE\b"), "Quileute Tribe"),
    (_pat(r"\bCONFEDERATED TRIBES\b"), "Confederated Tribes (specific nation not auto-identified)"),
    (_pat(r"\bINDIAN HEALTH\b|\bINDIAN TRIBAL\b"), "Tribal/Indian Health organization (specific tribe not auto-identified)"),
    (_pat(r"\bPUBLIC HOSPITAL DIST(RICT)?\b"), "WA Public Hospital District (special-purpose government taxing district)"),
    (_pat(r"\bDEPARTMENT OF SOCIAL AND HEALTH SERVICES\b|\bDSHS\b"), "WA State Dept. of Social and Health Services"),
    (_pat(r"\bDEPT OF PUBLIC HEALTH\b|\bDEPARTMENT OF PUBLIC HEALTH\b"), "County/City Public Health Department"),
    (_pat(r"\bSTATE HOSPITAL\b"), "WA State-run hospital"),
    (_pat(r"\bDEPARTMENT OF CORRECTIONS\b"), "WA State Dept. of Corrections"),
    (_pat(r"\bVETERANS? AFFAIRS\b|\bVA MEDICAL CENTER\b"), "U.S. Dept. of Veterans Affairs"),
    (_pat(r"\bMADIGAN\b"), "U.S. Army (Madigan Army Medical Center)"),
    (_pat(r"\bNAVAL HOSPITAL\b|\bBREMERTON NAVAL\b"), "U.S. Navy"),
    (_pat(r"\bFAIRCHILD\b"), "U.S. Air Force (Fairchild AFB)"),
    (_pat(r"\bCOAST GUARD\b"), "U.S. Coast Guard"),
]

# Franchise brands that specifically denote an individually/locally owned
# pharmacy operating under a shared brand (not corporately owned by the
# franchisor) - a genuine positive signal for independent ownership, not
# just an absence of a chain match. Confidence is "medium" not "high"
# because a single franchisee could in principle own more than one
# location; we haven't verified that at the franchisee level.
INDEPENDENT_FRANCHISE_PATTERNS = [
    (_pat(r"\bHEALTH MART\b"), "Health Mart (McKesson franchise brand - individually owned)"),
    (_pat(r"\bMEDICINE SHOPPE\b"), "Medicine Shoppe (Cardinal Health franchise brand - individually owned)"),
    (_pat(r"\bGOOD NEIGHBOR PHARMACY\b"), "Good Neighbor Pharmacy (AmerisourceBergen franchise brand - individually owned)"),
]
