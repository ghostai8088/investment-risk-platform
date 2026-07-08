import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    // FE-1 (OD-FE-1-E): dev-only proxy to the local backend — the backend gains no CORS
    // configuration for a development concern.
    proxy: {
      "/risk": "http://localhost:8000",
    },
  },
  test: {
    environment: "jsdom",
  },
});
