import json
import os
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("AUTH_SECRET", "test-secret-that-is-long-enough-123")
os.environ.setdefault("ALLOWED_ORIGIN", "*")
os.environ.setdefault(
    "AUTH_USERS",
    json.dumps({"admin": "scrypt$16384$8$1$Y2FuZGlkYXRlcy1kZXYtMQ==$aYz/67aCRaL8SQxCWfYwt/nBlX7aSdAl8vE7H8hoQo8="}),
)

import dev_server


@pytest.fixture
def mock_run(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "dev.db"))
    monkeypatch.delenv("ALLOWED_ORIGIN", raising=False)
    run = MagicMock()
    monkeypatch.setattr("uvicorn.run", run)
    import container.main as m

    monkeypatch.setattr(m.app, "mount", MagicMock())
    return run


def test_defaults(mock_run):
    dev_server.main([])
    assert mock_run.call_args.kwargs["host"] == "127.0.0.1"
    assert mock_run.call_args.kwargs["port"] == 8080
    assert os.environ["ALLOWED_ORIGIN"] == "http://localhost:8080"


def test_positional_port(mock_run):
    dev_server.main(["8091"])
    assert mock_run.call_args.kwargs["port"] == 8091
    assert os.environ["ALLOWED_ORIGIN"] == "http://localhost:8091"


def test_host_option(mock_run):
    dev_server.main(["--host", "0.0.0.0", "9000"])
    assert mock_run.call_args.kwargs["host"] == "0.0.0.0"
    assert mock_run.call_args.kwargs["port"] == 9000


def test_existing_origin_kept(mock_run, monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGIN", "http://example.test")
    dev_server.main([])
    assert os.environ["ALLOWED_ORIGIN"] == "http://example.test"
