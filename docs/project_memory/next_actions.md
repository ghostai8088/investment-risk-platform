# Next Actions

> **As of 2026-06-25.** What to do next, the exact prompts, and the gates. **Nothing proceeds without explicit
> user approval.** Re-verify `git status` / HEAD / CI before acting (state may have advanced since this snapshot).

## Exact next step
**DONE:** the **P1B block** + **P1C-0** (AD-017) → **P1C-1 BUILD** (`bb89c74`, #43): `portfolio` EV hierarchy → **P1C-2 BUILD**
(`abb230f`, #46): `transaction` IA append-only → **P1C-3 BUILD** (`4ee124e`, #49): `position` FR → **P1C-4 BUILD** (`c5c5806`,
#54): `valuation` FR captured marks (**REQ-PPM-003 Done**) → **P1C-4 memory** (`6e3dcc1`, #55) → **P1C-5 plan** (`8a14173`, #56)
→ **P1C-5 BUILD** (`0bef45b`, #57): read-only as-of holdings / portfolio views (the first read-model package) → **P1C-5 memory**
(`867e576`, #58) → **P1C-6 plan** (`7dfdb79`, #59; OD-P1C6-1..7 signed off) → **P1C-6 BUILD** (`3e9882d`, CI-green run #60;
8-lens reviewed — a false-GREEN determinism test BLOCKER caught + fixed + re-validated env-unset): the **deterministic
synthetic dataset** — the `irp_shared/synthetic` package (uuid5 IDs + fixed `SeedClock`) seeded through the **governed**
binders via a keyword-only default-None seam (production call sites byte-for-byte unchanged); **never-auto-run + production /
non-synthetic refusal guard**; SYNTHETIC tenant under FORCE RLS, never BYPASSRLS; **no entity, no migration, no real
client/vendor data, no market/risk/exposure/dataset_snapshot**. **No REQ status change.** **The FULL P1C block
(P1C-1…P1C-6) is DELIVERED.**

**COMMIT-PENDING:** this `docs/project_memory/*` refresh (P1C-6 closeout; no code) — commit on explicit approval.

**NEXT — P1C CLOSEOUT / P2 READINESS REVIEW, PLANNING ONLY (on explicit approval):** a P1C closeout + a readiness review for
**P2** (market & private data, risk analytics, scenarios, limits, breach, reporting). **P2 readiness focus:** (1) market data
vs `dataset_snapshot` vs exposure **foundation** — their sequence/dependency; (2) whether `dataset_snapshot` must **precede**
exposure aggregation; (3) how P2 should **consume** the P1C captured positions / valuations / holdings views (the read-model
is the consumption surface — do not re-derive); (4) **preserve the capture-only boundaries (AD-017)** unless explicitly
reopened. **Planning only — do NOT implement P2.** **P2 stays unplanned/unbuilt until the closeout/readiness review AND P2
planning are approved.**

## Exact next prompt to run (when the user is ready for the P1C closeout / P2 readiness review)
> "Begin the P1C closeout / P2 readiness review (planning only): produce a P1C closeout note (the full P1C block P1C-1..P1C-6
> delivered + CI-green; what is realized vs deferred; REQ-PPM status) and a P2 readiness review. Do not write application
> code; do not create migrations; do not implement. The readiness review must settle: (1) the market-data vs
> `dataset_snapshot` vs exposure FOUNDATION and their sequence/dependency; (2) whether `dataset_snapshot` must PRECEDE
> exposure aggregation; (3) how P2 should CONSUME the P1C captured positions/valuations/holdings views (read-model as the
> consumption surface); (4) which capture-only boundaries (AD-017) stay closed unless explicitly reopened. Identify the P2
> sub-slice sequence + open decisions + risks, and run an 8-lens UltraCode adversarial review. STRICT EXCLUSIONS: NO P2
> implementation, NO market data ingestion, NO dataset_snapshot, NO exposure aggregation, NO risk calculations, NO pricing
> model, NO valuation model, NO reporting/dashboard build, NO real SSO. Do not commit until I approve."

## Approval gates (hard)
- **Commit only on explicit approval.** Never commit/push without the user saying so for that specific artifact.
- **Each slice/step is separately gated** — closeout, readiness review, plan, implementation, and commit are distinct approvals.
- **Do not start any P2 build** until the P1C closeout / P2 readiness review AND P2 planning are approved (the closeout /
  readiness review is the next step; review / plan / implement / commit are separate approvals). P2 stays unplanned; P1B-5
  stays conditional/deferred; the capture-only boundaries (AD-017) stay closed unless explicitly reopened.

## CI gates (must be green before a phase is "closed")
- Backend (ruff format + lint, mypy, pytest), Frontend, **DB migration (Postgres)** incl. `alembic check` drift +
  the per-rail/per-entity RLS steps (Reference hybrid-RLS + Legal-entity + Instrument/identifier FR-bitemporal +
  Corporate-action symmetric-RLS + **Portfolio symmetric-RLS** + **Transaction symmetric-RLS + append-only** + **Position
  symmetric-RLS + FR-bitemporal** + **Valuation symmetric-RLS + FR-bitemporal** all shipped) + downgrade smoke, Documentation
  check, Secret scan. **P1C-6 (deterministic synthetic dataset) added NO new migration/RLS step** — it is a never-auto-run
  seed module; the migration job's last domain step is still Valuation; that absence is the structural proof no table was
  persisted (`alembic check` drift-clean, head stays `0015_valuation`). The synthetic builder + governed-seam tests ran in
  Backend; the 4 synthetic FORCE-RLS tests ran in the Postgres job. **HEAD `3e9882d` = run #60 (id 28207899969) = success,
  all 5 jobs** (verified via the REST API this session).
- `gh` CLI is **not installed** — query GitHub Actions via the public-repo REST API (or Docker `postgres:16` locally to
  reproduce PG-only failures, as done throughout P1B/P1C). CI runs warning-free on the Node-24 action majors.

## Stop conditions (halt and ask)
- Any request to start the **P1C closeout / P2 readiness review** is fine **on explicit approval** (planning only); but do
  NOT pull in any **P2 build**, or **market-data ingestion / `dataset_snapshot` / exposure aggregation / risk / pricing /
  valuation models / reporting / dashboards / real SSO**, ABAC enforcement, or any P2+ domain — separate, later, planned slices.
- Any request to start **P1B-5** (conditional/deferred) ahead of a bulk-loading driver.
- Any change to **`audit/service.py`** (frozen) or any new audit code / permission / role / migration without the governed
  update (R-07).
- Any attempt to **wire the synthetic seed to a production / auto-run path**, **weaken its never-auto-run / refusal guard**,
  or seed a **non-SYNTHETIC tenant** — refuse; the seed is explicit-invocation-only, SYNTHETIC-tenant-only, never BYPASSRLS.
- A red CI on a just-committed slice → diagnose and fix (test-only fixes are in-scope for closing that slice).
- Missing or ambiguous approval → ask; do not assume.
- A stray **credential file** found on disk → do NOT inspect/use it; flag it for the user to revoke/rotate.
