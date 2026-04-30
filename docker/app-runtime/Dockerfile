# RESTai App Builder runtime image (v2 — React + MUI).
#
# A single container that previews a generated app: PHP 8.3 web server
# in front of /var/www/public, esbuild watching /var/www/src and emitting
# a bundled React + MUI SPA into /var/www/public/dist.
#
# The container expects the project source tree to be bind-mounted at
# /var/www by the host. It owns no source itself.
#
# v2 (this image) bakes React 18 + MUI v5 + Emotion into
# /opt/restai-app-deps/node_modules and exposes them via NODE_PATH so
# esbuild can resolve `react`, `@mui/material`, etc. from any project
# without each project needing its own `npm install`. The deployed app
# (whatever lands in public/) stays fully self-contained — esbuild
# bundles all imports into dist/app.js, so the production host needs
# only PHP, no Node.
#
# Build: docker build -t restai/app-runtime:2 docker/app-runtime
FROM php:8.3-cli-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        nodejs \
        npm \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g --silent esbuild@0.24.0 \
    && npm cache clean --force

# Bake the React + MUI dependency tree once at image build time. esbuild
# will resolve these via NODE_PATH no matter what project is mounted.
RUN mkdir -p /opt/restai-app-deps \
    && cd /opt/restai-app-deps \
    && npm init -y --silent \
    && npm install --silent --no-audit --no-fund \
        react@18 react-dom@18 \
        @mui/material@5 @mui/icons-material@5 \
        @emotion/react@11 @emotion/styled@11 \
    && npm cache clean --force
ENV NODE_PATH=/opt/restai-app-deps/node_modules

# Pre-create the bind-mount target so a missing host volume errors loudly
# rather than silently serving an empty docroot.
RUN mkdir -p /var/www/public /var/www/src /var/www/dist

WORKDIR /var/www

# Entrypoint:
#   - launch esbuild --watch in the background (only if src/ has .tsx/.ts)
#   - run php's built-in dev server on 0.0.0.0:8080, docroot=public
COPY entrypoint.sh /usr/local/bin/restai-app-entrypoint
RUN chmod +x /usr/local/bin/restai-app-entrypoint

EXPOSE 8080
CMD ["/usr/local/bin/restai-app-entrypoint"]
