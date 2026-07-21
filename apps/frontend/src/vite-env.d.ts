/// <reference types="vite/client" />

// FE-3b (OD-FE-3b-E): the front-end's build-time config surface. `VITE_`-prefixed vars are inlined
// by Vite at build time; typed here so `import.meta.env.VITE_*` is checked, not `any`.
interface ImportMetaEnv {
  /** Mirrors the backend `AUTH_MODE`: "dev_header" (the local demo, unverified) or "oidc" (the real
   * browser auth-code + PKCE login). Default "dev_header" so the demo runs locally with no OIDC. */
  readonly VITE_AUTH_MODE?: "dev_header" | "oidc";
  /** The OIDC issuer, e.g. `http://localhost:8080/realms/irp-local` (oidc mode only). */
  readonly VITE_OIDC_ISSUER?: string;
  /** The public client id (the Keycloak `irp-frontend` client). */
  readonly VITE_OIDC_CLIENT_ID?: string;
  /** The registered redirect URI, e.g. `http://localhost:5173/callback`. */
  readonly VITE_OIDC_REDIRECT_URI?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
