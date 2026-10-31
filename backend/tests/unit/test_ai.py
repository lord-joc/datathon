"""Profile suggestion rules, model file checks and the API answer (ADR21)."""

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest
from fastapi.testclient import TestClient

from app.ai import model as ai_model
from app.ai.model import ModelError, _allowed, _git_blob_sha1, _matches, load_ai_config
from app.ai.profiles import ProfileMatcher, calibrate
from app.api.v1 import ai as ai_route
from app.main import create_app

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"


class FakeEmbedder:
    """Maps each known text to a fixed direction, so similarities are exact and readable."""

    model_id = "fake"
    model_revision = "0"

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self.vectors = vectors

    def embed(self, texts: list[str]) -> npt.NDArray[np.float32]:
        rows = [np.array(self.vectors[t], dtype=np.float32) for t in texts]
        return np.stack([r / np.linalg.norm(r) for r in rows])


SETTINGS: dict[str, Any] = {
    "examples": {"cafe": ["kafić"], "office": ["ured"], "retail": ["trgovina"]},
    "min_similarity": 0.5,
    "min_margin": 0.1,
    "max_candidates": 3,
}
VECTORS = {
    "kafić": [1, 0, 0],
    "ured": [0, 1, 0],
    "trgovina": [0, 0, 1],
    "mala kavana": [0.9, 0.1, 0],  # clearly a café
    "kafić ili ured": [1, 1, 0],  # equally close to two profiles
    "autopraonica": [0.3, 0.3, 0.3],  # close to nothing
}


def _matcher() -> ProfileMatcher:
    return ProfileMatcher(FakeEmbedder(VECTORS), SETTINGS)  # type: ignore[arg-type]


def test_clear_description_is_suggested_with_all_candidates() -> None:
    result = _matcher().suggest("mala kavana")
    assert (result.status, result.profile) == ("suggested", "cafe")
    assert [c.profile for c in result.candidates] == ["cafe", "office", "retail"]
    assert result.candidates[0].example == "kafić"


def test_tie_between_profiles_is_unsupported_not_guessed() -> None:
    result = _matcher().suggest("kafić ili ured")
    assert (result.status, result.profile) == ("unsupported", None)
    assert result.candidates[0].similarity == pytest.approx(result.candidates[1].similarity)


def test_low_similarity_is_unsupported() -> None:
    assert _matcher().suggest("autopraonica").status == "unsupported"


def test_calibration_never_prefers_wrong_suggestions() -> None:
    items = [
        {"text": "mala kavana", "label": "cafe"},
        {"text": "autopraonica", "label": "unsupported"},
        {"text": "kafić ili ured", "label": "unsupported"},
    ]
    result = calibrate(_matcher(), items)
    assert result.supported_correct == 1 and result.supported_wrong == 0
    assert result.unsupported_rejected == 2


def test_config_examples_cover_every_profile_and_eval_is_separate() -> None:
    config = load_ai_config(CONFIG_DIR)
    examples = config["profile_suggestion"]["examples"]
    profiles = json.loads((CONFIG_DIR / "profiles.json").read_text(encoding="utf-8"))
    assert set(examples) == {p["code"] for p in profiles["profiles"]}
    evaluation = json.loads((CONFIG_DIR / "ai_eval_profiles.json").read_text(encoding="utf-8"))
    used = {t for texts in examples.values() for t in texts}
    assert not used & {i["text"] for i in evaluation["items"]}, "eval texts leaked into examples"
    assert config["profile_suggestion"]["evaluation"]["texts"] == len(evaluation["items"])


def test_file_pins_are_checked(tmp_path: Path) -> None:
    data = b'{"max_seq_length": 128}'
    path = tmp_path / "f.json"
    path.write_bytes(data)
    assert _matches(path, {"size": len(data), "git_sha1": _git_blob_sha1(data)})
    assert _matches(path, {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    assert not _matches(path, {"size": len(data), "sha256": "0" * 64})
    assert not _matches(path, {"size": len(data) + 1, "git_sha1": _git_blob_sha1(data)})
    # Known value of `git hash-object` for an empty file.
    assert _git_blob_sha1(b"") == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"


@pytest.mark.parametrize(
    ("url", "ok"),
    [
        ("https://huggingface.co/x/resolve/abc/model.onnx", True),
        ("https://cas-bridge.xethub.hf.co/xet/abc", True),
        ("http://huggingface.co/x", False),
        ("https://huggingface.co.evil.example/x", False),
        ("https://evilhf.co/x", False),
        ("https://127.0.0.1/x", False),
    ],
)
def test_download_hosts(url: str, ok: bool) -> None:
    assert _allowed(url) is ok


def test_missing_model_is_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(ModelError, match="ai-fetch-model"):
        ai_model.verify_files(load_ai_config(CONFIG_DIR), tmp_path)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(ai_route, "_matcher", _matcher)
    return TestClient(create_app())


def test_api_answer_is_transparent_and_needs_confirmation(client: TestClient) -> None:
    body = client.post("/api/v1/profile-suggestions", json={"description": "mala   kavana"})
    assert body.status_code == 200
    data = body.json()
    assert (data["status"], data["suggested_profile"], data["requires_confirmation"]) == (
        "suggested",
        "cafe",
        True,
    )
    assert data["candidates"][0] == {
        "profile": "cafe",
        "similarity": pytest.approx(0.9939, abs=1e-4),
        "matched_example": "kafić",
    }
    assert data["model_revision"] and len(data["config_sha256"]) == 64


@pytest.mark.parametrize("description", ["abc", "    a    ", "x" * 501])
def test_api_rejects_short_or_long_text(client: TestClient, description: str) -> None:
    response = client.post("/api/v1/profile-suggestions", json={"description": description})
    assert response.status_code == 422


def test_api_without_model_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing() -> ProfileMatcher:
        raise ModelError("nema modela")

    monkeypatch.setattr(ai_route, "_matcher", missing)
    response = TestClient(create_app()).post(
        "/api/v1/profile-suggestions", json={"description": "mala kavana"}
    )
    assert response.status_code == 503 and response.json()["code"] == "AI_NOT_READY"


def _real_model_ready() -> bool:
    try:
        ai_model.verify_files(load_ai_config(CONFIG_DIR))
    except ModelError:
        return False
    return True


@pytest.mark.skipif(not _real_model_ready(), reason="MiniLM not downloaded (ai-fetch-model)")
def test_real_model_suggests_obvious_profiles() -> None:
    config = load_ai_config(CONFIG_DIR)
    matcher = ProfileMatcher(ai_model.load_embedder(config), config["profile_suggestion"])
    assert matcher.suggest("Želim otvoriti malu kavanu").profile == "cafe"
    assert matcher.suggest("Igraonica za djecu do šest godina").profile == "education"
    assert matcher.suggest("Autopraonica").status == "unsupported"
