# RESTai App Builder runtime image.
#
# A single container that previews a generated app — vanilla PHP 8.3 web
# server in front of /var/www/public, with esbuild watching /var/www/src
# and emitting compiled JS into /var/www/public/dist.
#
# The container expects the project source tree to be bind-mounted at
# /var/www by the host. It owns no source itself.
#
# Build: docker build -t restai/app-runtime:1 docker/app-runtime
FROM php:8.3-cli-bookworm

# pdo_sqlite is built into php-cli but the SQLite extension itself needs
# the runtime lib. ca-certificates so the container can fetch deps if a
# generated app pulls in Composer (which is not required, just allowed).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        nodejs \
        npm \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g --silent esbuild@0.24.0 \
    && npm cache clean --force

# Pre-create the bind-mount target so a missing host volume errors loudly
# rather than silently serving an empty docroot.
RUN mkdir -p /var/www/public /var/www/src /var/www/dist

# Composer is occasionally useful even though we don't depend on it. Tiny.
RUN curl -sS https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer

WORKDIR /var/www

# Entrypoint:
#   - launch esbuild --watch in the background (only if src/ has .ts/.tsx)
#   - run php's built-in dev server on 0.0.0.0:80, docroot=public
# The router script handles /dist/ requests so esbuild output is served
# even if the file landed AFTER the request started.
COPY entrypoint.sh /usr/local/bin/restai-app-entrypoint
RUN chmod +x /usr/local/bin/restai-app-entrypoint

EXPOSE 8080
CMD ["/usr/local/bin/restai-app-entrypoint"]
