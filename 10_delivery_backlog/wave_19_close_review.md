# Wave-19 close review — closed EARLY at the 2026-09-17 product re-baseline

| Field | Value |
|---|---|
| Status | **CLOSED 2026-09-17 by the owner ("Proceed" on the re-baseline's nine decision points, DP-RB2-6 in particular).** |
| Why early | Two of five slices shipped (S3a, S3b). The third (S1) was built and reviewed and is parked unmerged, because the re-baseline found that the surface it decorates is one no persona journey reaches. The wave's remaining slices are re-homed, not dropped. The full argument is `02_requirements/product_rebaseline_2026-09-17.md`. |
| Verification | The re-baseline record that closes this wave was verified on a different engine (Fable 5.1, four lanes, 71 findings, 6 BLOCKING, all folded; its Part 7). This close review's counts were measured on a fresh battery (section 3). |

## GATE OUTCOME — user decisions, 2026-09-17

All nine decision points of `product_rebaseline_2026-09-17.md` Part 5 ratified as recommended
("Proceed"). The ones that shape this close:

- **DP-RB2-1** partial restart: keep the governed spine, restart the presentation layer
  persona-first, replace the deployed demo book.
- **DP-RB2-2** G5, the journey-walk gate, adopted as a standing gate (`scripts/check_journey_walks.py`).
- **DP-RB2-3** the twelve journey lines J-CRO-1..8 and J-PM-1..4 ratified as written.
- **DP-RB2-5** S1 parked unmerged; Outcome 4 dropped.
- **DP-RB2-6** Wave 19 closes now, with this review.
- **DP-RB2-7** Wave 20 = "A CRO CAN USE IT", seven slices, cut line DRILL-1 only.

## 1. WHAT WAVE 19 DELIVERED

| Slice | Landed | What |
|---|---|---|
| **S3a — INGEST-1 spine** | PR #234 = `7682a1c` (2026-08-21; stamp #235) | ENT-077 `ingestion_mapping_version` (migration `0075`); the anti-corruption upload path; propose and ratify verbs; the P9 mechanical limb (every refusal subclass proven to fire, from `__subclasses__()`). Six defects found by execution, none by reading. |
| **S3b — INGEST-1 governance** | PR #236 = `6dcb4e4` (2026-08-21; stamp #237) | ENT-078 `ingestion_mapping_ratification` (migration `0076`, an append-only four-eyes row); the R-07 mint of `ingest.mapping.propose` / `.ratify` / `.view`; migration `0077` binds `position` to its mapping; REQ-INT-001 DELIVERED; REQ-PPM-002's census clause delivered. Two BLOCKING found by the review (a withdrawal that shadowed a live ratification; a quoted exit code from an unreproducible state). |
| **Demo-tenant admission fix** | PR #238 = `95ac1d7` (2026-08-25; stamp #239) | The campaign never admitted its tenant to the ENT-074 registry, so every HTTP request 401'd; hidden because the admission check no-ops off PostgreSQL. Found by trying to open the demo. |
| **S1 — PRESENT-1 planning gate** | PR #240 = `e992861` (2026-09-05) | Ratified after two different-engine passes and one retraction; plus a time-bomb test fix (a hard-coded as-of instant the wall clock overtook on 2026-09-01). |
| **S1 — PRESENT-1 build** | branch `w19-s1-present`, four commits to `81d3247`, **PARKED UNMERGED** | Presentation contracts with an exact-set census, renderer-version dispatch, a byte-identical server-side SVG chart inside report HTML; 13/13 mutants; full-PG 3,758; review 39 raised / 38 confirmed / 2 BLOCKING, one folded and one (Outcome 4, the run-detail chart surface) left outstanding and now dropped. |

S2 (RPT-W19) and S5 (SHOW-1) did not start. Both have hosts (section 4).

## 2. WHY THE WAVE CLOSES HERE

The owner opened the deployed demo on 2026-09-17 and said it was not something a CRO or PM would
recognise. The re-baseline record measures why: the product has 178 read endpoints over 20
calculation families and no screen that shows a portfolio's risk; the deployed demo is one
three-position book seeded by hand; the persona journeys written in June were never cited by any
gate; and the 2026-08-12 re-baseline, which answered the same complaint, rebuilt the register and
kept it as the yardstick. S1 is the proof: it passed every gate and shipped a chart nobody can see.
Finishing S1, S2 and S5 as ratified would have spent two more slices decorating a surface the
restart retires. Part 4 rule 2 names "the user changes priorities" as a re-sequencing trigger; this
is that, recorded as rule 3 requires.

## Capability coverage (G4)

Both leaves below were requirement-covered before the wave opened. The wave's contribution is
delivered substance against them.

| Leaf | Taxonomy label (verbatim) | What the wave delivered against it |
|---|---|---|
| 18.1 | CSV/Excel upload | S3a + S3b: REQ-INT-001 DELIVERED end to end — validated, sandboxed upload through an anti-corruption layer, a ratified mapping version per source, four-eyes as an append-only row with maker and checker partitioned at role level, and every load bound to the mapping version that shaped it. |
| 1.2 | Position master | S3b: REQ-PPM-002's census clause — the holdings-consuming family set discovered mechanically from the AST, exact-set equality, positive and negative controls; corrected from a 21-family name collision to the true answer of one. The row stays In-Progress on portfolio-scope ABAC, by design. |

## 3. Counts and gates at the close (MEASURED, exit codes captured without pipes)

- `make check` = 0 — **3,097** unit-tier tests passed, 669 skipped (the PG-only tier); that
  includes the **34** new G5 controls and the two new G4 controls (`CHECK_EXIT=0`, captured
  without a pipe).
- Full-PG battery on a fresh four-part reset at this close: **exit 0, 3,730 passed, zero skips**
  (`PYTEST_EXIT=0`, measured on the main tree `f3bfbee` before the gate script landed; the gate
  controls are SQLite-tier and counted above).
- fe-check: unchanged from the S1 branch's measurement, 39 files / 284 tests; this close touches no
  front-end file.
- Mutation battery: **180 anchors, 180/180 match**; the new `rebaseline-2026-09-17` group **9/9
  killed** (one mutant, M-G5-7, SURVIVED its first run because the roster check masked the MODEL
  check; the control was extended to a model ON the roster and to an out-of-scope row, and the
  mutant then died).
- Route census: **315** operations, 178 GET (unchanged; this close ships no route).
- Migrations: **77** files, single head `0077_bind_position_to_mapping` (unchanged; no migration).
- Canonical ids: contiguous through ENT-078; next free **ENT-079**. Next free control id CTRL-040.
- Run types: **22** constants, 20 calculation families; the test campaign registers 27 model codes.
- G2: no slice in flight (declared emptiness; the parked S1's scope withdrawn). G4: this section.
  G5: born this close, ledger empty by design, its empty-ledger control instructs its own deletion
  at the first walk.
- Verify-on-main: to be stamped in `current_state.md` after the ratification PR merges.

## 4. Carries out of Wave 19 (P19 — each names a host or trigger, or is a DECISION)

1. **S1 (PRESENT-1 build)** — parked on `w19-s1-present`. Host: it is resumed when S2 enters a wave
   sequence; resumption is a rebase of a full slice (route census and migration head will have
   moved), accepted explicitly at the re-baseline (Part 4.6, a P7 clause-c acceptance).
2. **S2 (RPT-W19, the report definition entity)** — host: the **Wave-21 candidate list** (a
   sequenced host; the earlier "trigger" was a judgement and P19 says a judgement is a decision).
3. **ING-2 (external market data)** — host: the **Wave-21 candidate list** (was DP-19-9's Wave-20
   candidate; displaced by DP-RB2-7).
4. **S5 (SHOW-1, deployed OIDC posture)** — host: **Wave 20 slice 7**, the wave's exit, not
   cuttable.
5. **LIM-3 (stored utilisation, ENT-032)** — host: **Wave 20 slice 4, UTIL-1**.
6. **The DP-19-1 Wave-20 spine (pricing, risk decomposition, derivative expressibility)** — host:
   **Wave 21's spine** (DP-RB2-6). DP-19-2's commissioned algorithm decision stands unchanged.
7. **The cross-family portfolio summary read** (deferred 2026-07-20 at API-1 planning to "a later
   fast-follow", never swept) — host: **Wave 20 slice 3, CRO-1**.
8. **REQ-PRS-002 re-adjudication** (its acceptance is complete as evidence and silent on whether
   anyone sees it) — trigger: **CRO-1 scopes it** (P20 T1).
9. **The outward-facing benchmark section** (re-baseline Part 4.7) — trigger: **before CRO-1's
   planning gate**, two public sources quoted verbatim with locators, read by a citation lane.
10. **Twelve test files carrying literal future instants** (the class that fired on 2026-09-01) —
    **DECISION for the owner:** a hygiene insertion (a mechanical guard that greps for literal
    future instants in tests, plus the twelve repairs) proposed for ratification at BOOK-1a's
    planning gate under Part 4 rule 3. Its trigger otherwise is the wall clock, which fires on its
    own and reddens CI when it does.
11. **The nondeterministic mutant `R-D5`** (survives on identical bytes 12 of 30 runs) — **DECISION
    for the owner:** no shrinkage slice exists in any sequence; recommend it rides UTIL-1's gate as
    a re-anchor or a withdrawal with reason, since a mutant that flips on identical bytes proves
    nothing either way.
12. **`g2_slice_scope.json`** — flipped to a declared no-scope in this close's commit (the parked
    S1 was its declared slice); BOOK-1a declares its own at its gate.

## 5. Outward-facing benchmark (Part 4 rule 6b)

Not written at this close, and said so rather than faked: the re-baseline's first draft wrote the
section "from general knowledge and not as a citation", the verifier refused it as a sidestep of
rule 6a, and the repair is trigger-bound (carry 9 above). The progress check toward the
public-plus-private destination is the re-baseline itself: the private-asset mathematics exists
(desmoothing, proxying, pacing, unified VaR) and no screen shows it; J-CRO-5 is the line that puts
it on the first screen.

## 6. NEXT

**BOOK-1a**, the public demo tenant (Wave 20 slice 1), after the ratification PR merges. Its
planning gate declares its G2 scope, its G5 scope (expected: none, with the reason written), and
weighs carry 10.
