import js from "@eslint/js";
import tseslint from "typescript-eslint";

// Both import fences live in ONE `no-restricted-imports` rule, because ESLint flat config REPLACES
// a rule's options when a later config object names the same rule — two blocks each declaring
// `no-restricted-imports` over overlapping files would silently disable whichever came first. The
// per-file differences are expressed by re-declaring the rule with a different pattern set below,
// never by adding a second block that happens to overlap.
const WRITE_FENCE = {
  group: ["**/client", "./client", "../client", "./**/client", "../**/client"],
  importNames: ["request"],
  message:
    "Import `request` only in src/api/writes.ts — the single audited write surface. Use `apiGet` for reads.",
};

// FE-M1 (OQ-FE-M1-4=D), fence 1 of 3 — the router package cannot come back.
//
// `react-router-dom` was REMOVED upstream at v8; every symbol this app uses now resolves at the root
// `react-router` entry. The reintroduction risk is not hypothetical: `npm audit` on the
// pre-migration tree reported `fixAvailable: { name: "react-router-dom", version: "7.11.0" }` — the
// tooling's own advice is the very downgrade OPS-1's OQ-1=C was REFUTED IN BUILD for (7.11.x
// re-exposes six advisories including a High DoS and two reachable open-redirects). A contributor
// following that advice would silently undo this slice.
const ROUTER_FENCE = {
  group: ["react-router-dom", "react-router-dom/*"],
  message:
    "react-router-dom was removed upstream at v8 (FE-M1) — import from `react-router`. " +
    "Reinstalling it re-opens GHSA-qwww-vcr4-c8h2 and, at 7.11.x, five more.",
};

export default tseslint.config(
  { ignores: ["dist", "node_modules", "src/api/generated"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    // OPS-1 (OQ-2=A), review fold M-4 — ENFORCE the write fence rather than asserting it in a
    // comment. `client.ts` exports the shared `request()` core so identity injection has exactly
    // ONE implementation; but the governance value of OQ-2=A ("the entire write capability in one
    // auditable file") only holds if nothing else can reach that core and issue a POST. Reads use
    // `apiGet`. The single exemption is the write module itself, below.
    //
    // Wave-12 close fold: a literal `paths` enumeration covered only depths 2-3, so the natural
    // src-root form (`./api/client`) and any depth-4+ form passed the fence clean. `patterns`
    // matches EVERY relative spelling that resolves to the client module (there are no tsconfig/
    // vite aliases, so relative specifiers are the only route). The glob set is pinned by
    // write-fence.test.ts against the actual bypass forms.
    //
    // FE-M1 widened the file glob from `src/**` to `**/*`: the three root-level guard tests
    // (write-fence, api-prefixes, openapi-contract, audit-gate) were outside every fence, and the
    // router ban in particular must not have a directory-shaped hole.
    files: ["**/*.ts", "**/*.tsx"],
    rules: {
      "no-restricted-imports": ["error", { patterns: [WRITE_FENCE, ROUTER_FENCE] }],
    },
  },
  {
    // The one file permitted to build on the shared core.
    //
    // FE-M1 verifier finding V-3: this exemption used to be `"no-restricted-imports": "off"`, which
    // switched off the WHOLE rule for this file. That was correct while the rule carried only the
    // write fence; the moment a second, unrelated fence joined it, `off` would have handed
    // `writes.ts` a free pass on the router ban too. The exemption is now expressed as
    // "re-declare the rule WITHOUT the write fence" so it stays scoped to the thing it exempts.
    files: ["src/api/writes.ts"],
    rules: {
      "no-restricted-imports": ["error", { patterns: [ROUTER_FENCE] }],
    },
  },
);
