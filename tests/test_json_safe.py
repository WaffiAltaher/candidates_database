import datetime
import json
from decimal import Decimal
from unittest.mock import MagicMock

from candidates.database import Database, to_json_safe


def test_to_json_safe_types():
    row = {
        "a": Decimal("2.50"),
        "b": Decimal("3"),
        "c": datetime.date(2020, 1, 2),
        "d": datetime.datetime(2020, 1, 2, 3, 4, 5),
        "e": datetime.timedelta(days=3),
        "f": memoryview(b"hi"),
        "g": None,
    }
    safe = {k: to_json_safe(v) for k, v in row.items()}
    assert json.loads(json.dumps(safe)) == {
        "a": 2.5, "b": 3, "c": "2020-01-02", "d": "2020-01-02T03:04:05",
        "e": "3 days, 0:00:00", "f": "hi", "g": None,
    }
    assert isinstance(safe["b"], int)


def test_execute_query_returns_json_safe_rows():
    cursor = MagicMock()
    cursor.description = [("avg",), ("d",)]
    cursor.fetchall.return_value = [(Decimal("1.5"), datetime.date(2021, 5, 6))]
    db = Database.__new__(Database)
    db._execute = lambda sql, params=None: cursor
    rows = db.execute_query("SELECT 1")
    json.dumps(rows)
    assert rows == [{"avg": 1.5, "d": "2021-05-06"}]
