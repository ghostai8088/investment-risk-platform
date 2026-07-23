# Wave-10 Close Review — the fast-follow read-surface + the §2.1 unification arc (THE DESTINATION)

**Status: DRAFT for ratification (2026-07-23).** The mandatory rolling-wave close (roadmap Part 4
rule 2) after Wave 10 shipped its ratified sequence **API-1b → FE-3b → the §2.1 private/public
unification (PPF-1 → PPF-2 → PPF-3)** (OQ-W9C-3 fork A). This is the wave that finished Wave 9's
read-surface/identity product AND shipped **the platform's declared strategic destination**: the
unified public+private portfolio VaR the whole math roadmap called itself the substrate for. Open
decisions (OQ-W10C-1…5) are in Part 6 — the pivotal one is the Wave-11 fork now that the destination
is reached.

**Method.** Four cross-cutting close auditors over the wave diff (`11967b8..4070438`, 148 files,
+13.4k/−0.8k) — cross-slice integration/composition, security + doctrine (a dedicated lens for the
FE-3b browser-auth flow AND the PPF private-asset math, which could mislead if wrong), doc / register
/ closure-stamp coherence, and a completeness-critic + outward-benchmark + destination pass — on top
of each slice's own shipped 4-finder review (every slice already reviewed; PPF-3 folded a HIGH
in-slice). Opus-only, proportionate to a five-slice wave whose slices were each already reviewed
(ultracode off). **Every material finding was independently re-verified by the synthesizer** — the
frozen-file diff, the migration chain, the governed counts, `gen-api-check`, `make check`, and the
closure-stamp state were each re-run by hand; the stamp finding's blast radius was measured before
any edit. Model confidence is not evidence.

Counts at wave end, DB-consistent across the docs and asserted by the live-PG demo test:
**23 governed model codes / 38 validation records / 109 COMPLETED demo runs** (17/20/35/101 at
Wave-9 end → PPF-1 21/36/103 → PPF-2 22/37/104 → PPF-3 23/38/109; API-1b + FE-3b were
count-neutral). Migration head advanced `0045 → 0046 → 0047 → 0048` — a clean single linear chain.

---

## Part 1 — Did Wave 10 ship what was ratified? — YES; ZERO shipped-CODE defects (the sixth consecutive clean close on the code axis)

All five slices shipped as ratified, each CI-green, in order. The cross-cutting audit found **zero
shipped-code defects** — every previously-folded finding is present and correct at HEAD:

