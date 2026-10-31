import io
import stat
import zipfile
from decimal import Decimal

import pytest

from app.adapters.districts_shp import parse_districts_shp
from app.adapters.geojson_points import parse_geojson_points
from app.adapters.spaces_csv import parse_area, parse_spaces_csv
from tests import fixtures as fx


@pytest.fixture(scope="module")
def reg():  # type: ignore[no-untyped-def]
    return fx.registry()


# --- D01 / D02 -----------------------------------------------------------------------------


def test_d01_header_on_second_row_and_values(reg) -> None:  # type: ignore[no-untyped-def]
    result = parse_spaces_csv(fx.spaces_csv(preamble_rows=1), reg.get("D01"))
    assert result.blocking == []
    by_id = {r["space_id"]: r for r in result.records}
    assert set(by_id) == {"10422", "4763", "4010"}
    first = by_id["10422"]
    assert first["area_m2"] == Decimal("87.96")
    assert first["position_code"] == "street"
    assert first["address"] == "STRMEČKA CESTA 0057"
    assert first["district_name_source"] == "BREZOVICA"
    assert first["inventory_kind"] == "regular"
    assert by_id["4010"]["position_code"] == "other"
    assert by_id["4010"]["position_source"] == "DVORIŠNI"
    assert by_id["4010"]["district_name_source"] == "GORNJI GRAD - MEDVEŠČAK"


def test_d02_header_on_third_row_is_unfit(reg) -> None:  # type: ignore[no-untyped-def]
    content = fx.spaces_csv(fx.D02_HEADER, fx.D02_ROWS, preamble_rows=2)
    result = parse_spaces_csv(content, reg.get("D02"))
    assert result.blocking == []
    assert result.records[0]["space_id"] == "5357"
    assert result.records[0]["inventory_kind"] == "unfit"
    assert result.records[0]["area_m2"] == Decimal("41.00")


def test_missing_column_is_schema_changed(reg) -> None:  # type: ignore[no-untyped-def]
    header = [h for h in fx.D01_HEADER if h != "POLOŽAJ"]
    rows = [r[:5] + r[6:] for r in fx.D01_ROWS]
    result = parse_spaces_csv(fx.spaces_csv(header, rows), reg.get("D01"))
    assert result.first_blocking_code == "schema_changed"


def test_header_not_found_is_schema_changed(reg) -> None:  # type: ignore[no-untyped-def]
    content = fx.spaces_csv(["X", "Y"], [["1", "2"]])
    assert parse_spaces_csv(content, reg.get("D01")).first_blocking_code == "schema_changed"


def test_bad_decimal_is_field_invalid_not_repaired(reg) -> None:  # type: ignore[no-untyped-def]
    rows = [[*fx.D01_ROWS[0][:3], "87.96.1", *fx.D01_ROWS[0][4:]]]
    result = parse_spaces_csv(fx.spaces_csv(rows=rows), reg.get("D01"))
    assert result.first_blocking_code == "field_invalid"
    assert result.records == []


def test_duplicate_id_blocks(reg) -> None:  # type: ignore[no-untyped-def]
    rows = [fx.D01_ROWS[0], fx.D01_ROWS[0]]
    assert (
        parse_spaces_csv(fx.spaces_csv(rows=rows), reg.get("D01")).first_blocking_code
        == "duplicate_id"
    )


def test_non_numeric_id_blocks(reg) -> None:  # type: ignore[no-untyped-def]
    rows = [["A1", *fx.D01_ROWS[0][1:]]]
    assert (
        parse_spaces_csv(fx.spaces_csv(rows=rows), reg.get("D01")).first_blocking_code
        == "field_invalid"
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("87,96", Decimal("87.96")),
        ("1.234,5", Decimal("1234.50")),
        ("41", Decimal("41.00")),
        ("", None),
    ],
)
def test_parse_area(text: str, expected: Decimal | None) -> None:
    assert parse_area(text) == expected


@pytest.mark.parametrize("text", ["0", "-5", "12,3,4", "abc"])
def test_parse_area_rejects(text: str) -> None:
    with pytest.raises(ValueError):
        parse_area(text)


# --- GeoJSON point layers -------------------------------------------------------------------


def test_tram_stops_parse_with_mode(reg) -> None:  # type: ignore[no-untyped-def]
    content = fx.geojson_points(
        [fx.point(1, 15.9775, 45.8131, **{"Naziv_stajališta": "Trg bana Jelačića"})]
    )
    result = parse_geojson_points(content, reg.get("D03"))
    assert result.blocking == []
    rec = result.records[0]
    assert rec["category"] == "transit"
    assert rec["properties"]["mode"] == "tram"
    assert rec["name"] == "Trg bana Jelačića"
    assert (rec["lon"], rec["lat"]) == (15.9775, 45.8131)


