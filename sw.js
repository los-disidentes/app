// Service Worker — Los Disidentes App v20
const CACHE = 'disidentes-v20';
const PRECACHE = [
  '/app/',
  '/app/index.html',
  '/app/manifest.json',
  '/app/icon-192.png',
  '/app/icon-512.png',
];

// Instalar: pre-cachear shell de la app
self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE)
      .then(c => c.addAll(PRECACHE))
      .then(() => self.skipWaiting())
  );
});

// Activar: limpiar caches viejos
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(k => k !== CACHE).map(k => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

// Mensaje desde la app para activar nuevo SW inmediatamente
self.addEventListener('message', e => {
  if (e.data?.type === 'SKIP_WAITING') self.skipWaiting();
});

// Fetch: network-first para API y Firebase, cache-first para assets
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // Dejar pasar Firebase y APIs externas sin caché
  if (
    url.hostname.includes('firebase') ||
    url.hostname.includes('firebaseio') ||
    url.hostname.includes('ligacountrysur') ||
    url.hostname.includes('allorigins') ||
    url.hostname.includes('fonts.googleapis') ||
    url.hostname.includes('fonts.gstatic') ||
    url.hostname.includes('gstatic')
  ) {
    return; // fetch normal, sin intervención
  }

  e.respondWith(
    caches.match(e.request).then(cached => {
      // Para el HTML principal, intentar red primero (para actualizaciones)
      if (e.request.mode === 'navigate') {
        return fetch(e.request)
          .then(resp => {
            if (resp.ok) {
              const clone = resp.clone();
              caches.open(CACHE).then(c => c.put(e.request, clone));
            }
            return resp;
          })
          .catch(() => cached || caches.match('/app/index.html'));
      }
      // Para el resto: cache-first
      return cached || fetch(e.request).then(resp => {
        if (resp.ok && url.origin === self.location.origin) {
          caches.open(CACHE).then(c => c.put(e.request, resp.clone()));
        }
        return resp;
      });
    })
  );
});
