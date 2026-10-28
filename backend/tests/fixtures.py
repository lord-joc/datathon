"""Builders for small, deterministic source files with the real v3 structure.

Rows 10422 and 5357 are the documented "Izvorni primjer" records (doc. A, chapter 6);
the rest are synthetic test values with Croatian characters to exercise Windows-1250.
"""

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import shapefile
from pyproj import CRS, Transformer
from pyproj.enums import WktVersion

from app.adapters.registry import Registry, load_registry

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"

D01_HEADER = [
    "ID",
    "GRADSKA ČETVRT",
    "ADRESA",
    "Površina u m2",
    "Status korištenja",
    "POLOŽAJ",
    "Opis strukture",
]
D01_ROWS = [
    [
        "10422",
        "BREZOVICA",
        "STRMEČKA CESTA 0057",
        "87,96",
        "G-GP",
        "ULIČNI",
        "dvije prostorije i sanitarni čvor u prizemlju samostojećeg objekta",
    ],
    [
        "4763",
        "DONJI GRAD",
        "TRG ANTE STARČEVIĆA 0007",
        "66,50",
        "G-GP",
        "ULIČNI",
        "dvije prostorije u podzemnom objektu",
    ],
    [
        "4010",
        "GORNJI GRAD - MEDVEŠČAK",
        "VLAŠKA ULICA 0096",
        "33,50",
        "G-GP",
        "DVORIŠNI",
        "jedna prostorija",
    ],
]
D02_HEADER = [
    "ID",
    "GRADSKA ČETVRT",
    "ADRESA",
    "Površina m2",
    "Status korištenja",
    "POLOŽAJ",
    "Opis strukture",
]
D02_ROWS = [
    [
        "5357",
        "DONJA DUBRAVA",
        "MAKSIMIRSKA CESTA 0286",
        "41,00",
        "G-ND",
        "DVORIŠNI",
        "jedne prostorije u podrumu, ulaz iz dvorišta",
    ],
]


def registry() -> Registry:
    return load_registry(CONFIG_DIR)


def spaces_csv(
    header: list[str] | None = None,
    rows: list[list[str]] | None = None,
    preamble_rows: int = 1,
) -> bytes:
    lines = [f"Popis praznih poslovnih prostora {i};;;;;;" for i in range(preamble_rows)]
    lines.append(";".join(header or D01_HEADER))
    lines += [";".join(r) for r in (rows if rows is not None else D01_ROWS)]
    return ("\r\n".join(lines) + "\r\n").encode("cp1250")


def geojson_points(features: list[dict[str, Any]], crs: str | None = None) -> bytes:
    doc: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs:
        doc["crs"] = {"type": "name", "properties": {"name": crs}}
    return json.dumps(doc, ensure_ascii=False).encode("utf-8")


def point(key: int, lon: float, lat: float, **props: Any) -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": {"OBJECTID": key, **props},
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
    }


def districts_zip(
    epsg: int = 3765,
    extra_member: tuple[str, bytes] | None = None,
    prj_override: bytes | None = None,
) -> bytes:
    """Two square districts around central Zagreb, written in the given projected CRS."""
    to_proj = Transformer.from_crs(4326, epsg, always_xy=True)

    def square(lon: float, lat: float, d: float) -> list[list[float]]:
        ring = [(lon, lat), (lon + d, lat), (lon + d, lat + d), (lon, lat + d), (lon, lat)]
        return [list(to_proj.transform(x, y)) for x, y in reversed(ring)]

    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    writer = shapefile.Writer(
        shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POLYGON, encoding="cp1250"
    )
    writer.field("JMS_MB", "C", size=10)
    writer.field("JMS_IME", "C", size=60)
    writer.poly([square(15.96, 45.80, 0.02)])
    writer.record("01", "Donji grad")
    writer.poly([square(15.98, 45.82, 0.02)])
    writer.record("02", "Gornji grad - Medveščak")
    writer.close()
    prj = prj_override or CRS.from_epsg(epsg).to_wkt(WktVersion.WKT1_ESRI).encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("rpj_gc/rpj_gc.shp", shp.getvalue())
        zf.writestr("rpj_gc/rpj_gc.shx", shx.getvalue())
        zf.writestr("rpj_gc/rpj_gc.dbf", dbf.getvalue())
        zf.writestr("rpj_gc/rpj_gc.prj", prj)
        if extra_member:
            zf.writestr(*extra_member)
    return buf.getvalue()


# HTRS96 / Croatia TM as some GIS tools export it: non-standard datum name and a zero
# TOWGS84, which pyproj cannot match to EPSG:3765 by identity (seen on the real D07 file).
HTRS96_TM_VARIANT_WKT = (
    'PROJCS["HTRS96 / Croatia TM",GEOGCS["HTRS96",DATUM["Croatian_Terrestrial_Reference_System",'
    'SPHEROID["GRS 1980",6378137,298.257222101,AUTHORITY["EPSG","7019"]],TOWGS84[0,0,0,0,0,0,0]],'
    'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],'
    'PARAMETER["latitude_of_origin",0],PARAMETER["central_meridian",16.5],'
    'PARAMETER["scale_factor",0.9999],PARAMETER["false_easting",500000],'
    'PARAMETER["false_northing",0],UNIT["metre",1],AXIS["Easting",EAST],AXIS["Northing",NORTH]]'
)


def zip_of(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def point_shapefile_zip(epsg: int | None = 3765, with_prj: bool = True) -> bytes:
    """Two kindergartens in central Zagreb as a point Shapefile in the given CRS."""
    points = [(15.9775, 45.8131, "DV Jelačić"), (15.9750, 45.8050, "DV Glavni kolodvor")]
    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    writer = shapefile.Writer(
        shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POINT, encoding="cp1250"
    )
    writer.field("OBJECTID", "N", size=10)
    writer.field("naziv", "C", size=60)
    to_proj = Transformer.from_crs(4326, epsg or 4326, always_xy=True)
    for i, (lon, lat, name) in enumerate(points, start=1):
        writer.point(*to_proj.transform(lon, lat))
        writer.record(i, name)
    writer.close()
    members = {
        "vrtici.shp": shp.getvalue(),
        "vrtici.shx": shx.getvalue(),
        "vrtici.dbf": dbf.getvalue(),
    }
    if with_prj and epsg:
        members["vrtici.prj"] = CRS.from_epsg(epsg).to_wkt(WktVersion.WKT1_ESRI).encode()
    return zip_of(members)
