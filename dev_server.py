#!/usr/bin/env python3
"""
Local development server.
Runs the FastAPI app with uvicorn and serves the static frontend.
Uses SQLite locally (no PostgreSQL needed).
"""

import argparse
import json
import os

# Set defaults for local dev before any imports that read env vars
os.environ.setdefault("DATABASE_PATH", "cvs.db")
os.environ.setdefault("AUTH_SECRET", "local-dev-secret-not-used-in-production")
# Default user: admin/admin (scrypt hash of "admin")
os.environ.setdefault(
    "AUTH_USERS",
    json.dumps({"admin": "scrypt$16384$8$1$Y2FuZGlkYXRlcy1kZXYtMQ==$aYz/67aCRaL8SQxCWfYwt/nBlX7aSdAl8vE7H8hoQo8="}),
)


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Local development server")
    parser.add_argument("port", nargs="?", type=int, default=8080)
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Interface to listen on (default 127.0.0.1; use 0.0.0.0 to allow other machines)",
    )
    args = parser.parse_args(argv)

    # Must be set before importing container.main: candidates.helpers reads it on import
    os.environ.setdefault("ALLOWED_ORIGIN", f"http://localhost:{args.port}")

    import uvicorn
    from candidates.database import Database

    # Initialize database
    db_path = os.environ.get("DATABASE_PATH", "cvs.db")
    db = Database(db_path=db_path)
    db.initialize()
    db.close()

    from container.main import app

    if args.host == "127.0.0.1":
        print(f"Dev server running at http://localhost:{args.port}")
    else:
        print(f"Dev server running at http://{args.host}:{args.port} (reachable from other machines)")
    print(f"Using SQLite database: {db_path}")
    print("Default login: admin / admin")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
