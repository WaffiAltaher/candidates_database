import json
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

os.environ.setdefault("AUTH_SECRET", "test-secret-that-is-long-enough-123")
os.environ.setdefault("ALLOWED_ORIGIN", "*")
os.environ.setdefault(
    "AUTH_USERS",
    json.dumps({"admin": "scrypt$16384$8$1$Y2FuZGlkYXRlcy1kZXYtMQ==$aYz/67aCRaL8SQxCWfYwt/nBlX7aSdAl8vE7H8hoQo8="}),
)

from fastapi.testclient import TestClient  # noqa: E402

import container.main as main_module  # noqa: E402
from candidates import client_network, helpers, usage  # noqa: E402
from candidates.database import Database  # noqa: E402
from candidates.login_limiter import LoginLimiter  # noqa: E402
from candidates.search_engine import SQL_GENERATION_PROMPT  # noqa: E402

TODAY = date(2026, 6, 15)


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(helpers, "_schema_ready", False)
    monkeypatch.setattr(client_network, "country", lambda ip: "NL")
    monkeypatch.setattr(main_module, "login_limiter", LoginLimiter())
    monkeypatch.setattr(usage, "_purged_on", None)
    monkeypatch.setattr(usage, "_clock", lambda: datetime(2026, 6, 15, 12, 0, tzinfo=ZoneInfo("Europe/Amsterdam")))
    return TestClient(main_module.app)


def rows():
    with helpers.open_db() as db:
        return db.execute_query("SELECT * FROM usage_daily ORDER BY username, network")


def login(client, user="admin", pw="admin", ip="10.1.2.3"):
    return client.post("/login", json={"username": user, "password": pw}, headers={"X-Real-IP": ip})


def token(client, ip="10.1.2.3"):
    return login(client, ip=ip).json()["token"]


def auth(client, ip="10.1.2.3"):
    return {"Authorization": f"Bearer {token(client, ip)}", "X-Real-IP": ip}


def test_authenticated_call_counts_request(client):
    h = auth(client)
    client.get("/candidates", headers=h)
    r = [x for x in rows() if x["username"] == "admin"]
    assert len(r) == 1 and r[0]["requests"] == 1 and r[0]["logins"] == 1
    assert r[0]["day"] == "2026-06-15" and r[0]["country"] == "NL"
    assert r[0]["network"] != "*"


def test_static_and_anonymous_not_counted(client):
    client.get("/")
    client.get("/nope.html")
    client.get("/candidates")
    client.get("/candidates", headers={"Authorization": "Bearer junk"})
    assert rows() == []


def test_login_success_counts_login(client):
    login(client)
    r = rows()
    assert len(r) == 1 and r[0]["logins"] == 1 and r[0]["requests"] == 0


def test_failed_login_known_user_keeps_network(client):
    login(client, pw="bad")
    r = rows()
    assert r[0]["username"] == "admin" and r[0]["failed_logins"] == 1 and r[0]["network"] != "*"


def test_failed_login_unknown_users_single_row(client):
    for i, u in enumerate(["a", "b", "c"]):
        assert login(client, user=u, pw="x", ip=f"10.{i}.0.1").status_code == 401
    r = rows()
    assert len(r) == 1
    assert (r[0]["username"], r[0]["network"], r[0]["country"], r[0]["failed_logins"]) == ("(unknown)", "*", "*", 3)


def test_blocked_login_on_star_row(client):
    for _ in range(5):
        login(client, pw="bad")
    assert login(client).status_code == 429
    r = [x for x in rows() if x["blocked_logins"]]
    assert len(r) == 1 and (r[0]["username"], r[0]["network"], r[0]["country"]) == ("admin", "*", "*")


def test_blocked_unknown_user_on_unknown_row(client):
    for _ in range(5):
        login(client, user="ghost", pw="x")
    assert login(client, user="ghost", pw="x").status_code == 429
    r = rows()
    assert len(r) == 1 and r[0]["username"] == "(unknown)"
    assert r[0]["failed_logins"] == 5 and r[0]["blocked_logins"] == 1


def test_missing_fields_not_counted(client):
    assert client.post("/login", json={"username": "admin"}).status_code == 400
    assert rows() == []


def test_write_failure_does_not_break_request(client, monkeypatch, caplog):
    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(Database, "increment_usage", boom)
    with caplog.at_level("WARNING"):
        resp = login(client)
    assert resp.status_code == 200 and "token" in resp.json()
    assert "Usage write failed" in caplog.text


