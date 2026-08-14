"""
Address normalization for grouping NPIs at the same physical location.
Deliberately conservative: canonicalizes common abbreviations and
punctuation so trivial formatting differences (STREET vs ST, a trailing
period, double spaces) don't split one real address into two groups, but
does NOT strip suite/unit numbers - two different suites in the same
building are two different normalized addresses on purpose, since we
can't assume they're the same pharmacy without evidence.
"""
import re

_SUFFIX_MAP = {
    "STREET": "ST", "AVENUE": "AVE", "BOULEVARD": "BLVD", "DRIVE": "DR",
    "ROAD": "RD", "LANE": "LN", "COURT": "CT", "PLACE": "PL",
    "HIGHWAY": "HWY", "PARKWAY": "PKWY", "CIRCLE": "CIR", "TRAIL": "TRL",
    "SUITE": "STE", "BUILDING": "BLDG", "APARTMENT": "APT",
    "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W",
    "NORTHEAST": "NE", "NORTHWEST": "NW", "SOUTHEAST": "SE", "SOUTHWEST": "SW",
}
_SUFFIX_RE = re.compile(r"\b(" + "|".join(_SUFFIX_MAP.keys()) + r")\b")


def normalize_address(address_1):
    if not address_1:
        return ""
    text = address_1.upper()
    text = re.sub(r"[.,]", "", text)          # drop periods/commas
    text = re.sub(r"[^A-Z0-9# ]", " ", text)   # drop other punctuation, keep # for suite/unit
    text = _SUFFIX_RE.sub(lambda m: _SUFFIX_MAP[m.group(1)], text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
