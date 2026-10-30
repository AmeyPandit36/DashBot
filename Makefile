# Agentic BI — developer entrypoints.
PYTHON ?= /home/user/.venv/bin/python
PYTHONPATH_API = apps/api
API_URL ?= http://127.0.0.1:8000

.PHONY: help setup seed dev api web test test-api smoke migrations typecheck build docker-up docker-down clean

help:
	@echo "setup       install Python + Node dependencies"
	@echo "seed        create the demo organisation, dataset, dashboard and insights"
	@echo "api         run the FastAPI server on :8000"
	@echo "web         run the Next.js dev server on :3000"
	@echo "dev         run api and web together"
	@echo "test        run the Python suite and the frontend type check"
	@echo "smoke       HTTP end-to-end smoke against a running API"
	@echo "migrations  verify Alembic upgrade/downgrade round-trip"
	@echo "build       production build of the frontend"
	@echo "docker-up   docker compose up --build"

setup:
	$(PYTHON) -m pip install -r apps/api/requirements-dev.txt
	cd apps/web && npm ci

seed:
	PYTHONPATH=$(PYTHONPATH_API) $(PYTHON) apps/api/scripts/seed_demo.py

api:
	PYTHONPATH=$(PYTHONPATH_API) $(PYTHON) -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

web:
	cd apps/web && npm run dev

dev:
	@echo "Run 'make api' and 'make web' in two terminals (or use docker compose)."

test-api:
	cd apps/api && PYTHONPATH=. $(PYTHON) -m pytest -q

typecheck:
	cd apps/web && npm run typecheck

test: test-api typecheck

smoke:
	PYTHONPATH=$(PYTHONPATH_API) $(PYTHON) scripts/smoke_e2e.py

migrations:
	cd apps/api && PYTHONPATH=. $(PYTHON) scripts/check_migrations.py

build:
	cd apps/web && npm run build

docker-up:
	docker compose up --build

docker-down:
	docker compose down -v

clean:
	rm -rf apps/api/data apps/web/.next apps/web/out
