# LIM-2 Decision Record — concentration limits: the dimensional selector (Wave-14 slice 2)

**Status: GROUNDING RESEARCH ONLY (Part 0 written 2026-07-31). Part 1 — the Tier-3 decision ledger —
is NOT yet drafted and nothing here is ratified.** This part exists so the decisions in Part 1 are
taken against what the platform *does*, not against what its records *say* it does. Every fact below
was read out of the tree at `cfcce34` (`origin/main`, CI run 30585105043 green all six) and carries
its `file:line` so a reviewer can refute it without trusting this document.

Slice source: `delivery_roadmap.md` row Wave-14 slice 2. Inherited scope from that row —
dimension selector columns on `limit_definition`, echo columns on `breach`, `_METRIC_MAP` /
`_resolve_latest` re-founded on a registry (the SCH-2 pattern), the ENT-032 `limit_utilization`
slice-gate call, a P4 dry run on the double-table ALTER — plus the three named carries the CON-1
descope handed forward (`con_1_decision_record.md` Part 1, the LIM-2 acceptance constraint).

---

## Part 0 — The facts that shape the slice

### The carried obligations, re-derived from code (not taken on the record's word)

**1. The family dispatch's `else` is an unguarded fallthrough, and registering the metrics is what
arms it.** `_resolve_latest` branches on exactly one value —
`if limit.target_run_type == RUN_TYPE_VAR: … else: <active risk>`
(`limit/service.py:197-210`) — and the `else` carries a comment asserting "the only other admitted
family" rather than a check. What *admits* a family is `_METRIC_MAP`, a module-level dict
(`limit/service.py:121-143`), edited in a different place. So the moment LIM-2 adds a
`(CONCENTRATION, MAX_SHARE_ISSUER)` entry, a concentration limit routes into
`latest_active_risk_for_portfolio`, which accepts `benchmark_id=None` happily
(`risk/active_risk_service.py:754-761`) and returns rows whose `metric_type` never matches the
filter at `limit/service.py:211`. **The failure is SILENT, not loud:** `matching` is empty,
`_resolve_latest` returns `None`, and the limit reports `NEVER_EVALUABLE` — a plausible-looking
state a reader would attribute to a cold metric. CON-1's record already named the fix (`elif` per
family + a fail-closed `else` raise, OQ-CON-1-15); what this adds is that the registration and the
dispatch are **two edits in two places with no mechanical link between them**, which is the same
shape as the `_SYN_MODULES` and `SNAPSHOT_COMPONENT_KINDS` enumerations that failed this wave. A
registry keyed on the family, with a census asserting every `_METRIC_MAP` family has a resolver, is
what makes the second edit impossible to forget.

**2. The result row records its scheme; the SELECTOR does not — so a threshold silently
re-anchors.** *(NEW — not recorded in the CON-1 record, the wave plan, or the roadmap.)*
OQ-CON-1-23 made `scheme_id` NOT NULL on classification SUMMARY rows precisely so "the number
records which taxonomy produced it" (`con_1_decision_record.md:381-386`;
`concentration/models.py:114-121`). That makes each *number* self-describing. It does not make the
*binding* scheme-aware, and three shipped facts combine to make the gap reachable:

- the scheme is a **per-run argument**, not a property of the tenant or the portfolio —
  `run_concentration(…, scheme_by_dimension: dict[str, str])` (`concentration/service.py:89-98`);
- the summary grain is `UNIQUE(calculation_run_id, metric_type)` **with no scheme column**
  (`concentration/models.py:89-96`), so each run yields exactly one `MAX_SHARE_SECTOR_INDUSTRY` row
  whatever taxonomy produced it;
- **no read filters by scheme** — `list_concentration_results` takes `portfolio_id`,
  `dimension_kind`, `metric_type`, `as_of`, `include_issuer_detail` and nothing else
  (`concentration/service.py:379-388`).

So a limit selecting `(CONCENTRATION, MAX_SHARE_SECTOR_INDUSTRY)` resolves the newest COMPLETED run
and reads whichever scheme that run happened to use. A 10% threshold written against a GICS-style
scheme evaluates a vendor scheme's sector partition the day someone runs concentration under it —
same metric name, same portfolio, different economic meaning, no refusal and no signal. This is the
"frozen selector" question OQ-CON-1-14 explicitly deferred to LIM-2; the answer has to live in the
selector or in the resolver, because the result row cannot supply it after the fact.

