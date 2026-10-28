"""D08 competitors and D19 address points from a local Geofabrik OSM PBF (ADR08).

The PBF is never parsed during a user request and never fetched from public Overpass.
Only objects inside the Zagreb bounding box are kept. Ways are represented by the mean of
their node locations (building-level accuracy); relations are skipped and counted.
"""

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import osmium

from app.adapters.geojson_points import ZAGREB_BBOX
from app.adapters.parsing import ParseResult

# Category per primary tag. Matches the competitor CHECK constraint (migration 0003).
COMPETITOR_TAGS: dict[str, dict[str, str]] = {
    "amenity": {"cafe": "cafe", "bar": "bar", "pub": "pub", "fast_food": "fast_food"},
    "shop": {"bakery": "bakery", "hairdresser": "hairdresser", "beauty": "beauty"},
}
_LIFECYCLE = {
    "disused": "disused",
    "abandoned": "closed",
    "was": "closed",
    "demolished": "closed",
    "razed": "closed",
    "removed": "closed",
    "construction": "construction",
    "proposed": "proposed",
}


@dataclass
class OsmExtract:
    addresses: list[dict[str, Any]] = field(default_factory=list)
    competitors: list[dict[str, Any]] = field(default_factory=list)
    skipped_relations: int = 0
    replication_timestamp: str | None = None


def normalize_text(value: str | None) -> str | None:
    """Spec chapter 10: NFKC, casefold, collapse whitespace. House numbers are kept."""
    if not value:
        return None
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split()) or None


def _inside(lon: float, lat: float) -> bool:
    minx, miny, maxx, maxy = ZAGREB_BBOX
    return minx <= lon <= maxx and miny <= lat <= maxy


def _classify(tags: dict[str, str]) -> tuple[str, str] | None:
    """Return (category, lifecycle_status) or None if the object is not a competitor."""
    for key, mapping in COMPETITOR_TAGS.items():
        value = tags.get(key)
        if value in mapping:
            status = (
                "closed"
                if tags.get("opening_hours", "").strip().lower() == "closed"
                else "mapped_active"
            )
            return mapping[value], status
    for prefix, status in _LIFECYCLE.items():
        for key, mapping in COMPETITOR_TAGS.items():
            value = tags.get(f"{prefix}:{key}")
            if value in mapping:
                return mapping[value], status
    return None


def _address(tags: dict[str, str]) -> str | None:
    street = tags.get("addr:street") or tags.get("addr:place")
    number = tags.get("addr:housenumber")
    return f"{street} {number}" if street and number else None


def _point(obj: Any) -> tuple[float, float] | None:
    if obj.is_node():
        loc = obj.location
        return (loc.lon, loc.lat) if loc.valid() else None
    coords = [(n.lon, n.lat) for n in obj.nodes if n.location.valid()]
    if obj.is_closed() and len(coords) > 1:
        coords = coords[:-1]
    if not coords:
        return None
    return sum(c[0] for c in coords) / len(coords), sum(c[1] for c in coords) / len(coords)


_KEYS = (
    "addr:housenumber",
    *COMPETITOR_TAGS,
    *(f"{p}:{k}" for p in _LIFECYCLE for k in COMPETITOR_TAGS),
)
_HOUSE = re.compile(r"\d")


def extract_osm(path: Path) -> OsmExtract:
    result = OsmExtract()
    reader = (
        osmium.FileProcessor(str(path))
        .with_locations()
        .with_filter(osmium.filter.KeyFilter(*_KEYS))
    )
    header = reader.header
    stamp = header.get("osmosis_replication_timestamp") if header else None
    result.replication_timestamp = stamp or None
    for obj in reader:
        if not isinstance(obj, (osmium.osm.Node, osmium.osm.Way, osmium.osm.Relation)):
            continue
        if obj.is_relation():
            result.skipped_relations += 1
            continue
        point = _point(obj)
        if point is None or not _inside(*point):
            continue
        tags = dict(obj.tags)
        osm_type = "node" if obj.is_node() else "way"
        timestamp = obj.timestamp
        ts = timestamp.isoformat() if timestamp and timestamp.year > 1970 else None
        lon, lat = point

        if "addr:housenumber" in tags and (tags.get("addr:street") or tags.get("addr:place")):
            number = tags["addr:housenumber"]
            if _HOUSE.search(number):
                result.addresses.append(
                    {
                        "osm_type": osm_type,
                        "osm_id": obj.id,
                        "street": tags.get("addr:street") or tags["addr:place"],
                        "housenumber": number,
                        "lon": lon,
                        "lat": lat,
                    }
                )

        classified = _classify(tags)
        if classified:
            category, status = classified
            address = _address(tags)
            result.competitors.append(
                {
                    "osm_type": osm_type,
                    "osm_id": obj.id,
                    "category": category,
                    "lifecycle_status": status,
                    "name": tags.get("name"),
                    "normalized_name": normalize_text(tags.get("name")),
                    "address": address,
                    "normalized_address": normalize_text(address),
                    "lon": lon,
                    "lat": lat,
                    "tags": tags,
                    "osm_timestamp": ts,
                }
            )
    return result


def as_parse_result(extract: OsmExtract, kind: str) -> ParseResult:
    """Wrap one half of the extract (addresses or competitors) for the importer."""
    result = ParseResult()
    rows = extract.addresses if kind == "osm_addresses" else extract.competitors
    for row in rows:
        canonical = json.dumps(row, sort_keys=True, ensure_ascii=False, default=str)
        result.records.append(
            {
                **row,
                "natural_key": f"{row['osm_type']}/{row['osm_id']}",
                "raw": {"osm": f"{row['osm_type']}/{row['osm_id']}", "tags": row.get("tags")},
                "sha256": hashlib.sha256(canonical.encode()).hexdigest(),
            }
        )
    if extract.skipped_relations:
        result.warn(
            "relations_skipped",
            f"Preskočeno relacija (multipoligona): {extract.skipped_relations}.",
        )
    if not result.records:
        result.block("empty_source", "U obuhvatu Zagreba nema nijednog odgovarajućeg OSM objekta.")
    return result


def extract_timestamp(extract: OsmExtract) -> datetime | None:
    if not extract.replication_timestamp:
        return None
    try:
        return datetime.fromisoformat(
            extract.replication_timestamp.replace("Z", "+00:00")
        ).astimezone(UTC)
    except ValueError:
        return None
