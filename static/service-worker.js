const CACHE = 'ceremio-v5';
const APP_SHELL = [
  '/static/offline.html',
  '/static/app.css',
  '/static/mobile.css',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  // Never cache non-GET (logins, RSVP submissions, saves) — must always hit the server.
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // Stale-while-revalidate for our own static assets:
  // serve the cached copy instantly, but refresh it in the background so
  // updates (CSS/JS/icons) propagate on the next load. Keeps it fast AND fresh.
  if (url.origin === self.location.origin && url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.open(CACHE).then((cache) =>
        cache.match(req).then((cached) => {
          const network = fetch(req)
            .then((res) => { cache.put(req, res.clone()); return res; })
            .catch(() => cached);
          return cached || network;
        })
      )
    );
    return;
  }

  // Network-first for page navigations; offline page as fallback.
  // Dynamic/logged-in HTML is intentionally NOT cached (privacy + freshness).
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req).catch(() => caches.match('/static/offline.html'))
    );
    return;
  }
});