**3. A limit binds only to a matching `denominator_basis` — and today's refusal layer is
Python-only, on tables with ZERO CHECK constraints.** *(Carry (a), plus a NEW structural fact.)*
`limit_definition` and `breach` declare only `UniqueConstraint`s — no `CheckConstraint` anywhere in
the ORM (`limit/models.py:61-63`, `limit/models.py:99-101`) and none in the migration
(`grep -c CheckConstraint migrations/versions/0050_limit_breach.py` → `0`). Every vocabulary the
limit machinery relies on — `threshold_unit`, `breach_direction`, `limit_kind`, `status` — is
enforced solely by `_validate_config` (`limit/service.py:348-377`). A basis-match refusal written in
that idiom would be Python-only too. That is the exact posture the CON-1 fold reversed one slice ago:
the `issuer_only_on_issuer_rows` CHECK was added with the comment *"Only binder discipline kept that
row class nonexistent; now the engine does"* (`concentration/models.py:137-146`). **LIM-2 would be
adding the first CHECK constraints these two tables have ever carried** — that is a decision to take
deliberately in Part 1, not a detail to inherit.

**4. The refusal-after-success staleness carry is NOT concentration-specific — it is shipped,
platform-wide, and live for VaR limits today.** *(Carry (c), and materially broader than the record
that handed it over.)* The chain: `limit_health` calls `_resolve_latest`
(`limit/service.py:626`) → the family resolver → `list_governed_results`, which filters
`CalculationRun.status == RunStatus.COMPLETED.value` (`calc/reads.py:90`). The **shared** scaffold
commits a FAILED run with zero rows for *every* governed family, not just concentration
(`calc/scaffold.py:136-143`). Therefore: whenever the newest run of a limit's family FAILS while an
older one succeeded, `_resolve_latest` keeps returning the older run and `limit_health` reports
`IN_APPETITE` off it. `calc/reads.py:11` states the assumption in its own words — *"FAILED runs have
zero rows, so COMPLETED-filtering hides nothing readable"* — which is true for a row read and false
for a latest-resolver used as a **control input**: it hides that the newest attempt failed. OD-L's
claim is that `limit_health` exists "so an un-evaluable limit is never silently green"
(`limit/service.py:15-16, 621-623`); against a just-failed run it is silently green. CON-1 framed
this as a consequence of its zero-invested-long refusal. The mechanism is the scaffold's, so the fix
belongs at the resolver, and it retro-fixes VaR and active-risk limits in the same edit.

### The shape of the write surfaces LIM-2 must alter

**5. `breach` carries the P0001 append-only trigger; `limit_definition` does not — the two ALTERs
are not symmetric.** 0050 puts `breach` alone in `APPEND_ONLY_TABLES` and creates
`breach_append_only BEFORE UPDATE OR DELETE … irp_prevent_mutation()`
(`migrations/versions/0050_limit_breach.py:29, 148-153`), while `limit_definition` is EV and edited in
place. So **any backfill `UPDATE` on `breach` raises P0001** and the echo columns are
additive-nullable by construction. The shipped precedent is settled rather than novel: `var_result`
is append-only (`migrations/versions/0026_var.py:42`) and has been widened three times — 0038, 0040,
0048 — every column nullable, none backfilled. Pre-LIM-2 breach rows keeping NULL is *honest*, not a
gap: those breaches were VAR/ACTIVE_RISK, which have no dimension. A conditional CHECK of the form
"dimension columns NOT NULL iff `target_run_type = 'CONCENTRATION'`" validates clean against every
existing row, which is what makes the double-table ALTER tractable — but see fact 3: it would be the
table's first CHECK.

**6. `uq_breach_limit_run` permits exactly ONE breach per `(limit, run)`.**
(`limit/models.py:99-101`; `migrations/versions/0050_limit_breach.py:130-132`.) A per-bucket
wildcard limit — "flag any issuer above 5%" — physically cannot record the three issuers it breached
on. OQ-CON-1-16 reached this conclusion at CON-1's gate; it is confirmed here against the shipped
constraint rather than re-derived.

**7. A per-bucket limit would route fenced issuer identity onto two surfaces the fence does not
cover.** *(NEW.)* `auditor_3l` holds `limit.view` and `breach.view`
(`entitlement/bootstrap.py:470-472`) and **deliberately does not hold `concentration.issuer.view`**
— the exclusion is commented as the point of the two-code split
(`entitlement/bootstrap.py:462-466`). CON-1 fenced issuer identity twice: at the query
(`concentration/service.py:391-395, 418-424`) and, after the review fold, at the engine
(`concentration/models.py:143-146`). A per-bucket ISSUER limit would put an issuer identity into
`limit_definition` (readable at `limit.view`) and echo it onto `breach` (readable at `breach.view`),
reachable by exactly the role the fence excludes. **The run-level MAX form discloses nothing** —
summary rows carry `issuer_id IS NULL` and `bucket_code = '__SUMMARY__'`
(`concentration/models.py:114-121`). So the disclosure argument and fact 6's idempotency argument
point the same way; what Part 1 owes is making that exclusion *mechanical*, and checking that no
`failure_reason` or breach narrative reintroduces the identity in prose.

