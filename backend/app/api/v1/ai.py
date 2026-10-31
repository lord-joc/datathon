"""AI endpoints (ADR21): a local model, suggestions only, never part of any score."""

import logging
import threading
from functools import lru_cache

from fastapi import APIRouter

from app.ai.model import ModelError, config_sha256, load_ai_config, shared_embedder
from app.ai.profiles import ProfileMatcher
from app.api.v1.schemas import ProfileCandidate, ProfileSuggestion, ProfileSuggestionRequest
from app.core.errors import ProblemError

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
    try:
        matcher = _matcher()
    except ModelError as exc:
        raise ProblemError(503, "AI_NOT_READY", "Lokalni model trenutno nije dostupan.") from exc
    result = matcher.suggest(body.description)
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
