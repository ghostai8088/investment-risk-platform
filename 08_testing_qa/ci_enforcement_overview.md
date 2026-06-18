# CI Enforcement Overview

## Document Control

| Field | Value |
|---|---|
| Document ID | TESTQA-CIENFORCE-001 |
| Version | 0.1 (Draft) |
| Status | Accepted as Step 1D scaffold description |
| Owner | R-12 DevOps/SRE AI |
| Approver | H-06 Engineering Lead |
| Created | 2026-06-17 |
| Last Reviewed | 2026-06-17 |
| Related Documents | build_rules.md, control_matrix_skeleton.md, automation_hooks.md, README.md, docs/developer_setup.md |
| Supported Build Rules | BR-1, BR-10, BR-12, BR-15, BR-16 |

## 1. Purpose

Describe how the Step 1D engineering scaffold enforces the ratified standards from the first commit. CI (`.github/workflows/ci.yml`)
runs four jobs; any failing step fails its job and blocks the merge (BR-1: no feature complete without tests; enforcement gate).

## 2. CI jobs → checks → build rules

| CI Job | Steps | Enforces | Maps to control |
|---|---|---|---|
| `backend` | ruff format --check, ruff check, mypy, pytest (incl. foundation-slice tests) | BR-1, BR-11, BR-12, BR-17, BR-18, BR-19 | CTRL-001, CTRL-005, CTRL-011, CTRL-016, CTRL-017, CTRL-019, CTRL-026 |
| `frontend` | eslint, tsc, vitest, vite build | BR-1, UI builds & is typed | CTRL-001 |
| `migration` | alembic upgrade head + downgrade base against a Postgres service | DB schema, RLS tenant isolation (BR-17), append-only triggers (BR-12) | CTRL-011, CTRL-026 |
| `secret-scan` | scripts/secret_scan.py (gitleaks later) | BR-10 (no secrets in source) | CTRL-010 |
| `docs-check` | scripts/check_docs.py | documentation present & doc-control headers | CTRL-002, CTRL-004 |

As of Step 1E the foundation-slice tests make the audit hash-chain, append-only immutability, deny-by-default entitlement,
tenant isolation, and temporal-class declaration into **executable controls** (see `03_architecture/foundation_slice.md`).

## 3. Current placeholders (to be replaced as the platform is built)

- **secret-scan** is a lightweight regex script; replace with the full gitleaks engine (threat model THR-23).
- **docs-check** verifies README presence and Document Control headers; extend to code-change → required-doc-change checks
  (automation_hooks: documentation-consistency hook).
- **Identity** is a dev header shim, not SSO (AD-007); the entitlement gate is real but the principal source is a placeholder.
- **Lineage and model-inventory enforcement checks** are not active yet — they activate when those frameworks/domains are
  built (BR-3, BR-13). No governed surface bypasses audit/entitlement; the foundation simply has no domain surfaces yet.

## 4. Local equivalents

`make check` (backend) and `make fe-check` (frontend) run the same checks locally. See `docs/developer_setup.md`.

## 5. Open Decisions

| ID | Open Decision |
|---|---|
| OD-049 | Choose the production secret-scanning engine and wire it into the `secret-scan` job (gitleaks vs alternative). |
| OD-050 | Add branch protection / required-status-checks configuration once the GitHub repository exists. |

## 6. Dependencies

- build_rules.md (BR-1 … BR-19), control_matrix_skeleton.md (CTRL mapping), automation_hooks.md (hook intent).