**8. The metric vocabulary fits the shipped columns — no widening, no new unit.**
`limit_definition.metric_type` and `breach.metric_type` are `String(30)`
(`limit/models.py:69, 114`); the longest concentration summary name is 25
(`MAX_SHARE_SECTOR_INDUSTRY`, `MAX_SHARE_COUNTRY_OF_RISK` — `concentration/models.py:58-68`).
`target_run_type` is `String(100)`; `CONCENTRATION` is 13 (`concentration/events.py:9`). All nine
summary metrics are dimensionless ratios in [0,1] — `max_share` and `cr_n` are sums of fractional
shares and `hhi` a sum of their squares, all over `total_long`
(`concentration/kernel.py:180-183`) — so `THRESHOLD_UNIT_FRACTION` covers the family and the unit
landmine stays disarmed with the shipped vocabulary. `SHARE` (the DETAIL metric) is excluded from
registration by CON-1's ratification. **`benchmark_id` must stay NULL:** `_validate_config` refuses a
`benchmark_id` on a family whose spec does not require one (`limit/service.py:366-369`), which is
already the correct behavior for concentration.

### The operating context the slice will sit in

**9. Nothing creates concentration runs on a cadence.** OQ-CON-1-17 deferred the `FAMILY_REGISTRY`
entry, and the shipped registry holds exactly two families — VAR and EXPOSURE_AGGREGATE
(`scheduling/service.py:450-461`). The limit machinery does not *need* schedulability, and this is
load-bearing rather than incidental: `evaluate_limit` discovers via `calculation_run`, not
`scheduled_run` (`limit/service.py:10-12`; the worker phase at `irp_worker/breaches.py:42-56`), so a
MANUAL concentration run is limit-checked like any other. But the consequence should be stated
plainly rather than assumed away: **a shipped concentration limit only ever evaluates when a human
runs concentration by hand.** Whether that is acceptable for v1, or whether LIM-2 should pay
OQ-CON-1-17's deferred cadence, is a Part 1 question.

**10. The FE renders `metric_type` verbatim in three places and would show an ambiguous number.**
`LimitHealth.tsx:186`, `BreachQueue.tsx:128`, `BreachDetail.tsx:118` each render
`verbatim(…metric_type)`. A concentration limit would display `MAX_SHARE_SECTOR_INDUSTRY` with no
indication of which taxonomy produced it — fact 2's ambiguity surfacing to the user. Rule 7 (every
governed number ships entity/time reads in-slice) applies, so the scheme identity has to reach these
components or they display a number whose meaning is not determinable from the screen.

**11. ENT-032 `limit_utilization` remains the platform's sole reserved-on-paper follow-on**
(`04_data_model/canonical_data_model_standard.md:97, 140`). OQ-CON-1-18's observation holds against
code: utilization is a pure function of the two values `_resolve_latest` already returns
(`limit/service.py:216`) and the frozen threshold, over a run id `LimitHealth` already carries
(`limit/service.py:605-614`). The roadmap makes realizing it a slice-gate call; nothing found in
this pass makes it a *prerequisite* for the dimensional selector.

---

## What Part 1 must decide (agenda only — no recommendations taken yet)

1. **The selector's shape.** Does `limit_definition` carry `scheme_id` (fact 2), and does the
   dimension identity extend to `node_code` for per-bucket limits or stop at the run-level MAX form
   (facts 6, 7)?
2. **Where the basis-match refusal is enforced** — `_validate_config` alone, or the tables' first
   CHECK constraints (fact 3).
3. **Whether the staleness fix is scoped to concentration or taken at the resolver**, where it also
   repairs VaR and active-risk limits (fact 4).
4. **The registry's contract** — what a family declares, and which census makes a registered metric
   without a resolver impossible (fact 1).
5. **The echo set on `breach`**, including the pre-existing missing portfolio-scope echo the wave
   plan folded as a LOW (`wave_14_planning.md:55, 315`), under the additive-nullable constraint
   (fact 5).
6. **ENT-032**: realize or leave reserved (fact 11).
7. **Schedulability**: pay OQ-CON-1-17 here, or ship a manual-only concentration limit and record it
   (fact 9).

## Verification note

Facts 2, 3 (the zero-CHECK half), 4 (the platform-wide scope), and 7 are **new to this pass** — they
are not in `con_1_decision_record.md`, `wave_14_planning.md`, or the roadmap row. Facts 1, 5, 6, 8,
9, 10 and 11 confirm or sharpen positions those records already hold. Nothing here has been
adversarially reviewed; the facts most worth attacking are 4 (a claim about shipped behavior on
families outside this slice) and 7 (a disclosure claim that depends on the holder sets staying as
`ROLE_TEMPLATES` declares them).
