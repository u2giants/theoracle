# Candidate companion only. Documentary Python and Vercel builds remain separate.
FROM node:24.21.0-bookworm-slim@sha256:51b1100cc2a83d370c6a60952e3f2989c8a43159d0e38586e090f3b3326efefd AS build
WORKDIR /source
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/* && npm install -g pnpm@9.5.0
COPY . .
ARG REVISION
RUN test "$(git rev-parse HEAD)" = "$REVISION" && test -z "$(git status --porcelain --untracked-files=all)" && test "$(node -p 'require("./package.json").packageManager')" = pnpm@9.5.0 && pnpm install --frozen-lockfile
ENV ORACLE2_NATIVE_BROWSER_BUILD=1 NEXT_TELEMETRY_DISABLED=1
RUN pnpm run build:vercel && pnpm exec tsc -p dev/oracle2/browser/bootstrap.tsconfig.json && node dev/oracle2/browser/build-static-manifest.mjs

FROM node:24.21.0-bookworm-slim@sha256:51b1100cc2a83d370c6a60952e3f2989c8a43159d0e38586e090f3b3326efefd AS candidate
ARG REVISION
LABEL org.opencontainers.image.source="https://github.com/u2giants/theoracle" org.opencontainers.image.revision="$REVISION" org.opencontainers.image.title="Oracle invented native browser companion"
WORKDIR /app
COPY --from=build --chown=10001:10001 /source/apps/web/.next/standalone ./
COPY --from=build --chown=10001:10001 /source/apps/web/.next/static ./apps/web/.next/static
COPY --from=build --chown=10001:10001 /source/apps/web/.source-offer ./apps/web/.source-offer
COPY --from=build --chown=10001:10001 /source/apps/web/.next/native-browser-bootstrap ./apps/web/.next/native-browser-bootstrap
COPY --from=build --chown=10001:10001 /source/apps/web/.next/native-browser-static.json ./native-browser-static.json
COPY --from=build --chmod=0555 /source/dev/oracle2/browser/entrypoint.sh /app/entrypoint.sh
COPY --from=build --chmod=0444 /source/dev/oracle2/browser/launcher.mjs /app/native-browser-launcher.mjs
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0 ORACLE2_NATIVE_BROWSER_SOURCE_REVISION=$REVISION
USER 10001:10001
EXPOSE 3000
ENTRYPOINT ["/app/entrypoint.sh"]
