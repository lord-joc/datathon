"""A personal starting point from a free-text business description (ADR24).

Rules, not the model, read the concrete wishes: the area, the budget and which criteria matter.
They keep the user's own words as the reason, so every proposal can be checked at a glance. The
profile suggestion stays with the local model (ADR21). Everything here is a proposal: the user
sees it in step 3 and may change it; recommended profile weights are not changed.
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

from app.gis.addresses import strip_accents

Criterion = Literal["transit", "universities", "culture", "parking", "schools", "area", "street"]

MAX_AREA_M2 = 100000
MAX_BUDGET_EUR = 1_000_000
HIGH: Literal[3] = 3
NONE: Literal[0] = 0

_AREA = re.compile(r"(\d{1,6}(?:[.,]\d{1,2})?)\s*(?:m2|m²|kvadrat\w*|metara kvadratnih)\b")
_BUDGET = re.compile(
    r"(?:do|budzet\w*|najam\w*|zakupnin\w*|maksimalno|max)?[^\d]{0,12}"
    r"(\d{1,3}(?:[.,]\d{3})*|\d+)\s*(?:eur\w*|€)"
)
_NEGATION = re.compile(
    r"\b(?:ne treba\w*|ne trebam\w*|nije bit\w*|nije vaz\w*|nebit\w*|nevaz\w*|bez)\s+"
    r"(?:\w+\s+){0,2}$"
)
_NEGATION_AFTER = re.compile(r"^\s*(?:\w+\s+){0,1}(?:nije bit\w*|nije vaz\w*|nebit\w*|nevaz\w*)")

# Word stems over text without diacritics. Kept short and readable on purpose: a miss only means
# the recommended level stays, while a wrong hit is visible to the user with its reason.
PRIORITY_RULES: dict[Criterion, str] = {
    "transit": r"\b(tramvaj\w*|autobus\w*|javn\w+ prijevoz\w*|stajalist\w*|prijevoz\w*)",
    "universities": r"\b(fakultet\w*|student\w*|sveucilist\w*|kampus\w*)",
    "culture": r"\b(kultur\w*|kazalist\w*|muzej\w*|galerij\w*|kin[oau]\b|koncert\w*)",
    "parking": r"\b(parking\w*|parkiral\w*|garaz\w*|automobil\w*|autom\b|dostav\w*)",
    "schools": r"\b(skol\w*|vrtic\w*|djec\w*|djet\w*|ucenik\w*|roditelj\w*)",
    "street": r"\b(izlog\w*|prolaznik\w*|ulicn\w*|prolazn\w*|prometn\w+ ulic\w*)",
}
_COMPILED = {k: re.compile(v) for k, v in PRIORITY_RULES.items()}


@dataclass(frozen=True)
class PriorityProposal:
    criterion: Criterion
    level: Literal[0, 3]
    evidence: str


@dataclass(frozen=True)
class BriefFacts:
    area_m2: float | None
    budget_eur: float | None
    priorities: list[PriorityProposal]


def _plain(text: str) -> str:
    return " ".join(strip_accents(text).lower().split())


def _number(value: str) -> float | None:
    try:
        return float(Decimal(value.replace(",", ".")))
    except InvalidOperation:
        return None


def _money(value: str) -> float | None:
    # A separator followed by exactly three digits groups thousands: "1.200" and "1,200" = 1200.
    digits = re.sub(r"[.,](?=\d{3}\b)", "", value)
    return _number(digits)


def extract_area(text: str) -> float | None:
    match = _AREA.search(_plain(text))
    if not match:
        return None
    value = _number(match.group(1))
    return value if value is not None and 0 < value <= MAX_AREA_M2 else None


def extract_budget(text: str) -> float | None:
    match = _BUDGET.search(_plain(text))
    if not match:
        return None
    value = _money(match.group(1))
    return value if value is not None and 0 < value <= MAX_BUDGET_EUR else None


def extract_priorities(text: str) -> list[PriorityProposal]:
    plain = _plain(text)
    proposals: list[PriorityProposal] = []
    for criterion, pattern in _COMPILED.items():
        match = pattern.search(plain)
        if not match:
            continue
        negated = bool(
            _NEGATION.search(plain[: match.start()]) or _NEGATION_AFTER.match(plain[match.end() :])
        )
        proposals.append(PriorityProposal(criterion, NONE if negated else HIGH, match.group(0)))
    return proposals


def read_brief(text: str) -> BriefFacts:
    return BriefFacts(extract_area(text), extract_budget(text), extract_priorities(text))


ACTIVITY_KEYWORDS: dict[str, str] = {
    "cafe": r"ugostitelj|usluzivanj\w* (?:hrane i )?pic|kafic|caffe|\bbar\b",
    "office": r"\bured|administrativ|racunovod|odvjetn|projektir|savjetovanj|informaticke uslug",
    "retail": r"trgovin|prodaj",
    "food_takeaway": r"pekar|slasticar|brz\w+ hran|pizz|priprem\w+ hrane",
    "personal_care": r"frizer|kozmet|pedikir|manikir|njeg\w+ lica|depilacij|masaz",
    "education": r"obrazovanj|igraonic|tecaj|poduk|jezik|predskolsk",
    "workshop": r"popravak|popravk|servis|radionic|stolar|krojac|postolar|izrad\w+ ",
}
_ACTIVITY_COMPILED = {k: re.compile(v) for k, v in ACTIVITY_KEYWORDS.items()}


def activity_matches(profile: str, activity: str) -> bool:
    """Does a contract's activity text belong to this profile? Used for rent statistics only."""
    pattern = _ACTIVITY_COMPILED.get(profile)
    return bool(pattern and pattern.search(_plain(activity)))
