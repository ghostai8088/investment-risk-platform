.PHONY: help setup lint format typecheck test secret-scan docs-check mutant-anchors dep-audit check check-all fe-setup fe-check fe-audit gen-api gen-api-check

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
	@echo "  make mutant-anchors - every mutant's anchor still matches its target (seconds)"
	@echo "  make dep-audit   - pip-audit (mirrors the CI dependency-audit gate)"
	@echo "  make check       - run all backend checks"
	@echo "Frontend / Node:"
	@echo "  make fe-setup    - npm ci (lockfile-reproducible, as CI does)"
	@echo "  make fe-check    - lint, format, typecheck, test, build, runtime audit"
	@echo "  make fe-audit    - scripts/check_frontend_audit.mjs (mirrors the CI runtime audit)"
	@echo "Both tiers:"
	@echo "  make check-all   - check + fe-check + gen-api-check (THE local gate, both tiers)"

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

# The CHEAP half of the mutation battery, ratified into `check` at the Wave-17 close gate
# (2026-08-11, D5). It verifies only that every mutant's `find` string still matches the file it
# targets — seconds, no clone, no pytest. The full battery stays a per-slice manual run.
#
# Why it exists: the battery was wired into NO gate at all (`grep -rn mutation_battery Makefile
# .github/workflows/` returned nothing), and four `w16-close` mutants stopped matching when
# ALERT-1 moved bytes in a module it did not own the mutants for. An unmatched anchor is a
# SURVIVOR by the harness's own rule, so the committed battery was RED at HEAD for a day while
# four Wave-16 alarm controls sat with no executable proof — including the infinite-paging bug a
# different review engine had caught. A stale anchor is exactly the failure this just had, and it
# costs seconds to see.
mutant-anchors:
	$(PY) scripts/mutation_battery.py --check-anchors

# Mirrors the CI "Python dependency audit" step exactly, including the ignored advisory. CI has this
# gate and the local gate did not, so an advisory could fail CI with `make check` green (the same
# class as the prettier gap). NOT folded into `check`: it queries a LIVE advisory service, so an
# unchanged tree can flip red offline or on a service blip — CI owns the blocking verdict (with its
# retry), while this target makes the same answer reachable locally before pushing.
dep-audit:
	$(VENV_BIN)/pip-audit --ignore-vuln PYSEC-2026-1845

# Run the FORMATTERS (write mode, both tiers) BEFORE the first gate run. Process fold 2026-08-09:
# the ONBOARD-1b review fold ran `check-all` six times, and three of those runs died on formatting
# or a lint auto-fixable — each a ~5-minute gate cycle buying a 10-second formatter's lesson. This
# target is NOT a gate and proves nothing (the gates still run last and their exit codes are still
# the only claims); it just makes the first gate run start from a tree the formatters have seen.
fix:
	$(PY) -m ruff format .
	# `|| true`: a lint error this cannot auto-fix is `check`'s to REPORT, not this target's to
	# fail on. `fix` is a convenience that runs BEFORE the gate; making it exit non-zero would
	# stop the very gate run it exists to prepare.
	-$(PY) -m ruff check --fix .
	npm run -w apps/frontend format

check: lint typecheck test secret-scan docs-check capability-check mutant-anchors

# BOTH tiers in one command (DEP-1 / Wave-15 process fold). `check` covers Python only and
# `fe-check` has to be REMEMBERED — and the six-consecutive-red-push episode of 2026-08-03 began
# with a FRONTEND formatting failure that nothing local was running. A gate you have to remember to
# run is not a gate; it is a habit, and habits are exactly what P14 exists because of.
#
# Additive on purpose: `check` and `fe-check` are unchanged, so existing muscle memory, the CI job
# definitions and every doc that names them keep working. This target composes them, and the
# ordering is deliberate — `check` is the faster of the two, so a Python-tier failure surfaces
# before ~2 minutes of npm work.
#
# Per P14, quote this target's EXIT CODE, not its last line of output:
#   (make check-all > /tmp/gate.log 2>&1; echo "EXIT=$$?" >> /tmp/gate.log)
# gen-api-check ADDED by the process-fold audit (Fable, 2026-08-05): item 3 of DEP-1 drifted
# openapi.json by 140 lines and was caught only because the builder REMEMBERED to regenerate —
# the mechanical catch existed as a target and was not in the gate. It runs LAST because it
# needs node_modules, which fe-check's fe-setup has installed by then. (dep-audit stays out
# deliberately: it can flip red on an advisory-service blip with no tree change; CI owns that
# verdict with its retry.)
check-all: check fe-check gen-api-check

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

# Compares the regenerated artifacts against the WORKTREE, not against HEAD (process fold
# 2026-08-09). The old form (`git diff --exit-code` after regenerating) diffed worktree vs HEAD,
# which made this target STRUCTURALLY unable to pass before the API change was committed — the
# ONBOARD-1b fold spent a full check-all run discovering that. Snapshot-then-compare asks the
# question this gate actually means ("are the tree's generated artifacts current?") and answers it
# identically pre- and post-commit. CI's "API type drift" job keeps its own git-diff form — there
# the checkout IS HEAD, so the two are equivalent, and CI additionally guards against a locally
# regenerated-but-uncommitted tree being pushed without these files.
gen-api-check:
	@tmp=$$(mktemp -d) && \
	cp apps/frontend/openapi.json $$tmp/openapi.json && \
	cp apps/frontend/src/api/generated/api-types.d.ts $$tmp/api-types.d.ts && \
	$(MAKE) gen-api && \
	if ! diff -u $$tmp/openapi.json apps/frontend/openapi.json || \
	   ! diff -u $$tmp/api-types.d.ts apps/frontend/src/api/generated/api-types.d.ts; then \
		echo "gen-api-check: the tree's generated API artifacts were STALE (now regenerated — review and include them)"; \
		rm -rf $$tmp; exit 1; \
	fi && rm -rf $$tmp

.PHONY: capability-check
capability-check:
	@# Product re-baseline (2026-08-12). Reads the OWNER's capability taxonomy and SCOPE
	@# commitments and fails when one has no requirement behind it. Its inputs are deliberately
	@# documents Claude did not generate — every prior audit used the requirement register as its
	@# yardstick, which is exactly where the Wave 1-17 drift lived.
	$(PY) scripts/check_capability_coverage.py
