"""
Shared utilities: CORS, auth, response building, DB singleton, route dispatch.
"""

import hashlib
import hmac
import json
import logging
import os
import re
import threading
import time
from contextlib import contextmanager

from candidates.passwords import check_password

logger = logging.getLogger("helpers")

# Suppress noisy third-party loggers
for _noisy in ("httpcore", "httpx", "anthropic", "aisuite"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "")
AUTH_SECRET = os.environ.get("AUTH_SECRET", "")
if len(AUTH_SECRET) < 24 or AUTH_SECRET == "dev-secret-change-me":
    raise RuntimeError("AUTH_SECRET is missing or insecure")
if not ALLOWED_ORIGIN:
    raise RuntimeError("ALLOWED_ORIGIN is not set")
# AUTH_USERS: JSON map of username -> scrypt hash string, e.g.
# {"alice":"scrypt$16384$8$1$<salt_b64>$<hash_b64>"} (generate with scripts/add_user.py)
_auth_users_raw = os.environ.get("AUTH_USERS", "")
AUTH_USERS = json.loads(_auth_users_raw) if _auth_users_raw else {}
TOKEN_EXPIRY = 24 * 60 * 60  # 24 hours

CORS_HEADERS = {
    "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


def cors_preflight():
    """Return a 204 response for CORS preflight requests."""
    return {"statusCode": 204, "headers": CORS_HEADERS, "body": ""}


def response(status_code: int, body: dict) -> dict:
    """Build a JSON response with CORS headers."""
    return {
        "statusCode": status_code,
        "headers": {**CORS_HEADERS, "Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def create_token() -> str:
    """Create an HMAC-SHA256 signed auth token with expiry."""
    expiry = int(time.time()) + TOKEN_EXPIRY
    payload = str(expiry)
    signature = hmac.new(
        AUTH_SECRET.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    return f"{payload}.{signature}"


def validate_token(token: str) -> bool:
    """Validate an HMAC-SHA256 signed token."""
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return False
        payload, signature = parts
        expected = hmac.new(
            AUTH_SECRET.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return False
        expiry = int(payload)
        return time.time() < expiry
    except (ValueError, TypeError):
        return False


def require_auth(event: dict) -> dict | None:
    """Check auth header. Returns error response if invalid, None if OK."""
    headers = event.get("headers", {})
    auth = headers.get("authorization", headers.get("Authorization", ""))
    if not auth.startswith("Bearer "):
        return response(401, {"error": "Missing or invalid Authorization header"})
    token = auth[7:]
    if not validate_token(token):
        return response(401, {"error": "Invalid or expired token"})
    return None


def verify_password(username: str, password: str) -> bool:
    """Check password against stored hash for the given username."""
    expected_hash = AUTH_USERS.get(username)
    if not expected_hash:
        return False
    return check_password(password, expected_hash)


# --- Per-request DB connections ---
#
# Every request gets its own connection so no connection or cursor is shared
# between threads. PostgreSQL connections come from a small bounded pool
# (serverless SQL is billed on use and the container can run several
# instances); SQLite opens a short-lived connection per request.

DB_POOL_MAX = int(os.environ.get("DB_POOL_MAX", "4"))
DB_POOL_WAIT_SECONDS = 30

_pools: dict = {}
_pools_lock = threading.Lock()
_schema_ready = False
_schema_lock = threading.Lock()


class _PgPool:
    """ThreadedConnectionPool that makes callers wait instead of failing when full."""

    def __init__(self, database_url: str, maxconn: int):
        from psycopg2.pool import ThreadedConnectionPool

        self._pool = ThreadedConnectionPool(0, maxconn, database_url)
        self._slots = threading.BoundedSemaphore(maxconn)

    def acquire(self):
        if not self._slots.acquire(timeout=DB_POOL_WAIT_SECONDS):
            raise RuntimeError("Timed out waiting for a database connection")
        try:
            return self._get_live_connection()
        except Exception:
            self._slots.release()
            raise

    def _get_live_connection(self):
        """Borrow a connection and ping it; replace a dead one once, then raise.

        Serverless SQL drops idle connections server-side, which `conn.closed`
        does not reveal until a query fails.
        """
        last_error = None
        for _ in range(2):
            conn = self._pool.getconn()
            try:
                if conn.closed:
                    raise RuntimeError("connection is closed")
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.close()
                conn.rollback()
                return conn
            except Exception as e:
                last_error = e
                logger.warning("Discarding dead pooled connection: %s", e)
                self._pool.putconn(conn, close=True)
        raise last_error

    def release(self, conn):
        try:
            try:
                conn.rollback()
            except Exception:
                logger.warning("Rollback on release failed; discarding connection", exc_info=True)
                self._pool.putconn(conn, close=True)
            else:
                self._pool.putconn(conn)
        finally:
            self._slots.release()


def _get_pool(database_url: str) -> _PgPool:
    with _pools_lock:
        pool = _pools.get(database_url)
        if pool is None:
            pool = _pools[database_url] = _PgPool(database_url, DB_POOL_MAX)
        return pool


def _ensure_schema(database) -> None:
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if not _schema_ready:
            database.initialize()
            _schema_ready = True


@contextmanager
def open_db(readonly: bool = False):
    """Yield a Database bound to its own connection for the duration of the block.

    readonly=True uses DATABASE_URL_READONLY when set (for LLM-generated SQL),
    otherwise falls back to the regular connection settings.
    """
    from candidates.database import Database

    database_url = os.environ.get("DATABASE_URL")
    url = (os.environ.get("DATABASE_URL_READONLY") if readonly else None) or database_url

    if url:
        pool = _get_pool(url)
        conn = pool.acquire()
        try:
            conn.autocommit = False
            database = Database.from_connection(conn, "postgresql")
            if url == database_url:
                _ensure_schema(database)
            yield database
        finally:
            pool.release(conn)
    else:
        database = Database(db_path=os.environ.get("DATABASE_PATH", "cvs.db"))
        try:
            _ensure_schema(database)
            yield database
        finally:
            database.close()


# --- Route dispatcher ---

def get_body(event: dict) -> dict:
    """Parse JSON body from event."""
    body = event.get("body", "")
    if isinstance(body, str) and body:
        return json.loads(body)
    if isinstance(body, dict):
        return body
    return {}


def dispatch(event: dict, context, routes: list) -> dict:
    """Dispatch event to matching route handler.

    routes: list of (method, path_pattern, handler_fn, requires_auth)
    path_pattern uses regex with named groups for path params.
    """
    method = event.get("httpMethod", "GET").upper()
    path = event.get("path", "/")
    request_start = time.time()

    logger.info(">>> %s %s", method, path)

    # Handle CORS preflight
    if method == "OPTIONS":
        return cors_preflight()

    for route_method, pattern, handler, auth_required in routes:
        if route_method != method:
            continue
        match = re.fullmatch(pattern, path)
        if match:
            if auth_required:
                t0 = time.time()
                auth_error = require_auth(event)
                logger.debug("Auth check took %.1fms", (time.time() - t0) * 1000)
                if auth_error:
                    logger.warning("Auth failed for %s %s", method, path)
                    return auth_error
            try:
                result = handler(event, context, **match.groupdict())
                total_ms = (time.time() - request_start) * 1000
                status = result.get("statusCode", "?")
                logger.info("<<< %s %s -> %s (%.1fms total)", method, path, status, total_ms)
                return result
            except Exception as e:
                total_ms = (time.time() - request_start) * 1000
                logger.error("!!! %s %s -> 500 error: %s (%.1fms)", method, path, e, total_ms, exc_info=True)
                return response(500, {"error": str(e)})

    logger.warning("No route matched: %s %s", method, path)
    return response(404, {"error": "Not found"})
