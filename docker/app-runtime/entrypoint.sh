#!/usr/bin/env sh
# RESTai App Builder runtime entrypoint.
#
# - If /var/www/src has any TypeScript, esbuild watches and emits to /var/www/public/dist.
# - PHP's built-in dev server serves /var/www/public on 0.0.0.0:80 with router.php
#   so missing files don't 404 with the wrong content-type.
set -eu

WEBROOT="/var/www/public"
SRCDIR="/var/www/src"
DISTDIR="${WEBROOT}/dist"

mkdir -p "${WEBROOT}" "${SRCDIR}" "${DISTDIR}"

# Background esbuild watcher — only if there's anything to compile. We bundle
# the canonical entry point app.ts; users can change the entry by editing
# this script later, or we can promote it to a per-project setting.
if ls "${SRCDIR}"/*.ts "${SRCDIR}"/*.tsx 2>/dev/null | head -n1 >/dev/null; then
    if [ -f "${SRCDIR}/app.ts" ] || [ -f "${SRCDIR}/app.tsx" ]; then
        ENTRY="${SRCDIR}/app.ts"
        [ -f "${SRCDIR}/app.tsx" ] && ENTRY="${SRCDIR}/app.tsx"
        echo "[restai-app] esbuild --watch ${ENTRY} → ${DISTDIR}/app.js"
        esbuild "${ENTRY}" \
            --bundle \
            --format=esm \
            --outfile="${DISTDIR}/app.js" \
            --sourcemap=inline \
            --watch=forever \
            --log-level=warning \
            > /tmp/esbuild.log 2>&1 &
    else
        echo "[restai-app] no src/app.ts(x) — skipping esbuild"
    fi
fi

# Tiny router enforcing the SPA-first contract:
#   - `/` ALWAYS serves index.html when it exists (the SPA shell). PHP-S's
#     default directory-index picks index.php first, which is wrong for our
#     architecture — index.php exists only as a thin SPA fallback router for
#     shared hosts without URL rewriting; in dev we want the real shell.
#   - Static files served directly.
#   - Everything else falls through to PHP-S (which handles .php execution).
ROUTER="/tmp/router.php"
cat >"${ROUTER}" <<'PHP_ROUTER'
<?php
$uri = $_SERVER['REQUEST_URI'];
$qpos = strpos($uri, '?');
if ($qpos !== false) { $uri = substr($uri, 0, $qpos); }
$path = parse_url($uri, PHP_URL_PATH);

// SPA root: serve index.html if it exists; otherwise fall through to PHP-S
// (which will look for index.php). This keeps the dev container honest to
// the architecture: TypeScript renders all UI, PHP serves only /api/.
if ($path === '/' || $path === '') {
    $shell = __DIR__ . '/index.html';
    if (is_file($shell)) {
        header('Content-Type: text/html; charset=utf-8');
        readfile($shell);
        return true;
    }
    return false;
}

// Static asset (CSS, compiled JS, images, etc.) — let PHP-S serve directly.
$candidate = __DIR__ . $path;
if (is_file($candidate)) {
    return false;
}
return false;
PHP_ROUTER

echo "[restai-app] php -S 0.0.0.0:8080 -t ${WEBROOT}"
exec php -S 0.0.0.0:8080 -t "${WEBROOT}" "${ROUTER}"
