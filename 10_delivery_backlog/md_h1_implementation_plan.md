# MD-H1 Implementation Plan — marketdata/registrar hardening + guardrail annex

> Companion to `md_h1_decision_record.md`. Sequenced so each step is independently testable and the
> tree stays green between steps. **No migration** (head stays `0034`). Gated behind OQ-MD-H1-1…8
> ratification. Follows the [[test-data-realism]] fixture rule; `audit/service.py` stays FROZEN.

## Step 0 — Branch + baseline
- Branch `md-h1` off `main` (`9286da1`). Confirm `make check` green at baseline before any edit.

## Step 1 — FR supersede window-coherence guard (OD-MD-H1-B)
1. Add `assert_supersede_effective_at(prior_valid_from: datetime, effective_at: datetime, *, error: Callable[[], Exception]) -> None` to a shared marketdata helper (co-locate with the existing bitemporal helpers; if none, a new `marketdata/_bitemporal.py`). Raises `error()` when `not (effective_at > prior_valid_from)`.
2. Wire it into all 8 supersede functions BEFORE the `prior.valid_to = effective_at` line, each passing its family's existing pre-write `ValueError` subclass (`FxRateValueError`, `PriceValueError`, `CurveValueError`, `FactorValueError`, `BenchmarkSeriesValueError` ×2, `ProxyMappingValueError`, `BenchmarkValueError`). Membership (multi-row): guard each closed row's `valid_from`.
3. Tests: one boundary test per family — `effective_at < valid_from` → refusal (422 at the endpoint), `effective_at == valid_from` → refusal (strictly-greater), `effective_at > valid_from` → success. A parametrized SQLite test covers the shape; add the endpoint-level 422 assertion for one representative family.

## Step 2 — Registrar first-registration race (OD-MD-H1-D)
1. Add `resolve_or_register_model(...)` and `resolve_or_register_version(...)` to `model/service.py`, wrapping the INSERT in `with session.begin_nested(): ...` and, on `IntegrityError`, re-SELECTing the now-committed row (mirroring `dq/gates.py:59`). The governed-conflict checks (code_version mismatch, squatted label) run AFTER the resolve, unchanged.
2. Refactor the 8 bootstrap registrars (7 `risk/bootstrap.py` + 1 `perf/bootstrap.py`) to call the shared helpers instead of open-coding `SELECT → None → register_*`.
3. Test: a forced-collision test (pre-insert the model/version, then drive the bootstrap) proves the loser re-SELECTs instead of 500-ing — the `dq/gates.py` race-test pattern. Add a PG variant (the race is RLS/constraint-real only on PG).

## Step 3 — marketdata IntegrityError→409 (OD-MD-H1-C)
1. Add `IntegrityError: (409, "<stable per-family detail>")` to each `_*_WRITE_ERRORS` map, and ensure each capture route's `except` tuple includes `IntegrityError` routing through the existing dispatch (`_raise_*_write_error`).
2. Test: a duplicate-open-head capture per family returns 409 (not 500), with the transaction cleanly rolled back (a subsequent read sees the original row intact).

## Step 4 — Guardrail annex (OD-MD-H1-E)
1. **Migration identifier sweep** — one test iterating every `migrations/versions/*.py`'s declared identifiers, asserting `len(name) <= 63`. Remove the 2 now-redundant per-file asserts (or keep as fast local guards — decide in review; the repo-wide test is the guarantee).
2. **Shared `_json_safe`** — add a canonical `json_safe(value)` to `snapshot/serialize.py` (datetime→ISO, Decimal→`f"{:f}"` canonical, passthrough). Replace all 10 copies with imports. A characterization test pins the Decimal-canonicalization output so no future copy re-drifts. NOTE: this changes the audit payload for any Decimal previously serialized via `str()` — that is the intended fix; assert the new canonical form explicitly.
3. **Audit-action constants** — a small `ACTION_CREATE/UPDATE/CORRECT/SUPERSEDE/CAPTURE` constant set; replace the raw literals; a conformance test asserts every marketdata emit uses a constant (AST or grep-based test).
4. **PG GUC re-arm fixture** — a pytest fixture/helper that re-arms `set_tenant_context` after commit; adopt it in the existing PG suites where a post-commit read follows a write.
5. **Strict-Decimal parser** — `parse_strict_decimal(raw, *, error)` (reject NaN/Inf via `is_nan()`/`is_infinite()`, quantize) in a shared numeric helper; adopt at the binder parse sites currently doing ad-hoc gates.
6. **No-RUNNING-orphan helper** — `assert_no_running_orphan(session, run_id)` test helper; adopt in the failure-path tests across the governed families.

## Step 5 — Process amendments (OD-MD-H1-F)
1. **Pre-commit hook** — a `.githooks/pre-commit` (or documented `pre-commit` config) running `ruff format --check` + `ruff check` on staged Python; opt-in install documented in `developer_setup`. Full `make check` remains the manual gate.
2. **Golden-derivation rule** — amend `08_testing_qa/` (the test-data-realism doc's sibling) to require every full-stack golden ship its reproduction script/comment.
3. **Design-completeness checklist** — four lines into `claude_operating_instructions.md` (both-sides gates / empty-list inputs / doc-stated-scope enforced / no-RUNNING-orphan).

## Step 6 — Validation + review
- `make check` (incl. `ruff format --check`) green; full local-PG suites + downgrade smoke (head `0034`, no migration); fe-check only if an FE surface is touched (none expected); diff-fence check (`audit/service.py` untouched; no permission/audit/role mint).
- The proportionate **4-finder local review** (OD-MD-H1-H); fold findings pre-commit per the clean-code bar; record dispositions in decision-record Part 6.

## Step 7 — Commit + PR
- Tier-2 gate: Claude pushes `md-h1` on explicit approval; USER opens+merges the PR; CI-watch-to-green; then the closeout appends Part 6 + refreshes the roadmap/status docs.

## Sequencing note
Steps 1–3 (the three register items) are independent and could ship as one commit; the annex (Step 4) and process (Step 5) are additive and low-risk. If the review or the user prefers, Steps 1–3 could land first and Steps 4–5 as a follow-up — but the ratified intent is one slice, so the default is a single coherent MD-H1 branch.
