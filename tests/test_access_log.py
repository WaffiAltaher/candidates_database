import json
import logging
import os

os.environ.setdefault("AUTH_SECRET", "test-secret-that-is-long-enough-123")
os.environ.setdefault("ALLOWED_ORIGIN", "*")
os.environ.setdefault(
    "AUTH_USERS",
    json.dumps({"admin": "scrypt$16384$8$1$Y2FuZGlkYXRlcy1kZXYtMQ==$aYz/67aCRaL8SQxCWfYwt/nBlX7aSdAl8vE7H8hoQo8="}),
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import container.main as main_module  # noqa: E402
from candidates import client_network  # noqa: E402
from candidates.helpers import create_token  # noqa: E402


class ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(client_network, "country", lambda ip: "NL")
    main_module.login_limiter.reset("admin")
    return TestClient(main_module.app, raise_server_exceptions=False)


@pytest.fixture
def lines():
    handler = ListHandler()
    log = logging.getLogger("access")
    log.addHandler(handler)
    yield handler.lines
    log.removeHandler(handler)


def fields(line):
    out = {}
    for part in line.split(" "):
        k, _, v = part.partition("=")
        out[k] = v
    return out


def test_ipv4_truncated_to_24(client, lines):
    client.get("/app.js", headers={"X-Real-IP": "203.0.113.57"})
    assert "network=203.0.113.0/24" in lines[-1]
    assert "country=NL" in lines[-1]


def test_ipv6_truncated_to_48(client, lines):
    client.get("/app.js", headers={"X-Real-IP": "2001:db8:1:2::5"})
    assert "network=2001:db8:1::/48" in lines[-1]


def test_ipv4_mapped_ipv6_treated_as_ipv4(client, lines):
    client.get("/app.js", headers={"X-Real-IP": "::ffff:203.0.113.57"})
    assert "network=203.0.113.0/24" in lines[-1]


def test_missing_header_uses_peer(monkeypatch, tmp_path, lines):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(client_network, "country", lambda ip: "NL")
    peer = TestClient(main_module.app, client=("198.51.100.9", 123))
    peer.get("/app.js")
    assert "network=198.51.100.0/24" in lines[-1]


def test_garbage_header_falls_back_to_peer(monkeypatch, tmp_path, lines):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(client_network, "country", lambda ip: "NL")
    peer = TestClient(main_module.app, client=("198.51.100.9", 123))
    peer.get("/app.js", headers={"X-Real-IP": "garbage"})
    assert "network=198.51.100.0/24" in lines[-1]


def test_logfmt_escapes_unicode_line_breaks():
    from candidates.access_log import logfmt

    out = logfmt([("user", "a\u2028event=request x\x85y\x9bz\u2029")])
    assert out == 'user="a\\u2028event=request x\\u0085y\\u009bz\\u2029"'
    assert all(ord(c) < 0x7F and ord(c) >= 0x20 for c in out)


def test_x_forwarded_for_ignored(client, lines):
    client.get("/app.js", headers={"X-Forwarded-For": "203.0.113.57"})
    assert "203.0.113" not in lines[-1]


def test_full_ip_never_logged(client, lines, caplog):
    caplog.set_level(logging.DEBUG)
    client.get("/app.js", headers={"X-Real-IP": "203.0.113.57"})
    client.post("/login", json={"username": "admin", "password": "wrong"}, headers={"X-Real-IP": "203.0.113.57"})
    assert not any("203.0.113.57" in line for line in lines)
    assert "203.0.113.57" not in caplog.text


def test_static_file_logged_anonymous(client, lines):
    client.get("/app.js")
    assert len(lines) == 1
    assert "method=GET path=/app.js status=200" in lines[0]
    assert "user=-" in lines[0]


def test_authenticated_call_logs_user(client, lines):
    token = create_token("admin")
    client.get("/candidates", headers={"Authorization": f"Bearer {token}"})
    assert "user=admin" in lines[-1]


def test_login_logs_typed_username(client, lines):
    client.post("/login", json={"username": "nobody", "password": "x"})
    assert "path=/login status=401" in lines[-1]
    assert "user=nobody" in lines[-1]


def test_query_string_not_logged(client, lines):
    client.get("/app.js?secret=abc")
    assert "secret" not in lines[-1]
    assert "path=/app.js " in lines[-1]


def test_username_escaping_cannot_forge_fields(client, lines):
    evil = 'a" status=200\nevent=request'
    client.post("/login", json={"username": evil, "password": "x"})
    assert len(lines) == 1
    assert "\n" not in lines[0]
    assert 'user="a\\" status=200\\nevent=request"' in lines[0]


def test_500_is_logged(monkeypatch, client, lines):
    def boom():
        raise RuntimeError("boom")

    main_module.app.add_api_route("/_boom_access", boom)
    routes = main_module.app.router.routes
    routes.insert(0, routes.pop())
    resp = client.get("/_boom_access")
    assert resp.status_code == 500
    assert "path=/_boom_access status=500" in lines[-1]


def test_request_id_logged(client, lines):
    client.get("/app.js", headers={"X-Request-ID": "3f2a9c"})
    assert lines[-1].endswith("request_id=3f2a9c")


def test_field_order(client, lines):
    client.get("/app.js", headers={"X-Real-IP": "203.0.113.57"})
    keys = [p.split("=")[0] for p in lines[-1].split(" ")]
    assert keys == ["event", "method", "path", "status", "duration_ms", "user", "network", "country", "request_id"]
    assert fields(lines[-1])["request_id"] == "-"


def test_country_missing_db_is_dash(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("GEOIP_DB_PATH", str(tmp_path / "missing.mmdb"))
    client_network.reset_cache()
    caplog.set_level(logging.WARNING)
    try:
        assert client_network.country("8.8.8.8") == "-"
        assert client_network.country("8.8.4.4") == "-"
        warnings = [r for r in caplog.records if "GeoIP" in r.getMessage()]
        assert len(warnings) == 1
    finally:
        client_network.reset_cache()
