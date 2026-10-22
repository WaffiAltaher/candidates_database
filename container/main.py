"""
FastAPI application serving all candidates API endpoints.
Replaces the 4 Scaleway serverless functions with a single container.
"""

import base64
import logging
import os
import tempfile
import time
from pathlib import Path

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from candidates.login_limiter import LoginLimiter
from candidates.search_engine import SEARCH_FAILED_MESSAGE
from candidates.helpers import (
    ALLOWED_ORIGIN,
    create_token,
    open_db,
    validate_token,
    verify_password,
)

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    force=True,
)
logger = logging.getLogger("main")

app = FastAPI()
login_limiter = LoginLimiter()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN] if ALLOWED_ORIGIN != "*" else ["*"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


def _json(status: int, body: dict) -> JSONResponse:
    return JSONResponse(status_code=status, content=body)


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    logger.error("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return _json(500, {"error": "Internal server error"})


async def require_auth(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    username = validate_token(auth[7:])
    if username is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    request.state.username = username
    logger.info("%s %s user=%s", request.method, request.url.path, username)


def get_db():
    """Per-request read-write connection (runs in the thread pool)."""
    with open_db() as db:
        yield db


def get_db_readonly():
    """Per-request read-only connection for LLM-generated SQL."""
    with open_db(readonly=True) as db:
        yield db


# Handlers that touch the database or call the LLM are plain `def`, so FastAPI
# runs them in a thread pool instead of blocking the event loop.

# -- Auth --


@app.post("/login")
async def login(request: Request):
    logger.info("Login attempt started")
    body = await request.json()
    username = body.get("username", "")
    password = body.get("password", "")
    logger.debug("Login attempt for user=%s", username)
    if not username or not password:
        logger.warning("Login rejected: missing username or password")
        return _json(400, {"error": "Username and password are required"})
    wait = login_limiter.retry_after(username)
    if wait > 0:
        logger.warning("Login blocked for user=%s, retry after %ss", username, wait)
        response = _json(429, {"error": "Too many failed attempts. Try again later."})
        response.headers["Retry-After"] = str(wait)
        return response
    ok = await run_in_threadpool(verify_password, username, password)
    if not ok:
        login_limiter.record_failure(username)
        logger.warning("Login failed for user=%s", username)
        return _json(401, {"error": "Invalid username or password"})
    login_limiter.reset(username)
    logger.info("Login successful for user=%s", username)
    return _json(200, {"token": create_token(username)})


# -- Candidates --


@app.get("/candidates", dependencies=[Depends(require_auth)])
def list_candidates(db=Depends(get_db)):
    candidates = db.get_all_candidates()
    return _json(200, {"candidates": candidates})


@app.get("/candidates/{candidate_id}", dependencies=[Depends(require_auth)])
def get_candidate(candidate_id: int, db=Depends(get_db)):
    candidate = db.get_candidate(candidate_id)
    if not candidate:
        return _json(404, {"error": "Candidate not found"})
    return _json(200, {"candidate": candidate})


@app.post("/candidates/{candidate_id}/final-verdict", dependencies=[Depends(require_auth)])
def final_verdict(candidate_id: int, body: dict = Body(...), db=Depends(get_db)):
    db.update_final_verdict(candidate_id, body.get("final_verdict") or None)
    return _json(200, {"status": "ok"})


@app.post("/candidates/{candidate_id}/interviews", dependencies=[Depends(require_auth)])
def add_interview(candidate_id: int, body: dict = Body(...), db=Depends(get_db)):
    interview_id = db.add_interview(
        candidate_id=candidate_id,
        interview_number=body.get("interview_number", 1),
        interviewer_name=body.get("interviewer_name", ""),
        comments=body.get("comments", ""),
        verdict=body.get("verdict"),
        interview_date=body.get("interview_date"),
    )
    return _json(201, {"id": interview_id})


@app.put("/interviews/{interview_id}", dependencies=[Depends(require_auth)])
def update_interview(interview_id: int, body: dict = Body(...), db=Depends(get_db)):
    db.update_interview(
        interview_id=interview_id,
        interview_number=body.get("interview_number", 1),
        interviewer_name=body.get("interviewer_name", ""),
        comments=body.get("comments", ""),
        verdict=body.get("verdict"),
        interview_date=body.get("interview_date"),
    )
    return _json(200, {"status": "ok"})


@app.delete("/interviews/{interview_id}", dependencies=[Depends(require_auth)])
def delete_interview(interview_id: int, db=Depends(get_db)):
    db.delete_interview(interview_id)
    return _json(200, {"status": "ok"})


@app.post("/candidates/{candidate_id}/proposed-customers", dependencies=[Depends(require_auth)])
def add_proposed_customer(candidate_id: int, body: dict = Body(...), db=Depends(get_db)):
    customer_name = body.get("customer_name", "")
    if not customer_name:
        return _json(400, {"error": "customer_name is required"})
    pc_id = db.add_proposed_customer(candidate_id, customer_name)
    return _json(201, {"id": pc_id})


@app.delete("/proposed-customers/{proposed_customer_id}", dependencies=[Depends(require_auth)])
def delete_proposed_customer(proposed_customer_id: int, db=Depends(get_db)):
    db.delete_proposed_customer(proposed_customer_id)
    return _json(200, {"status": "ok"})


# -- Search --


@app.post("/search", dependencies=[Depends(require_auth)])
def search(body: dict = Body(...), db=Depends(get_db), db_ro=Depends(get_db_readonly)):
    t_start = time.time()
    logger.info("Search endpoint called")
    query = body.get("query", "").strip()
    if not query:
        logger.warning("Search rejected: empty query")
        return _json(400, {"error": "query is required"})

    logger.info("Search query: %s", query)

    from candidates.llm_client import LLMClient
    from candidates.search_engine import SearchEngine

    model = os.environ.get("LLM_MODEL", "anthropic:claude-sonnet-4-20250514")
    sql_model = os.environ.get("LLM_MODEL_FAST", "anthropic:claude-haiku-4-5-20251001")
    logger.info("Search using models: summary=%s sql=%s", model, sql_model)
    llm = LLMClient(model=model)
    sql_llm = LLMClient(model=sql_model)

    engine = SearchEngine(llm, db, sql_llm_client=sql_llm)

    t_sql = time.time()
    sql = engine._generate_sql(query)
    sql_gen_ms = (time.time() - t_sql) * 1000
    logger.info("Search SQL generated in %.1fms: %s", sql_gen_ms, sql.replace("\n", " "))

    t_exec = time.time()
    try:
        raw_results, truncated = db_ro.run_generated_query(sql)
    except ValueError as e:
        logger.warning("Search query rejected: %s", e, exc_info=True)
        return _json(200, {"sql": sql, "raw_results": [], "truncated": False, "summary": SEARCH_FAILED_MESSAGE})
    except Exception:
        logger.error("Search SQL execution failed", exc_info=True)
        return _json(200, {"sql": sql, "raw_results": [], "truncated": False, "summary": SEARCH_FAILED_MESSAGE})
    sql_exec_ms = (time.time() - t_exec) * 1000
    logger.info("Search SQL executed in %.1fms, %d rows, truncated=%s", sql_exec_ms, len(raw_results), truncated)

    t_summary = time.time()
    summary = engine._summarize_results(query, sql, raw_results)
    summary_ms = (time.time() - t_summary) * 1000
    total_ms = (time.time() - t_start) * 1000
    logger.info("Search summarized in %.1fms, total=%.1fms", summary_ms, total_ms)

    return _json(200, {"sql": sql, "raw_results": raw_results, "truncated": truncated, "summary": summary})


# -- Upload --


@app.post("/upload", dependencies=[Depends(require_auth)])
def upload(body: dict = Body(...), db=Depends(get_db)):
    filename = body.get("filename", "")
    file_data = body.get("file_data", "")

    if not filename or not file_data:
        return _json(400, {"error": "filename and file_data are required"})

    ext = os.path.splitext(filename)[1].lower()
    if ext != ".pdf":
        return _json(400, {"error": f"Only PDF files are allowed, got {ext}"})

    try:
        file_bytes = base64.b64decode(file_data)
    except Exception:
        return _json(400, {"error": "Invalid base64 file_data"})

    max_file_size = 10 * 1024 * 1024
    if len(file_bytes) > max_file_size:
        return _json(400, {"error": f"File too large (max {max_file_size // 1024 // 1024}MB)"})

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        from candidates.cv_extractor import CVExtractor
        from candidates.llm_client import LLMClient

        model = os.environ.get("LLM_MODEL", "anthropic:claude-sonnet-4-20250514")
        llm = LLMClient(model=model)
        extractor = CVExtractor(llm, db)
        result = extractor.ingest_file(tmp_path)

        resp = {"status": "ok", "candidate": result.get("name", "unknown")}
        if result.get("_was_replaced"):
            resp["warning"] = f"Existing CV for '{result['name']}' was replaced."
        return _json(200, resp)
    except Exception as e:
        logger.error("Upload failed: %s", e, exc_info=True)
        return _json(500, {"error": "Processing failed. Check that the file is a readable PDF."})
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _frontend_dir() -> Path:
    here = Path(__file__).resolve().parent
    for candidate in (here / "frontend", here.parent / "frontend"):
        if candidate.is_dir():
            return candidate
    raise RuntimeError("frontend directory not found")


# Must stay last so the API routes above match first
app.mount("/", StaticFiles(directory=_frontend_dir(), html=True), name="frontend")
