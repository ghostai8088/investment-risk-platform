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

// Wave-13 close fold — the SYNTAX axis, this fence class's THIRD un-enumerated bypass.
//
// `no-restricted-imports` is a STATIC-import rule: eslint's implementation registers visitors for
// `ImportDeclaration` / `ExportNamedDeclaration` / `ExportAllDeclaration` / `TSImportEqualsDeclaration`
// and NOTHING else (node_modules/eslint/lib/rules/no-restricted-imports.js — no `ImportExpression`
// visitor exists). A dynamic `await import("../api/client")` is therefore invisible to it. Proven by
// executed control at the close: the dynamic form linted CLEAN while the static form errored.
//
// The router half of this axis is already closed by a DIFFERENT control — `dependency-fence.test.ts`
// pins `react-router-dom` absent from both the manifest and the lockfile, so a bare specifier cannot
// resolve at all. The WRITE half was genuinely open: `../api/client` is a local module that resolves
// perfectly well through `import()`, so a dynamic import could reach `request()` and issue an
// unaudited POST past the OPS-1 M-4 fence.
//
// HONEST RESIDUAL, recorded rather than papered over: a COMPUTED specifier
// (`await import(someVariable)`) is not statically analysable and no lint rule can see it. This
// fence now covers every literal form; it does not and cannot cover a computed one. The three
// bypass axes found so far (specifier spelling at the Wave-12 close, file extension at FE-M1 R-1,
// import syntax here) were each found by an audit rather than by enumeration, which is the argument
// recorded at the close for pairing lint fences with a build-artifact check rather than broadening
// them a fourth time.
const DYNAMIC_IMPORT_FENCE = [
  {
    selector: "ImportExpression[source.type='Literal'][source.value=/(^|[./])client$/]",
    message:
      "Dynamic `import()` of the api client is restricted — `request` must be reached only from " +
      "src/api/writes.ts, the single audited write surface. Use a static `apiGet` import for reads.",
  },
  {
    selector: "ImportExpression[source.type='Literal'][source.value=/^react-router-dom($|\\/)/]",
    message:
      "react-router-dom was removed upstream at v8 (FE-M1) — import from `react-router`. " +
      "A dynamic import bypasses no-restricted-imports, so it is banned here explicitly.",
  },
];

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
    // FE-M1 widened the file glob from `src/**` to `**/*`: the SIX root-level guard tests
    // (write-fence, router-fence, dependency-fence, api-prefixes, openapi-contract, audit-gate)
    // were outside every fence, and the router ban in particular must not have a directory-shaped
    // hole. (That comment said "three" while naming four; corrected at the Wave-13 close, where a
    // sibling miscount of the same list was also found in `current_state.md`.)
    //
    // Wave-13 close fold: `.mts`/`.cts` added. FE-M1's R-1 closed the extension axis for the
    // JS family but left the TypeScript family's own module-signalling extensions out — Vite and
    // `tsc` both compile them, so the hole R-1 was raised to close was still open one letter over.
    files: ["**/*.ts", "**/*.tsx", "**/*.mts", "**/*.cts"],
    rules: {
      "no-restricted-imports": ["error", { patterns: [WRITE_FENCE, ROUTER_FENCE] }],
      "no-restricted-syntax": ["error", ...DYNAMIC_IMPORT_FENCE],
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
      // The dynamic-import fence is re-declared here WITHOUT its client clause, for exactly the
      // V-3 reason recorded above: turning the rule `off` for this file would also hand it a free
      // pass on the router half. The exemption stays scoped to the thing it exempts.
      "no-restricted-syntax": ["error", DYNAMIC_IMPORT_FENCE[1]],
    },
  },
  {
    // FE-M1 review fold — the EXTENSION axis of the fence-hole class.
    //
    // Both fences above are scoped to `.ts`/`.tsx`. The app is 100% TypeScript today, but Vite
    // compiles `.jsx`/`.js` just as happily, and a probe confirmed such a file is currently linted
    // by NOTHING at all — eslint reports "File ignored because no matching configuration was
    // supplied" and exits 0. So a single `.jsx` component could import `react-router-dom`, or reach
    // `client.ts::request` and issue an unaudited POST, past both governance fences.
    //
    // This is the same defect class the Wave-12 close took a HIGH for (the write fence was
    // bypassable by import-path shapes the ratifying probe did not enumerate) — one axis over:
    // there it was the specifier spelling, here it is the file extension. Closing it now rather
    // than waiting for a close audit to find it a third time.
    //
    // A separate block because these files need espree with JSX enabled (the TS parser covers
    // `.tsx` already), and because the file sets are DISJOINT from the blocks above — so this
    // re-declaration of the rule cannot silently override them.
    files: ["**/*.js", "**/*.jsx", "**/*.mjs", "**/*.cjs"],
    languageOptions: { parserOptions: { ecmaFeatures: { jsx: true } } },
    rules: {
      "no-restricted-imports": ["error", { patterns: [WRITE_FENCE, ROUTER_FENCE] }],
      "no-restricted-syntax": ["error", ...DYNAMIC_IMPORT_FENCE],
    },
  },
);
