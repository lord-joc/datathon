"""Address normalisation and matching for geocoding city premises (FZ03, D11/D19).

City list addresses look like "STRMEČKA CESTA 0057", "TRG ANTE STARČEVIĆA 0007",
"ILICA 0001/1" or "SAVSKA CESTA 0041A". OSM uses "Strmečka cesta" + "57".
Matching is deterministic and explainable; anything uncertain is sent to review rather
than placed somewhere plausible.

Two naming habits differ between the city list and OSM (ADR18):
- the generic word "ulica" is often left out ("VLAŠKA" vs "Vlaška ulica"), so it never
  takes part in the street key;
- the list uses the possessive form of a person's name ("HEINZELOVA") where OSM uses the
  official "Ulica Vjekoslava Heinzela". Such OSM streets also get possessive aliases, used
  only when there is no exact match and only when the alias names exactly one OSM street.
"""

import difflib
import math
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

Precision = Literal["building_approximate", "needs_review", "missing"]

_ABBREVIATIONS = {
    "ul": "ulica",
    "c": "cesta",
    "sv": "svetog",
    "dr": "doktora",
    "br": "",
}
_NUMBER = re.compile(r"^\s*0*(?P<num>\d{1,5})\s*(?P<letter>[a-zčćđšž])?\b", re.IGNORECASE)
_CITY_ADDRESS = re.compile(
    r"^(?P<street>.*?[^\d\s].*?)\s+(?P<house>0*\d{1,5}\s*[a-zčćđšž]?)(?:\s*[/\-,].*)?\s*$",
    re.IGNORECASE,
)
_GENERIC_STREET = "ulica"
FUZZY_CUTOFF = 0.88
FUZZY_MARGIN = 0.04
SAME_BUILDING_M = 80.0


def strip_accents(value: str) -> str:
    value = value.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _street_words(street: str) -> list[str]:
    text = strip_accents(street).casefold()
    text = re.sub(r"[.,;:()\"']", " ", text)
    expanded = [_ABBREVIATIONS.get(w, w) for w in text.split() if w]
    return [w for w in expanded if w]


def street_key(street: str) -> str:
    """'TRG KRALJA P. KREŠIMIRA IV' -> 'trg kralja p kresimira iv'; 'Vlaška ulica' -> 'vlaska'.

    Abbreviations are expanded and the generic word 'ulica' is dropped.
    """
    words = [w for w in _street_words(street) if w != _GENERIC_STREET]
    return " ".join(words)


def possessive_aliases(street: str) -> set[str]:
    """'Ulica Vjekoslava Heinzela' -> {'heinzelova', 'heinzeleva'}.

    Only for OSM names of the form 'Ulica <given name> <surname in genitive>'. Both suffixes
    are generated because accents are stripped (š/s, ž/z); the city key picks the right one.
    """
    words = _street_words(street)
    if len(words) < 3 or words[0] != _GENERIC_STREET:
        return set()
    surname = words[-1]
    if len(surname) < 4 or not surname.endswith("a") or "-" in surname:
        return set()
    stem = surname[:-1]
    return {stem + "ova", stem + "eva"}


@dataclass(frozen=True)
class HouseNumber:
    number: int
    letter: str  # lower case, '' when none

    @property
    def label(self) -> str:
        return f"{self.number}{self.letter}"


def parse_house_number(value: str) -> HouseNumber | None:
    match = _NUMBER.match(value or "")
    if not match:
        return None
    number = int(match.group("num"))
    if number <= 0:
        return None
    letter = (match.group("letter") or "").casefold()
    return HouseNumber(number, letter)


@dataclass(frozen=True)
class CityAddress:
    original: str
    street: str
    street_key: str
    house: HouseNumber


def parse_city_address(address: str) -> CityAddress | None:
    """Split a city list address into street and house number. None if there is no number."""
    text = " ".join(address.split())
    match = _CITY_ADDRESS.match(text)
    if not match:
        return None
    house = parse_house_number(match.group("house"))
    if house is None:
        return None
    street = match.group("street").strip(" ,")
    return CityAddress(address, street, street_key(street), house)


@dataclass(frozen=True)
class AddressPoint:
    osm_type: str
    osm_id: int
    street: str
    housenumber: str
    lon: float
    lat: float

    @property
    def url(self) -> str:
        return f"https://www.openstreetmap.org/{self.osm_type}/{self.osm_id}"


