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
    files: ["src/**/*.ts", "src/**/*.tsx"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          paths: ["./client", "../api/client", "../../api/client"].map((name) => ({
            name,
            importNames: ["request"],
            message:
              "Import `request` only in src/api/writes.ts — the single audited write surface. Use `apiGet` for reads.",
          })),
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
