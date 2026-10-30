from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.ranking.config import CRITERIA, load_profiles
from app.ranking.scoring import (
    BasisConflict,
    Candidate,
    NoActiveCriteriaError,
    RankingResult,
    RawMetric,
    q8,
    rank,
    utility,
)
from app.ranking.status import Assessment, evaluate
from tests import fixtures as fx

PROFILES = load_profiles(fx.CONFIG_DIR)
K = PROFILES.constants
D = Decimal


def _m(value: float | None, reason: str | None = None) -> RawMetric:
    if value is None:
        return RawMetric(None, reason or "location_not_confirmed")
    return RawMetric(D(str(value)))


def _space_4763(**overrides: float | None) -> Candidate:
    """Specification v3 control example: Trg Ante Starčevića 7."""
    values: dict[str, float | None] = {
        "transit": 147,
        "universities": 6,
        "culture": 10,
        "parking": 315,
        "schools": 2,
        "area": 66.5,
        "street": 1,
    }
    values.update(overrides)
    metrics = {k: _m(v) for k, v in values.items()}
    metrics["competition"] = RawMetric(None, "coverage_not_reviewed")
    metrics["cost"] = RawMetric(None, "cost_unavailable")
    return Candidate("4763", metrics)


def _rank(
    candidates: list[Candidate],
    profile: str = "cafe",
    *,
    competition: bool = True,
    weights: dict[str, Decimal] | None = None,
    choice: str | None = None,
) -> RankingResult | BasisConflict:
    p = PROFILES.get(profile)
    w = dict(weights or p.weights)
    if not competition:
        w["competition"] = D(0)
    return rank(
        candidates,
        weights=w,
        default_weights=p.weights if weights is None else weights,
        target_area_m2=p.target_area_m2,
        constants=K,
        choice=choice,  # type: ignore[arg-type]
    )


def _ok(result: RankingResult | BasisConflict) -> RankingResult:
    assert isinstance(result, RankingResult), result
    return result


def test_control_example_cafe_4763_scores_90_55() -> None:
    result = _ok(_rank([_space_4763()], competition=False))
    item = result.items[0]
    assert item.score == D("90.55357143")
    assert f"{item.score:.2f}" == "90.55"
    assert item.rank == 1
    assert result.criteria_used == [
        "transit",
        "universities",
        "culture",
        "parking",
        "area",
        "street",
    ]
    # TR02: competition switched off, cost unavailable.
    assert result.coverage_active == D("77.7778")
    assert result.coverage_default == D("70")
    assert ("cost", "cost_not_configured") in result.excluded_criteria
    assert sum(item.contributions.values()) == pytest.approx(item.score, abs=D("0.0000001"))


def test_competition_enabled_but_unreviewed_stays_in_active_denominator() -> None:
    result = _ok(_rank([_space_4763()]))
    assert result.items[0].score == D("90.55357143")
    assert result.coverage_active == D("70")
    assert ("competition", "coverage_unchecked") in result.excluded_criteria


@pytest.mark.parametrize(
    ("profile", "score", "coverage_active"),
    [
        ("cafe", "90.55357143", "70"),
        ("office", "84.41071429", "70"),
        ("retail", "82.68489583", "80"),
        ("food_takeaway", "72.36904762", "70"),
        ("personal_care", "69.89102564", "65"),
        ("education", "61.97135417", "80"),
        ("workshop", "87.07812500", "80"),
    ],
)
def test_reference_score_per_profile(profile: str, score: str, coverage_active: str) -> None:
    result = _ok(_rank([_space_4763()], profile))
    assert result.items[0].score == D(score)
    assert result.coverage_active == D(coverage_active)


def test_tr01_removing_a_criterion_for_everyone_changes_the_basis() -> None:
    weights = {c: D(0) for c in CRITERIA} | {"transit": D(60), "universities": D(40)}
    both = Candidate("1", {"transit": _m(400), "universities": _m(5)})
    first = _ok(_rank([both], weights=weights))
    assert first.items[0].score == D("70.00000000")
    assert first.items[0].utilities == {"transit": D("0.5"), "universities": D("1")}

    without = Candidate("1", {"transit": _m(400), "universities": _m(None, "source_missing")})
    second = _ok(_rank([without], weights=weights))
    assert second.items[0].score == D("50.00000000")
    assert second.coverage_default == D("60")
    assert ("universities", "source_unavailable") in second.excluded_criteria
    assert second.criteria_used != first.criteria_used


def test_tr03_office_without_cost_and_competition() -> None:
    result = _ok(_rank([_space_4763()], "office"))
    assert result.coverage_active == D("70")
    assert result.coverage_default == D("70")


def test_tr04_ties_break_on_numeric_id() -> None:
    same = {"transit": _m(100), "universities": _m(1)}
    result = _ok(_rank([Candidate("10", same), Candidate("9", same)]))
    assert [(i.space_id, i.rank) for i in result.items] == [("9", 1), ("10", 2)]


