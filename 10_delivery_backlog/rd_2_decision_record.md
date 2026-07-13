# RD-2 Decision Record — declared-parameter + resolver dedup (Wave-4 slice 1)

> **Status: DRAFT — awaiting OQ ratification (OQ-RD-2-1…5).** A hygiene/dedup slice — NO migration,
> NO permission/audit/methodology, NO new governed number. Pays the two TIPPED items reconciled at the
> Wave-3 close: the declared-parameter parse-back family (PA-1 D-1) and the RD-1 residual resolver
> copies (the Wave-3-close census undercount). The early Wave-4 hygiene slice (fork A), done first so
> PA-3 builds on clean rails — the RD-1 precedent. Delivered under the delivery-autonomy grant (Claude
> self-drives; the USER merges the PR).

## Part 1 — Problem (the census, verified 2026-07-13 at `main` `b6c21d6`)

### 1a — the declared-parameter parse-back family (PA-1 D-1)

Every governed model that carries a **declared identity parameter** parses it back from the version's
`model_assumption` rows with the SAME skeleton: load all assumptions for the version, extract the
sole well-formed value for a prefix, refuse fail-closed (`WrongModelVersionError`, 422 — never a bare
parse crash; the P3-4 lesson that generically-minted versions can stamp anything). That skeleton has
accumulated to **five `declared_*` functions** across two files, sharing three duplicated fragments:

| `declared_*` function | File:line | Returns | Extraction form |
|---|---|---|---|
| `declared_desmoothing_alpha` | `perf/bootstrap.py:319` | `Decimal` | inline single-prefix |
| `declared_window_observations` | `risk/bootstrap.py:376` | `int` | inline single-prefix |
| `declared_var_parameters` | `risk/bootstrap.py:543` | `VarParameters` | nested `_single()` ×3 prefixes |
| `declared_hs_var_parameters` | `risk/bootstrap.py:734` | `HsVarParameters` | nested `_single()` ×4 prefixes |
| `declared_var_backtest_alpha` | `risk/bootstrap.py:1076` | `Decimal` | inline single-prefix |

The duplicated fragments:
- the **identical `select(ModelAssumption).where(...==version.id).scalars().all()` load** — **5 verbatim copies**;
- the **`def _single(prefix) -> str | None` nested helper** — **2 byte-identical copies** (`declared_var_parameters:557`, `declared_hs_var_parameters:746`);
- the **inline "sole well-formed value for a prefix, else refuse" extraction** — **3 copies** (the three single-prefix functions), structurally identical, differing only in prefix / pattern / error code.

This meets the P3-4-R0 3rd-consumer tipping rule several times over (the load is at 5; each extraction
shape at 2–3). The families keep their OWN semantics (domain checks, cross-field validation like
`VAR_Z_SCORES.get(confidence)==z`) — only the load + the sole-value extraction are shared.

### 1b — the RD-1 residual resolver copies (the Wave-3-close census undercount)

RD-1 collapsed the ten resolver copies it enumerated into `calc/runs.py`, but the Wave-3-close audit
found its census was incomplete — **four more copies of the same body survive**, none deferred with a
trigger, contradicting OD-RD-1-C's own "leaving identical copies would be incoherent":

| Straggler | File:line | Shape | Fold target |
|---|---|---|---|
| `resolve_run` (SENSITIVITY) | `risk/service.py:306` | READ | `resolve_run_of_type(not_visible=SensitivityRunNotVisible)` |
| `resolve_run` (EXPOSURE) | `exposure/service.py:333` | READ | `resolve_run_of_type(not_visible=ExposureRunNotVisible)` |
| `_resolve_return_run` | `perf/benchmark_relative_service.py:335` | CONSUMED-guard (**3rd** — trigger MET) | `resolve_completed_run_of_type(error=BenchmarkRelativeInputError)` |
| `_resolve_boundary_dates` (inner core) | `perf/return_service.py:403` | CONSUMED-guard **superset** | inner resolve+COMPLETED core → `resolve_completed_run_of_type`; keep the snapshot/date logic |

The first two are pure misses: `risk/service.py` and `exposure/service.py` never imported the shared
helper at all. The two perf consumed-guards live in files that DID adopt the helper for their read
resolver but left these guard bodies raw.

## Part 2 — Decision

- **OD-RD-2-A — one shared module `model/assumptions.py`** (parallel to RD-1's `calc/runs.py`; low-level,
  imports only `ModelAssumption` + `Session`, so no import cycle — bootstrap imports it, not the reverse),
  with the sole-value primitives:
  - `load_assumption_texts(session, version) -> list[str]` — the one `select(ModelAssumption)` load;
  - `sole_declared(texts, prefix) -> str | None` — the `_single` replacement (exactly-one-or-None);
  - `require_declared(texts, prefix, *, pattern, on_invalid: Callable[[], Exception]) -> str` — builds on
    `sole_declared`; raises `on_invalid()` unless exactly one match AND `pattern.fullmatch`. The
    `on_invalid`-injection precedent is RD-1's `not_visible=` / `error=` and `assert_portfolio_in_tenant(error=…)`.

  All five `declared_*` functions delegate: the three single-prefix ones become
  `require_declared(...)` + their own type-conversion + domain check; the two composite ones become
  `load_assumption_texts(...)` + `sole_declared(...)` per prefix, KEEPING their cross-field validation.
  **Byte-identical behavior** — every path still raises `WrongModelVersionError(str(version.id), CODE)`
  (a class-only refusal with NO free-text message, so nothing observable changes).