def test_bus_stops_from_extra_registry(reg) -> None:  # type: ignore[no-untyped-def]
    result = parse_geojson_points(
        fx.geojson_points([fx.point(7, 16.05, 45.80, naziv="Dubrava")]), reg.get("D14")
    )
    assert result.records[0]["properties"]["mode"] == "bus"


def test_schools_category(reg) -> None:  # type: ignore[no-untyped-def]
    result = parse_geojson_points(fx.geojson_points([fx.point(3, 15.95, 45.79)]), reg.get("D18"))
    assert result.records[0]["category"] == "school"


def test_swapped_axes_are_rejected(reg) -> None:  # type: ignore[no-untyped-def]
    result = parse_geojson_points(
        fx.geojson_points([fx.point(1, 45.8131, 15.9775)]), reg.get("D04")
    )
    assert result.first_blocking_code == "axis_swapped"


def test_projected_crs_is_rejected(reg) -> None:  # type: ignore[no-untyped-def]
    content = fx.geojson_points([fx.point(1, 15.97, 45.81)], crs="urn:ogc:def:crs:EPSG::3765")
    assert parse_geojson_points(content, reg.get("D05")).first_blocking_code == "crs_invalid"


def test_outside_zagreb_is_warning_not_error(reg) -> None:  # type: ignore[no-untyped-def]
    result = parse_geojson_points(fx.geojson_points([fx.point(1, 16.44, 43.51)]), reg.get("D06"))
    assert result.blocking == []
    assert result.issues[0].code == "outside_zagreb"
    assert result.records[0]["properties"]["review"] == "outside_zagreb"


def test_non_point_geometry_is_rejected(reg) -> None:  # type: ignore[no-untyped-def]
    feature = fx.point(1, 15.97, 45.81)
    feature["geometry"] = {"type": "LineString", "coordinates": [[15.9, 45.8], [16.0, 45.81]]}
    assert (
        parse_geojson_points(fx.geojson_points([feature]), reg.get("D03")).first_blocking_code
        == "geometry_invalid"
    )


def test_not_a_feature_collection(reg) -> None:  # type: ignore[no-untyped-def]
    assert (
        parse_geojson_points(b'{"type":"Feature"}', reg.get("D03")).first_blocking_code
        == "schema_changed"
    )


# --- D07 districts ---------------------------------------------------------------------------


def test_districts_transform_from_3765_to_wgs84(reg) -> None:  # type: ignore[no-untyped-def]
    result = parse_districts_shp(fx.districts_zip(), reg.get("D07"))
    assert result.blocking == [], result.issues
    names = {r["district_id"]: r["name"] for r in result.records}
    assert names == {"01": "Donji grad", "02": "Gornji grad - Medveščak"}
    lon, lat = result.records[0]["geojson"]["coordinates"][0][0][0]
    # Back in WGS84 within ~0.5 m (TG02): first vertex of the first square.
    assert lon == pytest.approx(15.96, abs=1e-5)
    assert lat == pytest.approx(45.80, abs=1e-5)


def test_districts_wrong_crs_is_rejected(reg) -> None:  # type: ignore[no-untyped-def]
    assert (
        parse_districts_shp(fx.districts_zip(epsg=3857), reg.get("D07")).first_blocking_code
        == "crs_invalid"
    )


def test_zip_path_traversal_is_rejected(reg) -> None:  # type: ignore[no-untyped-def]
    content = fx.districts_zip(extra_member=("../evil.txt", b"x"))
    assert parse_districts_shp(content, reg.get("D07")).first_blocking_code == "zip_unsafe"


def test_zip_bomb_over_100_mib_is_rejected(reg) -> None:  # type: ignore[no-untyped-def]
    # TS02: 101 MiB of zeros compresses to ~100 KiB; the declared size is checked before reading.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("big.dbf", b"0" * (101 * 1024 * 1024))
    result = parse_districts_shp(buf.getvalue(), reg.get("D07"))
    assert result.first_blocking_code == "zip_unsafe"


def test_zip_symlink_is_rejected(reg) -> None:  # type: ignore[no-untyped-def]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo("link.shp")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, "/etc/passwd")
    assert parse_districts_shp(buf.getvalue(), reg.get("D07")).first_blocking_code == "zip_unsafe"


def test_not_a_zip(reg) -> None:  # type: ignore[no-untyped-def]
    assert parse_districts_shp(b"not a zip", reg.get("D07")).first_blocking_code == "zip_unsafe"


