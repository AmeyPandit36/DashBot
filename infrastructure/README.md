# Infrastructure assets

Everything needed to run Agentic BI outside a laptop lives at the repository root so that
`docker compose up` and CI work from a clean checkout:

| Path | Purpose |
| --- | --- |
| `docker-compose.yml` | PostgreSQL (pgvector) + Redis + API + Celery worker + Next.js |
| `apps/api/Dockerfile` | API/worker image; runs `alembic upgrade head` before starting uvicorn |
| `apps/web/Dockerfile` | Multi-stage Next.js standalone build (`BACKEND_URL` build arg) |
| `apps/api/alembic.ini`, `apps/api/migrations/` | Schema migrations |
| `Makefile` | `setup`, `seed`, `api`, `web`, `test`, `smoke`, `migrations`, `build`, `docker-up` |
| `infrastructure/ci/github-actions.yml` | CI: tests, migration round-trip, seed + smoke, frontend build, image builds, Playwright job |

The CI definition ships under `infrastructure/ci/` because the automation account that prepared this
repository cannot write to `.github/workflows/` (missing `workflows` scope). Install it with:

```bash
mkdir -p .github/workflows && cp infrastructure/ci/github-actions.yml .github/workflows/ci.yml
```

No cloud-specific Terraform is included: the deployment target is intentionally generic (any host
that runs containers plus a PostgreSQL 15+ instance with the `vector` extension). See
[`../docs/DEPLOYMENT.md`](../docs/DEPLOYMENT.md) for the production checklist.

Validate the Compose file without Docker:

```bash
python -c "import yaml,json; print(json.dumps(yaml.safe_load(open('docker-compose.yml'))['services'], indent=2)[:400])"
```
