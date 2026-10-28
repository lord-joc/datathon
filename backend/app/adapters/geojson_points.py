"""D03-D06, D14, D17, D18: point layers from the city Geoportal.

Accepted inputs: GeoJSON (UTF-8, UTF-8 with BOM, UTF-16), or a ZIP that contains exactly
one GeoJSON file or one point Shapefile (some Geoportal resources labelled "GeoJSON" are
delivered as ZIP). A Shapefile must carry a PRJ: HTRS96/TM is transformed to WGS84,
WGS84 is used as is, anything else is rejected. Nothing is assumed.

Rejected, never fixed silently: a non-WGS84 CRS, swapped axes, non-point geometry.
Points outside the Zagreb area are kept for review but flagged (FZ03, NF11).
"""

import io
import json
from typing import Any

import shapefile
from pyproj import CRS, Transformer

from app.adapters.districts_shp import is_htrs96_tm, safe_zip_members
from app.adapters.parsing import ParseResult
from app.adapters.registry import SourceSpec
from app.adapters.spaces_csv import record_sha256

# Generous bounding box around the City of Zagreb (lon, lat).
ZAGREB_BBOX = (15.70, 45.60, 16.30, 46.00)
_WGS84_NAMES = {
    "urn:ogc:def:crs:ogc:1.3:crs84",
    "urn:ogc:def:crs:epsg::4326",
    "epsg:4326",
}
_KEY_FALLBACKS = ("OBJECTID", "objectid", "FID", "fid", "id", "ID")
_NAME_FALLBACKS = ("naziv", "Naziv", "NAZIV", "name", "Name", "NAZIV_OBJEKTA")
_ADDRESS_FALLBACKS = ("adresa", "Adresa", "ADRESA", "address")


def _prop(props: dict[str, Any], primary: str | None, fallbacks: tuple[str, ...]) -> Any:
    if primary and primary in props:
        return props[primary]
    for key in fallbacks:
        if key in props:
            return props[key]
    return None


def parse_geojson_points(content: bytes, spec: SourceSpec) -> ParseResult:
    result = ParseResult()
    if not spec.category:
        result.block("registry_mapping_missing", f"Izvor {spec.code} nema kategoriju sloja.")
        return result
    doc: Any
    if content[:4] == b"PK\x03\x04":
        doc = _doc_from_zip(content, result)
        if doc is None:
            return result
        result.warn("zip_container", "Resurs je ZIP arhiva; sloj je pročitan iz nje.")
    else:
        doc = _decode_json(content, result)
        if doc is None:
            return result
    if not isinstance(doc, dict) or doc.get("type") != "FeatureCollection":
        result.block("schema_changed", "Očekivan je GeoJSON FeatureCollection.")
        return result

    crs = doc.get("crs")
    if isinstance(crs, dict):
        name = str(crs.get("properties", {}).get("name", "")).lower()
        if name and name not in _WGS84_NAMES:
            result.block("crs_invalid", f"Neočekivan CRS: {name}. Očekivan je WGS84.")
            return result

    key_field = _strip_props(spec.source_field("spatial_feature.feature_key"))
    name_field = _strip_props(spec.source_field("spatial_feature.name"))
    address_field = _strip_props(spec.source_field("spatial_feature.address"))
    extra_fields = [
        (_strip_props(src), tgt.removeprefix("spatial_feature.properties."))
        for src, tgt, _ in spec.mapping
        if tgt.startswith("spatial_feature.properties.")
    ]

    seen: set[str] = set()
    minx, miny, maxx, maxy = ZAGREB_BBOX
    for index, feature in enumerate(doc.get("features") or []):
        if not isinstance(feature, dict):
            result.block("schema_changed", f"Objekt {index} nije GeoJSON Feature.")
            continue
        props = feature.get("properties") or {}
        raw_key = _prop(props, key_field, _KEY_FALLBACKS)
        if raw_key is None:
            raw_key = feature.get("id")
        if raw_key is None or str(raw_key).strip() == "":
            result.block("field_invalid", f"Objekt {index} nema identifikator.")
            continue
        key = str(raw_key).strip()
        if key in seen:
            result.block("duplicate_id", f"Identifikator {key} se ponavlja.", key)
            continue
        seen.add(key)

        geom = feature.get("geometry") or {}
        if not geom.get("type"):
            # A record without geometry cannot be placed; keep the import, report it.
            result.warn("geometry_missing", f"Objekt {key} nema geometriju i preskočen je.", key)
            continue
        coords = geom.get("coordinates")
        if (
            geom.get("type") == "MultiPoint"
            and isinstance(coords, (list, tuple))
            and len(coords) == 1
        ):
            coords = coords[0]
        elif geom.get("type") != "Point":
            result.block("geometry_invalid", f"Objekt {key} nije točka.", key)
            continue
        if not (isinstance(coords, (list, tuple)) and len(coords) >= 2):
            result.block("geometry_invalid", f"Objekt {key} nema koordinate.", key)
            continue
        lon, lat = float(coords[0]), float(coords[1])
        if minx <= lat <= maxx and miny <= lon <= maxy:
            result.block("axis_swapped", f"Objekt {key}: zamijenjene osi (lat, lon).", key)
            continue
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            result.block("geometry_invalid", f"Objekt {key}: koordinate izvan raspona.", key)
            continue
        outside = not (minx <= lon <= maxx and miny <= lat <= maxy)
        if outside:
            result.warn("outside_zagreb", f"Objekt {key} je izvan obuhvata Zagreba.", key)

        properties: dict[str, Any] = dict(spec.feature_properties)
        for src, tgt in extra_fields:
            if src in props and props[src] not in (None, ""):
                properties[tgt] = props[src]
        if outside:
            properties["review"] = "outside_zagreb"

        name = _prop(props, name_field, _NAME_FALLBACKS)
        address = _prop(props, address_field, _ADDRESS_FALLBACKS)
        raw = {"properties": props, "geometry": geom}
        result.records.append(
            {
                "feature_key": key,
                "category": spec.category,
                "name": str(name).strip() if name not in (None, "") else None,
                "address": str(address).strip() if address not in (None, "") else None,
                "lon": lon,
                "lat": lat,
                "properties": properties,
                "raw": raw,
                "sha256": record_sha256({"k": key, "raw": json.dumps(raw, sort_keys=True)}),
            }
        )

    if not result.records and not result.blocking:
        result.block("empty_source", "Sloj nema nijedan objekt.")
    return result


