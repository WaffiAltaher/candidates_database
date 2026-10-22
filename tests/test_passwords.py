import hashlib
import os

os.environ.setdefault("AUTH_SECRET", "test-secret-that-is-long-enough-123")
os.environ.setdefault("ALLOWED_ORIGIN", "*")

import pytest  # noqa: E402

from candidates import helpers  # noqa: E402
from candidates.passwords import check_password, hash_password  # noqa: E402

VECTOR = "scrypt$16384$8$1$AAECAwQFBgcICQoLDA0ODw==$11kKyiyYAc8G7rp3KmncMc44YlkdllIqxOa7pq0fMaU="


def test_vector_verifies():
    assert check_password("correct horse battery staple", VECTOR)
    assert not check_password("correct horse battery stapler", VECTOR)


def test_hash_round_trip():
    h = hash_password("x")
    assert h.startswith("scrypt$16384$8$1$")
    assert check_password("x", h)
    assert hash_password("x") != hash_password("x")


@pytest.mark.parametrize(
    "stored",
    [
        hashlib.sha256(b"admin").hexdigest(),
        "",
        "scrypt$1$2$3",
        "bcrypt$16384$8$1$AAAA$BBBB",
        "scrypt$x$8$1$AAAA$BBBB",
        "scrypt$16384$8$1$!!!$BBBB",
    ],
)
def test_malformed_returns_false(stored):
    assert check_password("admin", stored) is False


def test_verify_password(monkeypatch):
    monkeypatch.setattr(
        helpers,
        "AUTH_USERS",
        {"alice": VECTOR, "old": hashlib.sha256(b"admin").hexdigest()},
    )
    assert helpers.verify_password("alice", "correct horse battery staple")
    assert not helpers.verify_password("alice", "wrong")
    assert not helpers.verify_password("nobody", "x")
    assert not helpers.verify_password("old", "admin")
