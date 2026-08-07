# RPT-2 slice record — the report becomes reachable

**Status:** built, reviewed adversarially, folded; awaiting the pre-merge fresh-context audit.
**Branch:** `rpt-2-report-access` · **Migration head:** `0064_entitlement_sync`
**Wave:** 16 slice 1 (gate ratified 2026-08-07, OQ-W16P-1…7 all as recommended).

The operating model: the remit defined OUTCOMES + PROOFS; method was free; deviations are recorded
here; the fresh-context audit checks the proofs before merge.

---

## 1. Invariants → named proofs

| # | Invariant | Proof | State |
|---|---|---|---|
| I1 | Every HTML read is a reproduction check; divergence is 5xx | `test_generate_then_fetch_html_and_the_BYTES_HASH_TO_THE_STORED_HASH`, `test_a_TAMPERED_stored_hash_makes_the_html_read_a_500_not_a_4xx`, and the deployed smoke's byte-hash arm | PROVEN, both tiers |
| I2 | The wire cannot assert `generated_at` | `test_a_caller_supplied_generated_at_is_REFUSED_not_ignored`, `test_generated_at_is_SERVER_stamped`, + the smoke's live 422 | PROVEN |
| I3 | Entitlement-fenced, P11-complete, hostile inputs refused with nothing persisted | route census + `test_report_grants_as_ratified` + SoD row + 8 hostile-caller tests + the smoke's live 401/403 | PROVEN |
| I4 | The FE renders the artifact safely; provenance verbatim | 8 FE tests incl. the sandbox mechanism; mutations F1/F2 | PROVEN **with a recorded limit** — see §5 carry (c) |
| I5 | Slice 0 lands both FE gates green at the new majors | `LINT_EXIT=0 FMT_EXIT=0 TYPECHECK_EXIT=0 TEST_EXIT=0`; the six root guards now typechecked | PROVEN, **with the TS7 deviation** — §3 |
| I6 | The deployed stack serves the endpoints — a proof not sharing the unit tier's assumptions (P15) | `prove_report_identity.sh` HTTP arm, in CI's `stack-proof` | PROVEN — and it found §4-A |

## 2. Named proofs and captured exit codes (P14)

| Proof | Evidence |
|---|---|
| `make check-all` | `CHECK_ALL_EXIT=0` — 2490 passed / 593 skipped, FE 216, mypy 287 files |
| Full-PG fresh-schema battery | `PYTEST_EXIT=0`, census **3,077 marks all passing**, cross-checked `2484 + 593 = 3077` (pre-fold run; re-run post-fold at close) |
| Deployed smoke | `SMOKE_EXIT=0`, every arm echoed |
| CI | `success` on `250cdd8`, incl. the extended stack-proof step |
| Migration `0064` | on a simulated live DB: `0 → 2` report codes, `8` grants, `UPGRADE_EXIT=0`; re-run idempotent |

## 3. Deviations from the ratified gate, recorded

**OQ-W16P-4 ratified "TS→7". It is NOT paid, and the refusal is executed evidence, not a citation.**
`typescript-eslint` (installed AND registry-latest) peers `typescript >=4.8.4 <6.1.0`;
`openapi-typescript` peers `^5.x`. Both are gate-critical. P12 says execute the plainest alternative
before recording an impossibility, so TS 7.0.2 **was installed**: `tsc --noEmit` exited 0, and npm
resolved 7 nested under the workspaces while the root kept 5.9.3 for the peer-bound tools — **a
split-brain toolchain**, the compiler on 7 and the governance fences' parser on 5.9, every gate
green and nothing anywhere to say so. Reverted; no override, no forced resolution.
**Trigger to pay:** `typescript-eslint` AND `openapi-typescript` both declare TS-7 support.

eslint 10 + jsdom 30 + the six root guards ARE paid.

## 4. Defects found, and by what

### A. Found by the deployed smoke (the first HTTP request ever made to a governed read)

**The backend and worker images never installed the PostgreSQL driver.** `ModuleNotFoundError: No
module named 'psycopg'` — since DEP-1 built them. Invisible by construction: DEP-1's deploy verify
probes `/health` and `/version` (neither touches the DB; the engine builds lazily), asserts DB state
via `psql` not HTTP, and the worker's fail-closed proof exits *before* connecting. So the deployed
backend had never served one governed read and the deployed worker had never ticked against its
database — with every gate green. Both images fixed.

