const CACHE = 'biblioteca-dga-v28';
const STATIC_ASSETS = ['/static/manifest.json', '/static/icons/icon-192.png', '/static/icons/icon-512.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(STATIC_ASSETS.filter(Boolean))));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
  ));
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;

  const url = new URL(e.request.url);

  // ── Páginas HTML (rutas Flask): siempre red primero, sin caché ──
  if (!url.pathname.startsWith('/static/')) {
    e.respondWith(
      fetch(e.request).catch(() => caches.match(e.request))
    );
    return;
  }

  // ── Recursos estáticos: caché primero ──
  e.respondWith(
    caches.match(e.request).then(cached => {
      if (cached) return cached;
      return fetch(e.request).then(resp => {
        const clone = resp.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return resp;
      });
    })
  );
});