def test_retention_deletes_old_rows(client):
    with helpers.open_db() as db:
        db.increment_usage("2025-06-14", "admin", "n", "NL", "requests")
        db.increment_usage("2025-06-15", "admin", "n", "NL", "requests")
    login(client)
    days = {r["day"] for r in rows()}
    assert "2025-06-14" not in days and "2025-06-15" in days


def test_retention_leap_day():
    assert usage.retention_cutoff(date(2028, 2, 29)) == date(2027, 2, 28)
    assert usage.retention_cutoff(date(2026, 6, 15)) == date(2025, 6, 15)


def seed(rows_):
    with helpers.open_db() as db:
        for day, user, col, n in rows_:
            for _ in range(n):
                db.increment_usage(day, user, "net", "NL", col)


def test_usage_defaults_last_30_days(client):
    h = auth(client)
    seed([("2026-05-17", "admin", "requests", 1), ("2026-05-16", "admin", "requests", 1)])
    body = client.get("/usage", headers=h).json()
    assert (body["from"], body["to"]) == ("2026-05-17", "2026-06-15")
    assert "2026-05-16" not in {r["day"] for r in body["rows"]}
    assert body["rows"][0]["day"] == "2026-06-15"


def test_usage_clamps_from_to_cutoff(client):
    h = auth(client)
    body = client.get("/usage?from=2020-01-01&to=2026-06-15", headers=h).json()
    assert body["from"] == "2025-06-15"


def test_usage_bad_date_400(client):
    h = auth(client)
    assert client.get("/usage?from=nope", headers=h).status_code == 400
    assert client.get("/usage?from=2026-06-10&to=2026-06-01", headers=h).status_code == 400


def test_usage_requires_token(client):
    assert client.get("/usage").status_code == 401


def test_summary_users_and_active_days_exclude_unknown(client):
    h = auth(client)
    seed([
        ("2026-06-10", "alice", "requests", 2),
        ("2026-06-11", "alice", "requests", 1),
        ("2026-06-12", "alice", "logins", 1),
        ("2026-06-12", "(unknown)", "failed_logins", 3),
        ("2026-06-12", "alice", "blocked_logins", 1),
    ])
    s = client.get("/usage", headers=h).json()["summary"]
    names = {u["username"]: u for u in s["users"]}
    assert "(unknown)" not in names
    assert names["alice"] == {"username": "alice", "requests": 3, "logins": 1, "active_days": 2}
    assert s["failed_logins"] == 3 and s["blocked_logins"] == 1


def test_day_uses_amsterdam_time(client, monkeypatch):
    monkeypatch.setattr(usage, "_clock", lambda: datetime(2026, 7, 1, 22, 30, tzinfo=ZoneInfo("UTC")).astimezone(usage._TZ))
    login(client)
    assert rows()[0]["day"] == "2026-07-02"


def test_real_clock_is_amsterdam():
    assert str(usage._clock().tzinfo) == "Europe/Amsterdam"


def test_purge_runs_once_per_day(client, monkeypatch):
    calls = []
    orig = Database.delete_usage_before
    monkeypatch.setattr(Database, "delete_usage_before", lambda self, d: (calls.append(d), orig(self, d))[1])
    login(client)
    login(client)
    assert calls == ["2025-06-15"]
    monkeypatch.setattr(usage, "_clock", lambda: datetime(2026, 6, 16, 12, 0, tzinfo=usage._TZ))
    login(client)
    assert calls == ["2025-06-15", "2025-06-16"]


def test_usage_strict_dates_and_empty_params(client):
    h = auth(client)
    for q in ("from=2026-W48-5", "from=", "to=", "to=20260101", "from=2026-1-1"):
        assert client.get(f"/usage?{q}", headers=h).status_code == 400, q
    assert client.get(f"/usage?from=2026-06-10&to=2026-06-01", headers=h).json() == {
        "error": "from must not be after to"
    }


def test_usage_range_entirely_before_cutoff_400(client):
    h = auth(client)
    assert client.get("/usage?from=2020-01-01&to=2024-01-01", headers=h).status_code == 400


def test_increment_rejects_bad_column(client):
    with helpers.open_db() as db:
        with pytest.raises(ValueError):
            db.increment_usage("2026-06-15", "a", "n", "c", "x; DROP TABLE y")


def test_prompt_mentions_usage_table_but_schema_does_not():
    assert "usage_daily" in SQL_GENERATION_PROMPT
    assert "usage_daily" not in Database.from_connection(None, "sqlite").get_schema_description()
