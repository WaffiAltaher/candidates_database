import json
import os
from pathlib import Path

os.environ.setdefault("AUTH_SECRET", "test-secret-that-is-long-enough-123")
os.environ.setdefault("ALLOWED_ORIGIN", "*")
os.environ.setdefault(
    "AUTH_USERS",
    json.dumps({"admin": "scrypt$16384$8$1$Y2FuZGlkYXRlcy1kZXYtMQ==$aYz/67aCRaL8SQxCWfYwt/nBlX7aSdAl8vE7H8hoQo8="}),
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import container.main as main_module  # noqa: E402

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    main_module.login_limiter.reset("admin")
    return TestClient(main_module.app)


def test_index_served_at_root(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert (FRONTEND / "index.html").read_text(encoding="utf-8") in resp.text


@pytest.mark.parametrize("path", ["/login.html", "/candidate.html", "/app.js"])
def test_frontend_files_served(client, path):
    assert client.get(path).status_code == 200


def test_app_js_uses_same_origin(client):
    assert "const API_BASE = '';" in client.get("/app.js").text


def test_api_route_wins_over_static_mount(client):
    assert client.get("/candidates").status_code == 401


def test_login_still_works(client):
    resp = client.post("/login", json={"username": "admin", "password": "admin"})
    assert resp.status_code == 200
    assert "token" in resp.json()


def test_unknown_file_is_404(client):
    assert client.get("/does-not-exist.html").status_code == 404
