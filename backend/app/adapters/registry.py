"""Source registry: documentation v3 (source_registry.json) plus team additions.

The registry is the only place adapters get URLs, resource ids and field names from.
Nothing is guessed at runtime (FZ02: "Download URL se ne gradi pogađanjem").
"""

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

Kind = Literal[
    "spaces_csv",
    "geojson_points",
    "districts_shp",
    "osm_competitors",
    "osm_addresses",
    "coordinates_csv",
    "tender_csv",
    "notices_html",
    "lease_csv",
    "unsupported",
]

# Which adapter handles which source, and how features are categorised.
_KIND: dict[str, Kind] = {
    "D01": "spaces_csv",
    "D02": "spaces_csv",
    "D03": "geojson_points",
    "D04": "geojson_points",
    "D05": "geojson_points",
    "D06": "geojson_points",
    "D07": "districts_shp",
    "D08": "osm_competitors",
    "D09": "notices_html",
    "D11": "coordinates_csv",
    "D12": "tender_csv",
    "D14": "geojson_points",
    "D17": "geojson_points",
    "D18": "geojson_points",
    "D19": "osm_addresses",
    "D20": "lease_csv",
}
_CATEGORY: dict[str, str] = {
    "D03": "transit",
    "D04": "university",
    "D05": "culture",
    "D06": "parking",
}
_FEATURE_PROPERTIES: dict[str, dict[str, str]] = {"D03": {"mode": "tram"}}


@dataclass(frozen=True)
class SourceSpec:
    code: str
    name: str
    publisher: str
    catalog_url: str | None
    metadata_endpoint: str | None
    resource_id: str | None
    resource_format: str | None
    resource_urls: tuple[str, ...]
    license_id: str
    attribution: str
    encoding: str | None
    reference_period: str | None
    kind: Kind
    category: str | None
    feature_properties: dict[str, str]
    mapping: tuple[tuple[str, str, str], ...]
    max_response_bytes: int
    raw: dict[str, Any] = field(repr=False)

    @property
    def policy_sha256(self) -> str:
        canonical = json.dumps(self.raw, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def source_field(self, target: str) -> str | None:
        """Source column/property name that maps to a target field, from the registry."""
        for source_field, target_field, _ in self.mapping:
            if target_field == target:
                return source_field
        return None


@dataclass(frozen=True)
class Registry:
    sources: dict[str, SourceSpec]
    allowed_hosts: tuple[str, ...]

    def get(self, code: str) -> SourceSpec:
        try:
            return self.sources[code]
        except KeyError:
            raise KeyError(f"Izvor {code} nije u registru.") from None


def _spec(entry: dict[str, Any]) -> SourceSpec:
    code = entry["source_code"]
    mapping = tuple(
        (m["source_field"], m["target_field"], m.get("transform", ""))
        for m in entry.get("mapping", [])
    )
    max_bytes = int(entry.get("network_policy", {}).get("max_response_bytes", 10 * 1024 * 1024))
    return SourceSpec(
        code=code,
        name=entry["name"],
        publisher=entry.get("publisher", ""),
        catalog_url=entry.get("catalog_url"),
        metadata_endpoint=entry.get("metadata_endpoint"),
        resource_id=entry.get("resource_id"),
        resource_format=entry.get("resource_format") or entry.get("format"),
        resource_urls=tuple(entry.get("resource_urls", [])),
        license_id=entry.get("license_id", "unknown"),
        attribution=entry.get("attribution", ""),
        encoding=entry.get("encoding"),
        reference_period=entry.get("reference_period"),
        kind=_KIND.get(code, "unsupported"),
        category=entry.get("category") or _CATEGORY.get(code),
        feature_properties=dict(
            entry.get("feature_properties") or _FEATURE_PROPERTIES.get(code, {})
        ),
        mapping=mapping,
        max_response_bytes=max_bytes,
        raw=entry,
    )


def load_registry(config_dir: Path) -> Registry:
    base = json.loads((config_dir / "source_registry.json").read_text(encoding="utf-8"))
    extra_path = config_dir / "source_registry_extra.json"
    extra = json.loads(extra_path.read_text(encoding="utf-8")) if extra_path.exists() else {}
    sources: dict[str, SourceSpec] = {}
    for entry in [*base.get("sources", []), *extra.get("sources", [])]:
        spec = _spec(entry)
        sources[spec.code] = spec
    hosts = tuple(extra.get("allowed_hosts", ("data.gov.hr", "data.zagreb.hr")))
    return Registry(sources=sources, allowed_hosts=hosts)
