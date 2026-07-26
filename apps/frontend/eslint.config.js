import js from "@eslint/js";
import tseslint from "typescript-eslint";

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
    files: ["src/**/*.ts", "src/**/*.tsx"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["**/client", "./client", "../client", "./**/client", "../**/client"],
              importNames: ["request"],
              message:
                "Import `request` only in src/api/writes.ts — the single audited write surface. Use `apiGet` for reads.",
            },
          ],
        },
      ],
    },
  },
  {
    // The one file permitted to build on the shared core.
    files: ["src/api/writes.ts"],
    rules: { "no-restricted-imports": "off" },
  },
);
