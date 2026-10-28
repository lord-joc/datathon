# syntax=docker/dockerfile:1.7
# Builds the static SPA and serves it with Caddy, which also proxies /api (same origin).
# Pin base images by digest before production (docker buildx imagetools inspect <image>).
FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM caddy:2.8-alpine AS runtime
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
EXPOSE 80 443
