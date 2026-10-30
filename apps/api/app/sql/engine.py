"""Controlled DuckDB execution service.

Guarantees:
* A fresh in-memory catalogue per dataset, loaded from the server-generated
  Parquet artefact (never from user-supplied paths).
* External file access disabled *after* the dataset view is registered.
* Row limits enforced by wrapping the query, memory limits and query timeouts.
* Every execution is logged by the caller with full provenance.
"""
from __future__ import annotations

import threading
import time
from datetime import date, datetime, time as dtime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

from app.core.config import settings
from app.core.errors import AppError

_local = threading.local()
_lock = threading.Lock()
_conn_cache: dict[str, duckdb.DuckDBPyConnection] = {}


def _json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date, dtime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")[:200]
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return None
    return value


def close_cached_connections() -> None:
    with _lock:
        for con in _conn_cache.values():
            try:
                con.close()
            except Exception:  # noqa: BLE001
                pass
        _conn_cache.clear()


class DatasetEngine:
    """Executes read-only SQL over one dataset version."""

    def __init__(self, parquet_path: str | Path, table_name: str):
        self.parquet_path = str(Path(parquet_path).resolve())
        self.table_name = table_name
        self._cache_key = f"{self.parquet_path}:{table_name}"

    # -- connection management -------------------------------------------------
    def _connection(self) -> duckdb.DuckDBPyConnection:
        cache: dict[str, duckdb.DuckDBPyConnection] = getattr(_local, "connections", {})
        con = cache.get(self._cache_key)
        if con is not None:
            return con
        con = duckdb.connect(database=":memory:")
        con.execute(f"SET memory_limit='{settings.DUCKDB_MEMORY_LIMIT}'")
        con.execute(f"SET threads={settings.DUCKDB_THREADS}")
        try:
            con.execute("SET preserve_insertion_order=false")
        except Exception:  # noqa: BLE001
            pass
        safe_path = self.parquet_path.replace("'", "''")
        quoted = self.table_name.replace('"', '""')
        con.execute(
            f'CREATE TABLE "{quoted}" AS SELECT * FROM read_parquet(\'{safe_path}\')'
        )
        try:
            con.execute("SET enable_external_access=false")
        except Exception:  # noqa: BLE001
            pass
        cache[self._cache_key] = con
        _local.connections = cache
        with _lock:
            _conn_cache[self._cache_key] = con
        return con

    def schema(self) -> list[dict]:
        con = self._connection()
        rows = con.execute(f'DESCRIBE "{self.table_name}"').fetchall()
        return [{"name": r[0], "type": r[1]} for r in rows]

    # -- execution -------------------------------------------------------------
    def execute(self, sql: str, params: list | None = None, limit: int | None = None) -> dict:
        row_limit = limit or settings.QUERY_ROW_LIMIT
        con = self._connection()
        wrapped = f"SELECT * FROM ({sql}) AS _abi_result LIMIT {int(row_limit) + 1}"
        started = time.perf_counter()
        result: dict[str, Any] = {}
        error: list[BaseException] = []

        def _run() -> None:
            try:
                cursor = con.execute(wrapped, params or [])
                columns = [d[0] for d in cursor.description] if cursor.description else []
                types = [str(d[1]) for d in cursor.description] if cursor.description else []
                rows = cursor.fetchall()
                result.update({"columns": columns, "types": types, "rows": rows})
            except BaseException as exc:  # noqa: BLE001 - surfaced to caller as AppError
                error.append(exc)

        worker = threading.Thread(target=_run, daemon=True)
        worker.start()
        worker.join(timeout=settings.QUERY_TIMEOUT_SECONDS)
        if worker.is_alive():
            try:
                con.interrupt()
            except Exception:  # noqa: BLE001
                pass
            with _lock:
                _conn_cache.pop(self._cache_key, None)
            cache = getattr(_local, "connections", {})
            cache.pop(self._cache_key, None)
            raise AppError("QUERY_TIMEOUT", "The query exceeded the execution time limit.", 408)

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        if error:
            message = str(error[0])
            raise AppError("QUERY_FAILED", f"The analytical query failed: {message}", 400)

        rows = result["rows"]
        truncated = len(rows) > row_limit
        if truncated:
            rows = rows[:row_limit]
        safe_rows = [[_json_safe(v) for v in row] for row in rows]
        return {
            "columns": result["columns"],
            "column_types": result["types"],
            "rows": safe_rows,
            "row_count": len(safe_rows),
            "truncated": truncated,
            "duration_ms": duration_ms,
            "limit": row_limit,
        }


def scalar(engine: DatasetEngine, sql: str, params: list | None = None) -> Any:
    result = engine.execute(sql, params=params, limit=1)
    if not result["rows"]:
        return None
    return result["rows"][0][0]
