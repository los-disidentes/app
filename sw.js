// Service Worker — Los Disidentes App v48
const CACHE = 'disidentes-v48';
const PRECACHE = ['/app/','/app/index.html','/app/manifest.json','/app/icon-192.png','/app/icon-512.png'];
self.addEventListener('install', e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(PRECACHE)).then(() => self.skipWaiting())); });
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()).then(() => self.clients.matchAll({type:'window'})).then(cs => cs.forEach(c => c.postMessage({type:'SW_UPDATED',version:'48'}))));
});
self.addEventListener('message', e => { if (e.data?.type === 'SKIP_WAITING') self.skipWaiting(); });
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (url.hostname.includes('firebase') || url.hostname.includes('firebaseio') || url.hostname.includes('firebasedatabase') || url.hostname.includes('ligacountrysur') || url.hostname.includes('allorigins') || url.hostname.includes('fonts.googleapis') || url.hostname.includes('fonts.gstatic') || url.hostname.includes('gstatic')) return;
  e.respondWith(caches.match(e.request).then(cached => {
    if (e.request.mode === 'navigate') return fetch(e.request).then(resp => { if (resp.ok) caches.open(CACHE).then(c => c.put(e.request, resp.clone())); return resp; }).catch(() => cached || caches.match('/app/index.html'));
    if (url.pathname.startsWith('/app/fixture.json') || url.pathname.startsWith('/app/standings.json') || url.pathname.startsWith('/app/results/')) return fetch(e.request).then(resp => { if (resp.ok) caches.open(CACHE).then(c => c.put(e.request, resp.clone())); return resp; }).catch(() => cached || new Response('null',{headers:{'Content-Type':'application/json'}}));
    return cached || fetch(e.request).then(resp => { if (resp.ok && url.origin === self.location.origin) caches.open(CACHE).then(c => c.put(e.request, resp.clone())); return resp; });
  }));
});
