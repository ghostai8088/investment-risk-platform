# investment-risk-platform — Claude entry pointer

Full-scope enterprise investment-risk platform (multi-tenant, auditable, reproducible, governed — NOT an MVP).
This file is the auto-loaded pointer; the discipline lives in the documents below. **Read them before acting.**

## Read in this order
1. `docs/project_memory/claude_operating_instructions.md` — the cadence, review pattern, verification &
   objectivity standing rules, commit discipline, engineering conventions, prohibited behavior.
2. `docs/project_memory/current_state.md` — the entry-point snapshot (re-verify HEAD/CI at session start).
3. `10_delivery_backlog/delivery_roadmap.md` — the operative rolling-wave slice sequence (the next slice comes
   from here by default; re-sequencing follows its Part 4 rules) — plus the latest decision record it points at.
   *(`phase_status.md` and `next_actions.md` were RETIRED to pointer stubs at the Wave-6 close, OQ-W6C-4.)*

## Hard invariants (non-negotiable)
- **Delivery autonomy (granted 2026-07-12; EXTENDED 2026-07-14): Claude self-drives the full
  plan → implement → review → commit → push → PR → merge cycle WITHOUT per-step approval.** The 2026-07-14
  extension ("I will defer to you on when to create pull requests and merge") makes PR creation and merging
  to `main` Claude's call too — via the GitHub REST API with the keychain-cached credential; branch
  protection's required status checks stay on, and the adversarial review + `make check` + full-PG +
  CI-to-green gates are the merge preconditions that replaced the human merge gate (never merge before they
  all pass). *(Operational note, REPLACED 2026-08-01 — the Wave-6 workaround is RETIRED, with executed
  evidence: PRs #156 and #157 were created, check-watched and merged autonomously via the `gh` CLI.
  The mechanics: `gh` at `~/.local/bin/gh`, authenticated via the device flow; the allowlist in the
  checked-in `.claude/settings.json` (which the classifier correctly refused to let Claude write
  for itself — the user created it); branch protection + required status checks UNCHANGED as the
  machine merge gate. Auto-merge is not enabled repo-side, so the pattern is `gh pr create` →
  `gh pr checks --watch` → `gh pr merge --merge`; a PR landing invalidates sibling PRs' contexts
  (update the branch and re-watch). The 2026-07-16 root cause, found only at retirement: every
  earlier auth attempt SUCCEEDED at GitHub and then failed writing the token into a root-owned
  `~/.config` from 2021.)* Still surface genuine decisions (Tier-3 methodology/model/grain/entity sign-offs, design forks,
  scope/ambiguity) and anything hard-to-reverse or outward-facing beyond the repo itself. The next slice
  comes from the roadmap sequence by default.
- **`packages/shared-python/src/irp_shared/audit/service.py` is FROZEN** — never modify it.
- **No BYPASSRLS app path; no hybrid/SYSTEM_TENANT behavior** beyond the closed **7-table** hybrid set (five at
  AD-013-R1, extended to seven by **AD-013-R2** at REF-1 2026-07-29 — user-ratified; the declaration is
  `reference.models.HYBRID_TABLES`, and each migration polices only the tables it created) **plus the
  three-part ONBOARD-1 clause (user-ratified 2026-08-09, OQ-ONB-2A):** (i) the `tenant.create`-guarded
  cross-tenant onboarding transaction, (ii) ONE standing authenticatable SYSTEM-tenant principal (the
  platform operator — refused on every router except provisioning, census-pinned), and (iii) the SYSTEM
  tenant's row in the ENT-074 registry. The hybrid TABLE set is unchanged at seven; proprietary
  data = symmetric FORCE RLS.
- **No new audit code, permission, or role** outside the governed R-07 mint; no secrets in source (BR-10).
- **A G2 amendment is TWO commits, in this order** (P20): the commit carrying the rewritten acceptance text
  lands FIRST, then the ledger entry whose `hash` is computed from the POST-amendment cells — via the gate's own
  `parse_rows`, against the committed blob, never the working tree. Adjudicating text that no longer exists is
  not an adjudication: the 2026-08-15 batch hashed pre-amendment cells and left **ten rows LAPSED on `main`**
  until 2026-08-20, and `make check` runs `g2-check`, so a lapsed row in a declared slice scope blocks the wave.
- **Verification gates are never waived** (`make check`, full-PG validation, CI-watch-to-green, reproduction
  tests) — model confidence is not evidence; see the standing rules in `claude_operating_instructions.md`.
- **A DIFFERENT ENGINE verifies every planning gate and every ratification diff** (P15's shared-assumption rule,
  made standing 2026-08-20). Fleet size is not independence: 15 same-engine agents produced a Wave-19 plan whose
  direction rationale was FALSE at its own citation, and a different engine found that plus 61 more (5 BLOCKING)
  in one pass; the ratification commit then yielded 39 more (3 BLOCKING), **all three in control rows that same
  commit had just minted**. Control rows assert their own proof — review them hardest. And re-measure the
  verifier: one of its counts was wrong, and my correction of it was wrong too.
- Governed derived numbers bind `dataset_snapshot` + `calculation_run` + a registered `model_version` (where a
  model applies) and are IA append-only; captured inputs bind none of those. Pick the pattern correctly.

## Environment quick facts
- The git repo is THIS directory (on this machine it sits nested under
  `~/Projects/investment_risk_platform/`); branch `main`; **origin is HTTPS** (flipped from SSH
  2026-07-09 — SSH port 22 is BLOCKED on this network; plain `git push` works via the keychain PAT).
- **`gh` IS installed, at `~/.local/bin/gh`** (not on `PATH` — invoke it by full path), authenticated via the
  device flow. *This line read "`gh` is NOT installed" until 2026-08-20, contradicting the autonomy note above
  it in this same file since 2026-08-01. Executed evidence: PRs #231 and #232 were created, check-watched and
  merged with it.* The REST API is still the right tool for **per-conclusion CI verification** — `gh pr checks
  --watch` can exit 0 for a head whose runs have not registered, so verify with
  `gh api repos/OWNER/REPO/commits/<sha>/check-runs` and quote every conclusion. Merge via
  `gh api -X PUT .../pulls/N/merge` when the GraphQL path is unavailable.
- Local PG validation uses the single reused container `irp_pg_local` (`postgres:16`); see the standing rule in
  the operating instructions. Reset the schema between full pytest runs against the same DB.
