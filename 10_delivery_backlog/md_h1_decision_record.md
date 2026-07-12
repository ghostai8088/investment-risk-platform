# MD-H1 Decision Record — marketdata/registrar hardening + guardrail annex (Wave-2 slice 4.5)

> **Status: RATIFIED 2026-07-12** — OQ-MD-H1-1…8 approved as recommended (user: "Approved").
> Drafted 2026-07-12 against HEAD `9286da1` (PA-0 fully closed, PR #9). A **Part-4 rule-3 hygiene
> insertion** (the TD-1 / P3-C3 "pay the debt while fresh" precedent), user-ratified 2026-07-11
> ("closeout, then MD-H1") after an objective bug-register review ahead of the last Wave-2 slice.
> Scope: pay the **three bug-shaped deferral-register items** before the Wave-2 close, plus a
> **guardrail annex** that converts the recurring bug *classes* of this build from remembered
> discipline into mechanism. **NO governed number, NO migration, NO new permission/audit/role.**
> Implementation gated separately.

## Part 1 — Decisions at a glance (OD-MD-H1-A…H)

| # | Decision | Choice (recommended) |
|---|---|---|
| OD-MD-H1-A | **Scope + character.** | A hardening slice, not a feature: (1) three register items — FR supersede window-coherence, marketdata IntegrityError→409, the registrar first-registration race; (2) a six-item mechanical guardrail annex; (3) three process amendments. **No migration, no governed number, no permission/audit/role mint.** The dedup/perf register rows (P3-7 B covariance adjudicator, P3-7 C lineage batching, P3-8/BT-1 return-shape dedup) stay trigger-based — their tipping points have not arrived, and folding them here would be scope creep, not hygiene. |
| OD-MD-H1-B | **(a) FR supersede window-coherence.** | A backdated `effective_at` below the head's `valid_from` silently inverts the closed version's validity window (`valid_to < valid_from`) — unreconstructable history, the one integrity-flavored open item. FIX: a shared guard `assert_supersede_effective_at(prior_valid_from, effective_at, *, error)` raising a **per-family pre-write ValueError → 422**, applied to all **8** supersede functions (fx_rate, price, curve, factor_return, benchmark_level, benchmark_return, proxy_mapping, membership). All share the identical `prior.valid_to = effective_at` CLOSE-FIRST shape; membership is the one multi-row variant (guard each closed row). Rule = **strictly greater** (`effective_at > prior.valid_from`) — a zero-width closed window is as incoherent as a negative one. |
| OD-MD-H1-C | **(b) marketdata IntegrityError→409.** | A duplicate-open-head capture (unique-constraint collision) currently escapes as an unhandled `IntegrityError` → raw 500 (the transaction rolls back; no data damage). FIX: catch `IntegrityError` at every marketdata capture endpoint and map to **409 Conflict** with a stable, non-leaking detail, via the existing `_*_WRITE_ERRORS` dispatch mechanism (add `IntegrityError` to each family's map rather than a bespoke try/except per route). Uniform across all capture families. |
| OD-MD-H1-D | **(c) registrar first-registration race.** | The `register_*` bootstrap functions do check-then-register (TOCTOU): `SELECT model → None → register_model` (naked INSERT), same for the version. Two concurrent first-registrations → the loser's flush hits the unique constraint → unhandled `IntegrityError` → 500. FIX: a shared `resolve_or_register_model` / `resolve_or_register_version` in `model/service.py` wrapping the INSERT in a SAVEPOINT + `except IntegrityError` re-SELECT — the **exact pattern already proven in `dq/gates.py:59`** (the P2-1/P3-C2 OD-E resolve-or-register) and `benchmark_series.py:229`. Applied to all **8** bootstrap registrars (7 risk + 1 perf). The governed-conflict paths (same label, different code_version → `ModelVersionConflictError`; squatted label → `WrongModelVersionError`) are UNCHANGED — only the true first-registration data race is closed. |
| OD-MD-H1-E | **Guardrail annex (mechanical, items 1–6).** | Convert this build's recurring bug classes into mechanism (each tied to a real incident): (1) **repo-wide migration identifier-length test** sweeping every migration for >63-char identifiers (replaces the 2 per-file asserts; incident: P3-8's 68-char FK, local-PG-only failure); (2) **one shared `_json_safe` audit-payload serializer** replacing the 10 drifted copies — the copies disagree on Decimal canonicalization (`str()` → `"1E+2"` vs `f"{:f}"` → `"100"`), so the same value serializes differently across audit trails, and the PA-0 copy originally lacked Decimal handling entirely (the crash); (3) **audit-action constants + a conformance test** (`"update"`/`"correct"`/`"capture"`/`"supersede"` are raw literals at 33+ sites in marketdata alone; incident: the PA-0 "update"→"correct" fold a query would have silently missed); (4) a **PG-test tenant fixture that re-arms the RLS GUC after commit** (incident: the PA-0 supersede test reading 0 rows because `SET LOCAL` dies at commit); (5) a **shared strict-Decimal input parser** (NaN/Inf refusal + quantize) for every binder (incident: BT-1's HIGH — a hand-minted NaN detonating as a 500); (6) a **no-RUNNING-orphan test assertion helper** asserting the universal "a refused/failed run is FAILED or absent, never RUNNING" (incident: the same BT-1 HIGH's RUNNING orphan). |
| OD-MD-H1-F | **Process amendments (items 7–8 + checklist).** | (7) a **git pre-commit hook** running the fast format/lint subset (full `make check` stays the manual gate — mechanism over the CI-#136 discipline); (8) a **golden-derivation standing rule** — every full-stack golden ships the script/comment that reproduces it from the exact fixture chain (the P3-4 dual-path model; incident: BT-1's wrong REF1 golden); and a **four-line design-completeness checklist** in the operating instructions ("every gate: both sides? every list input: empty behavior? every doc-stated scope: enforced in code? every failure path: no RUNNING orphan?") — the cheap catch for the judgment-gap class the review battery otherwise carries alone. These ride the planning/impl commit as operating-instructions + testing-doc amendments. |
| OD-MD-H1-G | **Blast radius + fences.** | Touches: 7 marketdata modules (guard), `model/service.py` (registrar helper), 8 bootstrap registrars, the marketdata API error maps, ~10 `_json_safe` call sites (consolidation), test infrastructure, and 2 process/doc files. `audit/service.py` stays FROZEN (the shared `_json_safe` lives in a NON-frozen module — `snapshot/serialize.py` or a new `audit_payload.py` helper, NEVER inside the frozen service). No schema, no RLS, no permission, no governed-number contract touched. The consolidation is behavior-preserving except where it FIXES the Decimal-drift (that behavior change is the point, and is covered by a characterization test). |
| OD-MD-H1-H | **Review + flow.** | A **proportionate 4-finder local review** (not the full governed-number ultrareview — no new number — but wider than PA-0's 2-finder because the blast radius spans many files and a shared-serializer consolidation can silently change audit output). Unreduced local gates in full (`make check` incl. `ruff format --check`, full local-PG + downgrade smoke — head stays `0034`, no migration — fe-check if any FE surface is touched; none expected). PR flow; Claude pushes, USER opens+merges. |

## Part 2 — Incident → guardrail traceability (why each item exists)

| Guardrail | Incident it would have caught | Class |
|---|---|---|
| Migration identifier sweep | P3-8 68-char FK (local-PG-only 500) | structural, mechanically catchable |
| Shared `_json_safe` | PA-0 Decimal audit crash + the 10-copy Decimal-canonicalization drift found 2026-07-12 | serialization, mechanically catchable |
| Audit-action constants | PA-0 "update"→"correct" fold (a restatement query would silently miss proxy corrections) | convention, mechanically catchable |
| PG GUC re-arm fixture | PA-0 supersede test reading 0 rows post-commit | test-infra, mechanically catchable |
| Strict-Decimal parser | BT-1 HIGH: NaN var_value → 500 + RUNNING orphan | input-hardening, mechanically catchable |
| No-RUNNING-orphan helper | BT-1 HIGH's RUNNING orphan | invariant, mechanically catchable |
| **(not mechanizable)** design-completeness checklist | horizon-blind Basel gate, one-sided TR-09, empty-list snapshot, doc-stated-unenforced CURRENCY scope | **judgment gap — the multi-finder review is the guardrail; the checklist is a cheap design-time assist** |

## Part 3 — Explicitly out of scope (recorded)

- **The dedup/perf register rows** (P3-7 B shared covariance adjudicator; P3-7 C `_persist_snapshot` lineage batching; P3-8/BT-1 return-shape adjudication dedup) — trigger-based; tipping points not reached. Re-confirmed deferred, not silently dropped.
- **`_reresolve_content` parse-hardening** (P3-8-era, unreachable via the trusted builder) — defense-in-depth; item (5)'s shared strict-Decimal parser may subsume part of it, but it is not a named MD-H1 deliverable.
- **Any schema/migration change** — MD-H1 is deliberately migration-free so it can land fast ahead of the wave close.

## Part 4 — Open decisions (OQ-MD-H1-1…8) — pending ratification

| # | Question | Recommendation |
|---|---|---|
| OQ-MD-H1-1 | Window-coherence rule: strictly-greater vs `>=`? | **Strictly-greater** (`effective_at > prior.valid_from`) — a zero-width closed window carries no information and is incoherent; reject it too. |
| OQ-MD-H1-2 | Window-coherence violation → HTTP status? | **422** (a pre-write refusal, the governed-refusal precedent) — the request is well-formed but semantically invalid; not a 409 (no concurrency), not a 400. |
| OQ-MD-H1-3 | IntegrityError→409 detail granularity? | **Per-family stable message** (e.g. "a current open version already exists for this key") — no DB-internal constraint names leaked; consistent with the existing `_*_WRITE_ERRORS` detail style. |
| OQ-MD-H1-4 | Registrar fix: shared helper vs in-place savepoint per bootstrap? | **Shared helper** in `model/service.py` — the clean-code bar; 8 call sites, one race pattern, one place to get it right (mirrors the dq/gates.py precedent). |
| OQ-MD-H1-5 | Guardrail annex: all 6 now, or a subset? | **All 6** — they are the substance of the slice, each cheap, each tied to a shipped incident; deferring any re-opens the class it closes. |
| OQ-MD-H1-6 | Pre-commit hook (item 7): include or defer? | **Include** — mechanism beats discipline (the CI-#136 lesson); fast subset only, non-blocking-escape documented so it never becomes a productivity tax. |
| OQ-MD-H1-7 | Shared `_json_safe` home? | A **non-frozen shared module** — extend `snapshot/serialize.py` (already the payload-serialization home) rather than mint a new file; NEVER touch the frozen `audit/service.py`. |
| OQ-MD-H1-8 | Review mode? | **Proportionate 4-finder local review** — wider than PA-0's 2-finder (broad blast radius + a consolidation that can change audit output), narrower than a governed-number ultrareview (no new number). |

## Part 5 — Implementation readiness gate

Ratify OQ-MD-H1-1…8, then the implementation plan (`md_h1_implementation_plan.md`) sequences: the shared guard + its 8 applications; the registrar helper + its 8 applications; the API 409 mapping; the six annex items; the two process amendments + checklist; then the full local gate battery and the 4-finder review. Model/effort for implementation: **Opus 4.8 · High** — known scope, established in-repo patterns (dq/gates savepoint, the `_*_WRITE_ERRORS` dispatch), no novel methodology; the risk is breadth (many files) not depth.

## Part 6 — Review dispositions + closure

*(Appended at MD-H1 closeout.)*
