.PHONY: help setup lint format typecheck test secret-scan docs-check dep-audit check fe-setup fe-check fe-audit gen-api gen-api-check

PY := .venv/bin/python
PIP := .venv/bin/pip
VENV_BIN := .venv/bin

help:
	@echo "Backend / Python:"
	@echo "  make setup       - create .venv and install dev deps + local packages"
	@echo "  make lint        - ruff format --check and ruff check"
	@echo "  make format      - auto-format and auto-fix"
	@echo "  make typecheck   - mypy"
	@echo "  make test        - pytest"
	@echo "  make secret-scan - scripts/secret_scan.py (placeholder)"
	@echo "  make docs-check  - scripts/check_docs.py (placeholder)"
	@echo "  make dep-audit   - pip-audit (mirrors the CI dependency-audit gate)"
	@echo "  make check       - run all backend checks"
	@echo "Frontend / Node:"
	@echo "  make fe-setup    - npm ci (lockfile-reproducible, as CI does)"
	@echo "  make fe-check    - lint, format, typecheck, test, build, runtime audit"
	@echo "  make fe-audit    - scripts/check_frontend_audit.mjs (mirrors the CI runtime audit)"

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

# Mirrors the CI "Python dependency audit" step exactly, including the ignored advisory. CI has this
# gate and the local gate did not, so an advisory could fail CI with `make check` green (the same
# class as the prettier gap). NOT folded into `check`: it queries a LIVE advisory service, so an
# unchanged tree can flip red offline or on a service blip — CI owns the blocking verdict (with its
# retry), while this target makes the same answer reachable locally before pushing.
dep-audit:
	$(VENV_BIN)/pip-audit --ignore-vuln PYSEC-2026-1845

check: lint typecheck test secret-scan docs-check

# CI installs with `npm ci` (lockfile-reproducible, fails on a package.json/lock mismatch); using
# `npm install` here meant the lockfile was never enforced locally and could be silently mutated —
# so a lock/manifest divergence only surfaced in CI. Same command both sides now.
fe-setup:
	npm ci

fe-check: fe-setup
	npm run -w packages/shared-ts test
	npm run -w apps/frontend lint
	npm run -w apps/frontend format:check
	npm run -w apps/frontend typecheck
	npm run -w apps/frontend test
	npm run -w apps/frontend build
	node scripts/check_frontend_audit.mjs

# The CI frontend job's "Runtime-dependency audit" (moderate+ gate over the PRODUCTION tree with the
# time-bound reachability-justified allowlist). Also reachable standalone: an EXPIRED exception in
# audit-allowlist.json fails CI by design, and this is how you find that out before pushing.
fe-audit:
	node scripts/check_frontend_audit.mjs

# FE-2 / OD-FE-2-A: regenerate the committed OpenAPI schema + the generated TS types and fail on any
# diff (the local mirror of the CI "API type drift" job). Run after any backend DTO change.
gen-api:
	$(PY) scripts/dump_openapi.py
	npm run -w apps/frontend gen:types

gen-api-check: gen-api
	git diff --exit-code apps/frontend/openapi.json apps/frontend/src/api/generated
