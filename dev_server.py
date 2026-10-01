#!/usr/bin/env python3
"""
Local development server.
Runs the FastAPI app with uvicorn and serves the static frontend.
Uses SQLite locally (no PostgreSQL needed).
"""

import json
import os
import sys

# Set defaults for local dev before any imports that read env vars
os.environ.setdefault("DATABASE_PATH", "cvs.db")
os.environ.setdefault("AUTH_SECRET", "dev-secret-change-me")
# Default user: admin/admin (sha256 hash of "admin")
os.environ.setdefault(
    "AUTH_USERS",
    json.dumps({"admin": "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918"}),
)
os.environ.setdefault("ALLOWED_ORIGIN", "*")


def main():
    import uvicorn
    from candidates.database import Database

    # Initialize database
    db_path = os.environ.get("DATABASE_PATH", "cvs.db")
    db = Database(db_path=db_path)
    db.initialize()
    db.close()

    # Mount static frontend files on the FastAPI app
    from container.main import app
    from fastapi.staticfiles import StaticFiles

    frontend_dir = os.path.join(
        os.path.dirname(__file__), "frontend"
    )
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    print(f"Dev server running at http://localhost:{port}")
    print(f"Using SQLite database: {db_path}")
    print("Default login: admin / admin")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
