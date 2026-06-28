/* RESTai mobile PWA service worker (hand-written, scope /mobile/).
 *
 * Scope is /mobile/, so this SW only ever intercepts requests under /mobile/ —
 * the API calls the app makes (/projects/..., /auth/...) are out of scope and
 * are never touched/cached here. Strategy: network-first for navigations (fall
 * back to the cached shell offline), cache-first for the hashed static assets. */
const CACHE = "restai-mobile-v1";
const SHELL = [
  "/mobile/",
  "/mobile/index.html",
  "/mobile/manifest.json",
  "/mobile/favicon.png",
  "/mobile/icons/icon-192.png",
  "/mobile/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  // App navigations: network-first, fall back to the cached shell when offline.
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req).catch(() => caches.match("/mobile/index.html"))
    );
    return;
  }

  // Static assets under /mobile/: cache-first, then populate the cache.
  event.respondWith(
    caches.match(req).then((hit) => {
      if (hit) return hit;
      return fetch(req).then((res) => {
        if (res && res.status === 200 && res.type === "basic") {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
        }
        return res;
      });
    })
  );
});
