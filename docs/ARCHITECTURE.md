# Architecture

## 1. Principles

1. **Numbers come from SQL, never from a language model.** Gemini can choose *what* to ask and how to
   phrase the answer; DuckDB computes every figure. The verifier re-checks each cited number against
   the rows that were actually returned.
2. **The LLM never touches executable surface.** It cannot emit React, HTML, CSS or a database
   handle. Dashboards are declarative JSON from a fixed widget allowlist. SQL is parsed by SQLGlot,
   validated against an allowlist and executed read-only with parameters.
3. **Tenant isolation is structural.** Organisation and workspace identifiers are part of every
   lookup, not a filter appended at the end. A foreign identifier produces 404.
4. **Jobs, not requests.** Ingestion and cleaning run as tracked jobs with retries and progress.
5. **Any external dependency can be absent.** Gemini, Redis, PostgreSQL, S3 and Celery all have
   local equivalents so the whole system runs end-to-end on a laptop.

## 2. Runtime topology

```
┌──────────────────────────────┐        ┌────────────────────────────────────────────┐
│ Browser (Next.js 15 client)  │        │ FastAPI (uvicorn, 1+ replicas)             │
│  - App Router pages          │  HTTPS │  - auth middleware (http-only JWT cookie)  │
│  - ECharts renderer          │───────▶│  - tenant context dependency               │
│  - no keys, no SQL           │  same  │  - routers: auth, workspaces, datasets,    │
└──────────────┬───────────────┘ origin │    semantic, dashboards, chat, queries,    │
               │ /api/v1/* rewrite      │    insights, documents, jobs, meta         │
               ▼                        └───────┬───────────────┬────────────────────┘
        Next.js server proxy                    │               │
                                                │               │
                        ┌───────────────────────▼──┐   ┌────────▼──────────────────┐
                        │ Metadata store            │   │ Object storage            │
                        │ PostgreSQL (pgvector)     │   │ local volume or S3        │
                        │ SQLite for local dev      │   │ originals + Parquet       │
                        └───────────────────────────┘   └────────┬──────────────────┘
                                                                  │
                        ┌───────────────────────────┐   ┌─────────▼─────────────────┐
                        │ Job queue                 │   │ DuckDB (in-process)        │
                        │ Celery + Redis            │   │ read-only view over Parquet│
                        │ thread fallback (local)   │   │ per-dataset table name     │
                        └───────────────────────────┘   └───────────────────────────┘
```

The browser only ever calls the Next.js origin. `/api/v1/*` is rewritten server-side to the API, so
cookies are same-origin and no CORS or API hostname leaks into client code.

## 3. Data pipeline

1. **Inspect** (`POST /datasets/inspect`) — validates extension/size and lists worksheets for XLSX.
2. **Create** (`POST /datasets/upload`, `/datasets/demo`) — stores the original bytes under
   `workspaces/{ws}/datasets/{id}/v{n}/`, creates a `Dataset` + `DatasetVersion` + `Job`, then
   dispatches the job.
3. **Parse** — CSV: encoding detection (`charset-normalizer`), delimiter sniffing, Polars CSV reader
   with retries across separators. XLSX: `openpyxl` read-only iteration, typed cells, empty rows and
   columns dropped. Column names are normalised to safe identifiers (`^[a-z_][a-z0-9_]*$`).
4. **Coerce** — numeric/date inference with explicit coercion issue tracking; no silent string
   coercion of mixed columns.
5. **Profile** — per column statistics, duplicates, ranges, outlier counts (IQR), quality components
   and recommendations. The formula is stored with the profile so the UI can explain it.
6. **Materialise** — typed frame written to Parquet in object storage; the DuckDB table name
   (`ds_<10 hex>`) is recorded on the version.
7. **Propose semantic model** — heuristic inference (optionally refined by Gemini) validated against
   the real columns; invalid metrics/dimensions are dropped with a report instead of persisted.

Cleaning (`POST /datasets/{id}/clean`) applies only allowlisted reversible operations
(`drop_duplicates`, `trim_whitespace`, `drop_all_null_rows`) to the stored Parquet and creates a new
version. Nothing is applied automatically.

## 4. Analytical query layer

`app/sql/builder.py` turns a declarative query into SQL + parameters:

```json
{
  "metrics": ["total_revenue", "total_orders"],
  "group_by": ["region"],
  "grain": null,
  "filters": [{"field": "region", "operator": "eq", "value": "North"}],
  "order_by": {"field": "total_revenue", "direction": "desc"},
  "limit": 12
}
```

- Identifiers are validated by regex and double-quoted; values are always bound parameters.
- Metrics are resolved through the approved semantic model (SUM / AVG / COUNT_DISTINCT / MIN / MAX /
  RATIO with referenced numerator and denominator).
- Time grains are limited to `day|week|month|quarter|year` and rendered with `DATE_TRUNC`.

`app/sql/validator.py` is the policy gate for every statement (dashboards *and* the analyst):

- exactly one statement, must be a `SELECT`/`WITH … SELECT`;
- no DDL/DML/`ATTACH`/`COPY`/`PRAGMA`/`SET`/transaction nodes anywhere in the tree;
- every referenced table must be the dataset's own view;
- every column must exist in the dataset schema (when the column policy is enabled);
- blocked functions (file system, network, extension management, dynamic SQL);
- the row cap is **injected into the statement** (`LIMIT 5000`) — not merely applied when fetching.

