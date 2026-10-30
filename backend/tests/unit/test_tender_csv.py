from decimal import Decimal

import pytest

from app.adapters.tender_csv import PROFILES, parse_tender_csv
from tests import fixtures as fx

HEADER = "space_id;monthly_rent_eur;tender_url;checked_at;profile;tender_active;evidence_note\n"
URL = "https://www.zagreb.hr/natjecaj-za-zakup/1234"


@pytest.fixture(scope="module")
def spec():  # type: ignore[no-untyped-def]
    return fx.registry().get("D12")


def _parse(body: str, spec, encoding: str = "utf-8-sig"):  # type: ignore[no-untyped-def]
    return parse_tender_csv((HEADER + body).encode(encoding), spec)


def test_rent_with_croatian_format_applies_to_every_profile(spec) -> None:  # type: ignore[no-untyped-def]
    result = _parse(f"4763;1.234,50 €;{URL};27.10.2026.;;da;Natječaj 3/2026\n", spec)
    assert not result.blocking
    assert {r["profile"] for r in result.records} == set(PROFILES)
    first = result.records[0]
    assert first["monthly_rent_eur"] == Decimal("1234.50")
    assert first["tender_active"] == "yes"
    assert first["physical_vacancy"] == "unknown"


def test_profile_row_and_dot_decimal(spec) -> None:  # type: ignore[no-untyped-def]
    result = _parse(f"4763;850.00;{URL};2026-10-27;cafe;;\n", spec)
    assert [r["profile"] for r in result.records] == ["cafe"]
    assert result.records[0]["monthly_rent_eur"] == Decimal("850.00")


def test_untouched_template_rows_are_counted_not_blocking(spec) -> None:  # type: ignore[no-untyped-def]
    result = _parse(f"4763;900;{URL};2026-10-27;;;\n10422;;;;;;\n5357;;;;;;\n", spec)
    assert not result.blocking
    assert len(result.records) == len(PROFILES)
    assert any(i.code == "rows_unfilled" and "2" in i.detail for i in result.issues)


def test_only_template_rows_is_empty_source(spec) -> None:  # type: ignore[no-untyped-def]
    result = _parse("10422;;;;;;\n", spec)
    assert [b.code for b in result.blocking] == ["empty_source"]


@pytest.mark.parametrize(
    "url",
    [
        "http://www.zagreb.hr/x",
        "https://zagreb.hr.evil.example/x",
        "https://example.com/zagreb.hr",
        "javascript:alert(1)",
        "",
    ],
)
def test_tender_url_must_be_https_zagreb_hr(spec, url: str) -> None:  # type: ignore[no-untyped-def]
    result = _parse(f"4763;900;{url};2026-10-27;;da;\n", spec)
    assert [b.code for b in result.blocking] == ["field_invalid"]


@pytest.mark.parametrize("rent", ["0", "-5", "abc", "2000000"])
def test_rent_must_be_a_positive_amount(spec, rent: str) -> None:  # type: ignore[no-untyped-def]
    result = _parse(f"4763;{rent};{URL};2026-10-27;;;\n", spec)
    assert [b.code for b in result.blocking] == ["field_invalid"]


def test_unknown_profile_condition_and_future_date_block(spec) -> None:  # type: ignore[no-untyped-def]
    assert _parse(f"4763;900;{URL};2026-10-27;casino;;\n", spec).blocking
    assert _parse(f"4763;900;{URL};2026-10-27;;mozda;\n", spec).blocking
    assert _parse(f"4763;900;{URL};2099-01-01;;;\n", spec).blocking


def test_duplicate_space_and_profile_blocks(spec) -> None:  # type: ignore[no-untyped-def]
    result = _parse(f"4763;900;{URL};2026-10-27;;;\n4763;950;{URL};2026-10-27;cafe;;\n", spec)
    assert [b.code for b in result.blocking] == ["duplicate_id"]


def test_missing_required_column_is_schema_changed(spec) -> None:  # type: ignore[no-untyped-def]
    result = parse_tender_csv(b"space_id;monthly_rent_eur\n4763;900\n", spec)
    assert [b.code for b in result.blocking] == ["schema_changed"]


def test_windows_1250_excel_file(spec) -> None:  # type: ignore[no-untyped-def]
    result = _parse(f"4763;900;{URL};2026-10-27;;;Zakup čl. 5\n", spec, encoding="cp1250")
    assert not result.blocking
    assert result.records[0]["evidence_note"] == "Zakup čl. 5"
