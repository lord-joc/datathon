"""AI endpoints (ADR21): a local model, suggestions only, never part of any score."""

import logging
import threading
from datetime import UTC, datetime
from functools import lru_cache

from fastapi import APIRouter

from app.ai.brief import read_brief
from app.ai.model import ModelError, config_sha256, load_ai_config, shared_embedder
from app.ai.profiles import ProfileMatcher
from app.api.v1 import market as market_presenter
from app.api.v1.schemas import (
    BriefDistrict,
    BriefPriority,
    BusinessBrief,
    ContextCard,
    ProfileCandidate,
    ProfileSuggestion,
    ProfileSuggestionRequest,
)
from app.core.errors import ProblemError
from app.db import public as q
from app.db.engine import get_engine
from app.gis.district_names import mentioned_districts

router = APIRouter(tags=["ai"])
log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _matcher() -> ProfileMatcher:
    return ProfileMatcher(shared_embedder(), load_ai_config()["profile_suggestion"])


def preload() -> None:
    """Warm the model without blocking start-up; a missing model only logs a warning."""

    def run() -> None:
        try:
            _matcher()
            log.info("ai_model_ready")
        except ModelError:
            log.warning("ai_model_missing")

    threading.Thread(target=run, name="ai-preload", daemon=True).start()


@router.post(
    "/profile-suggestions",
    response_model=ProfileSuggestion,
    summary="Prijedlog djelatnosti iz slobodnog opisa (lokalni MiniLM)",
)
def suggest_profile(body: ProfileSuggestionRequest) -> ProfileSuggestion:
    """The description is not stored or logged; only the answer goes back to the user."""
    return _suggest(body.description)


def _suggest(description: str) -> ProfileSuggestion:
    try:
        matcher = _matcher()
    except ModelError as exc:
        raise ProblemError(503, "AI_NOT_READY", "Lokalni model trenutno nije dostupan.") from exc
    result = matcher.suggest(description)
    config = load_ai_config()
    return ProfileSuggestion(
        suggested_profile=result.profile,
        status=result.status,
        candidates=[
            ProfileCandidate(
                profile=c.profile,
                similarity=c.similarity,
                matched_example=c.example,
            )
            for c in result.candidates
        ],
        min_similarity=result.min_similarity,
        min_margin=result.min_margin,
        method=str(config["profile_suggestion"]["method"]),
        model_id=str(config["model_id"]),
        model_revision=str(config["model_revision"]),
        config_sha256=config_sha256(config),
    )


def _relevant_notices(
    description: str, cards: list[ContextCard], min_similarity: float, limit: int
) -> list[ContextCard]:
    """Approved cards closest in meaning to the description. Similarity only orders them."""
    if not cards:
        return []
    vectors = shared_embedder().embed([description, *[c.summary for c in cards]])
    similarities = vectors[1:] @ vectors[0]
    ranked = sorted(zip(similarities, cards, strict=True), key=lambda x: -float(x[0]))
    return [card for sim, card in ranked if float(sim) >= min_similarity][:limit]


@router.post(
    "/business-brief",
    response_model=BusinessBrief,
    summary="Osobni polazni prijedlog iz opisa djelatnosti (lokalno, korisnik potvrđuje)",
)
def business_brief(body: ProfileSuggestionRequest) -> BusinessBrief:
    """The description is not stored or logged. Proposals never apply on their own (ADR24)."""
    suggestion = _suggest(body.description)
    facts = read_brief(body.description)
    settings = load_ai_config()["business_brief"]
    profile = suggestion.suggested_profile or suggestion.candidates[0].profile
    districts: list[BriefDistrict] = []
    notices: list[ContextCard] = []
    with get_engine().connect() as conn:
        bundle = q.active_bundle(conn)
        if bundle is not None:
            known = q.districts(conn, bundle)
            names = dict(known)
            districts = [
                BriefDistrict(district_id=d, name=names[d], words=w)
                for d, w in mentioned_districts(body.description, known)
            ]
            cards = [
                market_presenter.card(r) for r in q.context_cards(conn, profile, datetime.now(UTC))
            ]
            notices = _relevant_notices(
                body.description,
                cards,
                float(settings["notice_min_similarity"]),
                int(settings["max_notices"]),
            )
    return BusinessBrief(
        suggestion=suggestion,
        area_m2=facts.area_m2,
        budget_eur=facts.budget_eur,
        districts=districts,
        priorities=[
            BriefPriority(criterion=p.criterion, level=p.level, words=p.evidence)
            for p in facts.priorities
        ],
        notices=notices,
    )
