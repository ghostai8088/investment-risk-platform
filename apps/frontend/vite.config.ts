import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    // FE-1 (OD-FE-1-E): dev-only proxy to the local backend — the backend gains no CORS
    // configuration for a development concern. FE-3 (OD-FE-3-F) adds the read prefixes the
    // governance walk consumes beyond /risk.
    proxy: Object.fromEntries(
      [
        "/risk",
        "/perf",
        "/exposure",
        "/portfolios",
        "/positions",
        "/valuations",
        "/holdings",
        "/models",
        "/snapshots",
        "/audit",
        "/lineage",
        "/pacing",
        "/commitments",
      ].map((prefix) => [prefix, "http://localhost:8000"]),
    ),
  },
  test: {
    environment: "jsdom",
  },
});
