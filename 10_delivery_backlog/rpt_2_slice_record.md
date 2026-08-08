# RPT-2 slice record — the report becomes reachable

**Status:** built, adversarially reviewed, **fresh-context audited**, both folds applied.
**Branch:** `rpt-2-report-access` · **Migration head:** `0064_entitlement_sync`
**Wave:** 16 slice 1 (gate ratified 2026-08-07, OQ-W16P-1…7 all as recommended).

The operating model: the remit defined OUTCOMES + PROOFS; method was free; deviations are recorded
here; the fresh-context audit checks the proofs before merge.

---

## 1. Invariants → named proofs

| # | Invariant | Proof | State |
|---|---|---|---|
| I1 | Every HTML read is a reproduction check; divergence is 5xx | POSITIVE both tiers (unit + the deployed smoke's byte-hash arm); the REFUSAL arm is unit-tier only (`test_a_TAMPERED_stored_hash_makes_the_html_read_a_500_not_a_4xx`) | PROVEN — **corrected at the audit**: the earlier "PROVEN, both tiers" overstated it, the deployed tier proves only the positive direction (carry §5-g) |
| I2 | The wire cannot assert `generated_at` | `test_a_caller_supplied_generated_at_is_REFUSED_not_ignored`, `test_generated_at_is_SERVER_stamped`, + the smoke's live 422 | PROVEN |
| I3 | Entitlement-fenced, P11-complete, hostile inputs refused with nothing persisted | route census + `test_report_grants_as_ratified` + SoD row + hostile-caller tests (the cross-tenant leg now asserts WHICH fence fired) + the smoke's live 401/403 | PROVEN — **corrected at the audit**: three fences raise one error class, so bare-class assertions could not attribute the refusal; the cross-tenant test now matches the message |
| I4 | The FE renders the artifact safely; provenance verbatim | 10 FE tests incl. the sandbox mechanism; mutations F1/F2; the artifact's own CSP asserted server-side | PROVEN **with two recorded limits** — jsdom cannot see sandbox semantics (§5-c), and the remit's literal wording asked for a hostile string through the REAL pipeline, which was built as two layer-local proofs with a stubbed fetch between them (§5-h) |
| I5 | Slice 0 lands both FE gates green at the new majors | `LINT_EXIT=0 FMT_EXIT=0 TYPECHECK_EXIT=0 TEST_EXIT=0`; the six root guards now typechecked | PROVEN, **with the TS7 deviation** — §3 |
| I6 | The deployed stack serves the endpoints — a proof not sharing the unit tier's assumptions (P15) | `prove_report_identity.sh` HTTP arm, in CI's `stack-proof` | PROVEN — and it found §4-A |

## 2. Named proofs and captured exit codes (P14)

| Proof | Evidence |
|---|---|
| `make check-all` | `CHECK_ALL_EXIT=0` — 2490 passed / 593 skipped, FE 216, mypy 287 files |
| Full-PG fresh-schema battery | `PYTEST_EXIT=0`, census **3,083 marks all passing**, cross-checked `2490 + 593 = 3083` (post-review-fold); re-run again after the AUDIT fold — see §7 |
| Deployed smoke | `SMOKE_EXIT=0`, every arm echoed |
| CI | `success` on `250cdd8` AND on the review-fold head `a487a07` (all eight jobs), incl. the extended stack-proof step; the audit-fold head is quoted in §7 |
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
| **(a) The mint-reachability rule** | ~~Appending to `bootstrap.py` is NOT sufficient for a live deployment. Every future mint needs a sync migration (or a re-run of the `0064` pattern).~~ **PAID 2026-08-08 at the Wave-16 close fold.** Ratified as standing rule **P17** and, as ratified, carried a mechanical gate rather than prose: `test_entitlement_mint_delivery.py` asserts every code in the bootstrap constant is named by a literal `DELIVERS` tuple in some migration, so the next mint reddens a test whether or not anyone remembers the rule (mutation-proven, M-C4/M-C5) | ~~The next permission mint~~ — now enforced by CI on every commit |
| **(b) The deployed WORKER's DB path** | The psycopg fix is proven for the BACKEND by the HTTP smoke. The worker's only deployed proof still exits fail-closed *before* connecting, so its database path remains unproven by execution | A slice touching the worker, or a scheduled-tick proof (REPRO-1 is the natural host) |
| **(c) jsdom cannot see sandbox semantics** | jsdom neither executes `srcdoc` nor models `sandbox`, so two of the four FE sandbox assertions cannot fail. The attribute is pinned and the CSP is now server-asserted; a REAL browser check is the only thing that would close it | A browser-based E2E capability, or the first real-browser test harness |
| **(d) Duplicate generate is unbounded** | Each POST mints a new run, so the `(run, portfolio)` unique key can never fire from this route. Intended (a re-generation is a new governed act) but **recorded**, since the key reads as a dedup control | A slice that wants generate idempotency |
| **(f) VaR is unbindable via the snapshot-consume path** | The root exposure run records a NULL scope that propagates to VaR, and `var_result` has no `portfolio_id`, so nothing evidences the attribution. Refusing is correct; the FIX is upstream scope propagation | The next slice touching the exposure/factor/VaR binders — or a report that needs VaR over a consumed snapshot |
| **(g) I1's refusal arm is unit-tier only** | The deployed smoke proves the POSITIVE (served bytes hash to the record); the 5xx-on-divergence arm exists only in SQLite. The smoke has no negative control for identity, unlike its RPT-1 half | The next slice touching the smoke |
| **(h) I4's remit wording vs what was built** | The remit asked for a hostile string through the REAL pipeline to the view; what exists is two layer-local proofs with a stubbed fetch between them. Honest, and not what the remit's letter said | A real-browser harness (same trigger as (c)) |
| **(i) Durable template-grant revocation** | ~~`0064` re-inserts a revoked template grant — it cannot distinguish "never delivered" from "revoked". Accepted with the consequence documented.~~ **PAID 2026-08-08 at the Wave-16 close fold, because the close review refused to ratify carry (a) without it** — mandating the sync while leaving the resurrection in place would have institutionalised it, turning a governance act into a transient one. Built as named: `role_permission_revocation` (migration `0066`, a deliberate mirror of `role_permission`), the sync logic extracted to ONE implementation (`entitlement/sync.py`) that consults the ledger and skips + LOGS, and `0064` amended to route through it. Mutation-proven M-C1/M-C2/M-C3. Two limits stated rather than glossed: downgrading below `0066` drops the ledger, and re-granting is an administrative write, not the deletion of the evidence row | ~~An operator needing durable template-level revocation~~ — PAID |
| **(j) TS→7 is UNPAID** | The Wave-16 gate ratified "TS→7 paid as RPT-2 slice 0"; eslint→10 and jsdom→30 landed, TypeScript did not (`^5.9.3`). The refusal is sound — `typescript-eslint` and `openapi-typescript` had not declared TS 7 support — but it lived only in §7's deviations, so **a ratified gate outcome was unpaid and on no register at all**. Registered at the Wave-16 close (finding 5) here, in the roadmap's standing-deferrals list, and in `current_state.md` | Both `typescript-eslint` and `openapi-typescript` declaring TS 7 support. Monitor, do not force |
| **(e) The 103-test SQLite FK gap** | Unchanged from RPT-1; FK-1 is sequenced in Wave 16 | Wave-16 planning gate (already scheduled) |

## 6. The fresh-context pre-merge audit (4 lenses) — what it found

The audit ran on the review-folded head and made **12 blocking claims; all 12 survived adversarial
cross-check** (2 CONFIRMED, 10 DOWNGRADED to real-but-not-merge-blocking). It also listed **14
overstatements in my own records**. Every one is folded or recorded.

### CONFIRMED — a real disclosure the review missed

**`report.view` served ISSUER-dimension concentration rows.** `concentration.issuer.view` exists
solely to withhold issuer identity from `auditor_3l` — the split three prior mints made and REF-1
shipped a BLOCKING defect by collapsing. `auditor_3l` HOLDS `report.view` (correctly: a rendered
report is a governed output), so the report handed the 3L auditor exactly the read those four mints
refused, **through a new door, with every per-code holder pin still passing**. Closed at the QUERY
with the same predicate `list_concentration_results(include_issuer_detail=False)` uses, so the
report can never render a payload class broader than the `concentration.view` code permits.

**The mint's holder sets were never put to the user, and two records claimed they were.** The
Wave-16 gate asked no permission question and enumerated no holder set. `bootstrap.py`'s catalog
comment and the SoD row both said "user-ratified". Corrected in both places; the holder sets are
carried to the Wave-16 close as an explicit Tier-3 item — every prior mint had its sets enumerated
to the user before shipping and this one has not.

### The regression MY OWN review fold introduced

The attribution fence refuses an unscoped run. A VaR run reaches the report unscoped whenever its
ROOT exposure run was built through the snapshot-CONSUME path, which records an honest NULL
(OD-API-1b-D) that factor-exposure and VaR copy forward — and `var_result` carries no
`portfolio_id` of its own. So the report's LEAD family became unbindable on that path.

**Kept the refusal.** For such a run there is genuinely no evidence anywhere tying the number to a
book, and admitting it re-opens B1 exactly. What changed: the unscoped case now has its OWN message
naming the upstream cause and the remedy (the two failures were conflated), and the consequence is
carry (f) rather than a silent narrowing.

### The same defect class, still open on the DATE axis — now closed

The review's fold closed run↔PORTFOLIO and left run↔DATE open: `as_of_date` was caller-asserted and
rendered as "As of {date}" at the head of a board artifact while the bound run carried its own
economic date. A report headed with one quarter's date carrying another quarter's numbers is the
same misattribution one axis over. Fenced against the pinned snapshot's `as_of_valuation_date`.

### And the fold's own controls, mutation-proven — one survived again

H1 (delete the issuer exclusion) killed NOTHING until a test was written for it — the **same shape
as G5 one fold earlier**: the fix was written, believed, and nothing made it fire. Twice in one
slice. H1/H2/H3 now all killed against a green baseline.

## 7. Post-audit-fold gate evidence

Re-run after this fold and quoted at the close: `make check-all`, the full-PG battery, the deployed
smoke, and CI on the audit-fold head. (§2's numbers are the review-fold head's.)

## 8. Honesty corrections to my own commit messages and records

- Commit `250cdd8` claimed the smoke asserted **cross-generation byte-identity**. It did not — it
  compared each report to itself. The property was true empirically; the assertion did not exist.
  It exists now, and the claim is retracted here rather than left standing.
- The same commit's gate paragraph quoted **counts, not an exit code**, for a `check-all` run that
  was RED (on `gen-api-check`'s by-design refusal of uncommitted regen). P14 requires the captured
  exit code. The committed-tree re-run gave `CHECK_ALL_EXIT=0`, quoted in §2.
