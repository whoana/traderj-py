FROM node:20-alpine AS base

RUN corepack enable && corepack prepare pnpm@latest --activate
WORKDIR /app

# --- Dependencies ---
COPY dashboard/package.json dashboard/pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile 2>/dev/null || pnpm install

# --- Development target ---
FROM base AS dev
COPY dashboard/ .
CMD ["pnpm", "dev"]

# --- Build ---
FROM base AS builder
COPY dashboard/ .
RUN pnpm build

# --- Production target ---
FROM node:20-alpine AS production
RUN adduser -D -u 1001 appuser
WORKDIR /app

COPY --from=builder --chown=appuser /app/.next/standalone ./
COPY --from=builder --chown=appuser /app/.next/static ./.next/static
COPY --from=builder --chown=appuser /app/public ./public

USER appuser
ENV PORT=3000
EXPOSE 3000
CMD ["node", "server.js"]
