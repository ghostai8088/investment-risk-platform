# LIM-2 Decision Record — concentration limits: the dimensional selector (Wave-14 slice 2)

**Status: RATIFIED 2026-07-31 (OQ-LIM-2-1…8, all as recommended). No code has been written.**
Part 0 exists so the decisions in Part 1 were taken against what the platform *does*, not against
what its records *say* it does: every fact was read out of the tree at `cfcce34` (`origin/main`, CI
run 30585105043 green all six) and carries its `file:line` so a reviewer can refute it without
trusting this document.

**What the user ratified at the gate, in their own decision terms:** *full* v1 expressiveness —
named-bucket AND named-issuer limits alongside the nine run-level metrics (OQ-LIM-2-2=B and
OQ-LIM-2-3=B together, **accepting the reversal of CON-1's `SHARE` exclusion and the extension of
the issuer fence to the limit/breach read surfaces**); and the staleness defect fixed
**platform-wide** at the resolver, repairing VaR and active-risk limits in the same edit
(OQ-LIM-2-5=A). The remaining five were taken as recommended. The OQ-LIM-2-8 rationale correction —
that CON-1 recorded the wrong reason for deferring schedulability — rides with them.

**The P4 EXECUTED dry run has NOT been run and gates implementation.** On a migration slice the
verifier pass runs the migration in a throwaway workspace copy rather than reading it
(`claude_operating_instructions.md:283-290`). The gate above ratified *design* choices; the
migration mechanics in Part 3 are not ratified and the dry run is what tests them.

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

**12. A scheme REVISION is a new row with a new `scheme_id`, so "pin the scheme" is not one decision
but two.** *(NEW.)* `ClassificationScheme` is keyed `(tenant_id, scheme_family, version_label)` and
"a revision is a NEW row (OQ-REF-1-10) … Assignments FK the scheme VERSION, never the family"
(`classification/models.py:116-142`). `run_concentration` therefore receives a version-exact
`scheme_id` per dimension. This splits fact 2's question in two, and neither half is free: a limit
pinned to `scheme_id` **stops resolving the day the tenant adopts the next revision** — fail-closed,
but a live control quietly ceasing to bind at a taxonomy upgrade is itself a governance event nobody
signed off; a limit pinned to `scheme_family` **survives the upgrade and silently re-anchors** if the
revision split or merged the bucket it thresholds. The same fork applies to a named bucket, whose
`node_code` can simply cease to exist across a revision.

**13. A `schedule` row has nowhere to put `scheme_by_dimension`.** *(NEW — it makes fact 9's
deferral a structural cost rather than an unfired trigger.)* `Schedule`'s columns are `code`, `name`,
`target_run_type`, `scope_portfolio_id`, `model_version_id`, `environment_id`, `cadence_kind`,
`interval_days`, `anchor_date`, `status`, `record_version` (`scheduling/models.py:55-107`) — every
one a typed scalar. The concentration binder requires a per-dimension **map**
(`concentration/service.py:89-98`). So paying OQ-CON-1-17 is not the CHECK amendment its deferral
described; it is that amendment **plus** a schema decision about how a cadence config expresses a
per-dimension scheme selection — a JSON column against the platform's typed-column discipline, or a
child table.

---

## Part 1 — The decision ledger (Tier-3) — **RATIFIED 2026-07-31, all eight as recommended**

Eight open questions. Two are **reversals of positions ratified one slice ago** and are marked as
such — the SCH-2 lesson is that a reversal recorded anywhere but AT THE GATE is a reversal nobody
approved. Both reversals were put to the gate explicitly and accepted; the recommendations below
stand as ratified, and the text is left in its pre-gate voice so the reasoning that was actually
approved is legible rather than rewritten after the fact.

### OQ-LIM-2-1 — The scheme identity in the selector: bind by FAMILY, record the AUTHORED VERSION, and surface drift. **Recommend C.**

The fork is fact 12's: version-exact binding kills live limits at every taxonomy upgrade;
family-only binding silently re-anchors the threshold when a revision redraws the partition.

