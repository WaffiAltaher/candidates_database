import json
import logging
import os
from unittest.mock import patch

import pytest

os.environ.setdefault("AUTH_SECRET", "test-secret-that-is-long-enough-123")
os.environ.setdefault("ALLOWED_ORIGIN", "*")
os.environ.setdefault(
    "AUTH_USERS",
    json.dumps({"admin": "scrypt$16384$8$1$Y2FuZGlkYXRlcy1kZXYtMQ==$aYz/67aCRaL8SQxCWfYwt/nBlX7aSdAl8vE7H8hoQo8="}),
)

import base64  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

import candidates.helpers as helpers  # noqa: E402
import container.main as main_module  # noqa: E402

FIXED = "The search could not be run. Try rephrasing your question."
BOB = "scrypt$16384$8$1$Y2FuZGlkYXRlcy1kZXYtMQ==$aYz/67aCRaL8SQxCWfYwt/nBlX7aSdAl8vE7H8hoQo8="


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_READONLY", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(helpers, "_schema_ready", False)
    monkeypatch.setattr(helpers, "AUTH_USERS", {"admin": BOB})
    main_module.login_limiter.reset("admin")
    client = TestClient(main_module.app, raise_server_exceptions=False)
    r = client.post("/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200
    return client, {"Authorization": f"Bearer {r.json()['token']}"}


def _search(api, sql):
    client, headers = api
    with patch("candidates.llm_client.LLMClient.__init__", lambda self, *a, **k: None), \
         patch("candidates.llm_client.LLMClient.send_message", lambda self, *a, **k: sql):
        return client.post("/search", json={"query": "x"}, headers=headers)


def test_search_execution_error(api, caplog):
    with caplog.at_level(logging.INFO):
        r = _search(api, "SELECT * FROM no_such_table_xyz")
    assert r.status_code == 200
    body = r.json()
    assert body["summary"] == FIXED
    assert "no_such_table_xyz" not in body["summary"]
    assert "no_such_table_xyz" not in r.text.replace(body["sql"], "")
    assert any(rec.exc_info for rec in caplog.records)


def test_search_rejected_query(api):
    r = _search(api, "DELETE FROM candidates")
    assert r.status_code == 200
    assert r.json()["summary"] == FIXED
    assert "Forbidden" not in r.text


def test_upload_failure(api, monkeypatch, caplog):
    client, headers = api

    def boom(self, path):
        raise RuntimeError("secret detail 123")

    monkeypatch.setattr("candidates.cv_extractor.CVExtractor.ingest_file", boom)
    data = base64.b64encode(b"%PDF-1.4 not really a pdf").decode()
    with patch("candidates.llm_client.LLMClient.__init__", lambda self, *a, **k: None), \
         caplog.at_level(logging.INFO):
        r = client.post("/upload", json={"filename": "cv.pdf", "file_data": data}, headers=headers)
    assert r.status_code == 500
    assert r.json() == {"error": "Processing failed. Check that the file is a readable PDF."}
    assert "secret detail 123" not in r.text
    assert "secret detail 123" in caplog.text


def test_unhandled_error(api, monkeypatch):
    client, headers = api

    def boom(self):
        raise RuntimeError("secret detail 456")

    monkeypatch.setattr("candidates.database.Database.get_all_candidates", boom)
    r = client.get("/candidates", headers=headers)
    assert r.status_code == 500
    assert r.json() == {"error": "Internal server error"}
    assert "secret detail 456" not in r.text


def test_dispatch_hides_exception():
    def handler(event, context):
        raise RuntimeError("secret detail 789")

    routes = [("GET", "/boom", handler, False)]
    result = helpers.dispatch({"httpMethod": "GET", "path": "/boom"}, None, routes)
    assert result["statusCode"] == 500
    assert json.loads(result["body"]) == {"error": "Internal server error"}
