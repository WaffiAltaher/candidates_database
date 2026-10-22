import json
import os
import sqlite3
import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

os.environ.setdefault("AUTH_SECRET", "test-secret-that-is-long-enough-123")
os.environ.setdefault("ALLOWED_ORIGIN", "*")
os.environ.setdefault(
    "AUTH_USERS",
    json.dumps({"admin": "scrypt$16384$8$1$Y2FuZGlkYXRlcy1kZXYtMQ==$aYz/67aCRaL8SQxCWfYwt/nBlX7aSdAl8vE7H8hoQo8="}),
)

from candidates import database, helpers  # noqa: E402
from candidates.database import Database, check_generated_sql  # noqa: E402
from container.main import app  # noqa: E402


@pytest.fixture
def db_env(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_READONLY", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(helpers, "_schema_ready", False)


def insert_candidates(n):
    with helpers.open_db() as db:
        for i in range(n):
            db.conn.execute("INSERT INTO candidates (name) VALUES (?)", (f"c{i}",))
        db.conn.commit()


@pytest.mark.parametrize("sql", [
    "SELECT 1 AS created_count",
    "SELECT name FROM candidates WHERE name = 'DROP'",
    "WITH t AS (SELECT 1 AS x) SELECT x FROM t",
    "SELECT 1;",
])
def test_check_accepts(sql):
    check_generated_sql(sql)


@pytest.mark.parametrize("sql", [
    "DELETE FROM candidates",
    "UPDATE candidates SET name = 'x'",
    "SELECT 1; DROP TABLE candidates",
    "WITH t AS (SELECT 1) DELETE FROM candidates",
    "PRAGMA query_only = OFF",
])
def test_check_rejects(sql):
    with pytest.raises(ValueError):
        check_generated_sql(sql)


def test_readonly_connection(db_env):
    with helpers.open_db():
        pass
    with helpers.open_db(readonly=True) as db:
        with pytest.raises(sqlite3.OperationalError):
            db.conn.execute("INSERT INTO candidates (name) VALUES ('x')")
        assert db.conn.execute("PRAGMA query_only").fetchone()[0] == 1


def test_row_cap_truncates(db_env):
    insert_candidates(250)
    with helpers.open_db(readonly=True) as db:
        rows, truncated = db.run_generated_query("SELECT name FROM candidates")
    assert len(rows) == 200
    assert truncated is True


def test_row_cap_exact(db_env):
    insert_candidates(200)
    with helpers.open_db(readonly=True) as db:
        rows, truncated = db.run_generated_query("SELECT name FROM candidates")
    assert len(rows) == 200
    assert truncated is False


def test_timeout(db_env, monkeypatch):
    monkeypatch.setattr(database, "SEARCH_TIMEOUT_SECONDS", 0.2)
    with helpers.open_db():
        pass
    with helpers.open_db(readonly=True) as db:
        t0 = time.monotonic()
        with pytest.raises(sqlite3.OperationalError):
            db.run_generated_query(
                "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT count(*) FROM c"
            )
        assert time.monotonic() - t0 < 5
        rows, _ = db.run_generated_query("SELECT 1 AS one")
        assert rows == [{"one": 1}]


def _pg_mock(execute_side_effect=None):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.description = [("name",)]
    cursor.fetchmany.return_value = []
    calls = []

    def execute(sql, *a):
        calls.append(sql)
        if execute_side_effect and sql.startswith("SELECT"):
            raise execute_side_effect

    cursor.execute.side_effect = execute
    return conn, calls


def test_postgres_statement_order():
    conn, calls = _pg_mock()
    db = Database.from_connection(conn, "postgresql")
    assert db.run_generated_query("SELECT name FROM candidates") == ([], False)
    assert calls == [
        "SET TRANSACTION READ ONLY",
        "SET LOCAL statement_timeout = '10s'",
        "SELECT name FROM candidates",
    ]
    conn.rollback.assert_called()


def test_postgres_rollback_on_error():
    conn, _ = _pg_mock(RuntimeError("boom"))
    db = Database.from_connection(conn, "postgresql")
    with pytest.raises(RuntimeError):
        db.run_generated_query("SELECT name FROM candidates")
    conn.rollback.assert_called()


def test_search_endpoint_reports_truncated(db_env):
    import asyncio

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            r = await client.post("/login", json={"username": "admin", "password": "admin"})
            headers = {"Authorization": f"Bearer {r.json()['token']}"}
            replies = iter(["SELECT name FROM candidates", "ok"])
            with patch("candidates.llm_client.LLMClient.__init__", lambda self, *a, **k: None), \
                 patch("candidates.llm_client.LLMClient.send_message", lambda self, *a, **k: next(replies)):
                return await client.post("/search", json={"query": "x"}, headers=headers)

    resp = asyncio.run(scenario())
    assert resp.status_code == 200
    assert resp.json()["truncated"] is False