@dataclass(frozen=True)
class GeocodeResult:
    precision: Precision
    lon: float | None
    lat: float | None
    method: str
    note: str
    evidence_url: str | None


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class AddressIndex:
    """In-memory lookup: (street_key, number) -> points. Built once per OSM version."""

    def __init__(self, points: list[AddressPoint]) -> None:
        self._by_key: dict[tuple[str, int], list[tuple[str, AddressPoint]]] = defaultdict(list)
        self._streets_by_number: dict[int, set[str]] = defaultdict(set)
        # alias -> street keys it may stand for; more than one means ambiguous.
        self._aliases: dict[str, set[str]] = defaultdict(set)
        for point in points:
            house = parse_house_number(point.housenumber)
            if house is None:
                continue
            key = street_key(point.street)
            self._by_key[(key, house.number)].append((house.letter, point))
            self._streets_by_number[house.number].add(key)
            for alias in possessive_aliases(point.street):
                self._aliases[alias].add(key)

    def __len__(self) -> int:
        return sum(len(v) for v in self._by_key.values())

    def geocode(self, address: str) -> GeocodeResult:
        parsed = parse_city_address(address)
        if parsed is None:
            return GeocodeResult("missing", None, None, "unparsed", "Adresa nema kućni broj.", None)
        candidates = self._by_key.get((parsed.street_key, parsed.house.number))
        method = "exact"
        if not candidates and parsed.street_key in self._aliases:
            streets = sorted(self._aliases[parsed.street_key])
            if len(streets) > 1:
                return GeocodeResult(
                    "needs_review",
                    None,
                    None,
                    "alias_ambiguous",
                    f"Naziv odgovara više OSM ulica: {', '.join(streets)}.",
                    None,
                )
            candidates = self._by_key.get((streets[0], parsed.house.number))
            method = "alias"
        if not candidates:
            streets = list(self._streets_by_number.get(parsed.house.number, ()))
            scored = sorted(
                ((difflib.SequenceMatcher(None, parsed.street_key, s).ratio(), s) for s in streets),
                reverse=True,
            )
            if not scored or scored[0][0] < FUZZY_CUTOFF:
                return GeocodeResult(
                    "missing",
                    None,
                    None,
                    "no_match",
                    f"Nema OSM adrese za '{parsed.street} {parsed.house.label}'.",
                    None,
                )
            if len(scored) > 1 and scored[0][0] - scored[1][0] < FUZZY_MARGIN:
                return GeocodeResult(
                    "needs_review",
                    None,
                    None,
                    "fuzzy_ambiguous",
                    f"Više sličnih ulica: {scored[0][1]}, {scored[1][1]}.",
                    None,
                )
            candidates = self._by_key[(scored[0][1], parsed.house.number)]
            method = f"fuzzy:{scored[0][0]:.2f}"

        same_letter = [p for letter, p in candidates if letter == parsed.house.letter]
        if not same_letter:
            letters = sorted({letter or "-" for letter, _ in candidates})
            return GeocodeResult(
                "needs_review",
                None,
                None,
                "letter_mismatch",
                f"Kućni broj postoji samo kao {', '.join(letters)}.",
                candidates[0][1].url,
            )
        # A building outline (way) carrying the address beats business nodes inside it.
        buildings = [p for p in same_letter if p.osm_type == "way"]
        if buildings:
            same_letter = buildings
        spread = max(
            (haversine_m(a.lon, a.lat, b.lon, b.lat) for a in same_letter for b in same_letter),
            default=0.0,
        )
        if spread > SAME_BUILDING_M:
            return GeocodeResult(
                "needs_review",
                None,
                None,
                "spread",
                f"{len(same_letter)} OSM objekta s istom adresom udaljena do {spread:.0f} m.",
                same_letter[0].url,
            )
        lon = sum(p.lon for p in same_letter) / len(same_letter)
        lat = sum(p.lat for p in same_letter) / len(same_letter)
        best = same_letter[0]
        note = f"OSM {best.osm_type}/{best.osm_id}: {best.street} {best.housenumber} ({method})"
        return GeocodeResult("building_approximate", lon, lat, method, note, best.url)
