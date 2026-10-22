import base64
import hashlib
import hmac
import json
import logging
import os

import pytest

os.environ.setdefault("AUTH_SECRET", "test-secret-that-is-long-enough-123")
os.environ.setdefault("ALLOWED_ORIGIN", "*")
os.environ.setdefault(
    "AUTH_USERS",
    json.dumps({"admin": "scrypt$16384$8$1$Y2FuZGlkYXRlcy1kZXYtMQ==$aYz/67aCRaL8SQxCWfYwt/nBlX7aSdAl8vE7H8hoQo8="}),
)

from fastapi.testclient import TestClient  # noqa: E402

import candidates.helpers as helpers  # noqa: E402
import container.main as main_module  # noqa: E402
from candidates.helpers import create_token, validate_token  # noqa: E402
from candidates.passwords import hash_password  # noqa: E402

ALICE = "scrypt$16384$8$1$AAECAwQFBgcICQoLDA0ODw==$11kKyiyYAc8G7rp3KmncMc44YlkdllIqxOa7pq0fMaU="
BOB = "scrypt$16384$8$1$Y2FuZGlkYXRlcy1kZXYtMQ==$aYz/67aCRaL8SQxCWfYwt/nBlX7aSdAl8vE7H8hoQo8="


def b64(name):
    return base64.urlsafe_b64encode(name.encode("utf-8")).decode().rstrip("=")


@pytest.fixture(autouse=True)
def users(monkeypatch):
    d = {"alice": ALICE, "bob": BOB}
    monkeypatch.setattr(helpers, "AUTH_USERS", d)
    return d


def test_round_trip():
    assert validate_token(create_token("alice")) == "alice"


def test_username_with_dot(users):
    users["a.b"] = BOB
    assert validate_token(create_token("a.b")) == "a.b"


def test_create_token_unknown_user():
    with pytest.raises(KeyError):
        create_token("nobody")


def test_expired(monkeypatch):
    token = create_token("alice")
    expiry = int(token.split(".")[1])
    monkeypatch.setattr(helpers.time, "time", lambda: expiry - 1)
    assert validate_token(token) == "alice"
    monkeypatch.setattr(helpers.time, "time", lambda: expiry)
    assert validate_token(token) is None


@pytest.mark.parametrize("part", ["user", "expiry", "signature"])
def test_tampered_part_rejected(part):
    user, expiry, sig = create_token("alice").split(".")
    if part == "user":
        user = b64("bob")
    elif part == "expiry":
        expiry = str(int(expiry) + 1)
    else:
        sig = sig[:-1] + ("0" if sig[-1] != "0" else "1")
    assert validate_token(f"{user}.{expiry}.{sig}") is None


def test_removed_user_ends_only_their_sessions(users):
    alice, bob = create_token("alice"), create_token("bob")
    del users["alice"]
    assert validate_token(alice) is None
    assert validate_token(bob) == "bob"


def test_password_change_ends_sessions(users):
    old = create_token("alice")
    users["alice"] = hash_password("new")
    assert validate_token(old) is None
    assert validate_token(create_token("alice")) == "alice"


def test_old_format_rejected():
    expiry = helpers.time.time() + 1000
    sig = hmac.new(helpers.AUTH_SECRET.encode(), str(int(expiry)).encode(), hashlib.sha256).hexdigest()
    assert validate_token(f"{int(expiry)}.{sig}") is None


@pytest.mark.parametrize("token", ["", "a.b.c", "!!!.1.x"])
def test_garbage(token):
    assert validate_token(token) is None


def test_endpoint(tmp_path, monkeypatch, caplog):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_READONLY", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(helpers, "_schema_ready", False)
    monkeypatch.setattr(helpers, "AUTH_USERS", {"admin": BOB, "alice": ALICE})
    main_module.login_limiter.reset("admin")
    client = TestClient(main_module.app)
    r = client.post("/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200
    token = r.json()["token"]

    with caplog.at_level(logging.INFO, logger="main"):
        ok = client.get("/candidates", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200
    assert any("user=admin" in rec.getMessage() for rec in caplog.records)

    _, expiry, sig = token.split(".")
    forged = f"{b64('alice')}.{expiry}.{sig}"
    bad = client.get("/candidates", headers={"Authorization": f"Bearer {forged}"})
    assert bad.status_code == 401
