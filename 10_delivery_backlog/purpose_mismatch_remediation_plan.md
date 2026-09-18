# Purpose-mismatch remediation plan — 2026-09-18

**Status: RATIFIED 2026-09-18 by the owner** ("proceed ultracode", after the brief that closed with the two
recommendations below: keep the ratified CRO-1 order and take the design preview instead of a split; try the local
deploy fix before a CI-built image path). Drafted by Claude (Fable 5.1) the day after BOOK-1a merged, at the
owner's request: "Come up with a plan to remediate the application purpose mismatch that was identified
during the demo." It builds on the ratified re-baseline (`02_requirements/product_rebaseline_2026-09-17.md`)
and reopens none of its nine decisions. It exists because a status check on 2026-09-18 showed the
re-baseline is a ratified plan with one of seven slices built, and four things it depends on have no owner,
no date and no slice.

## 1. The mismatch, in one paragraph

The platform was built to satisfy a requirements register. Every gate asked "did we build it correctly" or
"does the register cover the taxonomy". Nobody asked "can the CRO use it". The result on 2026-09-17: a
deployed product whose front door is a governance story, whose nav is seven operations screens and a run
ledger, whose book is three hand-seeded positions, and which shows no total risk, no exposure breakdown,
no utilisation and no chart, while 20 governed calculation families sit behind it fully built. The owner's
words: "This is not something a CRO or PM would recognize."

## 2. What is already decided and done

Ratified 2026-09-17 (DP-RB2-1..9): partial restart; G5 (a human walks each journey line on the deployed
stack and names the decision); twelve journey lines J-CRO-1..8, J-PM-1..4; a three-fund demo tenant;
Wave 20 = BOOK-1a → BOOK-1b → CRO-1 → UTIL-1 → PM-1 → DRILL-1 → SHOW-1; S1 parked; owner walks every
line plus one outside walk before SHOW-1 closes.

