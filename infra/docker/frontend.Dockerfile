# Frontend build + static serve — scaffold. Aligns to AD-003 / AD-010.
FROM node:20-slim AS build

WORKDIR /app

COPY package.json ./
COPY apps/frontend ./apps/frontend
COPY packages/shared-ts ./packages/shared-ts

RUN npm install && npm run -w apps/frontend build

FROM nginx:1.27-alpine AS serve
COPY --from=build /app/apps/frontend/dist /usr/share/nginx/html
EXPOSE 80
