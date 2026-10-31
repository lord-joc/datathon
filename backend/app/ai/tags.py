"""Tags from the D01 "Opis strukture" field (ADR21): a controlled vocabulary and rules.

The vocabulary describes the physical layout (floor, rooms, sanitary, storage, ...). Rules are
regular expressions on the official text and keep the matched words as evidence. Every tag
starts as `pending_review`; only tags a person approves are shown publicly, and tags never
change any score.

The local MiniLM is not used here. On 30 Oct 2026 it was tried as a fallback for the 26
descriptions without a positional rule, and its best match was wrong in nearly every case
("jedne prostorije" -> basement 0.86, "uredske prostorije" -> upper floor 0.78). The model
stays in use for profile suggestions, where its output was measured (see ai_config.json).
"""

import re
import unicodedata
from dataclasses import dataclass

TAG_LABELS: dict[str, str] = {
    "ground_floor": "Prizemlje",
    "basement": "Podrum ili suteren",
    "upper_floor": "Na katu",
    "attic": "Tavan ili potkrovlje",
    "gallery": "Galerija",
    "street_facing": "Ulična zgrada ili ulično prizemlje",
    "courtyard": "Dvorišni položaj",
    "standalone": "Samostojeći objekt",
    "underpass": "U pothodniku",
    "barrack": "Baraka ili montažni objekt",
    "toilet": "Sanitarni čvor",
    "storage": "Skladište ili ostava",
    "kitchen": "Kuhinja ili čajna kuhinja",
    "shop_window": "Izlog",
    "terrace": "Terasa ili balkon",
    "unfinished": "Roh-bau (nedovršeno)",
    "poor_condition": "Derutno stanje",
    "room_count": "Broj prostorija",
}

_RULES: dict[str, str] = {
    "ground_floor": r"\bprizem\w*|\brazizem\w*",
    "basement": r"\bpodrum\w*|\bsuteren\w*|\bizb[aeiu]\b|\bpodzem\w*",
    "upper_floor": r"\bkat[au]?\b|\bkatov\w*",
    "attic": r"\btavan\w*|\bpotkrovl\w*|\bmansard\w*",
    "gallery": r"\bgalerij\w*",
    "street_facing": r"\buličn\w*",
    "courtyard": r"\bdvorišn\w*|\bdvorišt\w*",
    "standalone": r"\bsamostoje\w*",
    "underpass": r"\bp[oa][dt]hodnik\w*",
    "barrack": r"\bbarak\w*|\bmontažn\w*",
    "toilet": r"\bsanitarn\w*|\bwc\b|\bwc-\w+|\bkupaon\w*",
    "storage": r"\bskladi\w*|\bostav\w*",
    "kitchen": r"\bkuhinj\w*",
    "shop_window": r"\bizlog\w*",
    "terrace": r"\bteras\w*|\bbalkon\w*",
    "unfinished": r"\broh-?\s?bau\b",
    "poor_condition": r"\bderutn\w*",
}
_COMPILED = {tag: re.compile(rx, re.IGNORECASE) for tag, rx in _RULES.items()}

_NUMBERS = {
    "jedna": 1, "jedne": 1, "jedan": 1, "jednu": 1, "dvije": 2, "dva": 2, "tri": 3,
    "četiri": 4, "četri": 4, "pet": 5, "šest": 6, "sedam": 7, "osam": 8, "devet": 9, "deset": 10,
}  # fmt: skip
_ROOMS = re.compile(
    r"\b(" + "|".join(_NUMBERS) + r"|\d{1,2})\s+(?:\w+\s+)?(?:prostorij\w*|sob[aeiu]?)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TagProposal:
    tag: str
    value: int | None
    method: str  # always "rule" for now; the column also allows a future reviewed model
    evidence: str


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def rule_tags(text: str) -> list[TagProposal]:
    """Tags whose words appear in the official text, with the words as evidence."""
    text = normalize(text)
    found: list[TagProposal] = []
    for tag, rx in _COMPILED.items():
        hits = [m.group(0) for m in rx.finditer(text)]
        if hits:
            found.append(TagProposal(tag, None, "rule", ", ".join(dict.fromkeys(hits))))
    rooms = list(_ROOMS.finditer(text))
    if rooms:
        # "jedne prostorije u prizemlju i dvije prostorije u podrumu" = 3: the sum of every
        # counted phrase. A person confirms it, because the text can also repeat one room.
        total = sum(int(m.group(1)) if m.group(1).isdigit() else _NUMBERS[m.group(1).lower()]
                    for m in rooms)  # fmt: skip
        found.append(TagProposal("room_count", total, "rule", "; ".join(m.group(0) for m in rooms)))
    return found
