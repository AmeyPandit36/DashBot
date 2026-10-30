# Agentic BI

**Your business data. An intelligent new perspective.**

Agentic BI is a multi-tenant AI business-intelligence SaaS. Upload a retail CSV/XLSX file, get a
profiling report, review an automatically inferred semantic model, publish a dashboard, and ask
numerical questions that are answered by **real SQL executed in DuckDB** — with the generated SQL,
row counts and verification checks attached to every answer.

Nothing in this repository is a mock. There is no seeded "demo mode", no hard-coded chart data and
no fabricated insight: the demo dataset is generated deterministically on your machine, ingested
through the same pipeline as a user upload, and every number shown in the product is the result of a
query that actually ran.

---

## Highlights

| Capability | How it works |
| --- | --- |
| **Ingestion** | CSV (encoding + delimiter detection) and Excel (sheet selection, typed cells) → normalised Parquet → DuckDB. Files are parsed as *data*, never evaluated. |
| **Profiling** | Per-column nulls, uniques, ranges, outliers and coercion issues, plus a documented quality score: `100 × (0.35·completeness + 0.15·uniqueness + 0.20·validity + 0.15·consistency + 0.15·outlier_control)`. |
| **Semantic model** | Heuristic inference (or Gemini structured output when a key is configured) proposes metrics, dimensions, time dimensions and a glossary. A human approves, edits or rejects it; every proposal is validated against real columns before it is persisted. |
| **Dashboards** | A planner emits a **strict declarative JSON specification** (widget allowlist, encodings, grid, filters). A trusted React/ECharts component registry renders it. The model can never emit JSX, HTML or CSS. |
| **AI Analyst** | A LangGraph agent routes the question, writes read-only SQL (Gemini or the deterministic planner), executes it through the policy layer, composes a grounded narrative and has a verifier re-check every cited number against the returned rows. |
| **Business context** | Approved semantic definitions and free-text notes are chunked, embedded and retrieved with tenant/workspace isolation. Context explains *why*, it never computes numbers. |
| **Insights** | Deterministic scans (period deltas, dimension contributions, data quality) produce evidence-backed findings, each carrying its SQL. |
| **Tenancy** | Every dataset, dashboard, conversation, document, query log and insight is scoped by organisation *and* workspace. Cross-tenant access returns 404, never 403-with-detail. |
| **Background work** | Ingestion, cleaning and semantic generation are jobs. Celery + Redis in deployment; an in-process worker locally. Nothing heavy runs inside an HTTP handler. |

## Screens

| Route | Purpose |
| --- | --- |
| `/` | Marketing landing page (live component preview, dark/light). |
| `/login`, `/register`, `/forgot-password`, `/reset-password` | Auth flows with http-only cookie sessions. |
| `/app` | Overview: KPIs, datasets, dashboards, insights, recent analyst activity. |
| `/app/datasets`, `/app/datasets/[id]` | Upload/inspect, profiling report, schema, versions, opt-in cleaning, delete. |
| `/app/semantic`, `/app/semantic/[id]` | Semantic-model review: metrics, dimensions, time, glossary, approve. |
| `/app/dashboards`, `/app/dashboards/[id]` | Dashboard library and renderer with filters, cross-filtering, edit mode, versions, SQL inspection. |
| `/app/analyst` | Streaming-style analyst: suggested questions, verified answers, result tables, evidence SQL, follow-ups, feedback. |
| `/app/insights` | Verified findings with severity filters and evidence. |
| `/app/settings` | Profile, appearance, workspaces, members/invites, knowledge base, platform status. |

## Architecture at a glance

```
Next.js 15 (App Router, RSC + client islands)
   │  /api/v1/* rewrite (server-side proxy; the browser never sees a backend origin)
   ▼
FastAPI ── auth (http-only JWT cookie) ── auth gate middleware ── tenant context
   ├── PostgreSQL / SQLite metadata (SQLAlchemy 2, Alembic)
   ├── Object storage (local volume or S3) for originals + Parquet extracts
   ├── Job queue (Celery/Redis) or in-process worker for ingestion
   ├── DuckDB analytical engine (read-only views over Parquet)
   │      └── SQLGlot policy: single SELECT, allowlisted tables/columns, row cap, timeout
   ├── LangGraph agents: Router → Analyst → Execute → RAG → Compose → Verify → Respond
   └── RAG: chunk → embed (Gemini or deterministic hashing) → pgvector / JSON store
```

Deeper detail lives in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Quick start (local, no external services)

