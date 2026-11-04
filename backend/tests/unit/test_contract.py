"""The implemented public API and docs/contracts/openapi.yaml must not drift apart."""

from pathlib import Path
from typing import Any, get_args

import pytest
import yaml  # type: ignore[import-untyped]
from fastapi.routing import APIRoute
from pydantic import BaseModel

from app.api.v1 import schemas
from app.main import create_app
from app.ranking.config import CRITERIA

CONTRACT = Path(__file__).resolve().parents[3] / "docs" / "contracts" / "openapi.yaml"


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    return data


def test_every_implemented_route_is_in_the_contract(contract: dict[str, Any]) -> None:
    app = create_app()
    implemented = {
        (
            method.lower(),
            route.path.replace("{space_id}", "{id}").replace("{ranking_run_id}", "{id}"),
        )
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/api/v1/")
        for method in route.methods or ()
        if method != "HEAD"
    }
    documented = {(method, path) for path, ops in contract["paths"].items() for method in ops}
    missing = {r for r in implemented if r not in documented and r[1] != "/api/v1/health"}
    assert not missing, missing


@pytest.mark.parametrize(
    ("model", "name"),
    [
        (schemas.RankingRequest, "RankingRequest"),
        (schemas.Weights, "Weights"),
        (schemas.Profile, "Profile"),
        (schemas.Metric, "Metric"),
        (schemas.SpaceDetail, "SpaceDetail"),
        (schemas.SpaceSummary, "SpaceSummary"),
        (schemas.RankingResponse, "RankingResponse"),
        (schemas.RankingItem, "RankingItem"),
        (schemas.CompetitionResponse, "CompetitionResponse"),
        (schemas.Competitor, "Competitor"),
        (schemas.ProfileSuggestionRequest, "ProfileSuggestionRequest"),
        (schemas.ProfileSuggestion, "ProfileSuggestion"),
        (schemas.ProfileCandidate, "ProfileCandidate"),
        (schemas.DescriptionTag, "DescriptionTag"),
        (schemas.ContextCard, "ContextCard"),
        (schemas.ContextList, "ContextList"),
        (schemas.BusinessBrief, "BusinessBrief"),
        (schemas.MarketSummary, "MarketSummary"),
        (schemas.MarketDistrict, "MarketDistrict"),
        (schemas.RentStats, "RentStats"),
    ],
)
def test_model_fields_match_contract(
    contract: dict[str, Any], model: type[BaseModel], name: str
) -> None:
    documented = set(contract["components"]["schemas"][name]["properties"])
    assert set(model.model_fields) == documented


def test_profile_and_criterion_enums_match(contract: dict[str, Any]) -> None:
    c = contract["components"]["schemas"]
    assert set(c["Profile"]["properties"]["profile"]["enum"]) == set(get_args(schemas.ProfileCode))
    assert c["Weights"]["required"] == list(CRITERIA)
