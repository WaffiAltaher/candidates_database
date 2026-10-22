import sqlite3
from unittest.mock import MagicMock

import pytest

from candidates.database import Database


@pytest.fixture
def db(tmp_path):
    database = Database(db_path=str(tmp_path / "test.db"))
    database.initialize()
    yield database
    database.close()


def pg_database(cursor):
    database = Database.__new__(Database)
    database.backend = "postgresql"
    database.placeholder = "%s"
    database.conn = MagicMock()
    database.conn.cursor.return_value = cursor
    return database


def test_add_interview_commits_on_postgresql():
    cursor = MagicMock()
    cursor.fetchone.return_value = (7,)
    database = pg_database(cursor)

    assert database.add_interview(1, 1, "Bob", "Good") == 7
    database.conn.commit.assert_called_once()


def test_add_interview_visible_from_new_connection(db, tmp_path):
    cid, _ = db.store_candidate({"name": "Jane Doe"})
    db.add_interview(cid, 1, "Bob", "Good")

    other = sqlite3.connect(str(tmp_path / "test.db"))
    try:
        assert other.execute("SELECT COUNT(*) FROM interviews").fetchone()[0] == 1
    finally:
        other.close()


def test_failed_statement_rolls_back_postgresql():
    cursor = MagicMock()
    cursor.execute.side_effect = RuntimeError("boom")
    database = pg_database(cursor)

    with pytest.raises(RuntimeError):
        database.execute_query("SELECT 1")
    database.conn.rollback.assert_called_once()


def test_connection_usable_after_failed_query(db):
    with pytest.raises(sqlite3.OperationalError):
        db.execute_query("SELECT * FROM no_such_table")
    assert db.execute_query("SELECT 1 AS one") == [{"one": 1}]