def test_scores_compared_on_eight_decimals_half_up() -> None:
    assert q8(D("1.000000005")) == D("1.00000001")
    assert q8(D("1.000000004999")) == D("1.00000000")


def test_partial_criterion_is_a_basis_conflict_not_a_silent_choice() -> None:
    a = _space_4763()
    b = Candidate("5", {**a.metrics, "transit": _m(None, "location_not_confirmed")})
    conflict = _rank([a, b])
    assert isinstance(conflict, BasisConflict)
    assert conflict.missing_by_space == {"5": ["transit"]}
    assert "transit" not in conflict.proposed_criteria
    assert conflict.partial_criteria == ["transit"]


def test_confirmed_common_criteria_ranks_everyone_with_lower_coverage() -> None:
    a = _space_4763()
    b = Candidate("5", {**a.metrics, "transit": _m(None, "location_not_confirmed")})
    result = _ok(_rank([a, b], choice="common_criteria"))
    assert "transit" not in result.criteria_used
    assert ("transit", "partial_coverage") in result.excluded_criteria
    assert len([i for i in result.items if i.rank]) == 2
    assert result.coverage_default == D("50")


def test_confirmed_remove_incomplete_drops_only_the_incomplete() -> None:
    a = _space_4763()
    b = Candidate("5", {**a.metrics, "transit": _m(None, "location_not_confirmed")})
    result = _ok(_rank([a, b], choice="remove_incomplete"))
    assert result.removed_space_ids == ["5"]
    assert [i.space_id for i in result.items] == ["4763"]
    assert result.items[0].score == D("90.55357143")


def test_all_weights_zero_is_rejected() -> None:
    with pytest.raises(NoActiveCriteriaError):
        _rank([_space_4763()], weights={c: D(0) for c in CRITERIA})


def test_no_common_criteria_gives_null_score_with_reason() -> None:
    weights = {c: D(0) for c in CRITERIA} | {"transit": D(100)}
    nothing = Candidate("1", {"transit": _m(None, "location_not_confirmed")})
    result = _ok(_rank([nothing], weights=weights))
    assert result.items[0].score is None
    assert result.items[0].reason == "no_common_criteria"
    assert result.coverage_active == D("0")


@pytest.mark.parametrize(
    ("criterion", "value", "expected"),
    [
        ("transit", 0, "1"),
        ("transit", 800, "0"),
        ("transit", 2000, "0"),
        ("parking", 600, "0.5"),
        ("universities", 10, "1"),
        ("culture", 5, "0.5"),
        ("schools", 3, "0.5"),
        ("area", 120, "0"),
        ("area", 30, "0.5"),
        ("street", 0, "0.4"),
    ],
)
def test_utilities(criterion: str, value: float, expected: str) -> None:
    u = utility(criterion, D(str(value)), target_area_m2=D(60), constants=K)
    assert u == D(expected)


def test_tg04_competition_density_uses_the_full_circle() -> None:
    u = utility("competition", D(8), target_area_m2=D(60), constants=K, radius_m=500)
    density = 8 / (3.141592653589793 * 0.25)
    assert float(u) == pytest.approx(1 / (1 + density / 20))


NOW = datetime(2026, 10, 30, 12, tzinfo=UTC)


def test_status_without_assessment_is_conditional() -> None:
    s = evaluate("regular", None, now=NOW)
    assert s["candidate_status"] == "conditional"
    assert "tender_not_confirmed" in s["reasons"]


def test_unfit_inventory_is_always_excluded() -> None:
    yes = Assessment("yes", "yes", "yes", "yes", NOW - timedelta(hours=1))
    assert evaluate("unfit", yes, now=NOW)["candidate_status"] == "excluded"


def test_one_confirmed_no_excludes() -> None:
    a = Assessment(tender_active="no", checked_at=NOW)
    s = evaluate("regular", a, now=NOW)
    assert s["candidate_status"] == "excluded" and "no_active_tender" in s["reasons"]


def test_all_yes_is_ready_until_seven_days() -> None:
    fresh = Assessment("yes", "yes", "yes", "yes", NOW - timedelta(hours=167))
    assert evaluate("regular", fresh, now=NOW)["candidate_status"] == "ready"
    stale = Assessment("yes", "yes", "yes", "yes", NOW - timedelta(hours=168))
    s = evaluate("regular", stale, now=NOW)
    assert s["candidate_status"] == "conditional"
    assert s["reasons"][0] == "status_review_due"
    assert s["tender_active"] == "unknown"


def test_profiles_config_is_consistent() -> None:
    assert set(PROFILES.profiles) == {
        "cafe",
        "office",
        "retail",
        "food_takeaway",
        "personal_care",
        "education",
        "workshop",
    }
    hashes = {p.config_sha256 for p in PROFILES.profiles.values()}
    assert len(hashes) == 7
