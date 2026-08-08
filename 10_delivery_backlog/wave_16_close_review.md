# Wave-16 close review

**Produced 2026-08-08 by a FRESH-CONTEXT review on a DIFFERENT ENGINE from the builder** (five
independent lenses over merged main, a verifier that executed rather than read, and a synthesis
pass). Waves 1-15 each have a close-review document; Wave 16 had none until this one — which the
review itself flagged as a finding, since the wave's most-cited scrutiny existed only in
transcripts.

**The document below is the review's own output, committed verbatim.** Its [ran it] / [not re-run]
markers are the reviewer's. Two of its most consequential claims were independently spot-checked by
the builder before the gate: the 291-operations-zero-provisioning finding (confirmed: 251 paths,
291 operations, zero matches for user/role/tenant/principal/grant/onboard) and the FK-1 universality
refutation (confirmed: direct `create_engine` reports `PRAGMA foreign_keys = 0`, `make_engine`
reports `1`, and seven test modules build engines directly).

---

## GATE OUTCOME — user decisions, 2026-08-08

All four decisions put to the user were ratified **as recommended**:

| # | Decision | Outcome |
|---|---|---|
| **D3** | Tenant/user/role provisioning | **ONBOARD-1 as Wave-17 slice 0.** The platform's 291 RBAC-protected operations are unreachable by any real user; every other Wave-17 candidate is a feature for users who cannot exist. |
| **D1** | `report.*` holder sets | **Ratified as shipped.** `report.generate` -> platform_admin, data_steward, risk_analyst_1l; `report.view` -> those three plus risk_manager_2l and auditor_3l. The RPT-2 carry is DISCHARGED. Note the open sub-question the ratification does not settle: `auditor_3l` holds `report.view` but not `portfolio.view`, while reports carry `portfolio_code`/`portfolio_id`. |
| **D2** | Mint-reachability rule | **RATIFIED as a standing rule WITH a mechanical gate AND the revocation fix.** A test must assert every permission in the bootstrap constant is named by some migration; and the sync migration must stop re-inserting grants an administrator deliberately revoked. Ratifying the sync without the revocation fix would have institutionalised the resurrection. |
| **D4** | Reproduction alarm fail-open | **FIX IN THE WAVE-16 CLOSE FOLD**, not carried. CTRL-018 is *Implemented* today while carrying a tenant-wide silent fail-open whose shipped test asserts the fail-open as expected behaviour. |

D5 (carries with no owner) and D6 (three process rules the wave earned) were presented in the
briefing below and are NOT yet ratified — they are carried to the Wave-17 planning gate rather than
decided here, because they change how the process works rather than what ships.

---

# WAVE-16 CLOSE REVIEW — GATE BRIEFING

*Verified against merged main at `00993e1` (`git rev-parse HEAD == origin/main`, working tree clean). Everything below that I re-checked myself is marked **[ran it]**; everything I took from the lens/verifier without re-running is marked **[not re-run]**.*

---

## 1. WHAT WAVE 16 DELIVERED