`app/sql/engine.py` opens DuckDB per dataset version, registers the Parquet file, sets memory/thread
limits, and runs the query in a worker thread with a hard timeout (interrupt + connection reset).
Results are JSON-safe, row-limited, timed and returned with the executed SQL.

## 5. Semantic model

```
metrics[]            name, label, source_column, aggregation, format, numerator/denominator
dimensions[]         name, label, data_type, cardinality, confirmed
time_dimensions[]    name, label, default_grain, observed min/max
relationships[]      reserved for multi-table models (documented limitation)
business_definitions term + definition (also indexed for retrieval)
```

Lifecycle: `proposed → approved | rejected`, then any edit creates a **new version** in `proposed`
state (approved → superseded). Approval writes the glossary document, then produces a *draft*
dashboard so the user immediately sees the model in action.

## 6. Agents (LangGraph)

```
START → router
  ├─ sql / hybrid / decomposition ─▶ analyst ─▶ execute ─┬─(error, retry<2)─▶ analyst
  │                                                     └─▶ [rag if hybrid] ─▶ compose
  ├─ definition / business_context ─▶ rag ────────────────────────────────────▶ compose
  ├─ metadata ────────────────────────────────────────────────────────────────▶ verify
  └─ unsupported ─▶ clarify ─────────────────────────────────────────────────▶ verify
compose ─▶ verify ─(ungrounded & llm)─▶ compose      verify ─▶ respond
```

- **router** classifies intent and chooses a route; the choice is returned to the UI.
- **analyst** asks Gemini for a single SELECT (with schema + semantic model) *or* uses the
  deterministic planner that maps the question onto metrics/dimensions/grains. Decompositions build
  a period comparison plus dimension contributions.
- **execute** validates then executes each step; failures feed back into a bounded retry.
- **rag** retrieves approved context (glossary, policy notes) for hybrid and definition routes.
- **compose** writes the narrative. Without Gemini it is fully deterministic and derived from the
  rows; with Gemini the model may rewrite, and the verifier enforces numeric grounding.
- **verify** records five deterministic checks: query execution, SQL policy, evidence presence,
  context attribution and numeric grounding. `status` is `verified | unverified | failed |
  not_applicable`.
- Every step is persisted as a `QueryLog` (SQL, parameters, row count, duration, provenance) and each
  answer stores its query ids, so any figure can be traced from the UI back to the executed SQL.

`numeric_pool()` deliberately includes derived values that a correct narrative may legitimately cite:
shares of a total, deltas between columns, adjacent-period deltas and endpoint changes. Anything
outside that pool is treated as ungrounded.

## 7. Dashboard contract

```jsonc
{
  "schema_version": "1.0",
  "dashboard_id": "…",
  "title": "Business performance overview",
  "dataset_id": "…",
  "semantic_model_version": 2,
  "generation_mode": "automatic | review",
  "layout": {"columns": 12, "gap": 16, "density": "comfortable"},
  "filters": [{"id": "region_filter", "label": "Region", "field": "region",
               "type": "categorical", "default_value": null}],
  "queries": {"kpi_total_revenue": { "metrics": ["total_revenue"], "limit": 1, … }},
  "widgets": [{
    "id": "kpi_total_revenue", "type": "kpi", "title": "Total Amount",
    "query_ref": "kpi_total_revenue",
    "encoding": {"value": "total_revenue"},
    "layout": {"x": 0, "y": 0, "w": 3, "h": 2},
    "interactions": {"cross_filter": false, "click_to_ask": true},
    "options": {"value_format": "currency", "compare": "previous_period"}
  }],
  "metadata": {"…": "provider, dataset version, generator report"}
}
```

Validation rejects unknown widget types, unknown encoding keys, dangling `query_ref`s, duplicate
widget ids, grid overflow and illegal filter fields. Saved versions are immutable; publishing moves
the active pointer. Widget data is fetched per widget through
`POST /dashboards/{id}/widgets/{widget}/data`, which re-validates runtime filters against the
declared filter allowlist and re-runs the query through the policy layer.

KPI widgets may request a `previous_period` comparison. It is computed only when an explicit date
range is applied, by re-running the same aggregate over the equal-length preceding window; if there
is no prior data, no comparison is shown (never an estimate).

## 8. Retrieval

Documents (glossary, business notes, policies) are chunked line-aware (a glossary bullet never merges
with an unrelated metric), embedded and stored in `document_chunks` with organisation, workspace and
optional dataset scope. Gemini embeddings are used when configured; otherwise a deterministic hashed
bag-of-words embedding keeps retrieval functional offline. Similarity is computed over a bounded,
tenant-filtered candidate set, with a pgvector column available on PostgreSQL for ANN indexing.

Retrieved text is passed to the model as *data* inside a delimited block, with instructions that it
cannot override the task. Tests exercise a hostile document and confirm the answer stays grounded.

## 9. Persistence model

23 tables: users, organizations, memberships, invitations, workspaces, workspace_permissions,
datasets, dataset_versions, dataset_columns, jobs, semantic_models, metric_definitions,
dimension_definitions, dashboards, dashboard_versions, conversations, messages, query_logs,
agent_runs, documents, document_chunks, insights, audit_logs.

- UUID string primary keys, timezone-aware timestamps, JSON columns for specifications/profiles.
- SQLite runs in WAL mode with `NullPool` (thread-friendly for the local job runner).
- Alembic owns production schema changes; `init_db()` is only a local convenience.
