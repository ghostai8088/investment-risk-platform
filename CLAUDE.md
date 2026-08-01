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
  `reference.models.HYBRID_TABLES`, and each migration polices only the tables it created); proprietary
  data = symmetric FORCE RLS.
- **No new audit code, permission, or role** outside the governed R-07 mint; no secrets in source (BR-10).
- **Verification gates are never waived** (`make check`, full-PG validation, CI-watch-to-green, reproduction
  tests) — model confidence is not evidence; see the standing rules in `claude_operating_instructions.md`.
- Governed derived numbers bind `dataset_snapshot` + `calculation_run` + a registered `model_version` (where a
  model applies) and are IA append-only; captured inputs bind none of those. Pick the pattern correctly.

## Environment quick facts
- The git repo is THIS directory (on this machine it sits nested under
  `~/Projects/investment_risk_platform/`); branch `main`; **origin is HTTPS** (flipped from SSH
  2026-07-09 — SSH port 22 is BLOCKED on this network; plain `git push` works via the keychain PAT).
- `gh` is NOT installed — query CI via the public GitHub REST API.
- Local PG validation uses the single reused container `irp_pg_local` (`postgres:16`); see the standing rule in
  the operating instructions. Reset the schema between full pytest runs against the same DB.
