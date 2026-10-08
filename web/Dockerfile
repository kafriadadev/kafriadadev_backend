# The presentation tier.
#
# Uses Next.js standalone output: the final image carries the server, the built
# pages and only the node_modules actually reached at runtime.
#
# NOTE: not yet built or run anywhere — see docs/deploy-runbook.md.

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Every page is dynamic and calls the API per request, so no API address is
# baked in here. It arrives as an environment variable at runtime.
RUN npm run build

# ---------------------------------------------------------------------------
FROM node:22-alpine AS runtime
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN apk add --no-cache curl \
 && addgroup -g 10001 -S kafriada \
 && adduser -u 10001 -S kafriada -G kafriada

COPY --from=build --chown=kafriada:kafriada /app/.next/standalone ./
COPY --from=build --chown=kafriada:kafriada /app/.next/static ./.next/static
# The logo, icons, service worker, enhance.js and the figures. The standalone
# output does not include public/; without this the site has no images and no
# offline page.
COPY --from=build --chown=kafriada:kafriada /app/public ./public

USER kafriada
EXPOSE 3000

# The landing page is served without touching the API, so this answers even
# while the domain tier is restarting — which is the honest thing for a
# presentation tier to report about itself.
HEALTHCHECK --interval=15s --timeout=10s --start-period=15s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/find" -o /dev/null || exit 1

CMD ["node", "server.js"]
