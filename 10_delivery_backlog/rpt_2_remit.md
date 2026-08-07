# RPT-2 remit — the report becomes reachable

**Slice of:** Wave 16 (ratified 2026-08-07, OQ-W16P-1…7 all as recommended).
**Operating model:** this remit defines OUTCOMES and PROOFS. The build has freedom of method;
deviations are recorded in the slice record; a fresh-context audit checks the proofs BEFORE merge.

## Inherited gate commitments (the P7 fix — first instance; nothing here may fire silently)

| Source | Commitment | Discharged by |
|---|---|---|
| OQ-W16P-2 | `generated_at` is SERVER-stamped for HTTP callers; the wire cannot assert evidence time | Invariant I2 |
| OQ-W16P-3 | The FE report view is IN scope | Invariant I4 |
| OQ-W16P-4 | FE toolchain majors (TS→7, eslint→10, jsdom→30, the six untypechecked root guards) are PAID as slice 0, executed-dry-run style | Invariant I5 |
| RPT-1 close §7-D | This slice IS that ratified carry (report generate/read endpoints + the N3 decision) | The slice itself |
| P11 | Any permission mint carries holder-set pin + route census + SoD row | Invariant I3 |
| PERF-0 carries (§7-B) | **NOT inherited** — no parallelization or grain-level perf work in scope. Stated so the non-inheritance is a visible reading, not an oversight | — |

## Goal

A human outside the team, in a browser, can generate a governed report and read it — with every
read being a fresh proof of the platform's reproducibility claim, not a cached artifact. This
completes Wave-15's purpose sentence at the access level.

## Scope boundary

- **IN:** slice 0 = the FE toolchain majors (no feature code on the upgrade commit); HTTP verbs to
  generate a report, list reports, fetch one report's metadata, and fetch its RENDERED HTML; a
  minted permission pair under R-07/P11; the FE report view (list + render + provenance); the
  deployed-stack smoke extension for the new surface.
- **OUT (explicitly):** scheduled generation (REPRO-1's neighbor decision, its own approval
  semantics); PDF; distribution/e-mail; dashboards beyond the view; any new governed number,
  entity, or snapshot component kind; REPRO-1 and FK-1 (the next slices).

## Invariants (each becomes at least one named proof)

| # | Invariant | The proof that makes it real |
|---|---|---|
| I1 | **Every HTTP read of a report's HTML is itself a reproduction check.** ENT-072 stores the hash, not the body — so the HTML endpoint re-renders from the pinned snapshot and REFUSES on identity divergence. The refusal is a **5xx** (the platform failing its own BR-9 claim), never a 4xx: a client did nothing wrong | A test plants a tampered stored hash and the endpoint refuses with the correct class; the happy path returns bytes whose SHA-256 equals the stored hash, asserted in the test |
| I2 | An HTTP caller **cannot assert `generated_at`** — the server stamps it; the in-process parameter is unreachable from the wire | A request supplying any generated-at-shaped input either fails validation or demonstrably does not influence the stored row |
| I3 | Report endpoints are **entitlement-fenced with a minted permission pair** (view/generate split), P11-complete; cross-tenant reads AND generates are refused **with REAL foreign-owned objects** (the LIM-2 lesson), leaving nothing persisted on the generate path | Holder-set pin + route census + SoD row exist and are test-enforced; hostile-caller tests fire every refusal |
| I4 | The FE view renders the report HTML **safely** (no script-execution path from tenant-influenced strings) and shows provenance verbatim | A hostile metric/portfolio string round-trips through the real pipeline to the view without executing; an FE test asserts the sandboxing mechanism, not just the happy render |
| I5 | Slice 0 lands **both FE gates green at the new majors**, with the six root guard tests typechecked — or each remaining exclusion re-justified in writing at the slice record | `fe-check` + `gen-api-check` exit codes at the new majors, quoted; the exclusion list's delta stated |
| I6 | The deployed stack serves the report endpoints — **a proof not sharing the unit tier's assumptions** (P15) | The `stack-proof` CI job (or deploy.sh verify step) exercises generate + fetch-HTML against the running stack and checks the returned bytes' hash |

## Named proofs (P14 applies to every one)

1. `make check-all` — exit code quoted, both tiers, per commit that claims green.
2. Full-PG fresh-schema battery — `PYTEST_EXIT` quoted (exclusive DB per OQ-W15P-9).
3. The I1/I2/I3 hostile-caller tests, mutation-proven where a guard is new.
4. CI to green on the head SHA — run conclusion quoted.
5. **Fresh-context audit BEFORE merge**, checking these proofs; merge only after; P1 sweep after
   the merge, verified on `main`.

## Decision points already closed (no in-build gates expected)

The gate closed N3 (server-stamp), the view (in), and the toolchain (pay). The one foreseeable
in-build fork — what the LIST endpoint filters by — is a routine judgment call (tenant-scoped,
portfolio/as-of filters, newest-first) unless it grows a governance dimension, in which case it
surfaces per the standing rules.
