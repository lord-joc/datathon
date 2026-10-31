"""Public API contract tests on PostgreSQL + PostGIS, as the restricted API role.

Builds the slice-3 fixture bundle (3 regular spaces + 1 unfit), activates it and calls the
routes through FastAPI. The API role can read and insert ranking snapshots, nothing else.
"""

import csv
import io
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError

from app.api.v1 import presenters, public, rankings, system
from app.main import create_app
from app.pipeline.bundle import activate_bundle, build_bundle
from app.pipeline.description_tags import import_review, review_template_csv, tag_descriptions
from app.pipeline.geocode import geocode_spaces
from app.pipeline.importer import Importer
from app.pipeline.profiles import sync_profiles
from tests import fixtures as fx
from tests.integration.support import URL, import_ok, write_file

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not URL, reason="MIGRATION_DATABASE_URL not set"),
]
API_PASSWORD = "api_test_only"


@pytest.fixture
def client(
    imported: Engine, owner: Engine, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    geocode_spaces(imported)
    with imported.begin() as conn:
        sync_profiles(conn, presenters.profiles())
    activate_bundle(imported, build_bundle(imported, "api-test").bundle_id)
    with owner.begin() as conn:
        conn.execute(
            text(
                "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='test_api') "
                f"THEN CREATE ROLE test_api LOGIN PASSWORD '{API_PASSWORD}'; END IF; END $$"
            )
        )
        conn.execute(text("GRANT app_read, app_ranking_write TO test_api"))
    assert URL
    api_engine = create_engine(
        make_url(URL).set(username="test_api", password=API_PASSWORD),
        connect_args={"options": "-c search_path=prostoriq,public"},
    )
    for module in (public, rankings, system):
        monkeypatch.setattr(module, "get_engine", lambda: api_engine)
    yield TestClient(create_app())
    api_engine.dispose()


def _profile(client: TestClient, code: str = "cafe") -> dict[str, Any]:
    items = client.get("/api/v1/profiles").json()["items"]
    return next(p for p in items if p["profile"] == code)


def _request(client: TestClient, space_ids: list[str], **overrides: Any) -> dict[str, Any]:
    bundle = client.get("/api/v1/status").json()["active_bundle_id"]
    body: dict[str, Any] = {
        "profile": "cafe",
        "profile_version": _profile(client)["profile_version"],
        "dataset_bundle_id": bundle,
        "space_ids": space_ids,
        "radius_m": 500,
        "prefer_lower_competition": True,
        "include_conditional": True,
        "missing_policy": "require_ack",
    }
    body.update(overrides)
    return body


def test_profiles_are_served_with_db_versions_and_etag(client: TestClient) -> None:
    response = client.get("/api/v1/profiles")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 7
    cafe = next(p for p in items if p["profile"] == "cafe")
    assert cafe["weights"]["transit"] == 20 and cafe["competitor_categories"] == [
        "bar",
        "cafe",
        "pub",
    ]
    etag = response.headers["ETag"]
    again = client.get("/api/v1/profiles", headers={"If-None-Match": etag})
    assert again.status_code == 304


def test_districts_and_sources(client: TestClient) -> None:
    names = [d["name"] for d in client.get("/api/v1/districts").json()["items"]]
    assert "Donji grad" in names
    sources = {s["source_code"]: s for s in client.get("/api/v1/sources").json()["items"]}
    assert sources["D01"]["availability"] == "available"
    assert sources["D01"]["limitations"]


def test_space_list_filters_and_never_lists_unfit_by_default(client: TestClient) -> None:
    body = client.get("/api/v1/spaces", params={"profile": "cafe"}).json()
    assert body["total"] == 3
    assert {i["space_id"] for i in body["items"]} == {"4763", "4010", "10422"}
    assert body["without_usable_coordinate"] == 1
    assert all(i["status"]["candidate_status"] == "conditional" for i in body["items"])
    assert body["warnings"][0].startswith("Popis Grada iz 2024.")

    with_unfit = client.get("/api/v1/spaces", params={"profile": "cafe", "include_excluded": True})
    assert with_unfit.json()["total"] == 4

    ranged = client.get(
        "/api/v1/spaces", params={"profile": "cafe", "area_min_m2": 30, "area_max_m2": 70}
    ).json()
    assert {i["space_id"] for i in ranged["items"]} == {"4763", "4010"}

    bad = client.get("/api/v1/spaces", params={"profile": "cafe", "page_size": 101})
    assert bad.status_code == 422
    stale = client.get(
        "/api/v1/spaces", params={"profile": "cafe", "dataset_bundle_id": str(uuid.uuid4())}
    )
    assert stale.status_code == 409 and stale.json()["code"] == "DATASET_CHANGED"


def test_space_detail_has_metrics_with_sources_and_reasons(client: TestClient) -> None:
    body = client.get("/api/v1/spaces/4763", params={"profile": "cafe"}).json()
    transit = body["metrics"]["transit"]
    assert transit["unit"] == "m" and transit["value"] > 0
    assert transit["detail"]["name"] == "Jurišićeva" and transit["detail"]["distance"] == "air"
    assert transit["source_version_ids"]
    cost = body["metrics"]["cost"]
    assert (cost["value"], cost["unit"], cost["reason"]) == (
        None,
        "eur_month",
        "cost_not_configured",
    )
    assert body["metrics"]["street"]["value"] == 1
    assert "© OpenStreetMap contributors, ODbL" in body["attribution"]

    missing = client.get("/api/v1/spaces/10422", params={"profile": "cafe"}).json()
    assert missing["space"]["coordinate"]["geometry"] is None
    assert missing["metrics"]["transit"]["reason"] == "missing_coordinate"
    assert client.get("/api/v1/spaces/999", params={"profile": "cafe"}).status_code == 404


def test_ranking_snapshot_and_token(client: TestClient) -> None:
    response = client.post("/api/v1/rankings", json=_request(client, ["4010", "4763"]))
    assert response.status_code == 201, response.json().get("errors")
    body = response.json()
    assert [i["rank"] for i in body["items"]] == [1, 2]
    assert body["items"][0]["score"] >= body["items"][1]["score"]
    assert "competition" not in body["criteria_used"]
    assert {"criterion": "competition", "reason": "coverage_unchecked"} in body["excluded_criteria"]
    assert {"criterion": "cost", "reason": "cost_not_configured"} in body["excluded_criteria"]
    first = body["items"][0]
    assert sum(first["contributions"].values()) == pytest.approx(first["score"], abs=1e-6)
    token = body["access_token"]
    assert len(token) >= 32

    run = body["ranking_run_id"]
    stored = client.get(f"/api/v1/rankings/{run}", headers={"X-Ranking-Token": token})
    assert stored.status_code == 200
    again = stored.json()
    assert again["access_token"] is None and again["historical"] is False
    assert [(i["space_id"], i["score"]) for i in again["items"]] == [
        (i["space_id"], i["score"]) for i in body["items"]
    ]
    wrong = client.get(f"/api/v1/rankings/{run}", headers={"X-Ranking-Token": "x" * 43})
    assert wrong.status_code == 403
    unknown = client.get(f"/api/v1/rankings/{uuid.uuid4()}", headers={"X-Ranking-Token": token})
    assert unknown.status_code == 404


def test_partial_criterion_needs_confirmation_then_ranks(client: TestClient) -> None:
    request = _request(client, ["4763", "10422"])
    conflict = client.post("/api/v1/rankings", json=request)
    assert conflict.status_code == 409
    problem = conflict.json()
    assert problem["code"] == "COMPARISON_BASIS_CHANGED"
    assert "transit" in problem["missing_by_space"]["10422"]
    assert problem["options"] == ["common_criteria", "remove_incomplete"]
    token = problem["comparison_basis_token"]

    no_choice = client.post("/api/v1/rankings", json={**request, "comparison_basis_token": token})
    assert no_choice.status_code == 422

    removed = client.post(
        "/api/v1/rankings",
        json={**request, "comparison_basis_token": token, "basis_choice": "remove_incomplete"},
    ).json()
    ranked = [i for i in removed["items"] if i["rank"]]
    assert [i["space_id"] for i in ranked] == ["4763"]
    dropped = next(i for i in removed["items"] if i["space_id"] == "10422")
    assert dropped["reason"] == "partial_coverage" and "removed_incomplete" in dropped["reasons"]

    common = client.post(
        "/api/v1/rankings",
        json={**request, "comparison_basis_token": token, "basis_choice": "common_criteria"},
    ).json()
    assert len([i for i in common["items"] if i["rank"]]) == 2
    assert {"criterion": "transit", "reason": "partial_coverage"} in common["excluded_criteria"]
    assert common["coverage_active"] < removed["coverage_active"]

    # The token is bound to this request: another radius needs a new confirmation.
    other = client.post(
        "/api/v1/rankings",
        json={
            **request,
            "radius_m": 1000,
            "comparison_basis_token": token,
            "basis_choice": "common_criteria",
        },
    )
    assert other.status_code == 409 and "istekla" in other.json()["detail"]


def test_unfit_space_is_never_ranked(client: TestClient) -> None:
    body = client.post("/api/v1/rankings", json=_request(client, ["4763", "5357"])).json()
    unfit = next(i for i in body["items"] if i["space_id"] == "5357")
    assert unfit["candidate_status"] == "excluded" and unfit["rank"] is None
    assert "unfit_inventory" in unfit["reasons"]


@pytest.mark.parametrize(
    ("overrides", "status", "code"),
    [
        ({"dataset_bundle_id": str(uuid.uuid4())}, 409, "DATASET_CHANGED"),
        ({"profile_version": str(uuid.uuid4())}, 409, "PROFILE_CHANGED"),
        ({"space_ids": ["999999"]}, 422, "UNKNOWN_SPACES"),
        ({"space_ids": ["4763", "4763"]}, 422, "VALIDATION_FAILED"),
        ({"space_ids": [f"{i}" for i in range(501)]}, 422, "VALIDATION_FAILED"),
        ({"unexpected": 1}, 422, "VALIDATION_FAILED"),
        (
            {
                "weights": {
                    k: 0
                    for k in (
                        "transit",
                        "universities",
                        "culture",
                        "parking",
                        "schools",
                        "area",
                        "street",
                        "competition",
                        "cost",
                    )
                }
            },
            422,
            "NO_ACTIVE_CRITERIA",
        ),
    ],
)
def test_ranking_rejections(
    client: TestClient, overrides: dict[str, Any], status: int, code: str
) -> None:
    response = client.post("/api/v1/rankings", json={**_request(client, ["4763"]), **overrides})
    assert response.status_code == status, response.json()
    assert response.json()["code"] == code


def test_stored_ranking_survives_a_new_bundle(client: TestClient, imported: Engine) -> None:
    body = client.post("/api/v1/rankings", json=_request(client, ["4763"])).json()
    with imported.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO prostoriq.geo_evidence (space_id, source_version_id, geom,
                    precision_status, evidence_note, checked_at, license_id)
                SELECT '10422', source_version_id, ST_SetSRID(ST_MakePoint(15.87, 45.77), 4326),
                    'building_approximate', 'test', now(), 'ODbL-1.0'
                FROM prostoriq.source_version WHERE source_code = 'D19'
                ORDER BY fetched_at DESC LIMIT 1
                """
            )
        )
    activate_bundle(imported, build_bundle(imported, "newer").bundle_id)
    old = client.get(
        f"/api/v1/rankings/{body['ranking_run_id']}",
        headers={"X-Ranking-Token": body["access_token"]},
    ).json()
    assert old["historical"] is True
    assert old["items"][0]["score"] == body["items"][0]["score"]
    stale = client.post(
        "/api/v1/rankings",
        json={**_request(client, ["4763"]), "dataset_bundle_id": body["dataset_bundle_id"]},
    )
    assert stale.status_code == 409


def test_map_layers_are_geojson_with_etag(client: TestClient) -> None:
    districts = client.get("/api/v1/layers/districts")
    assert districts.status_code == 200
    assert districts.headers["content-type"].startswith("application/geo+json")
    body = districts.json()
    assert body["type"] == "FeatureCollection"
    assert body["features"], "fixture bundle has D07 districts"
    first = body["features"][0]
    assert first["geometry"]["type"] in {"Polygon", "MultiPolygon"}
    assert len(first["properties"]["label_point"]) == 2

    again = client.get(
        "/api/v1/layers/districts", headers={"If-None-Match": districts.headers["etag"]}
    )
    assert again.status_code == 304

    transit = client.get("/api/v1/layers/transit").json()
    assert {f["properties"]["kind"] for f in transit["features"]} <= {"tram", "bus"}
    assert client.get("/api/v1/layers/roads").status_code == 422


def test_d12_tender_rent_reaches_the_cost_metric_but_is_never_scored(
    client: TestClient, imported: Engine, tmp_path: Path
) -> None:
    url = "https://www.zagreb.hr/natjecaj-za-zakup/1234"
    d12 = (
        "space_id;monthly_rent_eur;tender_url;checked_at;profile;tender_active;evidence_note\n"
        f"4763;1.250,00;{url};2026-10-27;;da;Natječaj objavljen 17.02.2025., R.br. 27\n"
        "4010;;;;;;\n"
    ).encode()
    imp = Importer(imported, fx.registry(), tmp_path / "raw")
    import_ok(imp, "D12", write_file(tmp_path, "d12.csv", d12))
    built = build_bundle(imported, "with-tenders")
    assert built.report["spaces"]["with_tender_rent"] == 1
    activate_bundle(imported, built.bundle_id)

    cost = client.get("/api/v1/spaces/4763", params={"profile": "cafe"}).json()["metrics"]["cost"]
    assert (cost["value"], cost["unit"], cost["reason"]) == (1250.0, "eur_month", None)
    assert cost["detail"]["tender_url"] == url
    assert cost["detail"]["note"] == "Natječaj objavljen 17.02.2025., R.br. 27"
    assert cost["source_version_ids"]
    other = client.get("/api/v1/spaces/4010", params={"profile": "office"}).json()
    assert other["metrics"]["cost"]["reason"] == "cost_not_configured"

    ranked = client.post("/api/v1/rankings", json=_request(client, ["4763", "4010"]))
    assert ranked.status_code == 201, ranked.json()
    for item in ranked.json()["items"]:
        assert "cost" not in item["contributions"]


def test_competitors_are_listed_by_profile_but_never_scored(client: TestClient) -> None:
    bundle = client.get("/api/v1/status").json()["active_bundle_id"]
    url = "/api/v1/spaces/4763/competitors"
    cafe = client.get(url, params={"dataset_bundle_id": bundle, "profile": "cafe"}).json()
    assert [i["name"] for i in cafe["items"]] == ["Kavana Trg"]
    assert (cafe["count"], cafe["coverage_status"], cafe["reason"]) == (
        1,
        "unchecked",
        "coverage_unchecked",
    )
    assert cafe["counts_by_category"] == {"cafe": 1}
    assert 0 < cafe["items"][0]["distance_m"] < 100
    assert "OSM" in cafe["warnings"][0]

    bakery = client.get(url, params={"dataset_bundle_id": bundle, "profile": "food_takeaway"})
    assert [i["name"] for i in bakery.json()["items"]] == ["Pekara"]
    nearby = client.get(url, params={"dataset_bundle_id": bundle}).json()
    assert {i["name"] for i in nearby["items"]} == {"Kavana Trg", "Pekara"}, "disused is left out"
    distances = [i["distance_m"] for i in nearby["items"]]
    assert distances == sorted(distances)

    detail = client.get("/api/v1/spaces/4763", params={"profile": "cafe"}).json()
    assert detail["metrics"]["competition"]["value"] is None

    missing = client.get(
        "/api/v1/spaces/10422/competitors", params={"dataset_bundle_id": bundle}
    ).json()
    assert (missing["count"], missing["reason"], missing["items"]) == (
        None,
        "missing_coordinate",
        [],
    )
    stale = client.get(url, params={"dataset_bundle_id": str(uuid.uuid4())})
    assert stale.status_code == 409


@pytest.mark.parametrize("radius", ["500", "1000"])
def test_radius_query_is_accepted_as_text(client: TestClient, radius: str) -> None:
    bundle = client.get("/api/v1/status").json()["active_bundle_id"]
    detail = client.get("/api/v1/spaces/4763", params={"profile": "cafe", "radius_m": radius})
    assert detail.status_code == 200 and detail.json()["radius_m"] == int(radius)
    nearby = client.get(
        "/api/v1/spaces/4763/competitors",
        params={"dataset_bundle_id": bundle, "radius_m": radius},
    )
    assert nearby.status_code == 200 and nearby.json()["radius_m"] == int(radius)
    bad = client.get("/api/v1/spaces/4763", params={"profile": "cafe", "radius_m": "750"})
    assert bad.status_code == 422


def test_description_tags_need_review_and_only_approved_are_public(
    client: TestClient, imported: Engine, owner: Engine
) -> None:
    first = tag_descriptions(imported)
    assert first["proposed"] > 0
    assert tag_descriptions(imported)["proposed"] == 0, "re-running keeps existing rows"

    before = client.get("/api/v1/spaces/4763", params={"profile": "cafe"}).json()
    assert before["description_tags"] == []
    assert before["description_tags_pending"] == 2  # basement + room_count

    rows = list(csv.DictReader(io.StringIO(review_template_csv(imported)), delimiter=";"))
    mine = {r["tag"]: r for r in rows if r["space_id"] == "4763"}
    assert mine["basement"]["evidence"] == "podzemnom"
    assert mine["basement"]["description"] == "dvije prostorije u podzemnom objektu"

    bad = f"description_tag_id;decision;reviewer\n{mine['basement']['description_tag_id']};da;\n"
    assert import_review(imported, bad.encode()).errors, "reviewer initials are required"
    assert (
        client.get("/api/v1/spaces/4763", params={"profile": "cafe"}).json()[
            "description_tags_pending"
        ]
        == 2
    ), "an invalid file writes nothing"

    decisions = (
        "description_tag_id;decision;reviewer;review_note\n"
        f"{mine['basement']['description_tag_id']};da;LM;\n"
        f"{mine['room_count']['description_tag_id']};ne;LM;dvije prostorije su jedna cjelina\n"
    )
    outcome = import_review(imported, decisions.encode())
    assert (outcome.approved, outcome.rejected, outcome.errors) == (1, 1, [])
    assert import_review(imported, decisions.encode()).not_pending == 2

    after = client.get("/api/v1/spaces/4763", params={"profile": "cafe"}).json()
    assert [(t["tag"], t["label"], t["method"]) for t in after["description_tags"]] == [
        ("basement", "Podrum ili suteren", "rule")
    ]
    assert after["description_tags_pending"] == 0
    assert "evidence" not in after["description_tags"][0]

    with pytest.raises(ProgrammingError, match="permission denied"), imported.begin() as conn:
        conn.execute(text("UPDATE prostoriq.description_tag SET evidence = 'x'"))
