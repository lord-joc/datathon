from pathlib import Path

import pytest

from app.adapters.coordinates_csv import HEADER_LINE, parse_coordinates_csv
from app.adapters.osm import as_parse_result, extract_osm
from app.gis.addresses import (
    AddressIndex,
    AddressPoint,
    parse_city_address,
    parse_house_number,
    possessive_aliases,
    street_key,
)
from tests import fixtures as fx


@pytest.mark.parametrize(
    ("address", "street", "number", "letter"),
    [
        ("STRMEČKA CESTA 0057", "STRMEČKA CESTA", 57, ""),
        ("TRG ANTE STARČEVIĆA 0007", "TRG ANTE STARČEVIĆA", 7, ""),
        ("ILICA 0001/1", "ILICA", 1, ""),
        ("SAVSKA CESTA 0041A", "SAVSKA CESTA", 41, "a"),
        ("SAVSKA CESTA 41 B", "SAVSKA CESTA", 41, "b"),
        ("TRG KRALJA PETRA KREŠIMIRA IV 0003", "TRG KRALJA PETRA KREŠIMIRA IV", 3, ""),
        ("ULICA 1. SVIBNJA 0010", "ULICA 1. SVIBNJA", 10, ""),
    ],
)
def test_parse_city_address(address: str, street: str, number: int, letter: str) -> None:
    parsed = parse_city_address(address)
    assert parsed is not None
    assert parsed.street == street
    assert (parsed.house.number, parsed.house.letter) == (number, letter)


@pytest.mark.parametrize("address", ["ILICA BB", "TRG", ""])
def test_unparsable_addresses(address: str) -> None:
    assert parse_city_address(address) is None


def test_street_key_ignores_case_accents_and_abbreviations() -> None:
    assert (
        street_key("TRG ANTE STARČEVIĆA")
        == street_key("Trg Ante Starčevića")
        == "trg ante starcevica"
    )
    assert street_key("Vlaška ul.") == street_key("VLAŠKA ULICA") == street_key("VLAŠKA")
    assert street_key("Ulica Đure Salaja") == "dure salaja"


def test_possessive_aliases_only_for_ulica_given_name_surname() -> None:
    assert possessive_aliases("Ulica Vjekoslava Heinzela") == {"heinzelova", "heinzeleva"}
    assert "harambasiceva" in possessive_aliases("Ulica Augusta Harambašića")
    assert possessive_aliases("Vlaška ulica") == set()
    assert possessive_aliases("Ulica grada") == set()
    assert possessive_aliases("Ulica Ivane Brlić-Mažuranić") == set()


@pytest.mark.parametrize(
    ("text", "label"),
    [("96", "96"), ("96a", "96a"), ("96 A", "96a"), ("96/1", "96"), ("12-14", "12")],
)
def test_parse_osm_house_number(text: str, label: str) -> None:
    house = parse_house_number(text)
    assert house is not None and house.label == label


def _index() -> AddressIndex:
    return AddressIndex(
        [
            AddressPoint("way", 100, "Vlaška ulica", "96", 15.985, 45.825),
            AddressPoint("node", 1, "Trg Ante Starčevića", "7", 15.9775, 45.8045),
            AddressPoint("node", 22, "Trg Ante Starčevića", "7", 15.9770, 45.8040),
            AddressPoint("node", 2, "Strmečka cesta", "57A", 15.87, 45.77),
            AddressPoint("node", 5, "Ilica", "10", 15.96, 45.81),
            AddressPoint("node", 6, "Ilica", "10", 15.99, 45.81),
            AddressPoint("node", 7, "Savska cesta", "41", 15.96, 45.80),
            AddressPoint("node", 8, "Savska cesta", "41", 15.961, 45.80),
            AddressPoint("way", 30, "Ulica Vjekoslava Heinzela", "66", 16.00, 45.81),
            # Two different people with the same surname: the alias is ambiguous.
            AddressPoint("way", 31, "Ulica Ivana Horvata", "5", 15.95, 45.79),
            AddressPoint("way", 32, "Ulica Josipa Horvata", "5", 16.05, 45.83),
        ]
    )


def test_exact_match_is_building_approximate() -> None:
    result = _index().geocode("VLAŠKA ULICA 0096")
    assert result.precision == "building_approximate"
    assert (result.lon, result.lat) == (15.985, 45.825)
    assert result.evidence_url == "https://www.openstreetmap.org/way/100"


def test_two_nodes_of_same_building_are_averaged() -> None:
    result = _index().geocode("TRG ANTE STARČEVIĆA 0007")
    assert result.precision == "building_approximate"
    assert result.lon == pytest.approx(15.97725)


def test_fuzzy_street_name_is_accepted_when_unique() -> None:
    result = _index().geocode("VLASKA ULICA 0096")
    assert result.precision == "building_approximate"
    result = _index().geocode("SAVSKE CESTA 0041")
    assert result.precision == "building_approximate"
    assert result.method.startswith("fuzzy")


def test_city_name_without_ulica_matches_osm_ulica() -> None:
    result = _index().geocode("VLAŠKA 0096")
    assert result.precision == "building_approximate"
    assert result.method == "exact"


def test_possessive_city_name_matches_official_osm_name() -> None:
    result = _index().geocode("HEINZELOVA 0066")
    assert result.precision == "building_approximate"
    assert result.method == "alias"
    assert result.evidence_url == "https://www.openstreetmap.org/way/30"


