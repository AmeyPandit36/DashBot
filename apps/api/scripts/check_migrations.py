#!/usr/bin/env python
"""Verify Alembic migrations apply and roll back cleanly on a throw-away database."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]


def run(args: list[str], database_url: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": database_url, "PYTHONPATH": str(API_ROOT)}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=API_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="agentic-bi-migrations-"))
    database_url = f"sqlite:///{tmp / 'migrations.db'}"

    for step in (["upgrade", "head"], ["current"], ["downgrade", "base"], ["upgrade", "head"]):
        result = run(step, database_url)
        print(f"$ alembic {' '.join(step)} -> exit {result.returncode}")
        if result.returncode != 0:
            print(result.stdout)
            print(result.stderr)
            return result.returncode

    import sqlite3

    connection = sqlite3.connect(tmp / "migrations.db")
    tables = [row[0] for row in connection.execute("select name from sqlite_master where type='table'")]
    connection.close()
    print(f"✓ {len(tables)} tables present after upgrade (including alembic_version)")
    assert "alembic_version" in tables
    assert "document_chunks" in tables
    assert "dashboards" in tables
    print("✓ Migration round-trip succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
