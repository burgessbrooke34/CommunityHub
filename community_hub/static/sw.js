// Privacy-first service worker: cache app shell assets only, never private pages or API responses.
const CACHE = 'community-hub-static-v1';
const ASSETS = ['/static/style.css', '/static/icons/icon-192.png', '/static/icons/icon-512.png', '/static/offline.html'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith('community-hub-static-') && k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (req.mode === 'navigate') {
    event.respondWith(fetch(req).catch(() => caches.match('/static/offline.html')));
  } else if (ASSETS.includes(url.pathname)) {
    event.respondWith(caches.match(req).then(cached => cached || fetch(req)));
  }
});