- **A — pin `scheme_id` (version-exact).** Fail-closed, and wrong in practice: adopting ISIC Rev. 5
  turns every sector limit `NEVER_EVALUABLE` at once, with no distinction between "this limit was
  never evaluable" and "this limit was decommissioned by a reference-data upgrade".
- **B — pin `scheme_family` only.** The limit keeps binding, which is what an operator wants, and
  fact 2's silent re-anchoring becomes permanent and undetectable.
- **C (recommended) — bind by `scheme_family`; ALSO store `authored_scheme_id`, the version the
  threshold was written against; report a distinct `limit_health` state when the resolved run's
  `scheme_id` differs from it.** The limit keeps evaluating (B's benefit), and the re-anchoring
  stops being silent (A's protection) without decommissioning the control. This is the shipped
  doctrine applied, not a new idea: `breach` already echoes its arithmetic so a breach reproduces
  from its own row, and `limit_health` already exists to distinguish states rather than default to
  green. Cost: one nullable GUID column and one health state.

**`authored_scheme_id` takes NO foreign key**, for the reason CON-1 gave for
`concentration_result.scheme_id`: `classification_scheme` is one of the seven hybrid tables, and a
PostgreSQL referential check bypasses RLS, so an FK would let a proprietary row reference a row its
own `USING` clause cannot see (`concentration/models.py:173-178`, OQ-CON-1-14).

### OQ-LIM-2-2 — Named-bucket limits: ADMIT them for classification dimensions. **Recommend B. This REVERSES a CON-1 ratification and is flagged as such.**

CON-1 ratified that `SHARE` is "explicitly EXCLUDED from any future registration"
(`con_1_decision_record.md:324`). The exclusion's stated reason is Part 0 fact 8 of that record:
`_resolve_latest` takes `matching[0]`, so a registered `SHARE` would resolve whichever bucket sorted
first. **That reason is exactly what this slice removes** — a `bucket_code` selector column makes
the resolution deterministic. Presented as a reversal because the position is one slice old and
because the wave plan's own motivating example is a named bucket: *"`limit_definition` scopes only
by exact `scope_portfolio_id` — 'sector TECH ≤ 20%' has nowhere to put TECH"*
(`wave_14_planning.md:50-52`).

- **A — summary metrics only (the nine names).** Smallest surface, no reversal; ships a
  concentration-limit feature that cannot express the concentration limit the slice was scoped to
  express.
- **B (recommended) — admit BOTH:** the nine run-level summary metrics, AND named-bucket `SHARE`
  limits carrying `(dimension_kind, scheme_family, bucket_code)`.

A **wildcard** limit ("any bucket above 5%") stays refused — `uq_breach_limit_run` permits one
breach per (limit, run) and could not record the three buckets it breached on (fact 6). That is
OQ-CON-1-16's conclusion, unchanged: the wildcard appetite is served by the MAX metric. A *named*
bucket is one bucket, one breach, and does not touch that constraint.

### OQ-LIM-2-3 — Issuer-named limits: ADMIT them and EXTEND the fence to the limit/breach reads. **Recommend B.**

Fact 7 is the constraint: `auditor_3l` holds `limit.view` and `breach.view` but is deliberately
excluded from `concentration.issuer.view`. A limit naming an issuer puts that identity on two
surfaces the fence does not cover.

- **A — refuse issuer-named limits (summary `*_ISSUER` metrics only).** Fail-closed and cheap. It
  also refuses *"no more than 5% in Issuer X"* — the single most common concentration limit anyone
  writes. Shipping a concentration-limit slice that cannot express it is a functional gap, not a
  descope.
- **B (recommended) — admit them, and extend the existing structural split to the limit and breach
  reads:** a caller holding `limit.view` but not `concentration.issuer.view` does not receive
  issuer-bearing limit or breach rows. This is `list_concentration_results`'
  `include_issuer_detail` pattern (`concentration/service.py:391-395`) applied to two more read
  surfaces — the fence follows the data instead of stopping where CON-1's scope stopped.
- **C — grant `auditor_3l` the issuer code.** Rejected: it reverses a deliberate, one-slice-old
  exclusion whose comment states the split exists precisely so that line can differ
  (`entitlement/bootstrap.py:462-466`).

**If the gate holds the slice at M, A is the honest descope** — fail-closed, with the trigger
recorded as "the first operator ask for a named-issuer limit". Recommending B anyway because the
CON-1 descope precedent was about a number the schema *could not compute*; this is a control the
schema can express and only the read fence needs extending.

### OQ-LIM-2-4 — The basis discipline is TWO checks at two times, not one. **Recommend both layers; this CORRECTS the carried obligation's framing.**

The CON-1 record hands over a *definition-time* basis-match refusal
(`con_1_decision_record.md:140-149`). Definition time cannot see a run, and `denominator_basis` is a
property of the **result row** (`concentration/models.py:181-183`). So the obligation splits:

1. **At definition** — the declared basis must be in `DENOMINATOR_BASES`. This is what refuses a
   regulatory-shaped threshold today: a limit declaring a `NAV` basis is refused because no such
   value exists. Enforced in `_validate_config` **and** as a DB CHECK.
2. **At evaluation** — the resolved row's `denominator_basis` must equal the limit's declared basis,
   or the limit refuses rather than compares. This is the load-bearing half and it did not exist in
   the carried framing; it is what stops a future `NAV`-basis run from being silently thresholded by
   an `INVESTED_LONG` limit.

On enforcement layer: fact 3 established that `limit_definition` and `breach` carry **zero** CHECK
constraints today. Recommend LIM-2 add their first ones, per P7's measured hierarchy (exact
mechanical gate over binder discipline) and the CON-1 fold's own precedent — *"Only binder discipline
kept that row class nonexistent; now the engine does"*.

### OQ-LIM-2-5 — The staleness fix is taken at the RESOLVER, platform-wide. **Recommend A. This EXPANDS scope beyond the roadmap row.**

Fact 4 established that the "refusal after success" hazard is the shared scaffold's, not
concentration's: whenever the newest run of any family FAILS while an older one succeeded,
`limit_health` reports `IN_APPETITE` off the stale one — live for VaR limits at HEAD, against OD-L's
own claim that an un-evaluable limit is never silently green.

- **A (recommended) — fix at `_resolve_latest`/`limit_health`, for every family.** Add a health
  state distinguishing "evaluated against the newest run" from "the newest run FAILED; this is the
  last good one". Cost: one additional newest-run-any-status lookup per limit. Repairs VaR and
  active-risk limits in the same edit.
- **B — scope it to concentration only.** Satisfies the carried obligation literally and knowingly
  leaves the same defect in two shipped families, which the next reviewer will find.

Recorded as scope expansion because the roadmap row does not mention VaR or active risk. It is
small, and declining it means shipping a slice that fixes a defect for the new family while leaving
it in the two families that already have live limits.

### OQ-LIM-2-6 — The registry contract: declare only what has a consumer, and census it. **Recommend as stated.**

A `LimitFamily` dataclass mirroring `ScheduledFamily` (`scheduling/service.py:314-347`), declaring
per family: the resolver callable, whether a benchmark is required, whether a basis is required, and
whether a dimensional selector is required. **Nothing else** — SCH-2 removed
`produces_run_on_failure` on the finding that *"a false declaration with no consumer is worse than no
declaration"* (`scheduling/service.py:324-339`), and that lesson governs here.

The gate that makes fact 1's silent fallthrough unreachable is an **exact set-equality census**, not
a matcher: `{family for (family, _) in _METRIC_MAP} == set(LIMIT_FAMILY_REGISTRY)`, plus a
fail-closed `else: raise` in the dispatch. P7's measured hierarchy puts exact censuses at zero
recorded recurrences while matchers recurred five times, so the census is the primary gate and the
raise is defense in depth.

### OQ-LIM-2-7 — The `breach` echo set, and paying the pre-existing scope-echo gap. **Recommend paying it here.**

Every new echo column is **additive-nullable with no backfill DML** — fact 5's P0001 constraint, the
`var_result` precedent (0038/0040/0048). The echo set: `dimension_kind`, `scheme_family`,
`authored_scheme_id`, `bucket_code`, `denominator_basis`.

Add `scope_portfolio_id` to `breach` in the same ALTER. It is the LOW the wave plan folded
(`wave_14_planning.md:55, 315`) — `breach` echoes the metric identity but not the portfolio the
limit was scoped to, so a breach row is not fully self-describing, against the doctrine
`limit/models.py:9-15` states. Paying it here costs one nullable column on an ALTER already being
written and closes a recorded gap; deferring it means a second `breach` migration later for one
column.

### OQ-LIM-2-8 — Schedulability and ENT-032 both stay DEFERRED. **Recommend deferring both, with fact 13's reason recorded.**

- **Schedulability (OQ-CON-1-17):** defer — but **the deferral's stated reason is wrong and is
  corrected here.** CON-1 recorded the cost as "a migration amending the total-enumeration
  `ck_schedule_model_version_by_family` CHECK". Fact 13 shows the real cost: a `Schedule` row is
  eleven typed scalars with nowhere to put `scheme_by_dimension`, so paying it requires a schema
  decision (JSON column against the platform's typed-column discipline, or a child table) that does
  not belong inside the wave's highest-risk migration. **The honest consequence, recorded rather
  than claimed away: a v1 concentration limit evaluates only after someone runs concentration by
  hand.** Trigger for paying it: the first operator ask for an unattended concentration cadence, or
  the first slice that gives `schedule` a per-family parameter surface for any other reason.
- **ENT-032 `limit_utilization`:** leave RESERVED (fact 11). Nothing in this pass makes it a
  prerequisite, and realizing a canonical entity carries its own governance cost. OQ-CON-1-18's
  reasoning holds against code.

---

## Part 2 — Independently computed reference values

**None required, and the reason is not "no time".** LIM-2 introduces no kernel, no estimator and no
new number: it thresholds values CON-1 already computes and whose reference values that slice's
Part 2 already carries. The arithmetic this slice owns is `_breaches`, a two-line total function
with a boundary table pinned since LIM-1 (`limit/service.py:173-180`). Adding a hand-computed
reference set here would be theatre.

**What replaces it** is the mutation proof the CON-1 fold established: each refusal added by this
slice ships with an executed negative control — the guard is removed or inverted and the test is
shown to fail. The one refusal that most needs it is the evaluation-time basis match (OQ-LIM-2-4),
because with a single-value vocabulary in v1 it is trivially satisfiable and would otherwise be
exactly the structurally-unfireable guard CON-1 shipped and had to reimplement.

## Part 3 — Implementation shape

### 3.1 `limit_definition` — five additive nullable columns, all FROZEN identity

Frozen means simply: absent from `_UPDATABLE` (`limit/service.py:148`), so a re-target is a new
limit and a breach's echo stays meaningful (OD-I). `limit_definition` is EV and carries no
append-only trigger, so it has the wider option set — but the columns are nullable anyway, because
a VaR limit has no dimension and NULL is the honest value.

| column | type | meaning |
| --- | --- | --- |
| `dimension_kind` | `String(30)` | `ISSUER` / `SECTOR_INDUSTRY` / `COUNTRY_OF_RISK`; NULL for non-concentration limits |
| `bucket_code` | `String(100)` | the named bucket; **NULL means a run-level (summary-metric) limit** |
| `issuer_id` | `GUID` FK `issuer.id` | the fence predicate AND referential integrity; NOT NULL iff an issuer is named |
| `scheme_family` | `String(50)` | the BINDING selector (OQ-LIM-2-1=C); NULL for `ISSUER` |
| `authored_scheme_id` | `GUID`, **no FK** | the scheme VERSION the threshold was written against |

`authored_scheme_id` takes no foreign key for CON-1's reason: `classification_scheme` is hybrid, and
a PostgreSQL referential check bypasses RLS (`concentration/models.py:173-178`). `issuer_id` *does*
take one — `issuer` is same-tenant proprietary, so the FK is legal, exactly as CON-1 reasoned for
`concentration_result.issuer_id`.

### 3.2 The first CHECK constraints these tables have ever carried (OQ-LIM-2-4)

Named per the 0055/0057 convention — **suffix only**, because the naming convention prepends
`ck_<table>_` itself. This is the defect only execution found last slice (0057's names landed
double-prefixed and PG-truncated at 63 chars), so the migration ships with the live-catalog gate
CON-1's fold added: a test reading `pg_constraint` and asserting set-equality against the ORM's
declared names.

1. `concentration_shape` — the dimension columns are present iff `target_run_type = 'CONCENTRATION'`.
2. `issuer_only` — `issuer_id IS NULL OR dimension_kind = 'ISSUER'` (mirrors CON-1's
   `issuer_only_on_issuer_rows`, and it is the disclosure fence made structural rather than
   binder-enforced).
3. `scheme_by_dimension` — `(dimension_kind IN ('SECTOR_INDUSTRY','COUNTRY_OF_RISK')) =
   (scheme_family IS NOT NULL)`.
4. `denominator_basis_vocab` — NULL, or a member of `DENOMINATOR_BASES`. **This is the
   definition-time half of the basis discipline**: a limit declaring a `NAV` basis is refused
   because no such value exists yet.
5. `dimension_kind_vocab` — total enumeration, failing closed on an unenumerated kind.

Every one validates clean against existing rows, which are all VAR/ACTIVE_RISK with NULL dimension
columns — that is what makes the double-table ALTER tractable.

### 3.3 `breach` — echoes what was MEASURED, not what was declared

Additive-nullable, **no backfill DML**: `breach` carries the P0001 trigger, so any `UPDATE` raises
(fact 5). Columns: `dimension_kind`, `bucket_code`, `issuer_id`, `scheme_family`,
**`resolved_scheme_id`**, `denominator_basis`, `scope_portfolio_id`.

`resolved_scheme_id` is the scheme the EVALUATED run actually used — deliberately not the limit's
`authored_scheme_id`. The self-describing doctrine is that a breach reproduces from its own row
(`limit/models.py:9-15`), and the pair (authored on the limit, resolved on the breach) is what makes
a scheme-drift breach *provable* after the fact rather than merely flagged live.

`scope_portfolio_id` pays the pre-existing LOW (OQ-LIM-2-7).

### 3.4 The registry and its census (OQ-LIM-2-6)

`LimitFamily` mirrors `ScheduledFamily`, declaring only what has a consumer: the resolver callable,
`requires_dimension`, `requires_basis`. `requires_benchmark` stays on `MetricSpec` where it already
lives — it is a per-metric property, not a per-family one, and duplicating it would be the false
declaration SCH-2 removed.

The gate is an **exact set-equality census** —
`{run_type for (run_type, _) in _METRIC_MAP} == set(LIMIT_FAMILY_REGISTRY)` — plus a fail-closed
`else: raise` replacing the dispatch's current unguarded fallthrough (fact 1). Census first, raise
as defense in depth: P7's measured hierarchy puts exact censuses at zero recorded recurrences and
matchers at five.

### 3.5 `limit_health` — a REFINEMENT of the ratified wording, stated rather than slipped in

Both OQ-LIM-2-1=C and OQ-LIM-2-5=A were ratified as adding "a distinct health state". **Implementing
them literally would be wrong**, and the reason is worth recording: `state` is the appetite verdict,
and a limit can be breached *and* evaluating a stale run *and* drifting across scheme versions at
the same time. A fourth and fifth enum value would force a false choice — reporting `STALE` would
hide a real breach, reporting `BREACHED` would hide the staleness.

So the ratified INTENT is preserved exactly — never default to green, make both conditions visible —
via two orthogonal fields on `LimitHealth` alongside the unchanged `state`:

- `latest_run_failed: bool` — the newest run of the family is FAILED and this verdict is computed
  from an older one. Costs one newest-run-any-status lookup per limit.
- `scheme_drift: tuple[str, str] | None` — `(authored_scheme_id, resolved_scheme_id)` when they
  differ.

Flagged here because it modifies how a just-ratified decision is realized. If the gate prefers the
literal enum, say so and it changes.

### 3.6 The read fence extension (OQ-LIM-2-3=B)

`list_limits` / `get_limit` / the breach reads gain the structural split
`list_concentration_results` already ships (`concentration/service.py:391-395`): a caller holding
`limit.view` or `breach.view` but **not** `concentration.issuer.view` does not receive rows where
`issuer_id IS NOT NULL`. Excluded **at the query**, not filtered in the router — CON-1's finding was
that a router-level courtesy is not a fence.

Two things the review must check rather than assume: that no `failure_reason` or breach narrative
reintroduces the issuer name in prose, and that the FE ops views degrade honestly for a caller who
cannot see issuer-bearing rows (`LimitHealth.tsx`, `BreachQueue.tsx`, `BreachDetail.tsx`).

### 3.7 Rule 7 reads

The FE renders `metric_type` verbatim in three places (fact 10) and would show
`MAX_SHARE_SECTOR_INDUSTRY` with no indication of which taxonomy produced it. The dimension, the
bucket and the scheme family reach these components in-slice, and the drift signal surfaces where a
limit's health is shown.

---

## Part 4 — Sizing

**M at its upper edge**, on the ratified set. The roadmap row said M; OQ-LIM-2-3=B (extending the
issuer fence to the limit and breach reads) and OQ-LIM-2-5=A (the platform-wide staleness fix) each
add work that row did not contemplate, and both were ratified. Neither is large alone; together they
are the difference between a comfortable M and its upper edge. Recorded so the closeout can measure
the estimate rather than reverse-engineer it. If the slice runs long, OQ-LIM-2-3=A is the descope
that gives back the most and is fail-closed — but it is a descope of a ratified decision and would
return to the gate, not be taken unilaterally.

The migration is the risk, as the roadmap says: a double-table ALTER where one table carries the
P0001 append-only trigger and both would receive their first CHECK constraints. **P4 applies** — the
pre-ratification verifier pass runs the migration in a throwaway workspace copy rather than reading
it (`claude_operating_instructions.md:283-290`), and every number that dry run produces is
re-measured against the merged artifact at closeout rather than carried forward as a pin.

## Part 5 — The P4 EXECUTED dry run (2026-07-31)

Run against a throwaway database (`irp_lim2_dryrun` in the standing `irp_pg_local` container),
migrated to `0057`, **seeded with existing `limit_definition` and `breach` rows before the ALTER** —
a CHECK added to an empty table passes vacuously, which is the P5 trap this slice would otherwise
have walked into. Draft migration: `0058_limit_dimension_selector`.

**It found two defects, and neither was findable by reading.**

### Finding 1 — the identifier asymmetry (the CON-1 0057 defect class, in reverse)

The upgrade path was correct and I verified it against the live `pg_constraint` catalog: five CHECKs,
correctly named, longest 43 of 63 allowed. **The downgrade failed**, trying to drop
`ck_limit_definition_ck_limit_definition_dimension_kind_vocab`.

Root cause, and it generalizes past this slice: **`ck` is the ONLY entry in `NAMING_CONVENTION` keyed
on `%(constraint_name)s`** (`db/base.py:8-14`). `ix`/`uq`/`fk`/`pk` substitute column and table
names instead. So a CHECK name is the only identifier alembic expands from what you pass — on
`drop_constraint` exactly as on `create_check_constraint` — while FK and index operations take the
literal catalog name. **Within one migration, three identifier kinds follow two opposite
conventions**, and the wrong one looks *more* correct on the page, because dropping the name you can
see in the catalog is the obvious thing to write.

CON-1 hit this on create and shipped truncated names. This hit it on drop, where the doubled name
came to 60 chars — under the limit, so nothing truncated; the constraint simply did not exist. **A
reading lane comparing migration text to ORM text would report parity in both cases.**

### Finding 2 — the downgrade creates an UN-UPGRADEABLE database (the serious one)

After fixing finding 1 the downgrade succeeded — and the **re-upgrade then died** with a
`CheckViolation` on four rows.

This migration is not in the 0046 "additive column, no DML, no zero-row trap" class, and the
difference is the CHECK. Dropping the dimension columns destroys the selector data while leaving the
rows carrying `target_run_type = 'CONCENTRATION'`. Re-upgrade re-adds the columns as NULL, and
`concentration_shape` rejects exactly those rows. So a *completed* downgrade leaves a database that
cannot be upgraded again without manual data repair — discovered only because the dry run ran the
full cycle rather than stopping at "the downgrade worked".

**Fix: the downgrade REFUSES, before dropping anything**, while any `CONCENTRATION` limit rows
exist, naming the count and the remedy. Refusing beats the alternatives: deleting governed config
rows on the operator's behalf would destroy audited configuration silently, and weakening the CHECK
to make the round trip survivable would trade a real guard for a reversibility nobody needs in
production. Retiring a limit is a governed act with an audit trail; a migration should not perform
it.

### The full cycle, after both fixes

Every step's exit code was printed, not inferred:

| step | result |
| --- | --- |
| upgrade `0057` → `0058` over NON-EMPTY tables | exit 0; 5 CHECKs, longest 43 chars |
| existing rows | 2 limits, 1 breach survived; **0 of each carries a dimension** — NULL is the honest value |
| probe battery | **14/14** — 9 refusals fired, 5 positive controls admitted |
| downgrade with concentration limits present | **exit 1, guard fired**, named 3 rows, head unchanged — nothing dropped |
| downgrade after retiring them | exit 0 → `0057`; 3 limits + 2 breaches preserved |
| re-upgrade | exit 0 → `0058`; 5 CHECKs restored |

The nine refusals: the P0001 backfill on `breach` (twice — once on a pre-existing row, once on a
freshly inserted concentration echo, so the immutability covers the new columns too); a VAR limit
carrying a dimension; a concentration limit with no basis; **issuer identity on a
`SECTOR_INDUSTRY` limit — the disclosure fence, structural**; an ISSUER limit carrying a scheme
family; a classification limit missing one; a NAV-denominated (regulatory-shaped) threshold; and an
unenumerated dimension kind.

The five positive controls exist because eight refusals prove nothing on their own — a CHECK that
rejects everything would have passed all of them. They admit: a named-issuer limit, a named-bucket
sector limit ("tech ≤ 20%"), a run-level HHI limit, an ordinary VaR limit, and a new breach carrying
the full echo set.

### A standing rule this slice departs from, recorded rather than assumed

The operating instructions' **Genericity** rule says *"type/scheme/status columns are controlled-vocab
strings (no enum/CHECK) … new families extend by value, never a migration"*
(`claude_operating_instructions.md:193`). Three of the five CHECKs are SHAPE constraints, which that
rule does not reach. **Two are vocabulary CHECKs and ARE a departure**: `dimension_kind_vocab` and
`denominator_basis_vocab`.

Taken deliberately, with prior art one and four slices old — 0057's
`ck_concentration_result_dimension_kind` and 0053's `ck_schedule_cadence_kind_vocab` — because the
extensibility the rule protects is exactly what must not exist here: **adding a denominator basis
changes what every threshold written against the old one MEANS.** That has to cost a migration and a
governed decision, not a new string. Recorded per the standing requirement that a deviation is
written down, never a silent "confirm" (`claude_operating_instructions.md:198`).

**This correction belongs to Part 0 fact 3.** That fact framed "zero CHECK constraints on these two
tables" as an inconsistency to fix. Partly it is the standing rule being correctly followed. The
ratified recommendation does not change, but its justification does — and the justification is what
a reviewer checks. Missing the rule on the first pass is the same class as the Wave-14 planning
BLOCKING that recommended against an uncited Accepted ADR.

## Verification note

Facts 2, 3 (the zero-CHECK half), 4 (the platform-wide scope), 7, 12 and 13 are **new to this pass**
— they are not in `con_1_decision_record.md`, `wave_14_planning.md`, or the roadmap row. Facts 1, 5,
6, 8, 9, 10 and 11 confirm or sharpen positions those records already hold.

Nothing here has been adversarially reviewed. The claims most worth attacking, in order:

1. **Fact 4** — a claim about shipped behavior in two families outside this slice, reached by
   tracing the chain rather than by executing it. If it is wrong, OQ-LIM-2-5 collapses to B.
2. **Fact 7 / OQ-LIM-2-3** — a disclosure claim that holds only while `ROLE_TEMPLATES` declares the
   holder sets it declares today.
3. **OQ-LIM-2-2's reversal** — the argument is that the new `bucket_code` selector removes the
   exclusion's *stated* reason. If CON-1 had an unstated reason, the reversal is unsound.
4. **OQ-LIM-2-1=C** — it adds a column and a state to buy detectability. A reviewer should test
   whether the drift it detects is one an operator can actually act on, or telemetry nobody reads.