def _decode_json(content: bytes, result: ParseResult) -> Any:
    try:
        # utf-8-sig also accepts a leading byte-order mark, which some exports add.
        utf16 = content[:2] in (b"\xff\xfe", b"\xfe\xff")
        return json.loads(content.decode("utf-16" if utf16 else "utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        result.block(
            "schema_changed",
            f"Datoteka nije valjan GeoJSON: {describe_content(content)} ({type(exc).__name__}).",
        )
        return None


def _doc_from_zip(content: bytes, result: ParseResult) -> dict[str, Any] | None:
    files = safe_zip_members(content, result)
    if files is None:
        return None
    jsons = [n for n in files if n.endswith((".geojson", ".json"))]
    shps = [n for n in files if n.endswith(".shp")]
    if len(jsons) == 1 and not shps:
        doc = _decode_json(files[jsons[0]], result)
        return doc if isinstance(doc, dict) or doc is None else {"type": "invalid"}
    if len(shps) == 1 and not jsons:
        return _doc_from_point_shapefile(files, shps[0].removesuffix(".shp"), result)
    names = ", ".join(sorted(files)) or "prazno"
    result.block(
        "schema_changed",
        f"ZIP mora sadržavati točno jedan GeoJSON ili jedan Shapefile; sadrži: {names}.",
    )
    return None


def _doc_from_point_shapefile(
    files: dict[str, bytes], stem: str, result: ParseResult
) -> dict[str, Any] | None:
    dbf, prj = files.get(f"{stem}.dbf"), files.get(f"{stem}.prj")
    if dbf is None:
        result.block("schema_changed", "Shapefile u ZIP-u nema .dbf datoteku.")
        return None
    if prj is None:
        result.block(
            "crs_invalid", "Shapefile u ZIP-u nema .prj; koordinatni sustav se ne pretpostavlja."
        )
        return None
    try:
        crs = CRS.from_wkt(prj.decode("utf-8", errors="replace"))
    except Exception:  # pyproj raises several types for bad WKT
        result.block("crs_invalid", "PRJ datoteka nije valjan WKT.")
        return None
    if is_htrs96_tm(crs):
        to_wgs84: Transformer | None = Transformer.from_crs(
            CRS.from_epsg(3765), CRS.from_epsg(4326), always_xy=True
        )
    elif crs.to_epsg(min_confidence=70) == 4326:
        to_wgs84 = None
    else:
        result.block("crs_invalid", f"Neočekivan koordinatni sustav u Shapefileu: {crs.name}.")
        return None

    cpg = files.get(f"{stem}.cpg", b"").decode("ascii", errors="ignore").strip().lower()
    encoding = "utf-8" if cpg in {"utf-8", "utf8", "65001"} else "cp1250"
    shx = files.get(f"{stem}.shx")
    try:
        reader = shapefile.Reader(
            shp=io.BytesIO(files[f"{stem}.shp"]),
            dbf=io.BytesIO(dbf),
            shx=io.BytesIO(shx) if shx else None,
            encoding=encoding,
            encodingErrors="strict",
        )
        shape_records = list(reader.iterShapeRecords())
    except (UnicodeDecodeError, shapefile.ShapefileException) as exc:
        result.block("schema_changed", f"Shapefile se ne može pročitati: {type(exc).__name__}.")
        return None

    features: list[dict[str, Any]] = []
    for rec in shape_records:
        geo = rec.shape.__geo_interface__
        if geo.get("type") == "Point" and to_wgs84 is not None:
            x, y = geo["coordinates"][:2]
            lon, lat = to_wgs84.transform(x, y)
            geo = {"type": "Point", "coordinates": [lon, lat]}
        props = {
            k: (v.isoformat() if hasattr(v, "isoformat") else v)
            for k, v in rec.record.as_dict().items()
        }
        features.append({"type": "Feature", "properties": props, "geometry": geo})
    return {"type": "FeatureCollection", "features": features}


def describe_content(content: bytes) -> str:
    """Short, safe description of what was actually downloaded (never echoes the body)."""
    head = content[:512].lstrip()
    size = f"{len(content)} B"
    if not content:
        return "prazan odgovor"
    if head.startswith(b"PK\x03\x04"):
        return f"ZIP arhiva, {size}"
    if head[:1] == b"<":
        kind = "HTML stranica" if b"html" in head.lower() else "XML/HTML"
        return f"{kind} umjesto JSON-a, {size}"
    if head.startswith((b"\xff\xfe", b"\xfe\xff")):
        return f"UTF-16 tekst, {size}"
    if head[:1] in (b"{", b"["):
        return f"JSON koji se ne može pročitati do kraja, {size}"
    return f"nepoznat format, {size}"


def _strip_props(field: str | None) -> str | None:
    return field.removeprefix("properties.") if field else None
