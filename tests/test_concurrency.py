import json
import os
import threading
import time
from unittest.mock import patch

import pytest

os.environ.setdefault("AUTH_SECRET", "test-secret-that-is-long-enough-123")
os.environ.setdefault("ALLOWED_ORIGIN", "*")
os.environ.setdefault(
    "AUTH_USERS",
    json.dumps({"admin": "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918"}),
)

import httpx  # noqa: E402

from candidates import helpers  # noqa: E402
from container.main import app  # noqa: E402


@pytest.fixture
def client_factory(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_READONLY", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(helpers, "_schema_ready", False)
    return lambda: httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


def test_slow_search_does_not_block_other_requests(client_factory):
    import asyncio

    asyncio.run(_slow_search_scenario(client_factory))


async def _slow_search_scenario(client_factory):
    import asyncio

    started = threading.Event()

    def slow_send(self, *args, **kwargs):
        started.set()
        time.sleep(2)
        return "SELECT 1 AS one"

    async with client_factory() as client:
        r = await client.post("/login", json={"username": "admin", "password": "admin"})
        headers = {"Authorization": f"Bearer {r.json()['token']}"}

        with patch("candidates.llm_client.LLMClient.__init__", lambda self, *a, **k: None), \
             patch("candidates.llm_client.LLMClient.send_message", slow_send):
            search = asyncio.create_task(client.post("/search", json={"query": "x"}, headers=headers))
            while not started.is_set():
                await asyncio.sleep(0.01)

            t0 = time.time()
            login = await client.post("/login", json={"username": "admin", "password": "admin"})
            listing = await client.get("/candidates", headers=headers)
            elapsed = time.time() - t0

            assert login.status_code == 200
            assert listing.status_code == 200
            assert elapsed < 1.0
            await search


def test_each_request_gets_its_own_connection(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(helpers, "_schema_ready", False)
    with helpers.open_db() as a, helpers.open_db() as b:
        assert a.conn is not b.conn
