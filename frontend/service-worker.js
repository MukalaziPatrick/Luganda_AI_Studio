/* ============================================================
   Luganda AI Studio — Service Worker
   Strategy: Cache-first for UI shell assets.
             Network-first for API calls (never cache these).
   ============================================================ */

const CACHE_NAME = 'luganda-studio-v1';

// UI shell assets to cache on install
const PRECACHE_ASSETS = [
  '/app/index.html',
  '/app/translate.html',
  '/app/search.html',
  '/app/teach.html',
  '/app/chat.html',
  '/app/reviews.html',
  '/app/manifest.json',
  '/app/icons/icon-192.svg',
  '/app/icons/icon-512.svg',
];

// ── Install — pre-cache the UI shell ──────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(PRECACHE_ASSETS);
    }).then(() => self.skipWaiting())
  );
});

// ── Activate — clean up old caches ────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(key => key !== CACHE_NAME)
          .map(key => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

// ── Fetch — route requests ─────────────────────────────────────
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Never intercept API calls — always go to the network
  if (url.pathname.startsWith('/api/')) {
    return; // fall through to network
  }

  // Never intercept non-GET requests
  if (event.request.method !== 'GET') {
    return;
  }

  // Cache-first for everything else (HTML, CSS, JS, fonts, icons)
  event.respondWith(
    caches.match(event.request).then(cached => {
      if (cached) {
        return cached;
      }

      // Not in cache — fetch from network and cache the result
      return fetch(event.request).then(response => {
        // Only cache successful same-origin responses
        if (
          !response ||
          response.status !== 200 ||
          response.type !== 'basic'
        ) {
          return response;
        }

        const toCache = response.clone();
        caches.open(CACHE_NAME).then(cache => {
          cache.put(event.request, toCache);
        });

        return response;
      }).catch(() => {
        // Network failed — return offline page if we have it
        if (event.request.destination === 'document') {
          return caches.match('/app/index.html');
        }
      });
    })
  );
});
