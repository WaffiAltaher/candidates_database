"""
Shared utilities: CORS, auth, response building, DB singleton, route dispatch.
"""

import hashlib
import hmac
import json
import logging
import os
import re
import time

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("helpers")

# Suppress noisy third-party loggers
for _noisy in ("httpcore", "httpx", "anthropic", "aisuite"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
AUTH_SECRET = os.environ.get("AUTH_SECRET", "dev-secret-change-me")
# AUTH_USERS: JSON map of username -> sha256 hash, e.g. {"alice":"abc123...","bob":"def456..."}
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
    hashed = hashlib.sha256(password.encode()).hexdigest()
    return hmac.compare_digest(hashed, expected_hash)


# --- DB singleton ---

_db_instance = None
_db_readonly_instance = None


def get_db():
    """Get or create the database singleton. Reconnects if connection is dead."""
    global _db_instance
    database_url = os.environ.get("DATABASE_URL")

    if _db_instance is None:
        t0 = time.time()
        from candidates.database import Database
        if database_url:
            _db_instance = Database(database_url=database_url)
        else:
            _db_instance = Database(db_path=os.environ.get("DATABASE_PATH", "cvs.db"))
        _db_instance.initialize()
        logger.info("DB initialized (cold start) in %.1fms", (time.time() - t0) * 1000)
    elif database_url and not _db_instance.is_connected():
        t0 = time.time()
        _db_instance.reconnect(database_url)
        logger.info("DB reconnected in %.1fms", (time.time() - t0) * 1000)
    else:
        logger.debug("DB reusing existing connection")

    return _db_instance


def get_db_readonly():
    """Get or create a read-only database connection for LLM-generated queries.

    Falls back to the regular connection in local dev (SQLite).
    """
    global _db_readonly_instance
    database_url_ro = os.environ.get("DATABASE_URL_READONLY")

    if not database_url_ro:
        # Local dev / no read-only URL configured — fall back to regular DB
        return get_db()

    if _db_readonly_instance is None:
        t0 = time.time()
        from candidates.database import Database
        _db_readonly_instance = Database(database_url=database_url_ro)
        logger.info("DB read-only initialized (cold start) in %.1fms", (time.time() - t0) * 1000)
    elif not _db_readonly_instance.is_connected():
        t0 = time.time()
        _db_readonly_instance.reconnect(database_url_ro)
        logger.info("DB read-only reconnected in %.1fms", (time.time() - t0) * 1000)
    else:
        logger.debug("DB read-only reusing existing connection")

    return _db_readonly_instance


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
