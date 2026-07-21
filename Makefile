.PHONY: help setup lint format typecheck test secret-scan docs-check check fe-setup fe-check gen-api gen-api-check

PY := .venv/bin/python
PIP := .venv/bin/pip

help:
	@echo "Backend / Python:"
	@echo "  make setup       - create .venv and install dev deps + local packages"
	@echo "  make lint        - ruff format --check and ruff check"
	@echo "  make format      - auto-format and auto-fix"
	@echo "  make typecheck   - mypy"
	@echo "  make test        - pytest"
	@echo "  make secret-scan - scripts/secret_scan.py (placeholder)"
	@echo "  make docs-check  - scripts/check_docs.py (placeholder)"
	@echo "  make check       - run all backend checks"
	@echo "Frontend / Node:"
	@echo "  make fe-setup    - npm install"
	@echo "  make fe-check    - lint, typecheck, test, build"

setup:
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-dev.txt
	$(PIP) install -e packages/shared-python -e apps/backend -e apps/worker

lint:
	$(PY) -m ruff format --check .
	$(PY) -m ruff check .

format:
	$(PY) -m ruff format .
	$(PY) -m ruff check --fix .

typecheck:
	$(PY) -m mypy

test:
	$(PY) -m pytest

secret-scan:
	$(PY) scripts/secret_scan.py

docs-check:
	$(PY) scripts/check_docs.py

check: lint typecheck test secret-scan docs-check

fe-setup:
	npm install

fe-check: fe-setup
	npm run -w packages/shared-ts test
	npm run -w apps/frontend lint
	npm run -w apps/frontend typecheck
	npm run -w apps/frontend test
	npm run -w apps/frontend build

# FE-2 / OD-FE-2-A: regenerate the committed OpenAPI schema + the generated TS types and fail on any
# diff (the local mirror of the CI "API type drift" job). Run after any backend DTO change.
gen-api:
	python scripts/dump_openapi.py
	npm run -w apps/frontend gen:types

gen-api-check: gen-api
	git diff --exit-code apps/frontend/openapi.json apps/frontend/src/api/generated
