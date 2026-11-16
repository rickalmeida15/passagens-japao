// Service worker simples: guarda a casca do app; os preços sempre vêm da rede (com fallback offline).
const SHELL = "japao-shell-v1";
self.addEventListener("install", e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(["./", "index.html", "manifest.json", "icon.svg"])));
  self.skipWaiting();
});
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (url.pathname.endsWith("history.json")) {
    e.respondWith(fetch(e.request).then(r => {
      const copy = r.clone();
      caches.open(SHELL).then(c => c.put(e.request, copy));
      return r;
    }).catch(() => caches.match(e.request)));
    return;
  }
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
});