Built: the G5 gate (script, empty ledger, CI step); BOOK-1a (PR #244): three funds, 55 instruments,
597 runs, seedable by `deploy.sh --with-demo`.

Not built: everything a CRO would see. Zero journey lines walked. The deployed stack runs images from
late August with the Northlight tenant seeded in by hand.

## 3. Gaps the current execution leaves open

| # | Gap | Why it matters |
|---|---|---|
| G-1 | **The deployed stack cannot be rebuilt on this machine.** Docker Desktop cannot pull `python:3.12-slim`, `node:24-slim`, `nginx:1.27-alpine` (proxy); the daemon was not running on 2026-09-18. | G5 requires the DEPLOYED stack. If images cannot be rebuilt, CRO-1 cannot be walked and cannot merge. Nothing on the roadmap owns this. |
| G-2 | **The owner sees no change until CRO-1 exits**, two slices away. | The complaint was about what the owner sees. Two more slices of silence repeats the pattern that produced the drift: build, then show. |
| G-3 | **The outward benchmark section (4.7)** is due before CRO-1's planning gate and is unscheduled. | Without it the J-CRO lines rest on one person's judgement; the differentiation thesis requires the outside check. |
| G-4 | **One walker.** The roster is the owner alone; the outside walker (DP-RB2-9) has no name and no date. | Walks become the bottleneck of every slice from CRO-1 on; the sole walker shares the builder's context. |
| G-5 | **The old campaign tenant** (DEMO-GLOBAL, three positions) still sits in the deployed database beside Northlight. | Harmless under RLS, but a fresh `deploy.sh` verification asserts an empty tenant registry, so the only clean state is a fresh deploy plus `--with-demo`, which is G-1. |
| G-6 | **Engine limits the screens must disclose** (found by BOOK-1a): scenario engine single-portfolio and currency-only; tracking error currency-only; `exposure/latest/sum` leaf-only. | J-CRO-2 and J-CRO-6 will show numbers that are correct and narrower than a CRO expects. Undisclosed, they look wrong; disclosed, they are honest. |

## 4. The plan

Each phase has an exit that a person can check. Phases 0 and 1 run in parallel.

### Phase 0 — make the yardstick operable (owner: Claude; close restated 2026-09-18 at the ratification-diff fold, GOV-R-05 and CC-9: 0a and 0b close before CRO-1's planning gate; 0c, the CRO-1 walk slot, and 0d close by CRO-1's exit; the outside walker by PM-1's gate)

- **0a DEPLOY-PATH (G-1, G-5) — DONE 2026-09-18.** Docker had not been running; once started, the three base images pulled first try and `deploy.sh --with-demo` printed `DEPLOY VERIFIED`, then `DEMO SEEDED` (597 runs, 86.7 s, `DEPLOY_EXIT=0`) on a fresh volume. The stack was built from branch `w20-remediation-plan` at `d1c9161`, which is docs-only over `main` `e17b904` (the head at the time; `git diff --stat e17b904 d1c9161` touches three `.md` files and no code), so the image code is `main`'s at that head (CC-11; G5 needs a `deployed_head` per walk row). The registry holds `northlight` and `system` only. As `northlight-cro` over HTTP: `var_value 1734274.488757` (the BOOK-1a golden); unknown tenant 401; frontend 200. One carry for CRO-1: a non-UUID `X-User-Id` in dev-header mode returns 500, not 401 (moot after SHOW-1). Original text: Prove a full rebuild and fresh deploy on this machine:
  start the daemon; if the three base images are in the local cache, `deploy.sh --with-demo` needs no pull;
  if not, fix the registry path (proxy or mirror) or build the images in CI's `stack-proof` job and load
  them locally. Exit: `DEPLOY VERIFIED` printed by `deploy.sh --with-demo` on a fresh database, Northlight
  present, DEMO-GLOBAL absent, `northlight-cro` signs in. This is a hygiene insertion under roadmap Part 4
  rule 3; it ratifies before it starts but it is not a calculation slice.
- **0b OUTWARD BENCHMARK (G-3) — DONE 2026-09-18 (section written and lane-checked); carried: cited from the CRO-1 planning record at its gate** (`02_requirements/outward_benchmark_cro_overview_2026-09-18.md`, seven sources, 41 of 41 quotes verified verbatim by two Opus citation-lane passes — the second pass covered five of the seven quotes added at the first fold and supplied the 41st; the two from MSCI and BlackRock were checked at the round-2 fold against a fresh fetch (VF1-01); the exit's second half, "lands in the CRO-1 planning record", is the carried step, GOV-R-08, CC-8, CITE-4). Original text: Write the 4.7 section: at least two public vendor or regulatory sources
  on what a CRO risk overview shows, quoted verbatim with locators, read by a citation lane that sees only
  the sources. Exit: the section lands in the CRO-1 planning record and the citation lane passes.
- **0c WALK CALENDAR (G-4) — OPEN, asked 2026-09-18; the CRO-1 walk slot is due by CRO-1's exit, the outside walker by PM-1's gate (the original text below).** Added the same day, **0d:** a `record-walk` command that fills the seven mechanical ledger fields (line id, sha256 hash, persona, roster name, deployed head, route, date) and takes the walker's four (verdict, decision, driving value, reasoning), landing with CRO-1 before its first walk; today nothing fills them and nobody should type a sha256 by hand. Original text: The owner names a walk slot per slice exit (CRO-1, UTIL-1, PM-1, DRILL-1,
  SHOW-1) and names the outside walker (a practising risk or portfolio manager who did not build the
  product) before PM-1's gate, or records the recurrence acceptance DP-RB2-9 allows. Exit: dates and a
  name in the roadmap Part 2.22.

### Phase 1 — BOOK-1b, the private sleeves and the limits (next slice, as sequenced)

Unchanged from the roadmap row. Two additions to its remit: the line-to-data map below, so the slice
knows which journey lines it unblocks, and a stated disposition for the old campaign tenant (stays in the
test battery; absent from any deployed database after Phase 0a).

| Journey line | Needs from BOOK-1b |
|---|---|
| J-CRO-1 funds ranked by headroom | limits in force, two breaches, one utilisation between 0 and threshold |
| J-CRO-5 private sleeve, reported vs desmoothed | appraisal history, desmooth/regression/promotion chain, commitments and pacing |
| J-CRO-7 VaR trend over the last quarter | daily boundaries, one shared covariance and one VaR run per fund per daily date (the remit's Part 2.8 census). The line's rolling-DRAWDOWN half is served by no run family as a series: ROLLING_RISK v2 gives one 12-month maximum-drawdown point per fund over BOOK-1a's year; a CRO-1 gate decision (remit Part 2.11, Part 6 out (11); GOV-R-07) |
| J-CRO-2, 4, 6; J-CRO-8 | nothing; BOOK-1a already serves them |

### Phase 2 — CRO-1, the first screen a CRO sees

- **Before the planning gate, a design preview (new, addresses G-2).** A static HTML mock of the CRO
  overview over real Northlight numbers, reviewed with the owner in one sitting. The last product-UI
  decision (FE-3, 2026-07-21) was a choice between two engineering options; this time the persona-shaped
  screen is shown before a line of React is written. Exit: the owner marks each region keep / change / cut.
- The slice as ratified: restarted shell, tokens, fund selector, J-CRO-1, 2, 4, 5, 6, 7 over Part-3 reads,
  three additive reads (exposure by dimension, portfolio-scoped scenario, one-call summary). J-CRO-3 shows
  state words. The component-library call (Part 8) is decided at this gate; recommendation stays no.
- G-6 disclosures are on the screen, not in a footnote: tracking error labelled currency-only; the
  scenario panel names the account it ran on.
- Exit: six WALKABLE ledger rows by the owner on the Phase-0a deploy path.

### Phase 3 — UTIL-1, PM-1, DRILL-1 (as sequenced)

UTIL-1 turns J-CRO-3 and J-PM-2 from state words into numbers (ENT-032, the one migration of the wave).
PM-1 walks J-PM-1..4. DRILL-1 walks J-CRO-8 on the additive measure only. Each exits on its ledger rows.
DRILL-1 is the only cuttable slice.

### Phase 4 — SHOW-1 and the Wave-20 close: the remediation's own exit

SHOW-1 as ratified (deployed OIDC posture), then the re-walk of all twelve lines over real identity by
the owner **and** the outside walker. The Wave-20 close review carries the G5 coverage table.

**The remediation is done when:** on a stack built by `deploy.sh --with-demo` from `main`, a person who
did not build the product signs in as the CRO and every J-CRO and J-PM line that Wave 20 declared has a
WALKABLE row from them, with a decision and a driving value. Not when the register says so. Not when
`make check` is green.

## 5. One sequencing question for the owner (Tier 3)

**Should CRO-1 be split so a screen appears one slice earlier?** CRO-1a over BOOK-1a's data (J-CRO-2, 4,
6: headline row, composition, scenario) before BOOK-1b; CRO-1b (J-CRO-1, 5, 7) after.

Recommendation: **no, keep the ratified order**, and take the Phase-2 design preview instead. Reasons:
the ranking screen (J-CRO-1) is the front door and it cannot be designed without limits in the book; a
split costs two planning gates and two walk sessions for three lines; and BOOK-1b is a data slice with no
front end to wait on. The preview gives the owner the shape of the screen before BOOK-1b closes, which is
the part of G-2 that matters.

## 6. Risks that stay open after this plan

- The decomposition engine (Wave 21) is the VaR drill and the contribution view a CRO will ask for on
  the first walk. It is sequenced, not built; J-CRO-8 says so by design.
- Fund-level scenario across accounts and a multi-factor active-risk model are Wave-21 candidates; until
  then two Northlight funds show no scenario P&L and the euro fund shows tracking error of zero.
- If Phase 0a fails on this machine, the honest fallback is a deploy target elsewhere (a small VM or
  CI-hosted stack). That is an outward-facing change and would come back as its own decision.

## 7. What this plan changes in the records (DONE 2026-09-18, this commit)

Roadmap Part 2.22: a Phase-0 row (0a, 0b, 0c) ahead of BOOK-1b with a dated rationale in Part 5; the
BOOK-1b row gains the line-to-data map; the CRO-1 row gains the design preview as a planning-gate input.
No requirement row, no acceptance text, no G2 hash moves. `current_state.md` gains a re-baseline
scorecard block so "ratified" is never again read as "done".
