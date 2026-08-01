# Vendor / external-dataset onboarding diligence checklist (CTRL-034)

**Minted at CAL-1a (2026-08-01) as an R-10 act with H-05 approval, given at the CAL-1 ratification
gate** (`cal_1_decision_record.md` OQ-CAL-1-9; the deliverable pair ratified at Wave-14 planning —
this checklist artifact + the control-matrix row). The control exists because some dataset defects
are **undetectable in-data by design** (the SR-1 finding: a uniformly one-month-late risk-free
series joins one month late with matching row counts and nothing in the data can distinguish it) —
so acceptance is a procedural act executed BEFORE governed use, recorded here per execution.
This control is **procedural**; nothing in it claims code-side enforcement of what code cannot see.

## The checklist (executed once per dataset, before governed use)

| # | Item | What must be recorded |
|---|---|---|
| 1 | Dataset identity & consumer | What series/set it is, its key, and the exact join/read that consumes it (file:line). |
| 2 | Source & authority | The publisher; whether it is the authoritative origin; publication cadence and horizon. |
| 3 | Licensing & tenancy | Open/public ⇒ SYSTEM rows; licensed ⇒ per-tenant captures (the ratified OQ-W14P-6(iii) conditional; the `fx_rate` precedent). The reasoning, not just the verdict. |
| 4 | Dating/keying convention | The convention the CONSUMER declares, verbatim; every convention defect that is undetectable in-data enumerated, with the acknowledgment that this checklist — not code — is its control. |
| 5 | Completeness & horizon | The covered span; published vs PROJECTED portions labeled; the re-verification trigger for projections. |
| 6 | Encoding rules & known traps | Whether values are transcribed from the published source or derived from a rule — derivation traps named (for calendars: NYSE Rule 7.2 — a naive Saturday⇒Friday observance rule fabricates holidays on real trading days). |
| 7 | Delivery path & idempotence | The governed rail (verb) it enters through; re-run behavior; the audit event(s) emitted. |
| 8 | Acceptance censuses | The exact POSITIVE pins (set-equality/counts/anchors) and NEGATIVE pins (dates/values that must be ABSENT), with the test names that enforce them. |
| 9 | Maintenance obligation | Who re-executes this checklist, on what trigger. |

---

## Execution 1 — the XNYS holiday set (CAL-1a, 2026-08-01)

| # | Answer |
|---|---|
| 1 | The XNYS (NYSE) full-day scheduled-closure set, 2024–2035, keyed `(calendar, holiday_date)`. Consuming reads at `8637b67`: the read-only display endpoint `GET /calendars/{calendar_id}` (`apps/backend/src/irp_backend/api/reference.py:214`), which serves the refreshed set to tenants the moment the seed lands. No business-day / date-math CONSUMER exists yet — those are the CAL-1b predicates (scheduler tick + RM-1/SR-1 v2 acceptance). *(Review fold: the original wording claimed no runtime reader at all — refuted by the display endpoint; corrected, kept as history.)* |
| 2 | NYSE, the exchange itself ("Holidays and Trading Hours") — the authoritative origin; publishes ~3 years ahead. |
| 3 | **Public** — exchange-published holiday dates are published public facts ⇒ **SYSTEM rows** per the ratified conditional (`delivery_roadmap.md:369`); a licensed vendor calendar product would instead land as tenant captures. |
| 4 | Full-day scheduled closures only; early-close half-days are trading days (deliberately absent); unscheduled event closures out of scope. No join-key convention risk at this grain (a date set, not a dated series). |
| 5 | 2024–2028 from the published schedule; **2029–2035 PROJECTED** from the holiday definitions + observance rules incl. Rule 7.2 — labeled in `xnys_holidays.py`; re-verified against the published schedule as the exchange extends it (item 9). |
| 6 | Hand-encoded literals, never runtime-derived. The named trap: **NYSE Rule 7.2's year-end exception** — Saturday New Year's Days are NOT observed on the preceding Friday when it is a month-end, so 2028/2033 carry NINE holidays and **2027-12-31 / 2032-12-31 are trading days**; a naive observance encoding fabricates both AND corrupts the recorded month-end collision census from 4 to 6. |
| 7 | `refresh_calendar_holidays` (ADD-ONLY diff, intra-call duplicates dedupe first-spec-wins; one parent `REFERENCE.UPDATE` per effective refresh; idempotent no-op emits nothing), executed by `seed_system_reference` under SYSTEM context — its first execution. No removal path exists. **The CAL-1b carry, PAID (2026-08-01, migration 0059):** the verb now takes `complete_through` — a FORWARD-ONLY declared-coverage advance (a regression refuses; an advance alone is an effective refresh), negative-controlled in `test_reference.py`. *(Original wording: "this verb MUST be retrofitted at CAL-1b" — kept as history.)* |
| 8 | POSITIVE: per-year counts (10×10 years, 9 in 2028/2033), total 118, the four month-end collisions present (2024-03-29, 2027-05-31, 2029-03-30, 2032-05-31), published-calendar anchors, weekday-only, independent in-test rule re-derivation must agree — `test_the_xnys_dataset_census`, `test_the_xnys_dataset_agrees_with_an_independent_rule_derivation`. NEGATIVE: 2027-12-31 and 2032-12-31 ABSENT — same census test, plus the `XNYS_RULE_72_OPEN_FRIDAYS` module pin. |
| 9 | Re-execute at each dataset extension (new years appended) and when the exchange publishes a year currently PROJECTED; owner R-10. |

---

## Walk-through — the rf (risk-free) series dating convention (the carried SR-1 obligation)

The obligation this control was minted to discharge (`ref_1_decision_record.md` OQ-REF-1-22;
`wave_14_planning.md` fact 8): `capture_benchmark_return` accepts ANY `return_date`; the Sharpe
binder joins by MONTH KEY and catches a partial shift but **never a uniform one** — a uniformly
one-month-late series is undetectable in-data. The declared convention (verbatim, from
`sharpe_kernel.py`): *"the rf `return_date` must fall INSIDE the month its return is for."*

Checklist items 1/4/8 applied to the rf series as it exists today: the only rf data in the
platform is the demo-captured 18-row series (`demo/sr1_stage17.py`), authored in-repo — items
2/3/5/6/7 have no external vendor to interrogate yet. **The first REAL rf/benchmark vendor
dataset (DATA-1) executes this checklist in full**, with item 4 asking the vendor's dating
convention against the declared one and recording the re-dating rule if they differ. This
walk-through discharges the carry as ratified: the control EXISTS, is EXECUTED against the
dataset onboarded in-slice (Execution 1), and names the rf convention as its standing item-4
exemplar — with no claim of code-side enforcement.
