"""D07: city district boundaries (zipped Shapefile, DBF cp1250, PRJ EPSG:3765 -> WGS84).

The ZIP is unpacked in memory with strict limits (TS02): no absolute paths, no "..",
no symlinks, at most 50 members and 100 MiB uncompressed. The CRS is read from the PRJ
file; anything other than HTRS96/TM (EPSG:3765) is rejected, never assumed (NF11).
"""

import io
import math
import stat
import warnings
import zipfile
from typing import Any

import shapefile
import shapely
from pyproj import CRS, Transformer
from shapely.geometry import MultiPolygon, Polygon, mapping, shape

from app.adapters.parsing import ParseResult
from app.adapters.registry import SourceSpec
from app.adapters.spaces_csv import record_sha256

MAX_MEMBERS = 50
MAX_UNCOMPRESSED = 100 * 1024 * 1024
EXPECTED_EPSG = 3765

# HTRS96 / Croatia TM. ESRI/ArcGIS PRJ files often omit the EPSG code or use another datum
# name (plus a zero TOWGS84), so pyproj cannot identify them by name. The projection is
# accepted only when every defining parameter matches EPSG:3765 exactly.
_HTRS96_TM = {
    "proj": "tmerc",
    "lat_0": 0.0,
    "lon_0": 16.5,
    "k": 0.9999,
    "x_0": 500000.0,
    "y_0": 0.0,
}
_GRS80_A = 6378137.0
_GRS80_RF = 298.257222101


def _proj_params(crs: CRS) -> dict[str, Any]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        return dict(crs.to_dict())


def describe_projection(crs: CRS) -> str:
    params = _proj_params(crs)
    keys = ("proj", "lon_0", "k", "x_0", "y_0", "ellps", "units")
    return ", ".join(f"{k}={params[k]}" for k in keys if k in params) or "nepoznato"


def is_htrs96_tm(crs: CRS) -> bool:
    if crs.to_epsg(min_confidence=70) == EXPECTED_EPSG:
        return True
    if crs.equals(CRS.from_epsg(EXPECTED_EPSG), ignore_axis_order=True):
        return True
    params = _proj_params(crs)
    for key, expected in _HTRS96_TM.items():
        value = params.get(key, 0.0 if key in {"lat_0", "y_0"} else None)
        if isinstance(expected, float):
            if not isinstance(value, (int, float)) or not math.isclose(
                value, expected, abs_tol=1e-9
            ):
                return False
        elif value != expected:
            return False
    if params.get("units", "m") != "m":
        return False
    ellipsoid = crs.ellipsoid
    if ellipsoid is None:
        return False
    rf = ellipsoid.inverse_flattening
    return math.isclose(ellipsoid.semi_major_metre, _GRS80_A, abs_tol=1e-3) and math.isclose(
        rf, _GRS80_RF, rel_tol=1e-9
    )


def safe_zip_members(content: bytes, result: ParseResult) -> dict[str, bytes] | None:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        result.block("zip_unsafe", "Datoteka nije valjan ZIP.")
        return None
    infos = archive.infolist()
    if len(infos) > MAX_MEMBERS:
        result.block("zip_unsafe", f"ZIP ima više od {MAX_MEMBERS} datoteka.")
        return None
    total = 0
    files: dict[str, bytes] = {}
    for info in infos:
        name = info.filename
        mode = info.external_attr >> 16
        if (
            name.startswith(("/", "\\"))
            or ".." in name.replace("\\", "/").split("/")
            or ":" in name
        ):
            result.block("zip_unsafe", f"Nedopuštena putanja u ZIP-u: {name}")
            return None
        if stat.S_ISLNK(mode):
            result.block("zip_unsafe", f"Simbolička poveznica u ZIP-u: {name}")
            return None
        if info.is_dir():
            continue
        total += info.file_size
        if total > MAX_UNCOMPRESSED:
            result.block("zip_unsafe", "Raspakirani sadržaj je veći od 100 MiB.")
            return None
        files[name.replace("\\", "/").rsplit("/", 1)[-1].lower()] = archive.read(info)
    return files


