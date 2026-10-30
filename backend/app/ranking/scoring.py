"""Ranking as a pure function (master prompt §5.2, FZ07, FZ08). No I/O.

    A = criteria the user enabled with a positive weight
    C = criteria in A with a valid value for EVERY ranked candidate
    score[i]          = 100 * sum_{j in C} w_j * u_ij / sum_{j in C} w_j
    contribution[i,j] = 100 * w_j * u_ij / sum_{k in C} w_k
    coverage_active   = 100 * sum_{j in C} w_j / sum_{j in A} w_j
    coverage_default  = sum_{j in C} default_w_j

A criterion missing for all candidates is left out with a reason. A criterion missing for
only some of them is a basis conflict: nothing is chosen silently. The caller either asks
the user (409) or applies the user's confirmed choice: rank everyone on the common
criteria, or remove the incomplete candidates.

Arithmetic is Decimal; scores are compared on 8 decimals (ROUND_HALF_UP), ties go to the
numerically smaller official ID. Unknown is never zero.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Literal

from app.ranking.config import CRITERIA, RankingConstants

BasisChoice = Literal["common_criteria", "remove_incomplete"]

# 30 digits of pi: enough for 8-decimal results and identical on every platform.
_PI = Decimal("3.14159265358979323846264338328")
_ONE = Decimal(1)
_ZERO = Decimal(0)
_HUNDRED = Decimal(100)

# Reasons written by the bundle pipeline -> public reason codes of the API contract.
METRIC_REASONS = {
    "location_not_confirmed": "missing_coordinate",
    "no_feature_in_source": "data_not_available",
    "area_missing": "data_not_available",
    "source_missing": "source_unavailable",
    "coverage_not_reviewed": "coverage_unchecked",
    "position_unknown": "unknown_position",
    "cost_unavailable": "cost_not_configured",
}


class NoActiveCriteriaError(ValueError):
    """Every criterion has weight 0 (HTTP 422)."""


@dataclass(frozen=True)
class RawMetric:
    value: Decimal | None
    reason: str | None = None


@dataclass(frozen=True)
class Candidate:
    space_id: str
    metrics: Mapping[str, RawMetric]
    radius_m: int = 500


@dataclass(frozen=True)
class ScoredItem:
    space_id: str
    rank: int | None
    score: Decimal | None
    reason: str | None
    utilities: dict[str, Decimal]
    contributions: dict[str, Decimal]


@dataclass(frozen=True)
class RankingResult:
    criteria_active: list[str]
    criteria_used: list[str]
    excluded_criteria: list[tuple[str, str]]
    coverage_active: Decimal
    coverage_default: Decimal
    items: list[ScoredItem]
    removed_space_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BasisConflict:
    missing_by_space: dict[str, list[str]]
    proposed_criteria: list[str]
    partial_criteria: list[str]


def _clamp(x: Decimal) -> Decimal:
    return min(_ONE, max(_ZERO, x))


def utility(
    criterion: str,
    value: Decimal,
    *,
    target_area_m2: Decimal,
    constants: RankingConstants,
    radius_m: int = 500,
) -> Decimal:
    """Utility in [0, 1] of one known raw value."""
    with localcontext() as ctx:
        ctx.prec = 34
        if criterion == "transit":
            return _clamp(_ONE - value / constants.transit_zero_m)
        if criterion == "parking":
            return _clamp(_ONE - value / constants.parking_zero_m)
        if criterion == "universities":
            return min(value / constants.university_cap, _ONE)
        if criterion == "culture":
            return min(value / constants.culture_cap, _ONE)
        if criterion == "schools":
            return min(value / constants.school_cap, _ONE)
        if criterion == "area":
            return max(_ZERO, _ONE - abs(value - target_area_m2) / target_area_m2)
        if criterion == "street":
            return _ONE if value == _ONE else constants.other_position_utility
        if criterion == "competition":
            # Full circle, never clipped to a district (TG04). value = unique competitors.
            area_km2 = _PI * (Decimal(radius_m) / Decimal(1000)) ** 2
            density = value / area_km2
            return _ONE / (_ONE + density / constants.competition_density_scale_km2)
    raise ValueError(f"Kriterij {criterion} nema formulu korisnosti.")


def q8(value: Decimal, digits: int = 8) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)


def _public_reason(reason: str | None) -> str:
    if reason is None:
        return "data_not_available"
    return METRIC_REASONS.get(reason, reason)


def _known(candidate: Candidate, criterion: str) -> bool:
    if criterion == "cost":
        return False  # no comparable cost is published (MVP)
    metric = candidate.metrics.get(criterion)
    return metric is not None and metric.value is not None


def find_conflict(
    candidates: Sequence[Candidate], weights: Mapping[str, Decimal]
) -> BasisConflict | None:
    """Criteria known for some but not all candidates, or None when the basis is clear."""
    active = [c for c in CRITERIA if weights.get(c, _ZERO) > 0]
    partial = []
    full = []
    for criterion in active:
        known = sum(_known(c, criterion) for c in candidates)
        if 0 < known < len(candidates):
            partial.append(criterion)
        elif candidates and known == len(candidates):
            full.append(criterion)
    if not partial:
        return None
    missing = {
        c.space_id: [j for j in partial if not _known(c, j)]
        for c in candidates
        if any(not _known(c, j) for j in partial)
    }
    return BasisConflict(missing, full, partial)


def rank(
    candidates: Sequence[Candidate],
    *,
    weights: Mapping[str, Decimal],
    default_weights: Mapping[str, Decimal],
    target_area_m2: Decimal,
    constants: RankingConstants,
    choice: BasisChoice | None = None,
) -> RankingResult | BasisConflict:
    """Rank candidates. Returns a BasisConflict when a choice is needed and none was given."""
    active = [c for c in CRITERIA if weights.get(c, _ZERO) > 0]
    if not active:
        raise NoActiveCriteriaError("Barem jedan kriterij mora imati težinu veću od 0.")

    removed: list[str] = []
    conflict = find_conflict(candidates, weights)
    partial_reason: dict[str, str] = {}
    if conflict is not None:
        if choice is None:
            return conflict
        if choice == "remove_incomplete":
            removed = sorted(conflict.missing_by_space, key=int)
            candidates = [c for c in candidates if c.space_id not in conflict.missing_by_space]
        else:
            partial_reason = dict.fromkeys(conflict.partial_criteria, "partial_coverage")

    used: list[str] = []
    excluded: list[tuple[str, str]] = []
    for criterion in active:
        if criterion == "cost":
            excluded.append((criterion, "cost_not_configured"))
        elif criterion in partial_reason:
            excluded.append((criterion, partial_reason[criterion]))
        elif candidates and all(_known(c, criterion) for c in candidates):
            used.append(criterion)
        else:
            reasons = Counter(
                _public_reason(m.reason)
                for c in candidates
                if (m := c.metrics.get(criterion)) is not None
            )
            excluded.append(
                (criterion, reasons.most_common(1)[0][0] if reasons else "data_not_available")
            )

    sum_active = sum((weights[c] for c in active), _ZERO)
    sum_used = sum((weights[c] for c in used), _ZERO)
    with localcontext() as ctx:
        ctx.prec = 34
        coverage_active = _HUNDRED * sum_used / sum_active
        coverage_default = sum((default_weights.get(c, _ZERO) for c in used), _ZERO)

        scored: list[ScoredItem] = []
        for cand in candidates:
            if not used:
                scored.append(ScoredItem(cand.space_id, None, None, "no_common_criteria", {}, {}))
                continue
            utilities: dict[str, Decimal] = {}
            contributions: dict[str, Decimal] = {}
            for criterion in used:
                value = cand.metrics[criterion].value
                assert value is not None
                u = utility(
                    criterion,
                    value,
                    target_area_m2=target_area_m2,
                    constants=constants,
                    radius_m=cand.radius_m,
                )
                utilities[criterion] = u
                contributions[criterion] = _HUNDRED * weights[criterion] * u / sum_used
            score = sum(contributions.values(), _ZERO)
            scored.append(ScoredItem(cand.space_id, None, score, None, utilities, contributions))

    digits = constants.precision_digits
    ranked = sorted(
        (s for s in scored if s.score is not None),
        key=lambda s: (-q8(s.score, digits) if s.score is not None else _ZERO, int(s.space_id)),
    )
    final = [
        ScoredItem(
            s.space_id,
            position,
            q8(s.score, digits) if s.score is not None else None,
            None,
            {k: q8(v, digits) for k, v in s.utilities.items()},
            {k: q8(v, digits) for k, v in s.contributions.items()},
        )
        for position, s in enumerate(ranked, start=1)
    ]
    final += sorted((s for s in scored if s.score is None), key=lambda s: int(s.space_id))
    return RankingResult(
        criteria_active=active,
        criteria_used=used,
        excluded_criteria=excluded,
        coverage_active=q8(coverage_active, 4),
        coverage_default=q8(coverage_default, 4),
        items=final,
        removed_space_ids=removed,
    )
