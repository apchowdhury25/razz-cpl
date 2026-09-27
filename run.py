from __future__ import annotations

import argparse

import uvicorn

from app.database import init_db
from app.seed import seed_all


def main() -> None:
    parser = argparse.ArgumentParser(description="Razz CNPL Accounts")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--init", action="store_true", help="Create database tables")
    parser.add_argument("--seed", action="store_true", help="Load demo seed data (safe if already seeded)")
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    if args.init or args.seed:
        init_db()
    if args.seed:
        seed_all()
        print("Database initialized and seeded.")
    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
