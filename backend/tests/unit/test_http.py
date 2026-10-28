"""SafeFetcher: allowlist, SSRF protection (TS01), redirects, size and retry rules."""

import json
from collections.abc import Callable

import httpx
import pytest

from app.adapters.ckan import fetch_package
from app.adapters.http import FetchError, SafeFetcher

ALLOWED = ("data.gov.hr", "data.zagreb.hr", ".arcgis.com")


def public(_: str) -> list[str]:
    return ["93.184.216.34"]


def make(
    handler: Callable[[httpx.Request], httpx.Response],
    resolver: Callable[[str], list[str]] = public,
    sleeps: list[float] | None = None,
) -> SafeFetcher:
    return SafeFetcher(
        ALLOWED,
        resolver=resolver,
        transport=httpx.MockTransport(handler),
        sleep=(sleeps.append if sleeps is not None else (lambda _s: None)),
    )


def ok(_: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=b"hello")


def test_plain_http_is_rejected() -> None:
    with pytest.raises(FetchError) as exc:
        make(ok).get("http://data.gov.hr/x", max_bytes=100)
    assert exc.value.code == "url_not_https"


def test_unknown_host_is_rejected() -> None:
    with pytest.raises(FetchError) as exc:
        make(ok).get("https://evil.example/x", max_bytes=100)
    assert exc.value.code == "host_not_allowed"


def test_suffix_rule_allows_subdomain_only_of_that_domain() -> None:
    assert make(ok).get("https://opendata.arcgis.com/x", max_bytes=100).content == b"hello"
    with pytest.raises(FetchError):
        make(ok).get("https://arcgis.com.evil.example/x", max_bytes=100)


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "10.0.0.5", "169.254.169.254", "::1", "fd00::1", "::ffff:127.0.0.1"]
)
def test_private_addresses_are_rejected(address: str) -> None:
    with pytest.raises(FetchError) as exc:
        make(ok, resolver=lambda _h: [address]).get("https://data.gov.hr/x", max_bytes=100)
    assert exc.value.code == "private_address"


def test_redirect_to_disallowed_host_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "data.gov.hr":
            return httpx.Response(
                302, headers={"location": "https://169.254.169.254/latest/meta-data"}
            )
        return httpx.Response(200, content=b"secret")

    with pytest.raises(FetchError) as exc:
        make(handler).get("https://data.gov.hr/x", max_bytes=100)
    assert exc.value.code == "host_not_allowed"


def test_allowed_redirect_is_followed_and_recorded() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "data.gov.hr":
            return httpx.Response(302, headers={"location": "https://data.zagreb.hr/file.csv"})
        return httpx.Response(200, content=b"csv")

    result = make(handler).get("https://data.gov.hr/x", max_bytes=100)
    assert result.final_url == "https://data.zagreb.hr/file.csv"
    assert result.content == b"csv"


def test_too_many_redirects() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://data.gov.hr/again"})

    with pytest.raises(FetchError) as exc:
        make(handler).get("https://data.gov.hr/x", max_bytes=100)
    assert exc.value.code == "too_many_redirects"


def test_size_limit_while_streaming() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 2000)

    with pytest.raises(FetchError) as exc:
        make(handler).get("https://data.gov.hr/x", max_bytes=1000)
    assert exc.value.code == "too_large"


def test_retries_503_then_succeeds_with_backoff() -> None:
    calls = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] < 3 else httpx.Response(200, content=b"ok")

    sleeps: list[float] = []
    assert make(handler, sleeps=sleeps).get("https://data.gov.hr/x", max_bytes=100).content == b"ok"
    assert sleeps == [2.0, 5.0]


def test_404_is_not_retried() -> None:
    calls = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404)

    with pytest.raises(FetchError) as exc:
        make(handler).get("https://data.gov.hr/x", max_bytes=100)
    assert exc.value.code == "http_error"
    assert calls["n"] == 1


def test_ckan_package_and_resource_selection() -> None:
    package = {
        "success": True,
        "result": {
            "name": "prazni-poslovni-prostori",
            "license_id": "otvorena-dozvola",
            "license_title": "Otvorena dozvola",
            "resources": [
                {"id": "r1", "url": "https://data.zagreb.hr/a.csv", "format": "CSV"},
                {"id": "r2", "url": "https://data.zagreb.hr/b.csv", "format": "CSV"},
                {"id": "r3", "url": "https://data.zagreb.hr/c.geojson", "format": "GeoJSON"},
            ],
        },
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=json.dumps(package).encode())

    pkg = fetch_package(make(handler), "https://data.gov.hr/ckan/api/3/action/package_show?id=x")
    assert pkg.license_is_open
    assert pkg.resource("r2", None).url.endswith("b.csv")
    assert pkg.resource(None, "GeoJSON").resource_id == "r3"
    with pytest.raises(FetchError) as exc:
        pkg.resource(None, "CSV")
    assert exc.value.code == "resource_ambiguous"
    with pytest.raises(FetchError):
        pkg.resource("missing", None)


def test_ckan_unknown_licence_is_not_open() -> None:
    package = {"success": True, "result": {"name": "x", "license_id": "odc-odbl", "resources": []}}

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=json.dumps(package).encode())

    assert not fetch_package(make(handler), "https://data.gov.hr/p").license_is_open


def test_ckan_success_false() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b'{"success": false}')

    with pytest.raises(FetchError) as exc:
        fetch_package(make(handler), "https://data.gov.hr/p")
    assert exc.value.code == "metadata_unsuccessful"
