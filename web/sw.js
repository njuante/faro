// Offline shell: the interface loads without the network; data (/api/) is never cached.
const CACHE = 'faro-v1';
const SHELL = ['/', '/css/faro.css', '/js/main.js', '/js/i18n.js', '/js/fmt.js', '/js/chart.js', '/js/icons.js',
  '/js/views/home.js', '/js/views/system.js', '/js/views/services.js', '/js/views/disks.js', '/js/views/sheet.js',
  '/img/icon.svg'];

self.addEventListener('install', e => e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())));
self.addEventListener('activate', e => e.waitUntil(
  caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())));

// network first, cache as a fallback: a new version shows up on the next load
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin || url.pathname.startsWith('/api/')) return;
  e.respondWith(fetch(e.request).then(r => {
    const copy = r.clone();
    caches.open(CACHE).then(c => c.put(e.request, copy));
    return r;
  }).catch(() => caches.match(e.request)));
});