def test_ambiguous_possessive_alias_needs_review() -> None:
    result = _index().geocode("HORVATOVA 0005")
    assert result.precision == "needs_review"
    assert result.method == "alias_ambiguous"
    assert result.lon is None


def test_letter_mismatch_needs_review() -> None:
    result = _index().geocode("STRMEČKA CESTA 0057")
    assert result.precision == "needs_review"
    assert result.method == "letter_mismatch"


def test_far_apart_duplicates_need_review() -> None:
    result = _index().geocode("ILICA 0010")
    assert result.precision == "needs_review"
    assert result.method == "spread"


def test_spread_beyond_tolerance_but_close_is_kept() -> None:
    assert _index().geocode("SAVSKA CESTA 0041").precision == "building_approximate"


def test_no_match_is_missing_not_guessed() -> None:
    result = _index().geocode("MAKSIMIRSKA CESTA 0286")
    assert result.precision == "missing"
    assert result.lon is None


def test_osm_extract_from_pbf(tmp_path: Path) -> None:
    extract = extract_osm(fx.osm_pbf(tmp_path / "t.osm.pbf"))
    addresses = {(a["osm_type"], a["osm_id"]) for a in extract.addresses}
    assert ("way", 100) in addresses
    by_id = {c["osm_id"]: c for c in extract.competitors}
    assert by_id[20]["category"] == "cafe" and by_id[20]["lifecycle_status"] == "mapped_active"
    assert by_id[21]["category"] == "bar" and by_id[21]["lifecycle_status"] == "disused"
    assert by_id[22]["category"] == "bakery"
    assert 23 not in by_id  # Split is outside the Zagreb box
    way = next(a for a in extract.addresses if a["osm_id"] == 100)
    assert (round(way["lon"], 6), round(way["lat"], 6)) == fx.VLASKA_96
    assert as_parse_result(extract, "osm_addresses").blocking == []


def _coords(rows: list[str]) -> bytes:
    return ("\n".join([HEADER_LINE, *rows]) + "\n").encode()


def test_d11_confirmed_entrance() -> None:
    content = _coords(
        ["4763,15.97761,45.80455,entrance_confirmed,,Obilazak 27.10.2026.,2026-10-27"]
    )
    result = parse_coordinates_csv(content, fx.registry().get("D11"))
    assert result.blocking == []
    assert result.records[0]["precision_status"] == "entrance_confirmed"


def test_d11_unfilled_template_rows_are_skipped() -> None:
    content = _coords(
        [
            "4763,15.97761,45.80455,entrance_confirmed,,ok,2026-10-27",
            "5357,,,missing,,MAKSIMIRSKA: nema,",
        ]
    )
    result = parse_coordinates_csv(content, fx.registry().get("D11"))
    assert len(result.records) == 1
    assert any(i.code == "rows_unfilled" for i in result.issues)


@pytest.mark.parametrize(
    ("row", "code"),
    [
        ("4763,45.80455,15.97761,entrance_confirmed,,ok,2026-10-27", "axis_swapped"),
        ("4763,15.97761,45.80455,entrance_confirmed,,,2026-10-27", "field_invalid"),
        ("4763,15.97761,45.80455,entrance_confirmed,,ok,2099-01-01", "field_invalid"),
        ("4763,16.44,43.51,building_approximate,,ok,2026-10-27", "field_invalid"),
        ("A1,15.97,45.80,entrance_confirmed,,ok,2026-10-27", "field_invalid"),
        ("4763,15.97761,45.80455,needs_review,,ok,2026-10-27", "field_invalid"),
    ],
)
def test_d11_rejects_bad_rows(row: str, code: str) -> None:
    result = parse_coordinates_csv(_coords([row]), fx.registry().get("D11"))
    assert result.first_blocking_code == code


def test_d11_excel_croatian_export_is_accepted() -> None:
    content = (
        "space_id;lon;lat;precision_status;evidence_url;evidence_note;checked_at\r\n"
        "4763;15,97761;45,80455;entrance_confirmed;;Obilazak, ulaz iz dvorišta;27.10.2026.\r\n"
    ).encode("cp1250")
    result = parse_coordinates_csv(content, fx.registry().get("D11"))
    assert result.blocking == []
    record = result.records[0]
    assert (record["lon"], record["lat"]) == (15.97761, 45.80455)
    assert record["checked_at"].date().isoformat() == "2026-10-27"


def test_d11_review_template_round_trip_needs_real_evidence() -> None:
    # As written by 'geocode-review': BOM, ';', the hint only in auto_note.
    header = "space_id;lon;lat;precision_status;evidence_url;evidence_note;checked_at;auto_note"
    filled = "4763;15,97761;45,80455;entrance_confirmed;;;2026-10-27;ILICA 0001: nema"
    result = parse_coordinates_csv(f"\ufeff{header}\n{filled}\n".encode(), fx.registry().get("D11"))
    assert result.first_blocking_code == "field_invalid"

    with_evidence = filled.replace(";;;2026", ";;Obilazak tima;2026")
    result = parse_coordinates_csv(
        f"\ufeff{header}\n{with_evidence}\n".encode(), fx.registry().get("D11")
    )
    assert result.blocking == []
    assert result.records[0]["evidence_note"] == "Obilazak tima"