### B. Found by the adversarial review (5 lenses, 27 findings, refute-by-default verification)

| # | Defect | Severity | Why nothing else saw it |
|---|---|---|---|
| B1 | **A report could attribute one book's numbers to another** — the portfolio was tenant-fenced, each run was tenant-and-type fenced, and NOTHING related them | HIGH | Same tenant throughout: no cross-tenant control could fire. Both halves individually correct |
| B2 | **The permission mint could never reach an existing database** — `0002` is applied, so `upgrade head` is a no-op and deny-by-default 403s every holder | BLOCKING class | Every test, the smoke and CI build their database from empty |
| B3 | Malformed UUIDs **500 on PostgreSQL**; SQLite proves a 404 production never exhibits | BLOCKING | The unit tier stores GUID as CHAR(36) and simply matches nothing |
| B4 | The artifact is served **same-origin with no CSP** — the iframe sandbox protects the app, not a direct navigation with the bearer token in reach | HIGH | The FE test asserts the attribute; nothing tested the bytes' own boundary |
| B5 | The `/reports` SPA route is **shadowed** by the `/reports` API prefix — unreachable by URL, refresh or bookmark | MEDIUM | Every prior route was namespaced (`ops/limits`); this was the first collision |
| B6 | The **Reload button was a no-op** — the screen's fresh-reproduction promise was decorative | MEDIUM | No test asserted a second fetch |
| B7 | **Any** 500 was announced as an integrity failure | MEDIUM | The test stubbed only the identity case |
| B8 | The **list route's tenant fence was mutation-blind** — deleting it left all 18 tests green | HIGH | Every test seeded one tenant only |
| B9 | `apiGetHtml`'s content-type refusal had **never fired** | MEDIUM | No test supplied a non-HTML 200 |

**B2 is the one that matters beyond this slice.** It is platform-wide since P0.5 — `liquidity.*`,
`concentration.*`, `schedule.*`, `limit.*`, `breach.*` have all been undeliverable to a live
database the same way. Migration `0064` is the class fix (P10), syncing the WHOLE catalog.

### C. Found by mutation-proving the FOLD itself

**G5 survived**: the CSP headers added for B4 had no test. A security header nobody asserts is a
comment. Test added; G1–G5 now all killed by their intended tests.

## 5. Carries, with triggers

| Carry | Detail | Trigger |
|---|---|---|
| **(a) The mint-reachability rule** | Appending to `bootstrap.py` is NOT sufficient for a live deployment. Every future mint needs a sync migration (or a re-run of the `0064` pattern). **Proposed as a standing rule at the Wave-16 close** — not self-ratified | The next permission mint |
| **(b) The deployed WORKER's DB path** | The psycopg fix is proven for the BACKEND by the HTTP smoke. The worker's only deployed proof still exits fail-closed *before* connecting, so its database path remains unproven by execution | A slice touching the worker, or a scheduled-tick proof (REPRO-1 is the natural host) |
| **(c) jsdom cannot see sandbox semantics** | jsdom neither executes `srcdoc` nor models `sandbox`, so two of the four FE sandbox assertions cannot fail. The attribute is pinned and the CSP is now server-asserted; a REAL browser check is the only thing that would close it | A browser-based E2E capability, or the first real-browser test harness |
| **(d) Duplicate generate is unbounded** | Each POST mints a new run, so the `(run, portfolio)` unique key can never fire from this route. Intended (a re-generation is a new governed act) but **recorded**, since the key reads as a dedup control | A slice that wants generate idempotency |
| **(e) The 103-test SQLite FK gap** | Unchanged from RPT-1; FK-1 is sequenced in Wave 16 | Wave-16 planning gate (already scheduled) |

## 6. Honesty corrections to my own commit messages

- Commit `250cdd8` claimed the smoke asserted **cross-generation byte-identity**. It did not — it
  compared each report to itself. The property was true empirically; the assertion did not exist.
  It exists now, and the claim is retracted here rather than left standing.
- The same commit's gate paragraph quoted **counts, not an exit code**, for a `check-all` run that
  was RED (on `gen-api-check`'s by-design refusal of uncommitted regen). P14 requires the captured
  exit code. The committed-tree re-run gave `CHECK_ALL_EXIT=0`, quoted in §2.