```bash
# 1. Python 3.11+ environment
python3 -m venv .venv && source .venv/bin/activate
pip install -r apps/api/requirements-dev.txt

# 2. Configuration
cp .env.example .env            # SQLite + local storage works out of the box

# 3. Seed a complete demo organisation (idempotent)
PYTHONPATH=apps/api python apps/api/scripts/seed_demo.py

# 4. API on :8000
PYTHONPATH=apps/api uvicorn app.main:app --app-dir apps/api --reload --port 8000

# 5. Web on :3000
cd apps/web && npm ci && npm run dev
```

Open <http://localhost:3000> and sign in with the seeded account:

```
demo@agenticbi.dev / DemoPass123!
```

Prefer one command? `make setup && make seed && make dev`.

## Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

This starts PostgreSQL 16 with pgvector, Redis, the API (runs `alembic upgrade head` on boot), a
Celery worker and the Next.js frontend. Then seed the demo inside the running stack:

```bash
docker compose exec api python scripts/seed_demo.py
```

See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for production notes (TLS, secrets, object storage,
backups, scaling, health checks).

## AI configuration

| Mode | Requirements | Behaviour |
| --- | --- | --- |
| **Gemini** | `GEMINI_API_KEY` + `LLM_ENABLED=true` | Gemini proposes semantic models and dashboards (structured JSON only), writes SQL candidates, embeddings and narrative rewrites. Every output is still validated, executed and verified. |
| **Deterministic** (default here) | none | Rule-based semantic inference, planner-driven SQL, deterministic narrative composition and hashed embeddings. Same pipeline, same guardrails, no external calls. |

The Gemini key is read only by the API process. It is never sent to the browser and never appears in
logs, responses or error payloads. The frontend only receives a boolean `llm.enabled` flag plus a
human-readable note.

## Testing

```bash
cd apps/api
PYTHONPATH=. python -m pytest -q                 # unit + integration + eval benchmark
PYTHONPATH=. python scripts/check_migrations.py   # alembic upgrade/downgrade round-trip
PYTHONPATH=../.. python ../../scripts/smoke_e2e.py  # HTTP end-to-end smoke (optional)
cd ../../apps/web
npm run typecheck && npm run build
```

Current results, the 55-question AI benchmark and the honest list of what could **not** be executed
in this environment are in [`docs/TESTING.md`](docs/TESTING.md).

## Repository layout

```
apps/api/
  app/
    api/v1/        auth, workspaces, datasets, semantic, dashboards, chat, queries, insights, documents, jobs, meta
    analytics/     ingestion, profiling, cleaning, synthetic retail generator
    semantic/      inference, validation, glossary rendering
    sql/           declarative query builder, SQLGlot validator, DuckDB engine, planner
    agents/        LangGraph graph, tools, verifier, LLM client, narrative
    dashboards/    strict spec schema + planner
    rag/           chunking, embeddings, retrieval store
    services/      orchestration (datasets, semantic, dashboards, chat, insights, audit, jobs)
    workers/       Celery app + shared job runner
  migrations/      Alembic environment and revisions
  tests/           87 tests incl. the eval benchmark
  scripts/         seed_demo.py, check_migrations.py
apps/web/
  app/             App Router pages (landing, auth, workspace)
  components/      UI primitives, charts, layout, dashboard registry, common
  lib/             typed API client, auth context, chart option builders, formatting
scripts/           smoke_e2e.py
infrastructure/ci/ CI workflow (copy to .github/workflows/ci.yml)
docs/              architecture, deployment, testing, limitations, acceptance
infrastructure/    compose assets and notes
```

## Security posture

- Read-only analytical engine; the LLM never receives a database handle. It proposes SQL, which is
  parsed, policy-checked, capped and executed with parameters.
- SQL policy rejects non-SELECT statements, multiple statements, non-allowlisted tables/columns,
  schema-qualified references, file/extension/network functions and unsafe identifiers.
- Uploaded content is treated as untrusted: prompt-injection text in a dataset or document cannot
  alter tool instructions, and answers remain SQL-grounded (covered by tests).
- Tenant scoping is applied in every query path, including conversations, documents, query logs and
  insights. The audit log records who did what, in which workspace.
- http-only, SameSite=Lax session cookies; bcrypt password hashing; per-IP rate limiting; secure
  headers; no secrets in the frontend bundle.

## Known limitations

Read [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) before deploying. The short version: single
uploaded table per dataset (no joins yet), SQLite/in-process fallbacks for local runs, retrieval
similarity computed in-process unless PostgreSQL+pgvector is used, no forecasting, and Playwright
specs ship unexecuted because no browser binary could be installed in the build sandbox.

## License

Proprietary demonstration project. See the repository owner for terms.
