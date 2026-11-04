"""Recognising Zagreb's city districts in free Croatian text (ADR24).

Croatian inflects names ("na Trešnjevci", "u Novom Zagrebu"), so each district has explicit
patterns over text without diacritics. "Dubrava" and "Trešnjevka" alone name two districts each;
both are returned and a person or the user decides. "Zagreb" alone names no district (FZ15).
"""

import re

from app.gis.addresses import strip_accents

# Official district name without diacritics, lower case -> patterns that name it.
_PATTERNS: dict[str, tuple[str, ...]] = {
    "brezovica": (r"\bbrezovic\w*",),
    "crnomerec": (r"\bcrnomer\w*",),
    "donja dubrava": (r"\bdonj\w* dubrav\w*", r"(?<!gornj[aeio] )(?<!gornjoj )\bdubrav\w*"),
    "donji grad": (r"\bdonj\w* grad\w*",),
    "gornja dubrava": (r"\bgornj\w* dubrav\w*", r"(?<!donj[aeio] )(?<!donjoj )\bdubrav\w*"),
    "gornji grad - medvescak": (r"\bgornj\w* grad\w*", r"\bmedvescak\w*"),
    "maksimir": (r"\bmaksimir\w*",),
    "novi zagreb - istok": (r"\bnov\w* zagreb\w*", r"\bsiget\w*", r"\bzapruđ\w*", r"\bzaprud\w*"),
    "novi zagreb - zapad": (r"\bnov\w* zagreb\w*", r"\bsamoborsk\w*"),
    "pescenica - zitnjak": (r"\bpescenic\w*", r"\bzitnjak\w*"),
    "podsljeme": (r"\bpodsljem\w*",),
    "podsused - vrapce": (r"\bpodsused\w*", r"\bvrapc\w*"),
    "sesvete": (r"\bsesvet\w*",),
    "stenjevec": (r"\bstenjev\w*", r"\bspansk\w*"),
    "tresnjevka - jug": (r"\btresnjevk\w*", r"\btresnjevc\w*"),
    "tresnjevka - sjever": (r"\btresnjevk\w*", r"\btresnjevc\w*"),
    "trnje": (r"\btrnj[aeuo]\b", r"\btrnjem\b"),
}
_COMPILED = {k: tuple(re.compile(p) for p in v) for k, v in _PATTERNS.items()}


def normalize_name(name: str) -> str:
    return " ".join(strip_accents(name).lower().split())


def mentioned_districts(text: str, districts: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """(district_id, matched words) for every district in `districts` the text names."""
    haystack = " ".join(strip_accents(text).lower().split())
    found: list[tuple[str, str]] = []
    for district_id, name in districts:
        for pattern in _COMPILED.get(normalize_name(name), ()):
            match = pattern.search(haystack)
            if match:
                found.append((district_id, match.group(0)))
                break
    return found
