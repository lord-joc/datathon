"""Rate limits (NF18): token buckets per hashed client, 429 with Retry-After."""

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.rate_limit import SALT_TTL_SECONDS, RateLimiter, Rule
from app.main import create_app


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_burst_then_per_minute_rate() -> None:
    clock = Clock()
    limiter = RateLimiter(clock)
    rule = Rule("public", per_minute=30, burst=60)
    key = limiter.client_key("203.0.113.7")
    assert all(limiter.check(key, rule) is None for _ in range(60))
    wait = limiter.check(key, rule)
    assert wait is not None and 1.9 < wait <= 2.0
    clock.now += 2
    assert limiter.check(key, rule) is None
    assert limiter.check(key, rule) is not None


def test_clients_and_rules_are_separate() -> None:
    limiter = RateLimiter(Clock())
    heavy = Rule("heavy", per_minute=10, burst=10)
    a, b = limiter.client_key("203.0.113.7"), limiter.client_key("203.0.113.8")
    assert a != b and len(a) == 16 and "203" not in a
    for _ in range(10):
        limiter.check(a, heavy)
    assert limiter.check(a, heavy) is not None
    assert limiter.check(b, heavy) is None
    assert limiter.check(a, Rule("public", 30, 60)) is None


def test_salt_rotation_changes_the_key() -> None:
    clock = Clock()
    limiter = RateLimiter(clock)
    before = limiter.client_key("203.0.113.7")
    assert limiter.client_key("203.0.113.7") == before
    clock.now += SALT_TTL_SECONDS
    assert limiter.client_key("203.0.113.7") != before


def _client(**overrides: object) -> TestClient:
    settings = Settings(**overrides)  # type: ignore[arg-type]
    return TestClient(create_app(settings))


def test_api_answers_429_with_retry_after_and_health_is_exempt() -> None:
    # An unknown route still counts, and it needs no database.
    client = _client(public_rate_limit_per_minute=2)
    statuses = [client.get("/api/v1/no-such-route").status_code for _ in range(5)]
    assert statuses[-1] == 429
    response = client.get("/api/v1/no-such-route")
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "RATE_LIMITED"
    assert int(response.headers["retry-after"]) >= 1
    assert all(client.get("/api/v1/health").status_code == 200 for _ in range(10))


def test_heavy_routes_have_their_own_smaller_budget() -> None:
    client = _client(heavy_rate_limit_per_minute=2)
    body = {"description": "kafić s terasom"}
    codes = [client.post("/api/v1/profile-suggestions", json=body).status_code for _ in range(3)]
    assert codes[-1] == 429
    assert client.get("/api/v1/no-such-route").status_code != 429


def test_limits_can_be_switched_off() -> None:
    client = _client(rate_limit_enabled=False, public_rate_limit_per_minute=1)
    assert all(client.get("/api/v1/health").status_code == 200 for _ in range(5))
    assert client.get("/api/v1/no-such-route").status_code != 429
    assert client.get("/api/v1/no-such-route").status_code != 429
