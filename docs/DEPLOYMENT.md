# Deployment

## 1. What is required

| Component | Minimum | Notes |
| --- | --- | --- |
| Python | 3.11+ | API, workers, migrations |
| Node.js | 20+ (22 tested) | Next.js 15 build |
| PostgreSQL | 15+ with **pgvector** | Production metadata + embeddings |
| Redis | 7+ | Celery broker/result backend |
| Object storage | local volume or S3-compatible | Original uploads and Parquet extracts |
| Gemini API key | optional | Without it the platform runs deterministically |

Local development needs none of PostgreSQL/Redis/S3: SQLite + in-process jobs + a local volume are
the defaults.

## 2. Environment variables

All settings are read by `apps/api/app/core/config.py` (Pydantic settings) from `.env` or the
process environment. The authoritative template is [`.env.example`](../.env.example).

| Variable | Purpose |
| --- | --- |
| `ENVIRONMENT` | `development`, `test`, `production` |
| `SECRET_KEY` | JWT signing key — **required** in production |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Session lifetime (default 720) |
| `COOKIE_SECURE` | Set `true` behind HTTPS |
| `DATABASE_URL` | `postgresql+psycopg2://user:pass@host:5432/db` or `sqlite:///…` |
| `STORAGE_BACKEND` / `STORAGE_LOCAL_ROOT` / `S3_*` | Where originals and Parquet live |
| `USE_CELERY`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | Background jobs |
| `GEMINI_API_KEY`, `GEMINI_MODEL`, `LLM_ENABLED` | AI mode |
| `DUCKDB_MEMORY_LIMIT`, `DUCKDB_THREADS`, `QUERY_ROW_LIMIT`, `QUERY_TIMEOUT_SECONDS` | Analytical guardrails |
| `MAX_UPLOAD_BYTES`, `MAX_EXCEL_SHEETS` | Upload limits |
| `CORS_ORIGINS` | Allowed browser origins (only needed if you bypass the Next proxy) |
| `BACKEND_URL` (`apps/web`) | API origin used by the Next.js rewrite |

Generate a key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## 3. Docker Compose (recommended for a first deployment)

```bash
cp .env.example .env
# set SECRET_KEY, optionally GEMINI_API_KEY
docker compose up --build -d
docker compose exec api python scripts/seed_demo.py   # optional demo data
docker compose logs -f api
```

Services:

| Service | Port | Notes |
| --- | --- | --- |
| `web` | 3000 | Next.js standalone server; proxies `/api/v1` to `http://api:8000` |
| `api` | 8000 | Runs `alembic upgrade head` then uvicorn |
| `worker` | — | Celery worker consuming the same image |
| `postgres` | 5432 | `pgvector/pgvector:pg16` |
| `redis` | 6379 | broker + result backend |

Health checks: `GET /api/v1/health` (database + storage + LLM status) and the container-level
`HEALTHCHECK`. Compose waits for PostgreSQL and Redis before starting the API.

> The Next.js rewrite target is compiled into the image at build time
> (`docker build --build-arg BACKEND_URL=http://api:8000`). If the API hostname changes, rebuild the
> web image. This is intentional: the browser never needs to know the API address.

## 4. Manual deployment

```bash
# API
pip install -r apps/api/requirements.txt
export PYTHONPATH=apps/api
(cd apps/api && alembic upgrade head)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers \
  --workers "${WEB_CONCURRENCY:-2}"

# Worker (same image, same env)
celery -A app.workers.celery_app.celery_app worker --loglevel=info --concurrency=2

# Web
cd apps/web
npm ci && BACKEND_URL=https://api.internal.example.com npm run build
npm run start
```

Behind a reverse proxy (nginx/Caddy/ALB):

- terminate TLS and forward `X-Forwarded-Proto`;
- set `COOKIE_SECURE=true`;
- allow request bodies up to `MAX_UPLOAD_BYTES` (default 50 MB);
- keep `/api/v1/*` same-origin through the web tier, or set `CORS_ORIGINS` explicitly;
- `/api/v1/health` is safe for load-balancer checks.

## 5. Database

- PostgreSQL: create `vector` extension (migration `0002` runs `CREATE EXTENSION IF NOT EXISTS vector`
  and converts `document_chunks.embedding` to `vector(256)` with an IVFFlat index).
- SQLite: supported for development and evaluation; do not use it for multi-user production traffic
  (single-writer, no concurrent DDL).
- Migrations: `alembic upgrade head`. Verify a round-trip locally with
  `python apps/api/scripts/check_migrations.py`.

Backups: `pg_dump` for metadata, plus the storage volume (or S3 bucket) for originals and Parquet.
A dataset is unusable without both, so back them up together.

## 6. Object storage

```env
STORAGE_BACKEND=s3
S3_BUCKET=agentic-bi-prod
S3_REGION=eu-west-1
# S3_ENDPOINT_URL=            # set for MinIO/R2
S3_ACCESS_KEY_ID=…
S3_SECRET_ACCESS_KEY=…
```

Use a dedicated IAM principal with `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`,
`s3:ListBucket` on that bucket only. Originals are stored under
`workspaces/{workspace}/datasets/{dataset}/v{n}/`; Parquet extracts sit next to them.

## 7. Scaling notes

- The API is stateless (session in a cookie; metadata in PostgreSQL) → scale horizontally.
- DuckDB executes inside the API process against Parquet. For large concurrency, move analytical
  execution into a dedicated service or use a per-worker DuckDB instance with local Parquet caching.
- Ingestion is CPU-bound: scale Celery workers rather than API replicas.
- Embeddings and narrative rewriting are the only outbound calls; set `GEMINI_*` timeouts and keep
  `GEMINI_MAX_RETRIES` low.
- Rate limits are per process. For a multi-replica deployment put a shared limiter (Redis) in front.

## 8. Observability

- Structured JSON logs with a request id (`X-Request-ID`) on every response.
- `QueryLog` records SQL, parameters, row counts, duration and provenance for every executed query.
- `AuditLog` records authentication, uploads, semantic approvals, dashboard changes, document and
  insight activity.
- Optional Langfuse tracing when `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` are set.

## 9. CI

The pipeline is versioned at `infrastructure/ci/github-actions.yml`. Copy it to
`.github/workflows/ci.yml` in a repository that grants the app `workflows` permission:

```bash
mkdir -p .github/workflows && cp infrastructure/ci/github-actions.yml .github/workflows/ci.yml
```

Jobs: `api` (pytest + migrations + seed + smoke), `web` (typecheck + build), `docker` (image builds),
`e2e` (Playwright, manual dispatch).

## 10. Pre-flight checklist

- [ ] `SECRET_KEY` rotated, `COOKIE_SECURE=true`, TLS terminated
- [ ] `DATABASE_URL` points at PostgreSQL with the `vector` extension available
- [ ] `alembic upgrade head` succeeded
- [ ] Storage backend writable and backed up
- [ ] Celery worker running and `USE_CELERY=true`
- [ ] `GEMINI_API_KEY` set (or the deterministic mode accepted explicitly)
- [ ] `GET /api/v1/health` returns `status: ok`
- [ ] Demo data removed or clearly marked if this is a customer environment
