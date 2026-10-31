"""Profile suggestion from a free-text business description (FZ25, ADR21).

Each profile has a few example sentences in config/ai_config.json. A description is embedded
with the local MiniLM and compared with every example; a profile's similarity is its best
example. The top profile is suggested only if it reaches `min_similarity` and leads the second
by `min_margin`; otherwise the answer is "unsupported". The user always confirms. Scores are
never changed by this.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np

from app.ai.model import Embedder


@dataclass(frozen=True)
class Candidate:
    profile: str
    similarity: float
    example: str


@dataclass(frozen=True)
class Suggestion:
    status: str  # "suggested" | "unsupported"
    profile: str | None
    candidates: list[Candidate]
    min_similarity: float
    min_margin: float


class ProfileMatcher:
    def __init__(self, embedder: Embedder, settings: dict[str, Any]) -> None:
        self.embedder = embedder
        self.settings = settings
        self.labels: list[tuple[str, str]] = [
            (code, text) for code, texts in settings["examples"].items() for text in texts
        ]
        self.matrix = embedder.embed([text for _, text in self.labels])

    def candidates(self, description: str) -> list[Candidate]:
        query = self.embedder.embed([description])[0]
        sims = self.matrix @ query
        best: dict[str, Candidate] = {}
        for (code, text), sim in zip(self.labels, sims, strict=True):
            if code not in best or sim > best[code].similarity:
                best[code] = Candidate(code, round(float(sim), 4), text)
        return sorted(best.values(), key=lambda c: (-c.similarity, c.profile))

    def suggest(
        self,
        description: str,
        min_similarity: float | None = None,
        min_margin: float | None = None,
    ) -> Suggestion:
        threshold = float(
            self.settings["min_similarity"] if min_similarity is None else min_similarity
        )
        margin = float(self.settings["min_margin"] if min_margin is None else min_margin)
        ranked = self.candidates(description)
        top, second = ranked[0], ranked[1]
        ok = top.similarity >= threshold and top.similarity - second.similarity >= margin
        return Suggestion(
            "suggested" if ok else "unsupported",
            top.profile if ok else None,
            ranked[: int(self.settings["max_candidates"])],
            threshold,
            margin,
        )


@dataclass(frozen=True)
class Calibration:
    min_similarity: float
    min_margin: float
    accuracy: float
    supported_correct: int
    supported_total: int
    supported_wrong: int
    unsupported_rejected: int
    unsupported_total: int


def calibrate(matcher: ProfileMatcher, items: list[dict[str, str]]) -> Calibration:
    """Grid search on the development set: a wrong suggestion costs more than an honest "no".

    Ties prefer the stricter threshold. The result is reported with the sample size; it is a
    small team-written set, so the numbers show how the rule behaves, not production accuracy.
    """
    ranked = [(item["label"], matcher.candidates(item["text"])) for item in items]
    best: tuple[float, float, float, Calibration] | None = None
    for threshold in np.round(np.arange(0.30, 0.86, 0.01), 2):
        for margin in np.round(np.arange(0.0, 0.16, 0.01), 2):
            right = wrong = rejected = 0
            for label, cands in ranked:
                ok = (
                    cands[0].similarity >= threshold
                    and cands[0].similarity - cands[1].similarity >= margin
                )
                guess = cands[0].profile if ok else "unsupported"
                if label == "unsupported":
                    rejected += guess == "unsupported"
                elif guess == label:
                    right += 1
                elif guess != "unsupported":
                    wrong += 1
            unsupported = sum(1 for label, _ in ranked if label == "unsupported")
            supported = len(ranked) - unsupported
            accuracy = (right + rejected) / len(ranked)
            cost = (right + rejected) - 2 * wrong - 2 * (unsupported - rejected)
            result = Calibration(
                float(threshold),
                float(margin),
                round(accuracy, 4),
                right,
                supported,
                wrong,
                rejected,
                unsupported,
            )
            key = (cost, float(threshold), float(margin))
            if best is None or key > best[:3]:
                best = (*key, result)
    assert best is not None
    return best[3]