**RPT-2 (PR #181) — the governed report became reachable over HTTP.**
Before this slice a risk report could be generated only from a test or a script; now there are four endpoints (`POST /reports`, `GET /reports`, `GET /reports/{id}`, `GET /reports/{id}/html`) and a frontend Reports view that lists reports and renders one **[ran it — route census off the live OpenAPI spec]**. Every read re-proves the report's reproducibility rather than trusting the stored bytes. It also shipped migration `0064`, which fixed a real latent bug: newly-minted permissions had been undeliverable to any already-running database since the entitlement work began.

**REPRO-1 (PR #183) — the reproducibility claim became a machine check.**
The platform has always claimed every governed number can be regenerated identically; REPRO-1 built the sweep that actually re-runs a family and records a `MATCH` / `DIVERGED` / `UNREPRODUCIBLE` verdict as a durable row (new entity ENT-073, migration `0065`), with a CI proof that plants a divergence and confirms it is caught. Three of twenty-one governed families are registered as reproducible today; the other eighteen are enumerated with written reasons **[ran it — 3 registered / 18 not, imported from main]**. Nothing outside the CI proof harness can currently start the sweep, which the records do say, in most places.

**FK-1 (PR #185) — the test suite stopped tolerating impossible data.**
SQLite ignores foreign keys unless told not to, so for the platform's whole life the unit tier let fixtures write rows pointing at parents that did not exist. FK-1 turned enforcement on inside the shared engine factory and repaired 151 fixtures across 14 suites so they seed genuine parents. This is quiet but load-bearing: it removes a class of test that passes for the wrong reason.

---

## 2. WHAT IS TRUE, AND WHAT IS OVERSTATED

Ranked by how much it matters. All three slices are substantively real — the defects below are mostly the **records claiming more than the code delivers**, plus two genuine holes.

### Blocking

**1. There is no way to create a tenant, a user, or a role in a deployed system. [ran it]**
The API has 291 operations. Searching all of them for `user`, `role`, `tenant`, `principal`, `grant`, `onboard` returns the empty set — every one. Role templates are seeded only under the reserved system tenant by migrations; every governed route requires an entitled in-tenant principal. So a freshly deployed stack has zero principals and **none of its 291 operations is callable by anyone**. The only ways in are running a demo/proof script against the database or hand-written SQL. The codebase says this about itself in two places (`reproduction/events.py:43`, `infra/deploy/deploy.sh:108-110`); no ledger or roadmap does. This is the single biggest gap between what the records imply and what a buyer would find.

### High — real holes

**2. The reproducibility alarm can go permanently silent, tenant-wide, and it is filed as an accepted trade-off. [not re-run end-to-end; code path confirmed by reading]**
One malformed notification payload makes the alarm phase fail on every subsequent tick for that tenant, forever. The failure is caught and returns an empty list, which every caller reads as "nothing to alarm". The verifier reproduced this against main including with a poison row about an *unrelated* entity, and showed a genuinely diverged verdict created afterwards going unalarmed across five consecutive ticks — the only trace is a log line. The shipped test writes the poison row *for the diverged check itself* and asserts the empty result, i.e. it asserts the fail-open as expected behaviour rather than catching it. For a detective control whose entire value is "a machine tells you when a governed number stopped reproducing", this is a defect, not a carry.

**3. ENT-073's verdicts have no read surface at all. [ran it]** No endpoint contains `repro`; the frontend has eight routes and none is reproduction. Combined with (2), a divergence is discoverable only by raw SQL. The standing project rule that every governed number ships entity/time reads in-slice got no explicit disposition here.

**4. FK enforcement is not universal, and the claim that it is can be refuted in one command. [ran it]** `make_engine` sets the pragma; a direct `create_engine` does not (I measured `1` vs `0`). Three unit suites build SQLite engines directly and remain FK-blind: `test_concentration_kernel.py:181`, `test_demo_hg1.py:60`, `test_demo_multifamily.py:27`. Forcing the pragma globally turns four currently-green tests red with `FOREIGN KEY constraint failed` — `test_concentration_kernel.py::TestUnitTierGrain` is writing dangling foreign keys today and passing because of it **[verifier ran the forced-pragma suite; I confirmed the pragma difference and the three bypass sites]**. FK-1's census was measured *through the factory*, so it was structurally blind to suites that bypass the factory — the same shape of blind spot the slice was built to close.

**5. A ratified gate outcome was never paid and is on no register. [ran it]** The Wave-16 planning gate ratified "TS→7 paid as RPT-2 slice 0". `apps/frontend/package.json` shows eslint 10.8.0 ✓, jsdom 30.0.1 ✓, **typescript ^5.9.3 ✗**. The refusal is well-reasoned and honestly written up inside RPT-2's deviations section — but it is not in RPT-2's carries table, not in `current_state.md`, not in the roadmap's close agenda (which I read: it owes only two items), and the roadmap's deferral register still records the debt as undecided. The debt is invisible to every document a successor slice would read.

**6. Nine of the wave's carries are parked on slices that do not exist.** "An operational-alerting slice", "an operator-workflow slice", "a tenant-onboarding slice" — none is proposed or sequenced anywhere. All four known silent-failure modes of the reproduction alarm channel are parked on the same non-existent slice, so the mechanism that would fix them is nobody's work. Of 31 carries in the wave, exactly two (both FK-1's) have a trigger that cannot be missed.

### High — records that overstate

**7. The mutation batteries that are cited as proof four times do not exist in the repository. [ran it]** `git ls-files | grep -Ei 'mutat|battery'` returns nothing. Every mutation claim in Wave 16 rests on a scratch script that no longer exists on any branch. FK-1's four mutants are at least enumerated in prose and were independently re-derived; REPRO-1's headline "14/14" is enumerated nowhere and cannot be reconstructed by anyone.

**8. Two governed documents disagree about that number anyway.** The slice record says 14/14; the control matrix says "at the close it is 11/11" — which is the *fourth* fold's figure, two folds behind the merged code — in the same sentence that claims the number is deliberately kept in one place only.

**9. FK-1's headline measurement is from the wrong tree. [verifier ran the suite; arithmetic checks out]** The record quotes `2554 passed` as the after-state at the merge head; main measures `2557`. The gap is exactly the slice's own three guard tests, so the "after" number was taken before those tests existed. The same record's later section says 3,159 collected, which is consistent with 2557, so the record contradicts itself.

**10. CTRL-009's evidence citation is stale in two independent ways. [ran it]** It names a CI run whose step title no longer exists — the workflow file on main reads a renamed step — and 221 lines of production change have landed in the report code and proof harness it points at since. The control is substantively fine (the renamed step is green on main's own CI run); the *record* would send an auditor to the wrong place.

**11. The new citation rule was overridden one day after it was ratified. [ran it]** P16 says a control-status citation must survive a records-only diff at the PR boundary. `git diff --name-only e7ae526..origin/main`, excluding docs and tests, names exactly one file: `packages/shared-python/src/irp_shared/db/session.py` — production source, changed by FK-1. The change is dialect-guarded and behaviourally inert on PostgreSQL, so the judgement was defensible — but P16 exists precisely because that kind of judgement had already failed twice. Half-life of a mechanical rule under builder discretion: one slice.

**12. A false claim about control coverage is live in production source. [ran it]** `report/service.py:405` and the canonical data model both say the report binder is "recorded on the P8 census exception list". It is not on that list, and it cannot be — the census defines its population by a string neither the report nor the reproduction service uses. Both of the platform's two newest governed families are structurally invisible to that census. REPRO-1 noticed and filed it as a records carry; the coverage hole is the real finding.

**13. There is no committed evidence trail for the wave's most-cited scrutiny. [ran it]** Waves 1–15 each have a close-review document in the repo; Wave 16 has none. The last committed session log stops at REPRO-1's third fold — nothing covers folds 4–6, the different-engine reviews, the confirmation pass, or FK-1 at all. The strongest claims in the wave ("`ANY_DIFF: False`", "no seventh defect") exist only as the builder's own prose in the two files that assert them.

### Medium — worth knowing, not urgent

- **An auditor can read every portfolio's identity through the report surface.** `auditor_3l` holds `report.view` but not `portfolio.view` **[ran it]**, yet the report response carries `portfolio_code` and `portfolio_id`, renders the code into the report `<h1>`, and the unfiltered listing lets the auditor enumerate every book in the tenant that has a report. The project already minted a permission *solely* to withhold issuer identity from this role — by its own precedent this is the class it treats as a hole. Whether the auditor is *meant* to see book identity is a governance call, not a bug I can settle.
- **Running a migration silently restores an entitlement an administrator revoked.** Migration `0064` cannot distinguish "never delivered" from "revoked"; the behaviour is documented and was reproduced by the author. Honest disclosure, wrong home: its "host" is the moment an operator discovers it in production.
- **Reports cannot be generated from the UI.** The frontend can list and render reports and nothing else; when there are none it renders a dead end. Obtaining a report requires a raw `POST` with a hand-assembled map of run IDs. This is the project's own OPS-1 lesson ("a demo that cannot reach a control does not demonstrate it") recurring one wave later.
- **Two carries were paid inside the wave and neither carrying document was updated**, so a close reviewer reading RPT-2's carries table would re-open both.
- **The stated rule set is about half its real size.** Sixteen numbered principles, plus at least ten unnumbered standing rules, at least one of which duplicates a numbered one. Four numbered principles (P2, P4, P6, P13) are cited nowhere in Wave 16 — including P2, whose violation FK-1 then rediscovered from first principles and wrote up as two new local rules.
- **The prohibited-behaviour section still forbids things the autonomy grant requires.** "Starting the next slice unprompted" is listed as prohibited on the same page that says the next slice starts autonomously; six autonomous merges happened this wave. Dead prohibitions teach the reader that emphasis is not a reliable signal.
- **P9's mechanical half was never built.** Six days after ratification, and after a wave that cited it as a gate three times, no census enumerates refusal errors; applying it by hand finds 44 error classes raised in source and named in no test, five of them in exactly the population P9 names.

### What checked out clean

FK-1's two carries are the only ones in the wave with genuine, unmissable code-level triggers. FK-1's doctrine census (no pragma disabling, no nullable columns, no deleted tests) reproduces exactly. The reproduction coverage census is accurate. Carry (m) — "no deployment path creates a reproduction schedule" — is accurate and stated plainly. The three merge SHAs are all real and all ancestors of main. And migration `0064` is a genuine fix to a real, previously-invisible bug.

**Not verified by anyone:** the full-PG battery (needs a shared-database schema reset mid-review), the `0064` revoke→downgrade→upgrade reproduction, and an end-to-end HTTP transcript of the auditor disclosure (it was proven at the permission and route-guard layer instead).

---

## 3. DECISIONS YOU NEED TO MAKE

### D1 — Ratify the `report.*` permission holder sets (carried from RPT-2)

**The decision:** who is allowed to generate a governed report, and who is allowed to read one — every prior permission mint put its holder list to you before shipping; this one did not.

Shipped today **[ran it — imported from main]**:
- `report.generate` → platform_admin, data_steward, risk_analyst_1l
- `report.view` → those three, plus risk_manager_2l, plus auditor_3l

| Option | Consequence |
|---|---|
| **A. Ratify as shipped** | Nothing changes. The auditor keeps read access to portfolio identity through reports (see D2), which is the substantive question hiding inside this one. |
| **B. Ratify with a change to `report.generate`** | Most likely candidate: drop `data_steward` — a steward's remit is reference and market data, not producing a book's risk artifact. Small code change, one migration to sync live databases. |
| **C. Defer to a full entitlement review** | Puts a broader question (does the role model still fit after 24 governed families?) on the Wave-17 agenda; costs a slice. |

**Recommendation: A, conditional on deciding D2 first.** The generate set is defensible — the three roles that produce or steward governed numbers. `report.view` including risk_manager_2l and auditor_3l is right for a three-lines-of-defence model. The only genuinely contestable element is what the auditor sees inside the report, which is D2, not a holder-set question. Ratifying the holder sets while leaving D2 open would be ratifying the wrong half.

### D2 — The mint-reachability rule (carried from RPT-2)

**The decision:** make it a standing rule that adding a permission to the bootstrap file does not count as delivered until a migration syncs it into already-running databases.

Background: permissions live in a Python constant that seeds a *new* database. Any database already running never sees a newly-added permission, so every permission minted since the entitlement work began was undeliverable to a live deployment until RPT-2's migration `0064` fixed it. That is exactly the class of defect this project's rules exist to catch, and nothing caught it for many waves.

| Option | Consequence |
|---|---|
| **A. Ratify as a standing rule with a mechanical gate** — a test asserting that every permission in the bootstrap constant is also named by some migration | Cheap, enforceable, fires on the next mint. Requires deciding what to do about revocation (below). |
| **B. Ratify as prose only** ("remember to add a migration") | The project's own P7 says bare "remember X" rules do not hold. This has already been forgotten across many waves. |
| **C. Decline; handle it per-slice** | Guarantees recurrence. Not recommended. |

**Recommendation: A**, with one addition the finding forces: the sync migration currently **re-inserts grants an administrator deliberately revoked**. A rule that mandates the sync without addressing revocation durability institutionalises that behaviour. Ratify A *and* require the sync to consult a revocation record, or at minimum to log and skip previously-revoked grants. This is small work and it is the difference between "deny-by-default with governed mints" being true and being aspirational.

### D3 — Tenant / user / role provisioning (new; this is the big one)

**The decision:** does Wave 17 build a provisioning path, or does the platform continue to be reachable only from test fixtures and seed scripts?

| Option | Consequence |
|---|---|
| **A. Build ONBOARD-1 as Wave 17 slice 0** | Closes the gap between "291 governed operations behind RBAC" and "nobody can call any of them". Non-trivial: tenant creation, role cloning from templates, user creation, first-admin bootstrap, and the audit/entitlement discipline all of it must inherit. Probably the largest slice since the API work. |
| **B. Ship a documented admin CLI / seed script instead** | Much cheaper, honest, and enough for a demo or a pilot. But it is an operator running Python against production, which sits badly next to the platform's own governance thesis. |
| **C. Accept and disclose** | Add it explicitly to the records as a known scope boundary ("the platform assumes tenants are provisioned out of band") and move on. Legitimate if the near-term audience is a demo, not a deployment. |

**Recommendation: A, and sequence it first.** Every other Wave-17 candidate — alerting, reproduction reads, report generation from the UI — is a feature for users who cannot currently exist. The gap is also the one a technical due-diligence reader finds in about ten minutes, and finding it themselves is much worse than reading it in your own records. If A is too large for one wave, take **B as an explicit interim** with A named and sequenced, rather than leaving the gap unowned.

### D4 — The reproducibility alarm: fix now or carry

**The decision:** is the reproduction alarm's permanent-silence failure a defect to fix before the wave closes, or an accepted limitation?

| Option | Consequence |
|---|---|
| **A. Fix in a Wave-16 close fold** | Small: scope the queue read per-verdict so one bad row cannot kill the phase, add a health signal that recomputes from source rather than inferring from absence, and a test that constructs a *live* divergence after the poison row. A day's work; closes four related carries at once. |
| **B. Host it in a Wave-17 alerting slice** | Correct home, but that slice does not exist yet, and the control is *Implemented* on the control matrix today while carrying a silent fail-open. |
| **C. Accept as documented** | The control's status word would then be doing real work it cannot support. Not recommended — the project's own standing lesson is that a refusal is not implemented until a test has made it fire, and here the shipped test asserts the failure as expected behaviour. |

**Recommendation: A now, B for the rest.** Fix the fail-open in the close fold because it is cheap and because "Implemented" is currently claiming more than the code does. Leave the recipient-degradation and unbounded-retry carries for a real alerting slice — but only if that slice actually gets sequenced (see D5).

### D5 — What to do about carries with no owner

**The decision:** 29 of the wave's 31 carries name a host that does not exist, is not a trigger, or is "someone will notice in production".

| Option | Consequence |
|---|---|
| **A. Rule: a carry must name either a sequenced slice or a mechanical trigger; anything else is a decision, not a carry** | Forces the honest conversation at the moment of deferral instead of at the close. Costs discipline at slice-close time. |
| **B. Sweep the register once at each wave close and promote homeless carries to the roadmap** | Weaker but cheaper; keeps the register honest without changing how carries are written. |
| **C. Leave as is** | The carry register becomes a place where known problems go to be forgotten with a paper trail. Arguably already happening. |

**Recommendation: A**, with B as the backstop at each close.

### D6 — Process rules the wave earned

Three candidates, all supported by the evidence:

1. **Verification harnesses need their own controls, and must be committed.** Seven separate instances this wave of a harness that could not detect what it claimed to test (a test that could not plant its own divergence, a proof that minted its own tenant and proved nothing, a negative control that never received its input, a mutation battery that destroyed the fix it was testing, a smoke that compared a report to itself). **Recommend: ratify.** Every negative control ships a positive control asserting the harness's own precondition landed; any harness producing governed evidence is committed to the repository. This is the wave's dominant defect class and the strongest rule available.
2. **A review pass may not run on the same engine that introduced the defect it is folding.** Five consecutive same-engine passes each introduced a defect the next one caught; a different engine found the sixth blocking issue in one pass. **Recommend: accept as an amendment to the existing "two proofs sharing an assumption are one proof" rule**, not as a new principle — and phrase it as a trigger, not a standing assignment matrix, because engine availability is not guaranteed.
3. **A subagent's report is inadmissible unless it quotes a terminal exit code.** One audit this wave returned before finishing and was correctly discarded. **Recommend: accept as one clause on the existing exit-code rule**, not a new principle.

**And a cleanup, not a decision:** the rule document contains at least one prohibition that directly contradicts the autonomy grant, and roughly ten unnumbered standing rules. Recommend a single editorial pass to reconcile and number them. A rule set nobody can enumerate is the mechanism behind two of this wave's findings.

---

## 4. WHAT I RECOMMEND NEXT

**First: a Wave-16 close fold (not a Wave-17 slice) — cheap, and the wave cannot honestly close without it.**

| # | Item | Why |
|---|---|---|
| 1 | Re-cite CTRL-009; fix 14/14 vs 11/11; fix FK-1's 2554→2557; put the close-review evidence in the repo | Four records currently overstate or misdirect; all are one-line fixes |
| 2 | Correct the false "P8 exception list" sentence in production source and the canonical model, and widen that census's population so the report and reproduction binders are visible to it | A governed standard currently asserts coverage that does not exist |
| 3 | Census test-side engine construction; retire the one surviving per-suite pragma listener; fix the four tests writing dangling FKs | Makes FK-1's headline claim actually true |
| 4 | Fix the alarm-queue fail-open (D4-A) with a live-divergence-after-poison test | The control is claiming more than the code does |
| 5 | Register the unpaid TS→7 debt on the roadmap and in `current_state.md` | A ratified gate outcome is currently invisible |
| 6 | Commit the mutation harness | Four cited proofs currently have no artifact |

**Then Wave 17, in this order:**

1. **ONBOARD-1** — tenant/user/role provisioning. Without it none of the 291 operations is reachable by a real user; every other candidate is a feature for users who cannot exist.
2. **ALERT-1** — the operational alerting slice that six homeless carries already name as their host. Gives the reproduction control an alarm the operator can see and trust.
3. **REPRO-2** — a read surface over reproduction verdicts, a schedule write path, and more families registered. Moves CTRL-018 from "Implemented but unstartable" toward Operational; without it the nightly sweep is real code that nothing will ever run.
4. **RPT-3** — report generation from the UI, with a run picker. Currently the FE can read reports but not create one.
5. **TS→7** — when `typescript-eslint` and `openapi-typescript` both declare support. Monitor, don't force.

FK-1's own two carries need no slice — their triggers will fire on their own.

---

## 5. THE HONEST ASSESSMENT

Wave 16 shipped three genuinely valuable things and the process was **not proportionate** — but the diagnosis in the records is wrong. REPRO-1 took sixteen commits and nine review stages, and 41% of its production code was written *after* the first adversarial review; the folds were not corrections, they were new 300-line changes shipped under the word "fold" and reviewed once. "Five consecutive folds each introduced a defect the next one caught" is the arithmetically expected result of that, not evidence of thoroughness — and the scrutiny was spent on a control that no deployed tenant can currently start, for three of twenty-one families. The honest lever is scope, not stages: cap the fold, split the discovery work from the build work, merge earlier on less. Meanwhile FK-1, the one slice that got *neither* an adversarial review nor a fresh-context audit, merged with its headline claim refutable in a single grep and its measurement taken from the wrong tree — so the scrutiny is doing real work when it runs; it is the allocation that is wrong. **The single biggest risk carried into Wave 17 is not any of the process findings: it is that the platform has 24 governed families and 291 RBAC-protected operations and no way whatsoever to create the tenant, user, or role that every one of them requires.** The records describe a deployable multi-tenant product; the code describes a very well-governed engine with no ignition. That gap is discoverable by an outside reader in minutes, and it is currently written down nowhere except in two source-code comments that say so in passing.