- **OD-RD-2-B — fold the two clean read-resolver stragglers** (`risk/service.py` SENSITIVITY,
  `exposure/service.py` EXPOSURE) onto `calc/runs.py:resolve_run_of_type`, each a thin wrapper keeping its
  name / signature / `*RunNotVisible` class. **Byte-identical** (the read path raises
  `not_visible(str(run_id))` verbatim) — these two files were simply missed by RD-1.

- **OD-RD-2-C — fold the two consumed-guard stragglers** (`_resolve_return_run` fully;
  `_resolve_boundary_dates`' inner resolve+COMPLETED core) onto `resolve_completed_run_of_type`. This
  **normalizes their two refusal MESSAGES to the shared phrasing** — e.g. not-visible
  `"…is not a visible COMPLETED return run"` → `"…is not a visible PORTFOLIO_RETURN run"`; the
  non-COMPLETED branch is already byte-identical. This is NOT a new departure: RD-1 already normalized
  the var_backtest + scenario guards to exactly this shared phrasing when it collapsed them, and
  `var_backtest_service._resolve_run` demonstrates the established form. The **error CLASS is preserved**
  (unchanged; the API error-maps key on the class, not the string), and messages are not an API contract
  — the normalization makes the straggler messages consistent with their already-collapsed siblings, and
  is arguably more accurate (the not-visible branch is about run_type/visibility, not completeness).

- **OD-RD-2-D — `_resolve_boundary_dates` is a PARTIAL fold** — only its per-run resolve+COMPLETED core is
  deduped (removing ~13 duplicated lines); its extra logic (input-snapshot-present check, `resolve_snapshot`,
  boundary-date extraction over the run-id SET) stays in place. It keeps its own name / signature / return
  shape (`dict[str, date]`).

- **OD-RD-2-E — scope discipline (non-goals).** Test-and-refactor ONLY: NO migration, NO permission /
  audit / role / methodology, NO new governed number, NO change to any registrar's identity semantics.
  The FR-membership protocol generalization (P3-6 D-2) and the covariance-pin adjudicator (P3-7 B) stay
  DEFERRED with their existing triggers — RD-2 is the mechanical parse-back + resolver collapse, not a
  design-scale extraction.

## Part 3 — Implementation steps (proportionate; mirrors RD-1)

1. Add `model/assumptions.py` with the three primitives + export via `model/__init__.py`.
2. Rewrite the five `declared_*` functions to delegate (byte-identical; drop the 5 loads + 2 `_single` +
   3 inline extractions).
3. Fold the two read-resolver stragglers (OD-RD-2-B) — thin wrappers on `resolve_run_of_type`.
4. Fold the two consumed-guard stragglers (OD-RD-2-C/D) onto `resolve_completed_run_of_type`.
5. New `test_model_assumptions.py` pinning the shared contract directly (sole-value found / absent / ambiguous;
   the `pattern`+`on_invalid` refusal; byte-identical prefixes). The 5 `declared_*` + 4 resolver wrappers stay
   fully exercised by their family suites; add/adjust the two consumed-guard message assertions to the
   normalized strings.
6. Full gate set: `make check` + local-PG clean-schema + `alembic check` (expect NO drift — no migration) +
   the 4-finder adversarial review (proportionate — a hygiene slice; contract + line-scan + cross-file + sweep).

## Part 4 — Open questions for ratification

- **OQ-RD-2-1 — Collapse the declared-parameter parse-back family into `model/assumptions.py` (OD-RD-2-A), all
  five `declared_*` delegating, byte-identical.** *Recommend APPROVE — 5 loads + 2 `_single` + 3 inline
  extractions; the tipping rule fires several times; the families keep their own semantics.*
- **OQ-RD-2-2 — Fold the two clean read-resolver stragglers (OD-RD-2-B), byte-identical.** *Recommend APPROVE
  — pure RD-1 misses; `risk/service.py` + `exposure/service.py` never imported the shared helper.*
- **OQ-RD-2-3 — Fold the two consumed-guard stragglers (OD-RD-2-C/D), ACCEPTING the refusal-message
  normalization to the shared phrasing (class preserved; not API-contractual; extends the precedent RD-1 set
  for var_backtest/scenario).** *Recommend APPROVE — it makes the straggler messages consistent with their
  already-collapsed siblings; the alternative (parameterizing the helper to reproduce each old string exactly)
  adds complexity to preserve a message that is arguably less accurate. This is the one real judgment call.*
- **OQ-RD-2-4 — `model/assumptions.py` as the shared home (vs adding to the existing `model/service.py`).**
  *Recommend APPROVE the dedicated module — mirrors RD-1's focused `calc/runs.py`; keeps `model/service.py`
  (registration/resolution) uncluttered.*
- **OQ-RD-2-5 — Scope stays test-and-refactor only (OD-RD-2-E): NO migration / permission / methodology / new
  number; FR-membership engine + covariance adjudicator stay trigger-deferred.** *Recommend APPROVE.*
