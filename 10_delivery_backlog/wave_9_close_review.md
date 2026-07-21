# Wave-9 Close Review — the read-surface + front-end + identity wave

**Status: RATIFIED by the user 2026-07-21.** OQ-W9C-1/2/4/5 = "Approve all" (the zero-defect close
verdict; the register dispositions; the Python `pip-audit` CI gate landing in Wave 10 riding a slice;
the closure-discipline CI docs-check teeth). **OQ-W9C-3 = fork A "finish the surface first":** Wave 10
= **API-1b → FE-3b → a §2.1 private/public-unification headline** (Part 2.13). The mandatory
rolling-wave close (roadmap Part 4
rule 2) after Wave 9 shipped its ratified sequence **API-1 → FE-2 → SSO-1 → FE-3** (OQ-W8C-3). This
was the wave that made the platform's differentiator *legible*: a governed read surface (F1), the
governance story readable over GETs (F2), OpenAPI-generated FE types (F3), a real identity boundary
(F4), and the product UI that renders all of it. All four read-surface findings from the 2026-07-20
UI/read-surface assessment are now discharged.

**Method.** Four cross-cutting close auditors over the wave diff (`d47cf66..9d210e4`) — cross-slice
integration/composition, security + doctrine (a dedicated lens because this wave introduced the
platform's **first real authentication boundary**), doc/register/closure-stamp coherence, and a
completeness-critic + Wave-10-readiness/destination pass — on top of each slice's own shipped
4-finder review (every slice already reviewed with zero surviving HIGH). Opus-only, proportionate to
a four-slice wave whose slices were each already reviewed (not the 71-agent ultracode of the Wave-7
close; ultracode is opt-in and was off). **Every material finding was independently re-verified by
the synthesizer** (the frozen-file diff, the BR-10 secrets sweep, the API-1 stamp gap, FE-3's real
CI run number, and the absent Python audit gate were each re-run by hand — model confidence is not
evidence).

Counts at wave end, DB-consistent across the docs: **17 governed numbers / 20 registered model codes
/ 35 validation records / 101 COMPLETED demo runs** (API-1's stage 10 moved runs 96 → 101; FE-2 /
SSO-1 / FE-3 were count-neutral). No migration in any slice — head stays `0045`.

---

## Part 1 — Did Wave 9 ship what was ratified? — YES; the fifth consecutive zero-shipped-defect close

The Part-2.12 ratified sequence delivered in order, each with its own decision record + plan +
pre-ratification verifier pass + 4-finder review + closure stamps:

- **API-1** (slice 1) — the governed read surface + the F2 governance reads (PR #82 = `ae588a5`, CI
  #449; NO migration). Class-A entity/time reads (8 families) + Class-B latest-run resolvers
  (covariance / scenario / sensitivity) + 2 by-id parity GETs via the shared `calc/reads.py` helper;
  the four F2 governance reads (validation findings/evidence detail, `tier` on the inventory list, a
  snapshot listing, and the audit-trail read via a NEW read-only `audit/queries.py` — the FROZEN
  `audit/service.py` never imported, gated the ratified `lineage.view` reuse, metadata-only). Class-C
  (flagship VaR/active-risk-for-portfolio-P) DEFERRED to **API-1b** — the verifier *refuted* its
  read-only feasibility (subtree-scoped runs, no recorded root portfolio). Demo stage 10 paid the
  5-code demo-completeness rider (runs-only, 96 → 101).
- **FE-2** (slice 2) — OpenAPI-generated FE types (PR #84 = `2ce9e4a`, CI #456; NO migration). The
  precondition confirmed FIRST (every governed response decimal already serializes `string`);
  committed `openapi.json` + generated types + a NEW Python+Node "API type drift" CI job;
  `FAMILY_ROW_COLUMNS` bound to the generated `*RowOut` types — the FL-1 row-key drift kill, PROVEN.
  The review's own HIGH (a sampled 8-field decimal guard) was fixed with an EXHAUSTIVE guard.
- **SSO-1** (slice 3) — real identity / OIDC (PR #86 = `422c164`, CI #466; NO migration). The
  dev-placeholder header shim replaced by a real OAuth2 resource server (PyJWT/JWKS, RS256-only,
  iss/aud/exp/nbf + MFA, leeway 60s), fail-closed by default; `dev_header` survives local-only.
  Closes OD-048 (Keycloak local realm). Two HIGHs folded — the RLS false-deny from a non-canonical
  UUID tenant claim (canonicalize before the GUC bind; PG-tier regression), and the OpenAPI drift the
  new `authorization` header stamped.
- **FE-3** (slice 4, the last) — the product UI (PR #88 = `a0f31b5`, CI #475; NO migration). The
  generic run browser replaced by a six-step governance-narrative walk over `DEMO-GLOBAL`;
  `GovernedValue` makes provenance, a structurally-unfakeable verification mark, validation status,
  and disclosed limitations first-class on every number. ZERO HIGH; 2 MED + 6 LOW folded.

**The close audit (four auditors, wave diff `d47cf66..9d210e4`):**

- **Cross-slice integration — CLEAN (zero HIGH/MED/LOW).** All six composition seams verified: the
  OpenAPI → generated-types → FE-consumption pipeline is drift-free AND deterministic at HEAD
  (`make gen-api-check` regenerates the committed bytes exactly); the auth dispatch composes with the
  test/demo/local paths (the autouse conftest fixture pins `dev_header`, OIDC tests opt in, the oidc
  default fail-closes deployed envs only, `validate_auth_config` runs from the lifespan not at
  import); the demo stage sequence composes (stage9z is runs-only and collates last); the RLS
  tenant-GUC is fed a canonicalized value on every non-test path (the SSO-1 fix is the only new
  external-string→GUC path and it canonicalizes); the migration chain is untouched (single head
  `0045`, `alembic check` clean); and **the full gate is green at HEAD** — `make check` **1778
  passed / 365 skipped**, `make fe-check` **97 tests**, `make gen-api-check` clean.
- **Security / doctrine — CLEAN (zero findings).** All six hard invariants independently re-verified
  against the merged diff: `audit/service.py` byte-frozen (diff empty) and never imported by the new
  read path (metadata-only, `before_value`/`after_value`/`justification` not surfaced); no new
  BYPASSRLS/hybrid/SYSTEM_TENANT; no permission/role/audit-code mint outside R-07 (the FE-3
  `demo-auditor` reuses existing `*.view` codes and the existing `auditor_3l` role code — a seed row,
  not a mint); **BR-10 clean** — the Keycloak realm is a public PKCE client with no `clientSecret`,
  the docker-compose `admin/admin` is an env-overridable, profile-gated, explicitly-marked local-dev
  placeholder, config defaults no secret, and the RS256 test keys are generated at test time (no key
  file committed); the app DB role stays non-superuser/non-BYPASSRLS; and the auth boundary is
  fail-closed on all four sub-checks (startup config guard, `dev_header` local-only + per-request
  backstop, RS256-only allow-list, the canonicalization fix with its PG regression).
- **Completeness — the three existential contracts are PROVEN, not asserted.** The OIDC path is
  driven end-to-end through a live `TestClient` with locally-signed RS256 Bearer tokens (granted /
  no-header / non-Bearer / wrong-key / wrong-iss / wrong-aud / expired / uppercase-tenant /
  malformed-tenant-401-not-500 / unknown-subject / tenant-mismatch); FE-3's decimals-verbatim
  contract is proven on the rendered DOM (exact 20-decimal strings a `Number()` would collapse); the
  403 partial-entitlement degradation is proven at two tiers (the calm `role="note"`, and the
  governed numbers still rendering when `/models` 403s). No asserted-but-untested claim survived.

**At-close folds applied (doc/hygiene, this review):**

- **The API-1 decision record's Status line was still "DRAFT for ratification"** — its closeout (PR
  #83) updated the roadmap and current_state but never the record's own Status. Stamped **CLOSED (PR
  #82 / CI #449)** with its 4-finder review outcome (ZERO HIGH; the audit `_iso` naive-UTC MED + 2
  test-coverage MEDs + 1 LOW folded). *This is the fifth consecutive close at which the
  missing-closure-stamp class has recurred — see Part 5 and OQ-W9C-5.*
- **FE-3's CI-run cite was the long Actions run-id `#29852439513`**, out of format with the other
  three slices' short run numbers (#449 / #456 / #466). Normalized to **#475** (verified via the
  GitHub REST API: run id 29852439513 = run_number 475, head_sha `a0f31b5`, success — monotonic with
  the prior three) across the roadmap row, the amendment log, the current_state banner, and the FE-3
  record; the long id kept once in the roadmap row for traceability.

---

## Part 2 — The deferral register, reconciled

**Fixed at this close** (Part 1): the API-1 DRAFT→CLOSED stamp; the FE-3 CI-cite normalization.

**Carried, with disposition:**

- **B1 — no Python dependency-audit CI gate (the headline forward item).** Wave 9 shipped the
  platform's first Python **runtime** deps carrying a known-advisory surface (`pyjwt==2.13.0`,
  `cryptography==49.0.0` pinned in `requirements-dev.txt`; loose runtime ranges `>=2.9` / `>=43` in
  `apps/backend/pyproject.toml`). CI gates the JS supply chain (`npm audit --omit=dev
  --audit-level=moderate`) but has **no** pip-audit / safety / osv equivalent — verified by grep over
  `.github/workflows/`, `Makefile`, `scripts/`. Nothing would catch a future CVE in
  pyjwt/cryptography/fastapi/uvicorn/sqlalchemy — an asymmetry made pointed by the fact that Python is
  now the identity-verification surface. **Disposition: the strongest Wave-10 hygiene candidate; ride
  a pip-audit step into a Wave-10 slice's CI diff (small; not a standalone slot). See OQ-W9C-4.**
- **BT-3 D-F4 residual (the registered-limitation reword)** — the `risk.var_backtest` v1
  `VAR_BACKTEST_LIMITATIONS` strings still call Christoffersen "a named BT-3 candidate"
  (`risk/bootstrap.py:1413`, `:1434`) though it shipped as v2. **DEFERRED to a dedicated ES/var-backtest
  content touch** (OQ-W8C-2) — a content edit on immutable registered-limitation rows with the
  finding-key stage tests re-run, not a hygiene sweep. Unchanged from the Wave-8 disposition.
- **FE-2 `@redocly` dev-tree advisory** — re-confirmed dev-only: `npm audit --omit=dev
  --audit-level=moderate` returns **0 vulnerabilities**; the HIGH advisories are codegen-time-only,
  never shipped, disclosed at `fe_2_decision_record.md`. **No action.**
- **FE-3 `auditor_3l` demo-viewer read-gap** — confirmed demo-scoped: the `Role(code="auditor_3l")`
  row is created only in `demo/campaign.py`; `entitlement/bootstrap.py` mints no roles.
  **Disposition: a Wave-10 *consideration* only** — promote to a real onboarding template if/when a
  second read-only role is genuinely needed. Not now.
- **Two LOW completeness residuals** (close register, both honestly-disclosed, neither a defect): the
  IdP discovery/JWKS network round-trip is unit-tested offline but never integration-tested against a
  live IdP (the Keycloak realm is documented, not CI-required — FE-3b/RTM-P9 territory); and the
  stage9z read proof asserts *presence* (rows returned, non-empty resolvers) rather than
  *filter-precision* against a different book (very likely covered by the per-family endpoint tests;
  noted as the one presence-not-precision spot).
- **Standing** (unchanged): MG-2 remediation-lifecycle trigger (erosion; earliest real overdue
  2027-07-19); the first scheduler; OD-B expire-a-mapping; SC-2 the named pull-forward (expired
  unspent).

---

## Part 3 — The demo-completeness gap — CLOSED

**OQ-W7C-5 is finally paid.** The 5-code rider — `risk.sensitivity.analytic`,
`risk.active_risk.parametric`, `risk.scenario.factor_shock`, `perf.benchmark_relative`, and the
proxy-mode `risk.factor_exposure.proxy` — had zero living-tenant runs for two waves; API-1's demo
stage 10 (RUNS-ONLY) now exercises all five, moving runs 96 → 101, and a PG test
(`test_demo_stage9z_api1_reads_pg.py`) proves the five COMPLETED and the new resolvers non-empty. The
read surface is now a *demonstrable* one — every family API-1 exposes renders with real rows, which
is the precondition that made FE-3's walk possible. The one residual (presence-not-precision) is in
Part 2.

---

## Part 4 — Outward benchmark + destination check (rule 6b, wave scale)

**Frontier.** Wave 9 made the differentiator *legible*. Every governance artifact API-1 exposed
(validation findings/evidence, the audit trail, snapshot listing, model tier) is now machine-readable
over governed GETs, and FE-3 renders provenance + verification + validation + limitations first-class
on every number — the thesis §2.3 "AI-ready = agent-consumable + verifiable / no side doors" clause
moved from aspiration to shipped, for a screen AND an agent. Against a best-in-breed governed-risk
platform, the math frontier is genuinely advanced (17 governed numbers incl. Acerbi-Tasche HS-ES, the
Acerbi-Szekely ES-backtest, Christoffersen, Takahashi-Alexander pacing); the gap is not more math.

**Two named legibility holes remain, both scoped:** (1) the single most-wanted read — "latest
VaR/active-risk for portfolio P" — still 404s for both a screen and an agent (**API-1b**, one
additive `calculation_run.scope_portfolio_id` column + a bounded binder touch; the deferral was a
verifier *refutation*, not a punt); (2) no browser can actually *log in* — the identity is real
server-side but unreachable client-side, the demo rides `dev_header` (**FE-3b**, the SPA OIDC
auth-code + PKCE flow).

**Thesis (`01_product_strategy/differentiation_thesis.md`).** With the read surface + identity + UI
now built, the ranked destination gaps are: **(1)** productionize the surface just built (API-1b +
FE-3b — these *finish* Wave 9's own thesis rather than open a new front); **(2)** the §2.1
private/public **unification** — the strategic endgame the whole math roadmap declared itself the
substrate for (proxy-mapping + Geltner desmoothing are built; the unified public+private
portfolio-level risk number is not yet assembled); **(3)** operational/governance depth carried three
closes (MG-2, the scheduler, a limits/breach workflow). The user's standing note — real-data use +
demos come *after* the build — keeps (2) a build-first slice, not a data-ingestion project.

---

## Part 5 — Process findings

- **The pre-ratification verifier pass held its value a fourth wave.** API-1's Class-C refutation
  (the flagship VaR read is not read-only-resolvable) reshaped the slice's scope *before*
  implementation, not at review — the same pattern as CC-1/CC-2's structural HIGHs in Wave 8.
- **The 4-finder review caught real HIGHs slice-by-slice**: FE-2's sampled-guard HIGH (a narrow
  decimal guard is false security), SSO-1's two HIGHs (the RLS false-deny + the OpenAPI drift). The
  tier earns its keep on security-critical slices specifically.
- **The auth boundary — the wave's highest-risk change — shipped with zero doctrine or secrets
  findings under independent re-verification.** The BR-10 sweep on the new Keycloak realm / config /
  compose (the one place a real secret could have hidden) came back clean. Evidence the
  verifier + 4-finder + close-audit discipline scales to an authentication surface.
- **The missing-closure-stamp class recurred a FIFTH consecutive close** (API-1's record left at
  "DRAFT for ratification"). The standing checklist (grep-for-"pending"/"candidate", OQ-W8C-6) names
  the check but is not being *run* at closeout — a checklist without teeth. **Proposed teeth
  (OQ-W9C-5): a CI docs-check grep that fails when a decision record for a merged slice still
  contains "DRAFT for ratification" / "pending ratification".** A mechanical gate is the only thing
  that has ever stopped a recurring stamp class on this project.
- **New lesson (FE-3):** the `format:check` (Prettier) CI gate is exact-match — a review-fold commit
  that re-wraps JSX / object literals needs a Prettier re-run before push, or CI goes red on a
  pure-formatting diff. FE-3's pre-merge CI red was exactly this; the fix was a zero-semantic reflow.

---

## Part 6 — Open decisions (OQ-W9C-1…5) — the ratification gate

- **OQ-W9C-1 — Close verdict.** Ratify: Wave 9 shipped as ratified (API-1 → FE-2 → SSO-1 → FE-3); the
  close audit (four cross-cutting auditors, every material finding re-verified) found **zero
  shipped-code defects — the fifth consecutive clean close**; all four read-surface findings
  (F1–F4) are discharged; the two at-close doc-hygiene folds (Part 1) are applied. Gates green at
  HEAD (`make check` 1778 / `make fe-check` 97 / `make gen-api-check` clean).
- **OQ-W9C-2 — Register dispositions.** Ratify Part 2: the BT-3 D-F4 reword DEFERRED (unchanged); the
  `@redocly` dev-tree advisory disclosed, no action; the `auditor_3l` viewer confirmed demo-scoped, a
  Wave-10 consideration only; the two LOW completeness residuals carried as honestly-disclosed, not
  defects.
- **OQ-W9C-3 — Wave 10 sequence (a Tier-3 USER decision).** The genuine fork. **(A, recommended)
  Finish the surface first:** API-1b (the flagship VaR/active-risk entity read + the one scope
  column) → FE-3b (the SPA OIDC/PKCE browser login) → then a §2.1 private/public-unification slice as
  the headline. **(B) Pivot to the differentiator:** lead with the §2.1 unification headline and let
  API-1b + FE-3b ride behind. Recommendation is **A** — a half-reachable product (no browser login,
  no flagship read) undercuts exactly the §2.3 legibility win Wave 9 just paid for; A finishes the
  thesis this wave opened before opening the next. B is defensible if the appetite is to push the
  strategic destination now.
- **OQ-W9C-4 — The Python dependency-audit gate (B1).** Ratify that a `pip-audit` (or equivalent) CI
  step lands in Wave 10, **riding a slice's CI diff** rather than consuming a standalone slot — it
  must land given pyjwt/cryptography are now runtime deps and the JS/Python audit asymmetry is a real
  supply-chain hole. (Alternative: a standalone hygiene micro-slice, or continue deferring —
  recommended: ride it in.)
- **OQ-W9C-5 — Closure discipline (teeth for the fifth-time stamp miss).** Ratify adding a mechanical
  CI docs-check that fails when a merged slice's decision record still reads "DRAFT for ratification"
  / "pending ratification", so the closure-stamp class cannot recur a sixth time; the standing
  per-slice checklist, the pre-ratification verifier pass, and rule 7 all carry unchanged.

---

## Part 7 — Citation hygiene (carried for whoever plans Wave 10)

Wave 9 was a read-surface + FE + identity wave — light on external-methodology citation. SSO-1's
OIDC/OAuth2 implementation follows public standards (RFC 7519 JWT, RFC 8414 discovery, RFC 7517 JWKS,
RFC 7518 RS256, OpenID Connect Core) — standards, not paywalled research; the record cites them and
they need no reproduction. The one live citation debt remains the **BT-3 D-F4 registered-string
reword** (Part 2), owned by a future ES/var-backtest touch. No new paywalled-source reproductions are
pending. For a Wave-10 §2.1 unification slice, the citation that will matter is the desmoothing/proxy
literature already reproduced in PA-0/PA-1/DS-2 (Geltner 1993, Getmansky-Lo-Makarov 2004,
Okunev-White) — the substrate is cited; the unification math is the new work.
