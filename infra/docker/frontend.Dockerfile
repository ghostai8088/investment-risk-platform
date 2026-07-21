# Frontend build + static serve — scaffold. Aligns to AD-003 / AD-010.
FROM node:20-slim AS build

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
COPY --from=build /app/apps/frontend/dist /usr/share/nginx/html
EXPOSE 80
