/**
 * FE-3b (OD-FE-3b-E): the front-end auth configuration, read once from `import.meta.env`.
 *
 * `authMode` mirrors the backend `AUTH_MODE`: "dev_header" (the local demo — unverified identity,
 * the DevBanner shows) or "oidc" (the real browser auth-code + PKCE login — a verified Bearer
 * session). Default is "dev_header" so the demo runs locally with no OIDC setup. A misconfigured
 * oidc build fails loudly (`oidcConfig` throws) rather than silently falling back to dev headers.
 */

export type AuthMode = "dev_header" | "oidc";

export interface OidcConfig {
  issuer: string;
  clientId: string;
  redirectUri: string;
}

export const authMode: AuthMode = import.meta.env.VITE_AUTH_MODE === "oidc" ? "oidc" : "dev_header";

/** The OIDC config — call only in oidc mode. Throws if a required var is missing, so a
 * misconfigured oidc build fails at first use, never degrades to the unverified header shim. */
export function oidcConfig(): OidcConfig {
  const issuer = import.meta.env.VITE_OIDC_ISSUER;
  const clientId = import.meta.env.VITE_OIDC_CLIENT_ID;
  const redirectUri = import.meta.env.VITE_OIDC_REDIRECT_URI;
  if (!issuer || !clientId || !redirectUri) {
    throw new Error(
      "VITE_AUTH_MODE=oidc requires VITE_OIDC_ISSUER, VITE_OIDC_CLIENT_ID and VITE_OIDC_REDIRECT_URI",
    );
  }
  return { issuer, clientId, redirectUri };
}
