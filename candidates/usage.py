"""Daily usage totals: counting, retention and summaries."""

import logging
import threading
from datetime import date, datetime
from zoneinfo import ZoneInfo

from candidates import helpers

logger = logging.getLogger(__name__)

UNKNOWN_USER = "(unknown)"
ANY = "*"
_TZ = ZoneInfo("Europe/Amsterdam")


def _clock() -> datetime:
    return datetime.now(_TZ)


def today() -> date:
    return _clock().date()


def retention_cutoff(day: date) -> date:
    """Same calendar date one year earlier (29 Feb falls back to 28 Feb)."""
    try:
        return day.replace(year=day.year - 1)
    except ValueError:
        return day.replace(year=day.year - 1, day=28)


def row_key(column: str, username: str, network: str, country: str) -> tuple[str, str, str]:
    """Return (username, network, country) as stored for this event."""
    known = username in helpers.AUTH_USERS
    if column == "blocked_logins":
        return (username, ANY, ANY) if known else (UNKNOWN_USER, ANY, ANY)
    if column == "failed_logins" and not known:
        return (UNKNOWN_USER, ANY, ANY)
    return (username, network, country)


_purge_lock = threading.Lock()
_purged_on: date | None = None


def record(column: str, username: str, network: str, country: str) -> None:
    """Count one event. Never raises."""
    global _purged_on
    try:
        day = today()
        user, net, ctry = row_key(column, username, network, country)
        with helpers.open_db() as db:
            db.increment_usage(day.isoformat(), user, net, ctry, column)
            with _purge_lock:
                due = _purged_on != day
                if due:
                    _purged_on = day
            if due:
                try:
                    db.delete_usage_before(retention_cutoff(day).isoformat())
                except Exception:
                    with _purge_lock:
                        _purged_on = None
                    raise
    except Exception:
        logger.warning("Usage write failed", exc_info=True)


def summarise(rows: list[dict]) -> dict:
    users: dict[str, dict] = {}
    failed = blocked = 0
    for r in rows:
        failed += r["failed_logins"]
        blocked += r["blocked_logins"]
        if r["username"] == UNKNOWN_USER:
            continue
        u = users.setdefault(
            r["username"],
            {"username": r["username"], "requests": 0, "logins": 0, "_days": set()},
        )
        u["requests"] += r["requests"]
        u["logins"] += r["logins"]
        if r["requests"] > 0:
            u["_days"].add(r["day"])
    out = []
    for name in sorted(users):
        u = users[name]
        out.append({"username": name, "requests": u["requests"], "logins": u["logins"],
                    "active_days": len(u["_days"])})
    return {"users": out, "failed_logins": failed, "blocked_logins": blocked}
