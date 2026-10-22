import json
import os

import pytest

os.environ.setdefault("AUTH_SECRET", "test-secret-that-is-long-enough-123")
os.environ.setdefault("ALLOWED_ORIGIN", "*")
os.environ.setdefault(
    "AUTH_USERS",
    json.dumps({"admin": "scrypt$16384$8$1$Y2FuZGlkYXRlcy1kZXYtMQ==$aYz/67aCRaL8SQxCWfYwt/nBlX7aSdAl8vE7H8hoQo8="}),
)

from fastapi.testclient import TestClient  # noqa: E402

import container.main as main_module  # noqa: E402
from candidates.login_limiter import LoginLimiter  # noqa: E402


class FakeClock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


def test_fifth_failure_blocks():
    limiter = LoginLimiter(clock=FakeClock())
    for _ in range(4):
        limiter.record_failure("a")
    assert limiter.retry_after("a") == 0
    limiter.record_failure("a")
    assert limiter.retry_after("a") > 0


def test_retry_after_value_and_expiry():
    clock = FakeClock()
    limiter = LoginLimiter(clock=clock)
    for t in (0, 10, 20, 30, 40):
        clock.now = t
        limiter.record_failure("a")
    clock.now = 100
    assert limiter.retry_after("a") == 800
    clock.now = 901
    assert limiter.retry_after("a") == 0


def test_reset_and_isolation():
    limiter = LoginLimiter(clock=FakeClock())
    for _ in range(5):
        limiter.record_failure("alice")
    assert limiter.retry_after("bob") == 0
    limiter.reset("alice")
    assert limiter.retry_after("alice") == 0


def test_memory_is_bounded():
    clock = FakeClock()
    limiter = LoginLimiter(max_failures=1, clock=clock)
    for i in range(10_001):
        limiter.record_failure(f"u{i}")
    clock.now = 1000
    limiter.record_failure("late")
    assert len(limiter._failures) <= 2


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main_module, "login_limiter", LoginLimiter())
    return TestClient(main_module.app)


def _login(client, user, password):
    return client.post("/login", json={"username": user, "password": password})


def test_blocked_after_five_failures(client):
    for _ in range(5):
        assert _login(client, "admin", "wrong").status_code == 401
    resp = _login(client, "admin", "admin")
    assert resp.status_code == 429
    assert 1 <= int(resp.headers["Retry-After"]) <= 900
    assert resp.json()["error"] == "Too many failed attempts. Try again later."


def test_success_resets_count(client):
    for _ in range(4):
        assert _login(client, "admin", "wrong").status_code == 401
    assert _login(client, "admin", "admin").status_code == 200
    for _ in range(4):
        assert _login(client, "admin", "wrong").status_code == 401


def test_other_user_not_blocked(client):
    for _ in range(5):
        _login(client, "admin", "wrong")
    assert _login(client, "someone_else", "x").status_code == 401


def test_missing_username_is_400(client):
    assert client.post("/login", json={"password": "x"}).status_code == 400