- **API-1b** (PR #92 `f1e830f`): the flagship "latest VaR/active-risk for portfolio P" reads,
  resolved at the write boundary via one additive `calculation_run.scope_portfolio_id` column
  (migration 0046), stamped by all five binders + the pip-audit / closure-discipline CI riders.
- **FE-3b** (PR #95 `2cbb68c`): the SPA OIDC/PKCE browser login — state-before-exchange, single-use
  PKCE verifier, no `clientSecret`, zero backend weakening of SSO-1's RS256 verification.
- **PPF-1 → PPF-2 → PPF-3** (PRs #98 `9d64b49`, #101 `7aefd1c`, #104 `633e855`): the §2.1 arc — the
  pure-private return series (18th number, migration 0047), the Ω_pp private covariance block (19th,
  no migration), and the unified public+private VaR (20th, migration 0048).

**Gates green at HEAD** (all re-run by the integration auditor against live PG + independently by the
synthesizer): `make check` **1849 passed** / the PG-enabled full battery ~2231 passed, 0 failed /
`make fe-check` green / `make gen-api-check` no drift / `alembic check` clean, single head `0048`,
up→down→re-up smoke clean / secret-scan + docs-check pass.

**Load-bearing integration properties, verified:** (1) the private-family isolation holds across the
whole wave — every production read on the shared `covariance_result` / `factor` / `var_result` /
`calculation_run` tables filters `run_type`/`frequency`/family, and the two by-id reads that don't
are provably safe (a type-validated id; an FX-factor-set disambiguation a private set can't satisfy);
`list_risk_runs` excludes the two private run types while UNIFIED (as `run_type=VAR`) correctly
appears. (2) API-1b's `scope_portfolio_id` reads compose with PPF-3's new `VAR_PARAMETRIC_UNIFIED`
metric **for free** — `run_var_unified` stamps the scope from its pinned exposure run and reuses
`run_type=VAR`, proven live by `latest_var_for_portfolio(metric_type=UNIFIED)`. (3) The PPF-3
consume-path double-count fold and off-diagonal completeness gate are present + correct; cross-tenant
Ω_pp provenance is re-resolved under the acting tenant before every hard-FK write. (4) Every hard
invariant holds: `audit/service.py` byte-frozen + never imported as a writer; no BYPASSRLS /
superuser / new-mint; no secrets (the FE-3b Keycloak realm/compose swept clean); immutable model
identity.

**At-close folds (3, doc-hygiene — Part 3):** PPF-3's decision record stamped CLOSED + its Part 6
outcome added; CC-2's Wave-8 record stamped CLOSED (a historical miss the broadened gate surfaced);
the OQ-W9C-5 CI closure-teeth broadened to fix the two blind spots that let the class recur.

The one HIGH the audit surfaced is **not shipped code** — it is the recurring closure-stamp process
class (Part 3). On the code axis this is the sixth consecutive zero-defect close.

---

## Part 2 — The deferral register, reconciled

**Fixed at this close** (Part 1 / Part 3): the PPF-3 stamp + Part-6; the CC-2 historical stamp; the
closure-teeth broadening + its unit test.

**Carried, with disposition:**

- **The first scheduler — the highest-value forward item, now carried a fourth close.** Nothing in
  the platform runs on a cadence — every governed number is manual-invocation-only, so "current
  risk" is only as fresh as the last hand-run (confirmed absent at code AND infra level). This is the
  longest-standing *structural* gap and a prerequisite for limit monitoring, remediation deadlines,
  and data refresh. **Disposition: the leading Wave-11 candidate — see OQ-W10C-4 fork A.**
- **Limits / breach workflow (RTM-P6)** — the most conspicuous *missing product capability* for a
  risk platform: you can compute VaR but cannot say "alert me when it breaches X." **Disposition: the
  second leg of the operationalize theme (OQ-W10C-4 fork A).**
- **MG-2 remediation-lifecycle** — trigger eroding, earliest real overdue **2027-07-19** (a year
  out, so not date-urgent). The governance-workflow-with-teeth gap; rides naturally with the
  operational theme. **Disposition: carried; the third leg of fork A.**
- **The PPF-3 v2 seams** (the destination number's disclosed refinements) — **leverage** (the one
  load-bearing gap: a levered private book's true risk is not yet answered; needs new captured data),
  a global-factor public↔private linkage, HS/ES unified analogues, the multi-member asset-specific
  split. All honestly disclosed in the registered limitations. **Disposition: the Wave-11 fork B
  alternative (OQ-W10C-4); leverage is the highest-value single refinement.**
- **BT-3 D-F4 registered-string reword** — `VAR_BACKTEST_LIMITATIONS` still calls Christoffersen "a
  named BT-3 candidate" though it shipped v2. **DEFERRED to a dedicated ES/var-backtest content
  touch** (unchanged from the Wave-8/9 disposition).
- **LOW hygiene, disclosed, not defects:** the one demo-only `covariance_result` read
  (`demo/stage10_api1.py:217`) that disambiguates by exact-factor-set rather than the wave's uniform
  `run_type` filter (demo-only, provably disjoint from private sets — cannot leak Ω_pp); the
  `directAccessGrantsEnabled: true` ROPC on the public `irp-frontend` Keycloak client (pre-existing
  from SSO-1, README curl example — **flag if anything goes internet-facing**); the JWKS live-IdP
  integration test still offline-only; the stage9z presence-not-precision read proof.
- **Standing** (unchanged): OD-B expire-a-mapping; SC-2 the named pull-forward (expired unspent
  again); the FE-2 `@redocly` dev-tree advisory (dev-only, no action); the FE-3 `auditor_3l`
  demo-viewer (demo-scoped).

---

## Part 3 — The closure-stamp class recurred a SIXTH time — and the gate that was built to stop it was structurally blind

**The one HIGH (doc/process, not shipped code), independently confirmed and fixed at this close.**
PPF-3's own closeout (PR #105) swept `current_state.md` + `delivery_roadmap.md` but left the decision
record's Status cell at **"RATIFIED … Implementation follows"** — never bumped to CLOSED, still
carrying the baseline `22/37/104` and citing no impl PR/SHA/review. The other four Wave-10 records
were correctly stamped. This is the missing-closure-stamp class the Wave-9 close (OQ-W9C-5) ratified
CI teeth to end — recurring a sixth time.

**Worse: the teeth were structurally blind to it, on two independent counts** (both re-verified by
running `scripts/check_docs.py`, which *passed clean* while the miss stood):
1. **Too narrow a phrase** — `_DRAFT_MARK` matched only the literal `"DRAFT for ratification"`;
   PPF-3 sat at `"RATIFIED"`, a different pre-close stamp, and slipped.
2. **The arc-row shape excluded all three PPF slices from scope entirely** — the done-set detector
   keyed on the leading `✅ **DONE**` row shape, but the arc row marks each slice INLINE
   (`✅ **PPF-1**` / `✅ **PPF-2**` / `✅ **PPF-3**`), so `_is_unstamped_shipped` could never fire for
   any arc slice regardless of its Status text. A checklist without teeth, and teeth that couldn't
   reach the tooth-decay.

**Fixed at this close** (the at-close fold): `check_docs.py` broadened — (a) the miss now fires when
a DONE slice's Status cell is not stamped CLOSED (catching DRAFT / RATIFIED / pending — any pre-close
state), and (b) the done-set now also recognizes the arc-row inline `✅ **PPF-N**` marks. The
broadened gate, run against the tree, flagged **exactly two** records — PPF-3 (this wave) and **CC-2**
(a Wave-8 record *also* left at "RATIFIED", a genuine historical miss the narrow gate never caught) —
both now stamped CLOSED, with an added regression test proving the teeth fire on a RATIFIED-but-DONE
record and recognize the arc-row shape. The gate now passes clean *because the records are stamped*,
not because it is blind.

**The meta-lesson (OQ-W10C-5):** a mechanical gate only ends a recurring class if it is *tested
against the actual failure it was built to catch*. OQ-W9C-5's teeth were unit-tested against a
synthetic DRAFT row but never against the arc-row shape or the RATIFIED stamp — the two forms the
real recurrence took. Six-in-a-row says the human checklist will not hold; the fix is the broadened,
now-actually-tested gate.

---

## Part 4 — Outward benchmark + DESTINATION-REACHED check (rule 6b, wave scale)

**The §2.1 destination is genuinely SHIPPED as a defensible v1 — not a toy.** The unified number
`σ_unified = √(x'Σx + p'(Ω_pp/d_t)·p + residual_over_non-private-members)` exists as the 20th
governed number with its own binder, migration, snapshot predicate, reads, FE surface, and a live
two-fund demo. The single strongest evidence it is not a toy is the double-count catch: two
adversarial verifiers refuted the naive three-leg formula *before implementation* as a ~100% variance
double-count (PA-4's residual `σ_e²` is the WHOLE non-public residual, already inside Ω_pp), and the
team shipped a genuine **repartition** — each private-segment member's variance in exactly one leg,
coherence-tested both ways. The value the whole thesis pointed at — private books co-moving in their
pure-private risk, which independent-diagonal total-VaR structurally misses — **is the Ω_pp
off-diagonal, and it is real.**

**Three honest asterisks, ranked by how load-bearing they are:**
- **UNLEVERED (leverage = 1.0) — the one genuinely load-bearing gap.** MSCI factorizes leverage as
  an outer `×Leverage`; ILPA mandates levered-and-unlevered dual reporting. Private funds are levered,
  so an unlevered systematic VaR does not yet answer the risk manager's actual question. Labeled
  honestly, deferral defensible (leverage is a separable outer multiplier and the platform captures
  no leverage data) — but it is the seam a sophisticated user points at first, and closing it needs
  new captured data.
- **Parametric-only — a real asymmetry against the platform's own bar.** The unified number exists
  only in parametric form; the platform made HS-VaR + Acerbi-Tasche HS-ES + the ES-backtest
  first-class for the *public* side precisely because parametric tail risk is weak. Expected-v1, but
  a genuine gap.
- **Single-member-thin / block-diagonal / √-time i.i.d.** — correctly disclosed as thin/approximate;
  none is load-bearing for v1 correctness (block-diagonal is genuinely extra-justified; the
  asset-specific split only bites at ≥2 members/segment).

**One economic-honesty note:** the demo headline delta is *tiny* — σ_unified 85.758 vs σ_total 85.686,
≈0.08%. That is exactly what the math says (the off-diagonal of a 2×2 with two single-member,
low-correlation segments is small): the machinery is proven, but the destination demo proves the
*engine*, not yet a compelling *number*. A ≥2-member or higher-correlation book would produce a
bigger, still-honest delta.

**The frontier has crossed from methodology into operations.** Against the published state of the art
(MSCI PE/Private-Credit Factor Model, Barra, ILPA, FRTB, the desmoothing literature), the platform now
*implements the architecture MSCI describes* and its desmoothing suite sits at the literature
frontier; on governance / AI-legibility it is ahead of most vendor practice. What it lacks vs MSCI's
actual differentiators is exactly the disclosed v2 set — **led by leverage, the one remaining math
peak.** But the largest distance-to-frontier is no longer math: the platform computes 20 governed
numbers beautifully and reproducibly, yet **nothing runs on a cadence, nothing enforces a limit,
nothing carries a remediation to term.** A governed-risk *platform* is defined as much by cadence +
limits + breach-response as by the numbers it computes, and of that operational half the platform
ships zero. The thesis §2.3 "AI-ready = agent-consumable" clause actually points here — an agent's
value inside a risk platform is monitoring and acting on cadence and limits.

**Thesis status:** the §2.1 destination is declared shipped (v1). `REQ-SMR-001` (§2.1) remains coarse
"In-Progress" — defensible, since it spans the whole private-asset chain, and the leverage seam keeps
it honestly open. The user's standing note — real-data + demos come *after* the build — bears
directly on the Wave-11 fork (Part 6).

---

## Part 5 — Process findings

- **The pre-ratification verifier pass held its value a FIFTH wave — and, on the capstone, its
  highest-stakes catch yet.** Two verifiers refuted PPF-3's naive formula as a variance double-count
  *before implementation*, reshaping the design from an assembly into a repartition. Without it, the
  headline number would have shipped ~100% overstated on a single-member segment. The verifier tier
  earns its keep on genuinely-new math specifically.
- **The 4-finder review caught a real convergent HIGH on the capstone**: three independent finders
  found the consume-path double-count (the build-path repartition not re-enforced at the
  `snapshot_id` trust boundary). Independent convergence is a strong signal — and it generalizes the
  PPF-1 ("freeze the admission key at write time") and PPF-2 ("extend the isolation guard to every
  shared-table read") lessons into a third: **a fail-closed invariant spanning two adjudicated legs
  must be re-checked at BOTH the build and the consume boundary.**
- **Disclosure honesty is a distinct review axis from code correctness.** PPF-3's 4th finder caught
  an overstatement ("*exactly* the off-diagonal") that had survived a decision-record verifier pass
  and become a REGISTERED governed assumption — a governance defect, not a code defect. **Re-verify
  precision claims specifically at implementation time, not just at planning ratification.**
- **The closure-stamp class recurred a SIXTH consecutive close, past a gate built to stop it**
  (Part 3). The lesson is not "run the checklist" (six-in-a-row says that fails) but "test the
  mechanical gate against the actual failure forms" — now done.
- **A closeout must stamp its own decision record.** PPF-3's closeout swept the roadmap +
  current_state but skipped the record itself. The closeout checklist now has the CI teeth to enforce
  it (broadened this close).

---

## Part 6 — Open decisions (OQ-W10C-1…5) — the ratification gate

- **OQ-W10C-1 — Close verdict.** Ratify: Wave 10 shipped as ratified (API-1b → FE-3b → PPF-1 → PPF-2
  → PPF-3); the close audit (four cross-cutting auditors, every material finding independently
  re-verified) found **zero shipped-code defects — the sixth consecutive clean close on the code
  axis**; the §2.1 destination is genuinely shipped as a defensible v1. Gates green at HEAD
  (`make check` 1849 / full-PG ~2231 / `fe-check` / `gen-api-check` / `alembic`). The three at-close
  doc-hygiene folds (Part 3) are applied.
- **OQ-W10C-2 — Register dispositions.** Ratify Part 2: the scheduler / limits / MG-2 operational
  cluster carried as the highest-value forward work; the PPF-3 v2 seams (leverage-led) carried; the
  BT-3 D-F4 reword still deferred; the LOW hygiene items (the demo covariance read, the ROPC client,
  the offline JWKS test, stage9z presence-not-precision) carried as honestly-disclosed, not defects.
- **OQ-W10C-3 — The closure-stamp gate (the sixth-recurrence fix).** Ratify the at-close broadening:
  `check_docs.py` now fires on a DONE slice whose Status cell is not stamped CLOSED (any pre-close
  stamp) and recognizes the arc-row inline `✅ **PPF-N**` shape; PPF-3 and the historical CC-2 both
  stamped CLOSED; a regression test proves the teeth now fire on both forms. (This is the mechanical
  fix; the standing per-slice checklist and the pre-ratification verifier carry unchanged.)
- **OQ-W10C-4 — The Wave-11 sequence (a Tier-3 USER decision — the pivotal fork).** The
  destination-reached moment is exactly when to re-weigh priorities. Three genuinely distinct
  directions:
  - **(A, recommended) OPERATIONALIZE** — the first scheduler → a limits/breach workflow → the MG-2
    remediation lifecycle. *Why:* the platform's largest distance-to-frontier is no longer
    methodology; a governed engine that cannot run on a cadence or enforce a limit is an incomplete
    *product* regardless of how good its 20 numbers are. The scheduler is a four-close structural
    debt, a prerequisite for the rest, and introduces the first genuinely-new architectural primitive
    (background execution). §2.3's AI-readiness clause has its real unrealized value here.
  - **(B) DEEPEN THE NUMBER** — the PPF-3 v2 seams led by **leverage** (highest economic value), then
    global-factor linkage / HS-ES unified analogue. *Why:* the destination is v1 and its one
    load-bearing gap (unlevered) understates a levered private book's real risk; a sophisticated
    buyer's first question is "levered?". *Cost:* leverage needs new captured data (brushes the
    real-data-after-build note); the demo delta is already ~0.08%, so this polishes a number the
    platform cannot yet run on a cadence.
  - **(C) REAL DATA / vendor ingestion** — prove the machinery on non-synthetic private-fund data.
    Likely still premature by the user's own standing rule (real-data after the build), and Fork A is
    arguably still "build."
  **Recommendation: A (operationalize), optionally with a small leverage down-payment from B.** If
  the near-term goal is instead a *credible private-risk demo* rather than a running platform, B
  (finish the leverage/number) is the legitimate alternative — a genuine USER re-weighting, not a
  wrong answer.
- **OQ-W10C-5 — Process (the six-recurrence lesson).** Ratify the standing rule: a mechanical
  governance gate must be unit-tested against the ACTUAL failure forms it exists to catch (not just a
  synthetic happy-path), and a slice's closeout must stamp its own decision record CLOSED (now
  CI-enforced). No new per-slice discipline; the pre-ratification verifier, the 4-finder review, and
  rules 6/7 carry unchanged.

---

## Part 7 — Citation hygiene (carried for whoever plans Wave 11)

Wave 10's math slices (PPF-1/2/3) each cite the desmoothing / private-factor literature already
reproduced in PA-0/PA-1/DS-2 (Geltner 1993, Getmansky-Lo-Makarov 2004, Okunev-White 2003) plus the
MSCI PE/Private-Credit Factor Model decomposition (Shepard & Liu 2014; MSCI 2025) and ILPA
levered/unlevered norms — all cited, none needing fresh reproduction. The one live citation debt
remains the **BT-3 D-F4 registered-string reword** (Part 2), owned by a future ES/var-backtest touch.
For a Wave-11 **operationalize** slice (fork A), the relevant external practice is scheduling /
limit-monitoring / breach-workflow supervisory expectations (e.g. FRTB desk-limit monitoring, SR 11-7
ongoing monitoring, BCBS 239 risk-data-aggregation timeliness) — standards to cite at planning, not
paywalled research to reproduce. For a Wave-11 **leverage** slice (fork B), MSCI's relative-leverage
formulation + ILPA's levered/unlevered dual-reporting are the citations that will matter.