def test_districts_prj_variant_without_epsg_identity_is_accepted(reg) -> None:  # type: ignore[no-untyped-def]
    content = fx.districts_zip(prj_override=fx.HTRS96_TM_VARIANT_WKT.encode())
    result = parse_districts_shp(content, reg.get("D07"))
    assert result.blocking == [], result.issues
    lon, lat = result.records[0]["geojson"]["coordinates"][0][0][0]
    assert lon == pytest.approx(15.96, abs=1e-5)
    assert lat == pytest.approx(45.80, abs=1e-5)


def test_districts_other_central_meridian_is_rejected(reg) -> None:  # type: ignore[no-untyped-def]
    wrong = fx.HTRS96_TM_VARIANT_WKT.replace('"central_meridian",16.5', '"central_meridian",15')
    content = fx.districts_zip(prj_override=wrong.encode())
    result = parse_districts_shp(content, reg.get("D07"))
    assert result.first_blocking_code == "crs_invalid"
    assert "lon_0=15" in result.blocking[0].detail


def test_geojson_with_bom_is_accepted(reg) -> None:  # type: ignore[no-untyped-def]
    content = b"\xef\xbb\xbf" + fx.geojson_points([fx.point(1, 15.97, 45.81)])
    assert parse_geojson_points(content, reg.get("D17")).blocking == []


def test_geojson_utf16_is_accepted(reg) -> None:  # type: ignore[no-untyped-def]
    content = fx.geojson_points([fx.point(1, 15.97, 45.81)]).decode().encode("utf-16")
    assert parse_geojson_points(content, reg.get("D17")).blocking == []


def test_html_instead_of_geojson_is_described(reg) -> None:  # type: ignore[no-untyped-def]
    result = parse_geojson_points(b"<!DOCTYPE html><html><body>x</body></html>", reg.get("D17"))
    assert result.first_blocking_code == "schema_changed"
    assert "HTML" in result.blocking[0].detail


def test_broken_zip_is_rejected(reg) -> None:  # type: ignore[no-untyped-def]
    result = parse_geojson_points(b"PK\x03\x04rest", reg.get("D17"))
    assert result.first_blocking_code == "zip_unsafe"


def test_zip_with_one_geojson_is_read(reg) -> None:  # type: ignore[no-untyped-def]
    inner = fx.geojson_points([fx.point(1, 15.97, 45.81, naziv="DV Test")])
    result = parse_geojson_points(fx.zip_of({"data/vrtici.geojson": inner}), reg.get("D17"))
    assert result.blocking == []
    assert result.records[0]["name"] == "DV Test"
    assert result.records[0]["properties"]["kind"] == "kindergarten"
    assert any(i.code == "zip_container" for i in result.issues)


def test_zip_with_point_shapefile_in_htrs96_is_transformed(reg) -> None:  # type: ignore[no-untyped-def]
    result = parse_geojson_points(fx.point_shapefile_zip(3765), reg.get("D17"))
    assert result.blocking == [], result.issues
    first = result.records[0]
    assert first["name"] == "DV Jelačić"
    assert first["lon"] == pytest.approx(15.9775, abs=1e-6)
    assert first["lat"] == pytest.approx(45.8131, abs=1e-6)


def test_zip_with_point_shapefile_in_wgs84(reg) -> None:  # type: ignore[no-untyped-def]
    result = parse_geojson_points(fx.point_shapefile_zip(4326), reg.get("D17"))
    assert result.blocking == []
    assert result.records[1]["lat"] == pytest.approx(45.8050, abs=1e-9)


def test_zip_shapefile_without_prj_is_rejected(reg) -> None:  # type: ignore[no-untyped-def]
    result = parse_geojson_points(fx.point_shapefile_zip(3765, with_prj=False), reg.get("D17"))
    assert result.first_blocking_code == "crs_invalid"


def test_zip_with_two_layers_is_rejected(reg) -> None:  # type: ignore[no-untyped-def]
    inner = fx.geojson_points([fx.point(1, 15.97, 45.81)])
    result = parse_geojson_points(
        fx.zip_of({"a.geojson": inner, "b.geojson": inner}), reg.get("D17")
    )
    assert result.first_blocking_code == "schema_changed"


def test_feature_without_geometry_is_skipped_with_warning(reg) -> None:  # type: ignore[no-untyped-def]
    empty = fx.point(2, 0, 0)
    empty["geometry"] = None
    result = parse_geojson_points(
        fx.geojson_points([fx.point(1, 15.97, 45.81), empty]), reg.get("D17")
    )
    assert result.blocking == []
    assert len(result.records) == 1
    assert any(i.code == "geometry_missing" for i in result.issues)
