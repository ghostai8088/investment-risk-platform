import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

import { API_PREFIXES } from "./api-prefixes";

export default defineConfig({
  plugins: [react()],
  server: {
    // FE-1 (OD-FE-1-E): dev-only proxy to the local backend — the backend gains no CORS
    // configuration for a development concern. FE-3 (OD-FE-3-F) adds the read prefixes the
    // governance walk consumes beyond /risk. OPS-1 moved the list to `api-prefixes.ts` so the
    // dev proxy and the deployed nginx config cannot drift apart silently (verifier fold H1).
    proxy: Object.fromEntries(API_PREFIXES.map((prefix) => [prefix, "http://localhost:8000"])),
  },
  test: {
    environment: "jsdom",
  },
});
