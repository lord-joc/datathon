"""Topic and context proposals for the city's notices (ADR24, FZ14, FZ15, doc. chapter 11).

The model only scores a notice against four topic descriptions; it does not read, summarise or
judge truth. Place and dates come from explicit words in the text. The result is always a
proposal for a person (FZ17). A card's summary is built from confirmed fields by a template.
"""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import numpy as np
import numpy.typing as npt

from app.gis.addresses import strip_accents

ZAGREB = ZoneInfo("Europe/Zagreb")
PIPELINE_VERSION = "news-1.0.0"
MIN_STREET_STEM = 5
MAX_STREETS = 3
_MONTHS = {
    "sijecnja": 1,
    "veljace": 2,
    "ozujka": 3,
    "travnja": 4,
    "svibnja": 5,
    "lipnja": 6,
    "srpnja": 7,
    "kolovoza": 8,
    "rujna": 9,
    "listopada": 10,
    "studenoga": 11,
    "studenog": 11,
    "prosinca": 12,
}
_NUMERIC_DATE = re.compile(r"\b(\d{1,2})\.\s*(\d{1,2})\.\s*(20\d{2})\b")
_NAMED_DATE = re.compile(r"\b(\d{1,2})\.\s*(" + "|".join(_MONTHS) + r")\s+(20\d{2})\b")


class Tokenizer(Protocol):
    def encode(self, text: str, add_special_tokens: bool = ...) -> Any: ...


class TextEmbedder(Protocol):
    def embed(self, texts: list[str]) -> npt.NDArray[np.float32]: ...


@dataclass(frozen=True)
class TopicResult:
    status: str  # classified | uncertain | irrelevant
    topic: str | None
    scores: dict[str, float]
    margin: float


def content_chunks(text: str, tokenizer: Tokenizer, size: int, overlap: int) -> list[str]:
    """Windows of at most `size` content tokens with `overlap`, as slices of the original text."""
    encoding = tokenizer.encode(text, add_special_tokens=False)
    offsets = [o for o in encoding.offsets if o != (0, 0)]
    if not offsets:
        return []
    step = size - overlap
    chunks: list[str] = []
    for start in range(0, len(offsets), step):
        window = offsets[start : start + size]
        chunks.append(text[window[0][0] : window[-1][1]])
        if start + size >= len(offsets):
            break
    return chunks


def classify(
    title: str,
    chunks: list[str],
    embedder: TextEmbedder,
    topics: dict[str, str],
    min_similarity: float,
    min_margin: float,
) -> TopicResult:
    """Best cosine per topic over the title and every content block (ADR10)."""
    names = list(topics)
    topic_vectors = embedder.embed([topics[n] for n in names])
    block_vectors = embedder.embed([title, *chunks])
    similarities = (block_vectors @ topic_vectors.T).max(axis=0)
    scores = {n: round(float(s), 4) for n, s in zip(names, similarities, strict=True)}
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    (top, best), (_, second) = ranked[0], ranked[1]
    margin = round(best - second, 4)
    if best < min_similarity or margin < min_margin:
        return TopicResult("uncertain", None, scores, margin)
    if top == "irrelevant":
        return TopicResult("irrelevant", "irrelevant", scores, margin)
    return TopicResult("classified", top, scores, margin)


def extract_dates(text: str) -> list[date]:
    """Only complete dates. A date without a year stays for the reviewer (doc. chapter 11)."""
    plain = strip_accents(text).lower()
    found: set[date] = set()
    for match in _NUMERIC_DATE.finditer(plain):
        day, month, year = (int(g) for g in match.groups())
        _add(found, year, month, day)
    for match in _NAMED_DATE.finditer(plain):
        _add(found, int(match.group(3)), _MONTHS[match.group(2)], int(match.group(1)))
    return sorted(found)


def _add(found: set[date], year: int, month: int, day: int) -> None:
    try:
        found.add(date(year, month, day))
    except ValueError:
        return


def validity_window(dates: list[date], published: date | None) -> tuple[datetime, datetime] | None:
    """Local start of the first date and exclusive end of the last. Past-only dates give nothing."""
    usable = [d for d in dates if published is None or d >= published]
    if not usable:
        return None
    start = datetime.combine(usable[0], datetime.min.time(), ZAGREB)
    end = datetime.combine(usable[-1] + timedelta(days=1), datetime.min.time(), ZAGREB)
    return start.astimezone(UTC), end.astimezone(UTC)


def _street_pattern(name: str) -> re.Pattern[str] | None:
    """Tolerates Croatian case endings: 'Slavonska avenija' also finds 'Slavonskoj aveniji'."""
    words = strip_accents(name).lower().split()
    words = [w for w in words if w != "ulica"]
    if not words or (len(words) == 1 and len(words[0]) <= MIN_STREET_STEM):
        return None
    stems = [re.escape(w[:-2] if len(w) > MIN_STREET_STEM else w) + r"\w{0,4}" for w in words]
    return re.compile(r"\b" + r"\s+".join(stems) + r"\b")


def mentioned_streets(text: str, streets: list[str]) -> list[str]:
    """Longest street names found in the text; a person confirms them."""
    plain = " ".join(strip_accents(text).lower().split())
    hits: list[tuple[int, str]] = []
    for name in streets:
        pattern = _street_pattern(name)
        match = pattern.search(plain) if pattern else None
        if match:
            hits.append((match.end() - match.start(), name))
    hits.sort(key=lambda x: (-x[0], x[1]))
    return [name for _, name in hits[:MAX_STREETS]]


def template_summary(
    title: str, label: str | None, window: tuple[datetime, datetime] | None
) -> str:
    """Facts already in the notice, nothing inferred. A person may edit it before approval."""
    parts = [f"Grad Zagreb objavio je obavijest „{title}”"]
    if label:
        parts.append(f"za lokaciju {label}")
    if window:
        first = window[0].astimezone(ZAGREB).date()
        last = (window[1].astimezone(ZAGREB) - timedelta(days=1)).date()
        when = (
            f"{first.day}. {first.month}. {first.year}."
            if first == last
            else (
                f"od {first.day}. {first.month}. {first.year}. "
                f"do {last.day}. {last.month}. {last.year}."
            )
        )
        parts.append(when)
    return " ".join(parts).rstrip(".") + ". Provjerite izvornu obavijest."
