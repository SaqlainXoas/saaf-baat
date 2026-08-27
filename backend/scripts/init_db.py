"""
Initialize and inspect the local SQLite database.

Usage:
    python scripts/init_db.py            # create tables if missing, print status
    python scripts/init_db.py --reset    # drop and recreate (destroys local data)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db.sqlite_client import SqliteClient, default_sqlite_path  # noqa: E402

TABLES = ("raw_articles", "clusters", "analyzed_feed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize the local SQLite database.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the existing database file before creating the schema.",
    )
    args = parser.parse_args()

    path = default_sqlite_path()

    if args.reset and path.exists():
        confirm = input(f"Delete {path} and all local news data? [y/N] ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return 1
        path.unlink()
        for suffix in ("-wal", "-shm"):
            sidecar = path.with_name(path.name + suffix)
            if sidecar.exists():
                sidecar.unlink()
        print(f"Removed {path}")

    client = SqliteClient()
    print(f"Database: {client.path}")

    with client._connect() as conn:
        for table in TABLES:
            exists = client.table_exists(table)
            count = 0
            if exists:
                count = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            status = "ok" if exists else "MISSING"
            print(f"  {table:<16} {status:<8} rows={count}")

    print("Schema ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
