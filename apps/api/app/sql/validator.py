"""SQL policy validation using SQLGlot AST inspection.

Defence in depth: the API never accepts raw SQL from browsers for execution,
and every generated SQL statement is re-parsed and policy-checked here before
it can reach DuckDB.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

ALLOWED_ROOT_TYPES = (exp.Select, exp.Union, exp.Intersect, exp.Except)
BLOCKED_FUNCTIONS = {
    "read_csv", "read_csv_auto", "read_parquet", "read_json", "read_json_auto", "read_text",
    "parquet_scan", "csv_scan", "json_scan", "glob", "sniff_csv", "sqlite_scan", "sqlite_attach",
    "postgres_scan", "postgres_query", "mysql_scan", "iceberg_scan", "delta_scan",
    "install", "load", "shell", "system", "getenv", "duckdb_extensions", "duckdb_settings",
    "pg_read_file", "read_blob", "query", "query_table", "query", "write_csv", "write_parquet",
    "export_database", "import_database", "create_secret", "http_get", "url_encode",
}
MAX_SQL_LENGTH = 20_000


@dataclass
class ValidationResult:
    valid: bool
    sql: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)


def _table_aliases(tree: exp.Expression) -> set[str]:
    aliases: set[str] = set()
    for table in tree.find_all(exp.Table):
        if table.alias:
            aliases.add(table.alias.lower())
        aliases.add(table.name.lower())
    return aliases


def _defined_names(tree: exp.Expression) -> set[str]:
    names: set[str] = set()
    for cte in tree.find_all(exp.CTE):
        names.add(cte.alias_or_name.lower())
    for alias in tree.find_all(exp.Alias):
        names.add(alias.alias.lower())
    for sub in tree.find_all(exp.Subquery):
        if sub.alias:
            names.add(sub.alias.lower())
    return names


def validate_sql(
    sql: str,
    allowed_tables: set[str],
    allowed_columns: set[str] | None = None,
    row_limit: int = 5000,
) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    if not sql or not sql.strip():
        return ValidationResult(False, sql, ["The SQL statement is empty."])
    if len(sql) > MAX_SQL_LENGTH:
        return ValidationResult(False, sql, ["The SQL statement exceeds the maximum permitted length."])

    try:
        statements = sqlglot.parse(sql, read="duckdb")
    except ParseError as exc:
        return ValidationResult(False, sql, [f"SQL could not be parsed: {exc.errors[0]['description'] if exc.errors else exc}"])

    statements = [s for s in statements if s is not None]
    if len(statements) == 0:
        return ValidationResult(False, sql, ["No SQL statement was found."])
    if len(statements) > 1:
        return ValidationResult(False, sql, ["Multiple SQL statements are not permitted."])

    tree = statements[0]
    if not isinstance(tree, ALLOWED_ROOT_TYPES):
        return ValidationResult(
            False, sql, [f"Only read-only SELECT queries are permitted (received {type(tree).__name__})."]
        )

    # Reject non-select expressions anywhere in the tree (CTEs, subqueries).
    for node in tree.walk():
        if isinstance(node, (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter,
                             exp.Command, exp.Attach, exp.Detach, exp.Copy, exp.Transaction,
                             exp.Commit, exp.Rollback, exp.Use, exp.Set, exp.Grant, exp.TruncateTable)):
            return ValidationResult(False, sql, [f"Statement type {type(node).__name__} is not permitted."])

    tables: list[str] = []
    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        name = (table.name or "").lower()
        if name in cte_names:
            continue
        if table.db and table.db.lower() not in ("main", "temp"):
            return ValidationResult(False, sql, [f"Schema-qualified references are not permitted: {table.sql()}."])
        if name not in {t.lower() for t in allowed_tables}:
            errors.append(f"Table '{name}' is not part of this dataset.")
        tables.append(name)

    for func in tree.find_all(exp.Func):
        try:
            fname = func.sql_name().lower()
        except Exception:  # noqa: BLE001
            fname = ""
        if fname in BLOCKED_FUNCTIONS:
            errors.append(f"Function '{fname}' is not permitted in analytical queries.")
    for anonymous in tree.find_all(exp.Anonymous):
        if (anonymous.name or "").lower() in BLOCKED_FUNCTIONS:
            errors.append(f"Function '{anonymous.name}' is not permitted.")

    if allowed_columns:
        allowed_upper = {c.lower() for c in allowed_columns}
        defined = _defined_names(tree)
        aliases = _table_aliases(tree)
        for column in tree.find_all(exp.Column):
            name = (column.name or "").lower()
            if name == "*" or not name:
                continue
            qualifier = (column.table or "").lower()
            if qualifier and qualifier in aliases:
                if name not in allowed_upper:
                    errors.append(f"Column '{column.name}' does not exist in this dataset.")
            elif not qualifier:
                if name not in allowed_upper and name not in defined:
                    errors.append(f"Column '{column.name}' does not exist in this dataset.")
    if row_limit and row_limit > 0:
        # Enforce the row cap inside the statement itself. Relying only on the
        # fetch layer would still let DuckDB materialise an unbounded result.
        existing_limit = tree.args.get("limit")
        declared: int | None = None
        if existing_limit is not None:
            try:
                declared = int(existing_limit.expression.this)
            except (AttributeError, TypeError, ValueError):
                declared = None
        if declared is None or declared > row_limit:
            tree = tree.limit(row_limit)
            warnings.append(f"Result set capped at {row_limit} rows by the query policy.")
        sql = tree.sql(dialect="duckdb")

    # Strip trailing semicolons and collapse whitespace for execution.
    cleaned = sql.strip().rstrip(";").strip()
    return ValidationResult(
        valid=not errors,
        sql=cleaned,
        errors=errors,
        warnings=warnings,
        tables=sorted(set(tables)),
    )
