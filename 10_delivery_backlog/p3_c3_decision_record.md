# P3-C3 Decision Record — binder adjudication consistency (Wave-1 hardening carry-in)

| Field | Value |
|---|---|
| Status | **CLOSED — implemented `1bf172b`, CI run #132 GREEN (2026-07-09).** OQ-P3-C3-1…5 ratified (item A; B + C re-deferred). The three binders now fail-close IDENTICALLY on malformed pins. **In-scope discovery (OD-A Part 3):** `factor_service` had NO malformed-pin wrapper at all (worse than its `var`/`var_hs` siblings) — folded. Focused review (OD-D): no defects. Validation green (Part 6). |
| Basis | The P3-7 ultrareview (`p3_7_decision_record.md` Part 6) recorded three deferred findings. The user (2026-07-09) chose to pay item **A** now — a tight binder adjudication **consistency** pass — and to formally re-defer items B (shared covariance-pin adjudicator) and C (`_persist_snapshot` lineage batching). This slice is A only. |
| Grounding | Verified against HEAD `18d35d5` (P3-7 closed, CI #130). The P3-7 fold added `TypeError` to the malformed-pin catch + a 3-letter `base_currency` shape gate to `active_risk_service`. An audit of the sibling binders shows the SAME two gaps un-fixed: **`TypeError`-missing** in `var_service.py:367` + `var_hs_service.py:325`; **`base_currency` uniformity-only** (all-NULL `{None}`/`>3-char` slips to a `String(3) NOT NULL` result column) in `var_service.py:181`, `var_hs_service.py:149`, and `factor_service.py:165` (its atoms are pinned/hand-mintable per its own OD-H docstring; `factor_exposure_result.base_currency` is `String(3) NOT NULL`). No migration; no new permission/audit; `audit/service.py` FROZEN. |
| Honest severity | **LOW / defense-in-depth.** Both gaps are reachable ONLY by a hand-minted snapshot on the consume path; there is NO API endpoint that mints arbitrary snapshot content (`POST /snapshots` builds server-side from a bound portfolio). This slice does not fix a live, user-reachable bug — it makes every binder fail-close IDENTICALLY on malformed pins, closing a *symmetry* gap the P3-7 fold opened in `active_risk_service` alone. The value is consistency of a trust boundary, not urgency. |

---

## Part 1 — Decisions at a glance

| ID | Topic | Decision |
|---|---|---|
| **OD-P3-C3-A** | slice character | A **hardening/consolidation carry-in** (Wave-1). **NO** new governed number/entity/permission/audit code; **NO** migration; `audit/service.py` FROZEN. **Behavior-preserving for the governed (well-formed) path** — the ONLY change is that a malformed hand-minted pin now refuses **pre-create (422)** instead of raising **post-create (500)**; a strictly fail-closed improvement, no COMPLETED result changes. |
| **OD-P3-C3-B** | `TypeError` catch | Add `TypeError` to the `except (KeyError, ValueError, ArithmeticError)` malformed-pin wrapper in **`var_service`** + **`var_hs_service`** (mirror the `active_risk` fold verbatim, incl. the comment). `Decimal(None)` / indexing a non-object `captured_content` raise `TypeError`, which currently escapes as a raw 500 despite each wrapper's own "governed 422, never a raw parse 500" contract. |
| **OD-P3-C3-C** | `base_currency` shape gate | Add the non-null **3-letter** structural check (the exact `active_risk` form: `not isinstance(v, str) or len(v) != 3`) after the uniformity check in **`var_service`** + **`var_hs_service`** + **`factor_service`** — *conditioned on the parsed `base_currency` actually reaching the `NOT NULL` result column* (confirmed for var/var-hs; **verify for factor at impl** — if its `base_currency` is only uniformity-checked and never written, the fix is a no-op and is skipped with a recorded note). **Structural only — NO currency-vocabulary DB lookup** (consistent with `active_risk`; adds no new read to the adjudication path). |
| **OD-P3-C3-D** | proportionate review | A **focused review of the three touched binders** (the TC-1 mechanical-slice precedent), **not** the full 10-finder ultrareview — the change is a ~4-line-per-binder mirror of an already-reviewed, already-test-pinned fold. Each fix is **test-pinned**: a hand-minted malformed-pin (null field) → 422 and an all-NULL/`>3-char` `base_currency` → 422, per binder, mirroring the P3-7 `active_risk` hardening tests. |
| **OD-P3-C3-E** | B + C RE-DEFERRED | **B (shared covariance-pin adjudicator):** stays inline until the **THIRD** covariance consumer — the P3-4-R0 tipping-point rule (currently 2 copies: `var_service` inline + `active_risk_service._adjudicate_covariance`); both are now test-pinned so the drift the review flagged is already caught. **C (`_persist_snapshot` lineage batching):** stays deferred to a **scale-driven efficiency pass** (per-component `SELECT`+`flush` in shared P2-1 code used by every builder; the N-query cost only bites at large-benchmark constituent scale, which is not a current concern). Both recorded here so they are not lost. |

## Part 2 — Open questions (recommended defaults)

- **OQ-P3-C3-1 — scope = item A only.** RATIFIED via the 2026-07-09 scope decision (B + C re-deferred).
- **OQ-P3-C3-2 — `base_currency` check is structural (non-null 3-letter), no vocabulary lookup.** *Recommend APPROVE* — mirrors `active_risk`; keeps every binder identical; no new DB read.
- **OQ-P3-C3-3 — `factor_service` included only if its `base_currency` reaches the `NOT NULL` column (verify at impl; skip-with-note otherwise).** *Recommend APPROVE* — fix the real gap, don't add a vacuous check.
- **OQ-P3-C3-4 — proportionate focused review, not the full ultrareview.** *Recommend APPROVE* — proportionate to a mechanical, already-reviewed mirror fold.
- **OQ-P3-C3-5 — B + C formally re-deferred with the recorded rationale (OD-E).** *Recommend APPROVE.*

## Part 3 — Out of scope (recorded)

The B extraction; the C batching; any change to the governed/well-formed compute path; any new gate BEYOND the two identified (TypeError, base_currency shape) — if the focused review finds a *third* same-class gap in a touched binder it is folded (in-scope); anything else is recorded, not pulled in. No migration; no new permission/audit code; no `audit/service.py` change; no BYPASSRLS/hybrid.

## Part 4 — Implementation plan (the build contract)

1. **`var_service`** — add `TypeError` to the catch tuple (~L367); add the `base_currency` shape check after the uniformity check (~L181). Tests in `test_var.py`: (a) a hand-minted pin with a null numeric field → `VarInputError`/422; (b) all-NULL and `"USDX"` `base_currency` → 422 pre-create (not a post-create IntegrityError/DataError). Mirror the `active_risk` hardening tests.
2. **`var_hs_service`** — same two fixes (catch ~L325; base_currency ~L149). Tests in `test_var_hs.py`.
3. **`factor_service`** — verify the parsed `base_currency` reaches `factor_exposure_result.base_currency`; if so add the shape check (~L165) + a test in `test_factor_exposure.py`; if not, record the no-op finding and skip.
4. **Validation (unreduced gates):** `make check` (ruff/mypy/pytest) + full-PG suite + downgrade smoke (no migration → head unchanged `0030`; run it anyway for parity) + `fe-check` (untouched, run) + the diff fence (binder + test files ONLY; `audit/service.py` + `entitlement/bootstrap.py` untouched; no migration).
5. **Focused review** of the three binders (OD-D) + fold + **HOLD for Tier-2 commit approval.**

**Model/effort:** **Opus 4.8 / medium** — mechanical, templated verbatim on the P3-7 `active_risk` fold; the only judgment is the `factor_service` reach-verification.

## Part 5 — Sign-off
**OQ-P3-C3-1…5 RATIFIED (2026-07-09).** Implementation approved same session; commit is a separate approval (HOLDING).

## Part 6 — Implementation + review log (2026-07-09)

**Built per Part 4.** Three binders, each a ~4-line mirror of the P3-7 `active_risk_service` fold:
- **`var_service`** — `TypeError` added to the malformed-pin catch (L367); `base_currency` 3-letter shape gate (L181).
- **`var_hs_service`** — `TypeError` added (L325); `base_currency` shape gate (L149, after the window check).
- **`factor_service`** — `base_currency` shape gate (L165; verified `base_currency=atom.base_currency` reaches
  `factor_exposure_result.base_currency String(3) NOT NULL` at L215, so the gap is real) **PLUS** the
  malformed-pin `try/except` wrapper it entirely lacked (the OD-A Part-3 in-scope discovery — its `_parse_pins`/
  `_adjudicate_pins` were unguarded, so a missing key / `Decimal(None)` 500'd where the VaR/active-risk siblings
  returned a governed 422).

**Tests (each fix test-pinned, mirroring the P3-7 active-risk hardening tests):**
`test_var.py::test_p3c3_null_or_long_base_currency_and_malformed_pin_refused`;
`test_var_hs.py::test_adjudication_gate_probes` extended (null/long base_currency + null-amount probes);
`test_factor_exposure.py::test_p3c3_null_base_currency_and_malformed_pin_refused` (+ a new `_mint_fe_snapshot`
hand-mint helper — factor's test file had none). All assert the malformed pin → the binder's `*InputError` (422)
pre-create, `_count_runs == 0` (no post-create 500).

**Focused review (OD-D — inline, proportionate):** no defects. Verified: the `next(iter(base_currencies))` is safe
(guarded by the `len == 1` check + non-empty `exposure_raw`); the factor wrapper re-raises `FactorExposureInputError`
and converts only the structural errors; no existing test regressed (the wrapper never fires on the governed
well-formed path). Honest severity unchanged — LOW / defense-in-depth (no user-reachable arbitrary-snapshot path);
the value is binder symmetry on the adjudicator trust boundary.

**Validation (all green):** `make check` (ruff format+lint, mypy 143 files, **1046 passed / 230 skipped**,
secret-scan, docs-check) · full-PG **230 passed** (head unchanged `0030` — NO migration) · `fe-check` untouched
(tsc + **43 FE tests**) · diff fence: **7 files** (this record + 3 binders + 3 tests); `audit/service.py` +
`entitlement/bootstrap.py` + `migrations/` all UNTOUCHED; no new permission/audit code; no BYPASSRLS/hybrid.