def parse_districts_shp(content: bytes, spec: SourceSpec) -> ParseResult:
    result = ParseResult()
    files = safe_zip_members(content, result)
    if files is None:
        return result

    def find(ext: str) -> tuple[str, bytes] | None:
        hits = [(n, b) for n, b in files.items() if n.endswith(ext)]
        return hits[0] if len(hits) == 1 else None

    shp, dbf, prj = find(".shp"), find(".dbf"), find(".prj")
    if not (shp and dbf and prj):
        result.block("schema_changed", "ZIP mora sadržavati točno jedan .shp, .dbf i .prj.")
        return result
    shx = find(".shx")

    try:
        wkt = prj[1].decode("utf-8")
    except UnicodeDecodeError:
        wkt = prj[1].decode("latin-1")
    try:
        crs = CRS.from_wkt(wkt)
    except Exception:  # pyproj raises several types for bad WKT
        result.block("crs_invalid", "PRJ datoteka nije valjan WKT.")
        return result
    if not is_htrs96_tm(crs):
        result.block(
            "crs_invalid",
            f"Očekivan HTRS96/TM (EPSG:{EXPECTED_EPSG}), pročitano: {crs.name} "
            f"({describe_projection(crs)}).",
        )
        return result
    # Transform with the authoritative EPSG definition once the PRJ is confirmed to match it.
    to_wgs84 = Transformer.from_crs(
        CRS.from_epsg(EXPECTED_EPSG), CRS.from_epsg(4326), always_xy=True
    )

    reader = shapefile.Reader(
        shp=io.BytesIO(shp[1]),
        dbf=io.BytesIO(dbf[1]),
        shx=io.BytesIO(shx[1]) if shx else None,
        encoding="cp1250",
        encodingErrors="strict",
    )
    id_field = spec.source_field("district.district_id") or "JMS_MB"
    name_field = spec.source_field("district.name") or "JMS_IME"
    field_names = [f[0] for f in reader.fields[1:]]
    missing = [f for f in (id_field, name_field) if f not in field_names]
    if missing:
        result.block("schema_changed", f"DBF nema polja: {', '.join(missing)}.")
        return result

    seen: set[str] = set()
    try:
        shape_records = list(reader.iterShapeRecords())
    except (UnicodeDecodeError, shapefile.ShapefileException) as exc:
        result.block("schema_changed", f"Shapefile se ne može pročitati: {type(exc).__name__}.")
        return result
    for rec in shape_records:
        attrs: dict[str, Any] = rec.record.as_dict()
        district_id = str(attrs.get(id_field, "")).strip()
        name = " ".join(str(attrs.get(name_field, "")).split())
        if not district_id or not name:
            result.block("field_invalid", "Četvrt bez oznake ili naziva.", district_id or None)
            continue
        if district_id in seen:
            result.block("duplicate_id", f"Četvrt {district_id} se ponavlja.", district_id)
            continue
        seen.add(district_id)
        geom = shape(rec.shape.__geo_interface__)
        if not isinstance(geom, (Polygon, MultiPolygon)):
            result.block("geometry_invalid", f"Četvrt {district_id} nije poligon.", district_id)
            continue
        wgs = shapely.transform(geom, to_wgs84.transform, interleaved=False)
        if isinstance(wgs, Polygon):
            wgs = MultiPolygon([wgs])
        if not wgs.is_valid:
            result.block(
                "geometry_invalid", f"Geometrija četvrti {district_id} nije valjana.", district_id
            )
            continue
        raw = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in attrs.items()}
        result.records.append(
            {
                "district_id": district_id,
                "name": name,
                "geom_wkt": wgs.wkt,
                "geojson": mapping(wgs),
                "raw": raw,
                "sha256": record_sha256({"id": district_id, "raw": str(sorted(raw.items()))}),
            }
        )

    if not result.records and not result.blocking:
        result.block("empty_source", "Shapefile nema nijednu četvrt.")
    return result
