# Methodology — Pure-Private Segment Factor Returns (desmoothed minus proxy, pooled) v1

**Model code** `risk.factor_return.pure_private` · **version label** `v1` · **entity** ENT-060 `private_factor_return_result` · **migration** `0047` · **slice** PPF-1 (Wave-10; the platform's 18th governed number, §2.1 arc slice 1)

> **Written at RPT-1 (2026-08-05), and the gap is the point.** `PURE_PRIVATE_METHODOLOGY_REF` has
> pointed at this path since PPF-1 shipped, and **the file never existed** — `git log
> --diff-filter=A` over this directory does not list it. CTRL-002 ("every calculation has a
> methodology doc") was stamped *Operational* against that. Nothing caught it because the
> per-family doc tests were hand-copied and PPF-1 never got one; the census that now enforces this
> across all 27 registered references (`test_methodology_refs.py`) is the mechanical countermeasure,
> and this document is the debt it made visible being paid. The content below is reconstructed from
> the registered `model_assumption` / `model_limitation` rows in
> `risk/bootstrap.py` — the governed source of truth — not from memory.

## Purpose & applicability

The **private-only** component of a private asset's return: what is left after the part explained by
public risk factors is removed. PA-1 desmoothed the appraisal series (Geltner AR(1)); PA-3 estimated
each instrument's blend of public factors by regression. This slice subtracts the second from the
first and pools the remainder across a segment, producing a factor return series for the risk that
public markets do not explain — the liquidity/illiquidity premium and the private-market cycle.

Applies to a **segment** (a named grouping of private instruments) whose members each carry a
current-head REGRESSION proxy blend and a desmoothed return series on **exactly matching** period
intervals. It is the first slice of the §2.1 arc: PPF-2 builds its covariance block, PPF-3 the
unified public+private number.

It does **not** apply where members' period grids differ (a named-gap refusal, never interpolation),
nor to any book without a promoted REGRESSION blend.

## Inputs & data policy

- **Desmoothed returns** (ENT-056, PA-1) — the member's appraisal series with smoothing removed.
- **Proxy weights** (ENT-057, PA-3) — the member's current-head REGRESSION blend, `w_i,f`.
- **Public factor returns** (ENT-025 family) — captured, compounded over the half-open
  `(period_start, period_end]` window (the shared PA-3 alignment convention).

All three are **snapshot-pinned**; the computation reads pinned content only (AD-014 / TR-09), so a
later re-run upstream cannot move a historical pure-private number. Upstream run ids and instrument
ids are **re-resolved under the acting tenant** before being stamped into any hard FK — PostgreSQL FK
checks bypass RLS, so the database alone would durably admit a foreign tenant's row (the P3-5 guard).

## Formulas & numerical standards

For member `i`, period `t`, over factors `f`:

**1 — The member's pure-private return.**

```
pp_i,t = desmoothed_i,t − Σ_f  w_i,f · R_f,t
```

where `w_i,f` is the member's current-head REGRESSION proxy weight and `R_f,t` the public factor's
captured return compounded over `(period_start, period_end]`.

**2 — Segment pooling (EQUAL_WEIGHT, v1).**

```
PP_segment,t = (1/N) · Σ_i  pp_i,t
```

`N` = the member count, **disclosed on every row** — a thin segment is visible, never hidden.
`MV_WEIGHT` (concentration-faithful) is the recorded v2 convention and is refused against v1.

**3 — Numerical standard.** Computed in `Decimal` at 50-digit context; `quantize_HALF_UP` to **12
decimal places** (the `Numeric(20,12)` return scale).

## Assumptions

Registered as `model_assumption` rows; the version's identity is exactly one well-formed declaration
of each of `pooling_convention=`, `intercept_convention=` and `min_members=`.

1. **EQUAL_WEIGHT pooling** — robust to stale private market values; MSCI pools at segment grain.
2. **RETAIN_ALPHA intercept** — the mean out-of-proxy return (the liquidity premium and private
   market cycle) **stays IN** the factor realization. Per MSCI it is a genuine source of both risk
   *and* return. `MEAN_ZERO` (risk-only) is a recorded v2.
3. **TWO-STEP construction** (desmooth, then subtract). Shepard (2014) shows single-step joint
   Bayesian desmoothing-with-estimation is more robust — that is the recorded **v3**, disclosed
   rather than hidden. No thin-factor or shrinkage correction in v1 (also Bayesian v3).
4. **IDENTICAL-INTERVAL pooling** — members pool only on exactly-matching `(period_start,
   period_end]` intervals; any grid mismatch fails the segment run **closed** as a named gap.
   Cross-calendar interpolation is a recorded v2.
5. **min_members floor** — declared per version; a single-member segment runs at `min_members=1`
   with the count disclosed.

## Validation / reproduction tests

- `test_private_factor.py` — the kernel: pooling arithmetic, the identical-interval refusal, the
  member-count disclosure, and the declared-convention identity checks.
- `test_private_factor_pg.py` — symmetric RLS + append-only enforcement (ENT-060, BR-17/BR-18).
- `test_model_registry.py` — the P8 governed-binder census: this family calls
  `assert_model_version_of` like every other.
- `test_methodology_refs.py` — the RPT-1 census that makes *this document's existence* enforced.
- Demo stage 11 walks the family end-to-end on the PG battery.

## Governed-number contract

Every row binds `dataset_snapshot` + `calculation_run` + a registered `model_version` (all three FKs
NOT NULL at the database), is **IA append-only**, and carries symmetric per-tenant FORCE RLS. The
result is reproducible by construction: re-running against the same pinned snapshot and the same
registered version reproduces the same rows.

## Known limitations

Registered as `model_limitation` rows (verbatim in `risk/bootstrap.py`):

1. This is the pure-private factor **RETURN series only**. Its covariance block `Ω_pp` (PPF-2) and
   the unified number `√(x'Σx + p'Ω_pp p + residual)` (PPF-3) are later arc slices; until then the
   APPRAISAL-frequency segment factor is **fail-closed OUT** of the DAILY covariance/VaR gates — no
   accidental appraisal-vs-daily mixing.
2. The pure-private return regresses **model output** (the desmoothed series + the promoted
   REGRESSION blend), so desmoothing model risk (the declared alpha) and proxy-weight model risk
   **propagate into the factor** — stacked, and honestly disclosed.
3. A segment pools members with a current-head REGRESSION blend only; a member without a blend is a
   **named-gap refusal**, never a silent skip. Members are single-currency (the desmoothed series
   carries one `mark_currency`).
4. `validation_status` is **UNVALIDATED** — recorded and non-enforcing until a 2L validator records
   an outcome (VW-1); a REJECTED latest outcome refuses every new bind at the shared seam.

## External benchmarks

- **[V] MSCI PE Factor Model** — Shepard (2014); methodology restated 2025. The "pure private" leg,
  the segment-grain pooling, and the RETAIN-alpha treatment of the out-of-proxy mean all follow it.
  *Verified against the published methodology.*
- **[C] Geltner (1991, 1993), desmoothing** — cited as the upstream PA-1 input's basis; this slice
  consumes the desmoothed series and does not re-derive it.
- **[U] The two-step vs single-step choice** — the claim that two-step is *materially* less robust
  than joint Bayesian estimation on THIS platform's data is **uncited**: Shepard shows it in his
  setting; we have not reproduced it here, which is precisely why single-step is recorded as a
  future version rather than asserted as better.
