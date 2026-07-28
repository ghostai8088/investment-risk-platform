# Frontend build + static serve — scaffold. Aligns to AD-003 / AD-010.
#
# FE-M1 (OQ-FE-M1-2=A): node:20 -> node:24, matching the two `setup-node` steps in ci.yml. Three
# reasons, none of which CI can surface on its own — CI never builds this image:
#   (1) react-router@8 declares `engines: { node: ">=22.22.0" }`. There is no `.npmrc`, so npm
#       treats that as ADVISORY — the Node-20 build emitted an EBADENGINE warning and still produced
#       a bundle. This is a correctness-of-configuration fix, not a broken-build fix; saying
#       otherwise would overstate it (FE-M1 verifier finding V-4).
#   (2) Node 20 reached EOL 2026-04 (ci.yml records this in its own comment), so the PRODUCTION
#       artifact was being built by an unsupported toolchain while CI built it on a supported one.
#   (3) The asymmetry itself is the defect class the Wave-12 CI-parity slice paid on the Python
#       side: a harness the gates cannot see drifts silently.
FROM node:24-slim AS build

WORKDIR /app

COPY package.json package-lock.json ./
COPY apps/frontend ./apps/frontend
COPY packages/shared-ts ./packages/shared-ts

# FE-3b (OD-FE-3b-E, OQ-FE-3b-4=A): VITE_* vars are inlined at BUILD time. Default to the
# dev_header demo so a plain build is unchanged; the compose oidc profile passes these as build args.
ARG VITE_AUTH_MODE=dev_header
ARG VITE_OIDC_ISSUER=
ARG VITE_OIDC_CLIENT_ID=
ARG VITE_OIDC_REDIRECT_URI=
ENV VITE_AUTH_MODE=$VITE_AUTH_MODE \
    VITE_OIDC_ISSUER=$VITE_OIDC_ISSUER \
    VITE_OIDC_CLIENT_ID=$VITE_OIDC_CLIENT_ID \
    VITE_OIDC_REDIRECT_URI=$VITE_OIDC_REDIRECT_URI

RUN npm ci && npm run -w apps/frontend build

FROM nginx:1.27-alpine AS serve
# FE-3b (review HIGH-1 + MED-1): SPA history fallback (so /callback boots the app, not a 404) +
# the backend read-proxy. Without this the OIDC redirect 404s and the demo login cannot complete.
COPY infra/docker/frontend-nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/apps/frontend/dist /usr/share/nginx/html
EXPOSE 80
