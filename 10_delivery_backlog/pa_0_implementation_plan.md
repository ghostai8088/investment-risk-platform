# PA-0 Implementation Plan — private-asset foundations (the capture-first build contract)

> Executes ONLY on explicit direction after `pa_0_decision_record.md` OQ ratification. Branch
> `pa-0-impl` off `main`; lands via the PR flow (Claude pushes, the USER opens+merges after CI
> green). Captured-input scope ONLY (OD-A) — NO binder, NO snapshot builder, NO `calculation_run`,
> NO permission mint (the P2-7 exemplar, not the P3-7/BT-1 governed-number shape). Every step ends
> with `ruff format` + `ruff check` on the touched files; fixtures TD-1-realistic; dedup-by-default
> (the clean-code standing bar).

## Step 0 — Branch + pre-checks
`git checkout -b pa-0-impl` off the current `main`; confirm migration head `0033_var_backtest`, CI
green, working tree clean.

## Step 1 — ORM: `marketdata/models.py::ProxyMapping`
`FullReproducibleMixin` (the `FactorReturn`/`BenchmarkReturn` bitemporal precedent) + `TenantMixin`
+ `TimestampMixin`. Columns: `private_instrument_id` (hard FK → `instrument.id`, NOT NULL,
indexed), `factor_id` (hard FK → `factor.id`, NOT NULL, indexed), `weight` (signed
`PreciseDecimal(20,12)` — a factor loading, not currency), `mapping_method` (String(30),
controlled-vocab-by-value: `MANUAL` v1; `PEER_GROUP`/`REGRESSION` reserved). Current-head partial
unique index `(tenant_id, private_instrument_id, factor_id)` `WHERE valid_to IS NULL AND
system_to IS NULL` (the `FactorReturn`/`Valuation` bitemporal-uniqueness precedent — multiple
factor rows per instrument are fine; only ONE open version per `(instrument, factor)` pair).

## Step 2 — Migration `0034_proxy_mapping`
Table + the current-head partial unique index + the two FK indexes. Symmetric tenant-scoped RLS
(`FORCE ROW LEVEL SECURITY`, NEVER hybrid) — this is a PROPRIETARY table like every FR capture
table to date. **NOT append-only** (FR close-out UPDATEs the `valid_to`/`system_to` pair on
supersede/correct — the `factor_return`/`benchmark_return` precedent; no `irp_prevent_mutation`
trigger). Assert every DDL identifier ≤ 63 chars in-plan (the P3-8/BT-1 lesson). Single head; SQLite
build + local-PG upgrade/downgrade smoke 0034↔0033 before proceeding.

## Step 3 — Capture service: `marketdata/proxy_mapping.py`
Mirror `factor.py::capture_factor_return`/`supersede_factor_return` exactly:
- `capture_proxy_mapping(session, *, private_instrument_id, factor_id, weight, mapping_method,
  acting_tenant, actor, valid_from=None, ...)` — the FIRST open version for `(instrument, factor)`;
  re-resolves BOTH FK targets under the acting tenant pre-write (instrument via
  `reference.instrument.resolve_instrument`-equivalent tenant-filtered read; factor via
  `resolve_factor`) — a foreign/absent id refuses, never a durable cross-tenant row.
- `supersede_proxy_mapping(session, *, ..., new_weight, new_mapping_method, effective_at, ...)` —
  closes out the current version, inserts the successor (a proxy revision — a judgment call
  revisited, NOT an append-only fact).
- `reconstruct_proxy_mapping_as_of(session, *, private_instrument_id, factor_id, valid_at,
  known_at, acting_tenant)` — both-axes bitemporal read (the standard reconstruct signature every
  FR entity carries — future PA-1 snapshot-pinning will need it).
- `list_proxy_mappings(session, *, private_instrument_id, acting_tenant)` — the current-head set
  for one instrument (its full proxy blend).
- Finiteness guard on `weight` (no NaN/Infinity — the platform-wide Decimal-input precedent);
  NO sum-to-1 enforcement (OD-D — recorded, not gated).
- Audit: `MARKET.PROXY_MAPPING_CAPTURE`/`_SUPERSEDE` (additive EVT-200-decade codes — the
  `benchmark_return`/`factor_return` precedent; per-op grain, no read audit). REUSE
  `marketdata.view`/`marketdata.ingest` — NO new permission (OD-E).
- Lineage: an ORIGIN edge to a `data_source` (e.g. `MANUAL_PROXY` — a new source ROW, not a new
  lineage KIND) for `mapping_method='MANUAL'` (the `VENDOR_FACTOR`/`VENDOR_BENCHMARK` precedent
  reused for a non-vendor manual judgment call).

## Step 4 — Package wiring
`marketdata/__init__.py` exports the new symbols. No `snapshot`/`calc`/`model` import (a captured
FR entity, like `benchmark_return` before P3-8 consumed it — one-way, no governed-number coupling
yet).

## Step 5 — API (optional this slice — confirm at ratification)
If an API surface ships now: `POST /marketdata/proxy-mappings` (capture), `POST .../{id}/supersede`,
`GET /instruments/{id}/proxy-mappings` — gated `marketdata.ingest`/`marketdata.view`. If deferred to
PA-1 (since nothing consumes it yet), record that explicitly at the plan-ratification gate — either
is defensible for a captured-input-only slice (the `benchmark_level`/`benchmark_return` P2-7
precedent DID ship an API in the same slice; match that unless the user prefers to defer).

## Step 6 — Docs
Canonical registry: ENT-019 row REALIZED (mirroring the ENT-052/ENT-027 "REALIZED" wording — the id
was already reserved, not newly minted); the private `asset_class` convention documented (a
non-enforced value list, NOT a CHECK constraint — consistent with every other `asset_class` use);
audit taxonomy: `MARKET.PROXY_MAPPING_CAPTURE`/`_SUPERSEDE` additive rows; entitlement SoD:
`marketdata.*` REUSE note (mirroring the factor/benchmark reuse notes) + the parity test citation;
backbone + RTM: a REQ row under the private-asset capability (mirroring REQ-SMR/REQ-MKT numbering —
confirm the next free id at implementation time); roadmap left for closeout (PA-0 marked DONE, PA-1
queued as the desmoothing/proxy governed-number follow-on).

## Step 7 — Tests + ci.yml (SAME commit)
`test_proxy_mapping.py` (SQLite): capture/supersede/reconstruct round-trip (the FR bitemporal
protocol — current-head uniqueness, prior-version immutability, both-axes reconstruction);
multi-factor blend per instrument; the cross-tenant-FK refusal battery (foreign/absent instrument,
foreign/absent factor); the finiteness guard; audit (`MARKET.PROXY_MAPPING_*`, per-op grain, no
read audit); lineage ORIGIN edge; entitlement parity (`marketdata.*` reused, no new codes);
migration head. `test_proxy_mapping_pg.py`: symmetric FORCE RLS (visibility / no-context zero rows
/ forged-tenant 42501) + the closed 5-table hybrid set unchanged + audit chain — + the ci.yml PG
step in the SAME commit. TD-1 realism (plausible factor loadings, e.g. weights in [-2, 2], not
degenerate extremes outside a labeled boundary test).

## Then
Unreduced validation (make check + full local-PG + downgrade smoke + diff fence; fe-check only if
Step 5 ships FE) → a PROPORTIONATE local review (OQ-8 — lighter than the full 4-finder
governed-number battery, given the captured-input-only blast radius) → fold → revalidate → push
`pa-0-impl` → USER opens+merges the PR → closeout PR (docs + memory + PA-1 queued as next).
