# Definition of Ready & Definition of Done

## Document Control

| Field | Value |
|---|---|
| Document ID | REQ-DORDOD-001 |
| Version | 0.1 (Draft baseline) |
| Status | Accepted as the gating standard for all build work |
| Owner | R-01 Product Manager AI (with R-09 QA/Test Engineer AI) |
| Approver | H-07 Product Owner (H-06 Engineering Lead co-owns DoD) |
| Created | 2026-06-18 |
| Last Reviewed | 2026-06-18 |
| Related Documents | requirements_backbone.md, requirements_traceability_matrix.md, ../00_ai_operating_model/build_rules.md, ../09_compliance_controls/control_matrix_skeleton.md, ../08_testing_qa/ci_enforcement_overview.md |
| Supported Build Rules | BR-1 … BR-19 |

## 1. Purpose

Make the build rules operational as **entry and exit gates** for every requirement/story. A story may not enter build until it
is **Ready**; it may not be accepted until it is **Done**. These gates turn BR-1…BR-19 from prose into checkable conditions and
are enforced jointly by review and CI.

## 2. Definition of Ready (DoR)

A requirement/story is **Ready** to enter a build phase only when ALL of the following hold:

| # | Ready criterion | Traces to |
|---|---|---|
| R1 | Has a stable `REQ-…` ID and is linked to a `CAP-x.y` capability | backbone §2/§4 |
| R2 | Persona(s) and Line(s) of Defense identified | RTM, personas |
| R3 | Business purpose + functional requirement written and unambiguous | backbone §7 |
| R4 | Data requirement specified (entities + temporal class FR/IA/EV) | BR-19, BX-TMP |
| R5 | Calculation requirement specified with numerical conventions, or marked N/A | BR-2, QS standards |
| R6 | Inherited cross-cutting requirements (BX-*) enumerated: audit, entitlement, lineage, repro, SoD as applicable | backbone §5 |
| R7 | Model-governance applicability decided (inventory + tier + validation, or N/A) | BR-3, BR-15 |
| R8 | **Acceptance criteria** written as testable statements (Given/When/Then) | BR-1 |
| R9 | Control ID(s) assigned (existing `CTRL-…` or a control placeholder) | control matrix |
| R10 | Dependencies resolved or explicitly available for this phase (no unmet `DEP-*`) | backbone §6, RTM §4 |
| R11 | Build phase assigned and consistent with the build sequence | build_sequence.md |
| R12 | Known limitations noted | BR-14 |

A requirement with any unmet `DEP-*` for its phase is **Blocked**, not Ready.

## 3. Definition of Done (DoD)

A requirement/story is **Done** only when ALL of the following are satisfied and evidenced:

| # | Done criterion | Build Rule | CI/automation gate |
|---|---|---|---|
| D1 | Code implemented to the functional requirement; no domain logic in the UI layer | ARCH-P-04 | `backend`/`frontend` jobs |
| D2 | Unit + integration tests written and passing; meaningful coverage of acceptance criteria | BR-1 | `pytest` / `vitest` |
| D3 | Calculation methodology documented; numerical conventions applied | BR-2, QS | `docs-check`, review |
| D4 | Every model/calculation has a model-inventory entry; tier assigned | BR-3 | model-inventory check (future) |
| D5 | Every persisted field defined in the data dictionary; temporal class declared | BR-4, BR-19 | temporal-class test (CTRL-017) |
| D6 | State changes emit audit events; chain verifies | BR-5, BR-12, BR-18 | audit tests (CTRL-005/026) |
| D7 | Results bind full lineage (source→run→result) | BR-6, BR-13 | lineage-completeness test (CTRL-006/013) |
| D8 | Manual overrides carry BR-7 fields + approval | BR-7 | override test (CTRL-007) |
| D9 | Scenarios/assumptions versioned where applicable | BR-8 | versioning test (CTRL-008) |
| D10 | Reports/results reproducible from bound run | BR-9, BR-6 | reproduction test (CTRL-018) |
| D11 | No secrets in source | BR-10 | `secret-scan` (CTRL-010) |
| D12 | Access is entitlement-checked, deny-by-default, tenant-scoped | BR-11, BR-17 | entitlement tests (CTRL-011) |
| D13 | No bypass of audit / entitlement / lineage / temporal frameworks | BR-12/13/19 | framework tests |
| D14 | Known limitations documented | BR-14 | review |
| D15 | Human approval obtained for restricted change types (Tier-1 model, security, compliance, entitlement, audit, prod deploy) | BR-15 | approval record (CTRL-015) |
| D16 | Material AI agent actions logged | BR-16 | agent-log test (CTRL-016) |
| D17 | SoD/maker-checker enforced where required | BR-7, BR-15 | SoD tests (CTRL-021/025/031) |
| D18 | Acceptance criteria demonstrably met; PO/2L sign-off where required | — | review + release readiness |
| D19 | RTM updated: requirement Status moved (Draft→In-Progress→Done); control matrix status updated | — | docs-check / review |

A criterion that is **Not Applicable** to a given requirement must be explicitly marked N/A with a one-line justification — it
may not be silently skipped.

## 4. Phase-level exit (in addition to per-story DoD)

A build phase is complete only when every in-scope requirement is `Done`, the phase's controls are `Implemented` in the control
matrix, the enterprise review prompt has been run against the phase output, and no `Critical`/`High` review findings remain open.
See [build_sequence.md](../10_delivery_backlog/build_sequence.md).

## 5. Open Questions

| ID | Question |
|---|---|
| OQ-008 | Confirm coverage threshold for D2 (e.g., line/branch %) and whether it is CI-enforced per phase. |
| OQ-009 | Confirm which DoD items require human sign-off vs. automated-only for non-restricted changes. |

## 6. Dependencies

DoD items D4 (model inventory), D7 (lineage), D17 (SoD) depend on the future frameworks `DEP-MREG`, `DEP-LIN`, and SoD via
`REQ-ADM-002`; until those exist, requirements needing them are Blocked for those criteria and must not be marked Done.
