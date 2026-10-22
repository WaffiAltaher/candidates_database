import json
import os
import re
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
PAGES = sorted(FRONTEND.glob("*.html"))

EXPECTED = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; object-src 'none'; base-uri 'none'; "
        "form-action 'self'; frame-ancestors 'none'"
    ),
    "Strict-Transport-Security": "max-age=31536000",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    main_module.login_limiter.reset("admin")
    return TestClient(main_module.app)


@pytest.mark.parametrize("path", ["/", "/candidate.html", "/app.js", "/candidate.js", "/candidates"])
def test_all_headers_present(client, path):
    resp = client.get(path)
    for name, value in EXPECTED.items():
        assert resp.headers[name] == value


def test_candidates_without_token_is_401(client):
    assert client.get("/candidates").status_code == 401


def test_404_carries_csp(client):
    resp = client.get("/does-not-exist.html")
    assert resp.status_code == 404
    assert resp.headers["Content-Security-Policy"] == EXPECTED["Content-Security-Policy"]


def test_500_carries_headers(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))

    def boom():
        raise RuntimeError("boom")

    main_module.app.add_api_route("/_boom", boom)
    # The static mount is registered last and would shadow the new route
    routes = main_module.app.router.routes
    routes.insert(0, routes.pop())
    resp = TestClient(main_module.app, raise_server_exceptions=False).get("/_boom")
    assert resp.status_code == 500
    for name, value in EXPECTED.items():
        assert resp.headers[name] == value


def test_script_src_has_no_unsafe():
    script_src = re.search(r"script-src ([^;]*)", EXPECTED["Content-Security-Policy"]).group(1)
    assert "unsafe" not in script_src


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_no_inline_script_or_handlers(page):
    text = page.read_text(encoding="utf-8")
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", text)
    assert not re.search(r" on[a-z]+=", text)


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_page_includes_its_scripts(page):
    text = page.read_text(encoding="utf-8")
    assert '<script src="/app.js"></script>' in text
    assert f'<script src="/{page.stem}.js"></script>' in text
