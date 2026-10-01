"""
FastAPI application serving all candidates API endpoints.
Replaces the 4 Scaleway serverless functions with a single container.
"""

import base64
import logging
import os
import tempfile
import time

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from candidates.helpers import (
    ALLOWED_ORIGIN,
    create_token,
    get_db,
    get_db_readonly,
    validate_token,
    verify_password,
)

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("main")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN] if ALLOWED_ORIGIN != "*" else ["*"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


def _json(status: int, body: dict) -> JSONResponse:
    return JSONResponse(status_code=status, content=body)


async def require_auth(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    if not validate_token(auth[7:]):
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# -- Auth --


@app.post("/login")
async def login(request: Request):
    print("[LOGIN] /login endpoint hit")
    logger.info("Login attempt started")
    body = await request.json()
    username = body.get("username", "")
    password = body.get("password", "")
    logger.debug("Login attempt for user=%s", username)
    print(f"[LOGIN] user={username}")
    if not username or not password:
        logger.warning("Login rejected: missing username or password")
        print("[LOGIN] rejected: missing credentials")
        return _json(400, {"error": "Username and password are required"})
    if not verify_password(username, password):
        logger.warning("Login failed for user=%s", username)
        print(f"[LOGIN] FAILED for user={username}")
        return _json(401, {"error": "Invalid username or password"})
    logger.info("Login successful for user=%s", username)
    print(f"[LOGIN] SUCCESS for user={username}")
    return _json(200, {"token": create_token()})


# -- Candidates --


@app.get("/candidates", dependencies=[Depends(require_auth)])
async def list_candidates():
    db = get_db()
    candidates = db.get_all_candidates()
    return _json(200, {"candidates": candidates})


@app.get("/candidates/{candidate_id}", dependencies=[Depends(require_auth)])
async def get_candidate(candidate_id: int):
    db = get_db()
    candidate = db.get_candidate(candidate_id)
    if not candidate:
        return _json(404, {"error": "Candidate not found"})
    return _json(200, {"candidate": candidate})


@app.post("/candidates/{candidate_id}/final-verdict", dependencies=[Depends(require_auth)])
async def final_verdict(candidate_id: int, request: Request):
    db = get_db()
    body = await request.json()
    db.update_final_verdict(candidate_id, body.get("final_verdict") or None)
    return _json(200, {"status": "ok"})


@app.post("/candidates/{candidate_id}/interviews", dependencies=[Depends(require_auth)])
async def add_interview(candidate_id: int, request: Request):
    db = get_db()
    body = await request.json()
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
async def update_interview(interview_id: int, request: Request):
    db = get_db()
    body = await request.json()
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
async def delete_interview(interview_id: int):
    db = get_db()
    db.delete_interview(interview_id)
    return _json(200, {"status": "ok"})


@app.post("/candidates/{candidate_id}/proposed-customers", dependencies=[Depends(require_auth)])
async def add_proposed_customer(candidate_id: int, request: Request):
    db = get_db()
    body = await request.json()
    customer_name = body.get("customer_name", "")
    if not customer_name:
        return _json(400, {"error": "customer_name is required"})
    pc_id = db.add_proposed_customer(candidate_id, customer_name)
    return _json(201, {"id": pc_id})


@app.delete("/proposed-customers/{proposed_customer_id}", dependencies=[Depends(require_auth)])
async def delete_proposed_customer(proposed_customer_id: int):
    db = get_db()
    db.delete_proposed_customer(proposed_customer_id)
    return _json(200, {"status": "ok"})


# -- Search --


@app.post("/search", dependencies=[Depends(require_auth)])
async def search(request: Request):
    t_start = time.time()
    print("[SEARCH] /search endpoint hit")
    logger.info("Search endpoint called")
    body = await request.json()
    query = body.get("query", "").strip()
    if not query:
        logger.warning("Search rejected: empty query")
        print("[SEARCH] rejected: empty query")
        return _json(400, {"error": "query is required"})

    logger.info("Search query: %s", query)
    print(f"[SEARCH] query={query}")

    from candidates.llm_client import LLMClient
    from candidates.search_engine import SearchEngine

    model = os.environ.get("LLM_MODEL", "anthropic:claude-sonnet-5-5")
    sql_model = os.environ.get("LLM_MODEL_FAST", "anthropic:claude-haiku-4-5-20251001")
    logger.info("Search using models: summary=%s sql=%s", model, sql_model)
    print(f"[SEARCH] models: summary={model} sql={sql_model}")
    llm = LLMClient(model=model)
    sql_llm = LLMClient(model=sql_model)

    t_db = time.time()
    db = get_db()
    db_ro = get_db_readonly()
    logger.info("Search DB connections ready in %.1fms", (time.time() - t_db) * 1000)
    print(f"[SEARCH] DB ready in {(time.time() - t_db) * 1000:.1f}ms")

    engine = SearchEngine(llm, db, sql_llm_client=sql_llm)

    t_sql = time.time()
    sql = engine._generate_sql(query)
    sql_gen_ms = (time.time() - t_sql) * 1000
    logger.info("Search SQL generated in %.1fms: %s", sql_gen_ms, sql.replace("\n", " "))
    print(f"[SEARCH] SQL generated in {sql_gen_ms:.1f}ms: {sql[:200]}")

    t_exec = time.time()
    try:
        raw_results = db_ro.execute_query(sql)
    except ValueError as e:
        logger.error("Search query rejected: %s", e)
        print(f"[SEARCH] query rejected: {e}")
        return _json(200, {"sql": sql, "raw_results": [], "summary": f"Error: Generated query was rejected - {e}"})
    except Exception as e:
        logger.error("Search SQL execution failed: %s", e)
        print(f"[SEARCH] SQL execution failed: {e}")
        return _json(200, {"sql": sql, "raw_results": [], "summary": f"Error executing query: {e}"})
    sql_exec_ms = (time.time() - t_exec) * 1000
    logger.info("Search SQL executed in %.1fms, %d rows", sql_exec_ms, len(raw_results))
    print(f"[SEARCH] SQL executed in {sql_exec_ms:.1f}ms, {len(raw_results)} rows")

    t_summary = time.time()
    summary = engine._summarize_results(query, sql, raw_results)
    summary_ms = (time.time() - t_summary) * 1000
    total_ms = (time.time() - t_start) * 1000
    logger.info("Search summarized in %.1fms, total=%.1fms", summary_ms, total_ms)
    print(f"[SEARCH] summarized in {summary_ms:.1f}ms, total={total_ms:.1f}ms")

    return _json(200, {"sql": sql, "raw_results": raw_results, "summary": summary})


# -- Upload --


@app.post("/upload", dependencies=[Depends(require_auth)])
async def upload(request: Request):
    body = await request.json()
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

        model = os.environ.get("LLM_MODEL", "anthropic:claude-sonnet-5-5")
        llm = LLMClient(model=model)
        db = get_db()
        extractor = CVExtractor(llm, db)
        result = extractor.ingest_file(tmp_path)

        resp = {"status": "ok", "candidate": result.get("name", "unknown")}
        if result.get("_was_replaced"):
            resp["warning"] = f"Existing CV for '{result['name']}' was replaced."
        return _json(200, resp)
    except Exception as e:
        logger.error("Upload failed: %s", e, exc_info=True)
        return _json(500, {"error": f"Processing failed: {e}"})
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
