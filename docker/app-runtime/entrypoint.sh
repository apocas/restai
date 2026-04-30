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

# Background esbuild watcher. Entry preference: main.tsx → main.ts → app.tsx → app.ts
# (the React + MUI seed uses main.tsx; older vanilla projects used app.ts).
# React + MUI come from the image-baked /opt/restai-app-deps/node_modules
# via NODE_PATH, so esbuild can resolve `react`, `@mui/material`, etc.
# without each project shipping its own node_modules.
if ls "${SRCDIR}"/*.ts "${SRCDIR}"/*.tsx 2>/dev/null | head -n1 >/dev/null; then
    ENTRY=""
    for cand in main.tsx main.ts app.tsx app.ts; do
        if [ -f "${SRCDIR}/${cand}" ]; then
            ENTRY="${SRCDIR}/${cand}"
            break
        fi
    done
    if [ -n "${ENTRY}" ]; then
        # Preflight: when the entry is .tsx (React seed) the bundle WILL try
        # to resolve `react` from NODE_PATH. If the runtime image is :1
        # (which doesn't bake React) this fails silently and dist/app.js
        # never gets emitted. Surface a clear instruction in the esbuild
        # log so the runtime probe picks it up.
        case "${ENTRY}" in
            *.tsx)
                if [ ! -d "${NODE_PATH:-/opt/restai-app-deps/node_modules}/react" ]; then
                    cat > /tmp/esbuild.log <<EOF
✘ [ERROR] React is not available in this runtime image.
The project uses .tsx (React + MUI) but \`react\` cannot be resolved.
Fix: rebuild the runtime image with React + MUI baked in:
    docker build -t restai/app-runtime:2 docker/app-runtime
Then in Settings → App Builder, set "Container image" to
\`restai/app-runtime:2\` and click "Restart container" in the IDE.
EOF
                    echo "[restai-app] React deps missing — surfaced via /tmp/esbuild.log"
                    # Don't run esbuild; it would just spam the same error.
                    exec_esbuild=false
                else
                    exec_esbuild=true
                fi
                ;;
            *)
                exec_esbuild=true
                ;;
        esac
        if [ "${exec_esbuild}" = "true" ]; then
            echo "[restai-app] esbuild --watch ${ENTRY} → ${DISTDIR}/app.js"
            esbuild "${ENTRY}" \
                --bundle \
                --format=esm \
                --outfile="${DISTDIR}/app.js" \
                --sourcemap=inline \
                --jsx=automatic \
                --loader:.tsx=tsx \
                --loader:.jsx=jsx \
                --define:process.env.NODE_ENV='"production"' \
                --watch=forever \
                --log-level=warning \
                > /tmp/esbuild.log 2>&1 &
        fi
    else
        echo "[restai-app] no src/(main|app).ts(x) — skipping esbuild"
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
