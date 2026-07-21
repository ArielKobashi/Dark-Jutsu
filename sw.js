const CACHE_NAME = "dark-jutsu-app-v3";
const APP_SHELL = [
  "./style.css",
  "./mobile.css",
  "./dashboard-nav.js",
  "./logo.png",
  "./logo-tab.png",
  "./site.webmanifest"
];

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  const request = event.request;
  const url = new URL(request.url);
  if(request.method !== "GET"){
    return;
  }
  if(url.port === "8765" || request.mode === "navigate" || url.pathname.endsWith(".html") || url.pathname.endsWith("/")){
    return;
  }
  event.respondWith(
    fetch(request)
      .then(response => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(request, copy)).catch(() => {});
        return response;
      })
      .catch(() => caches.match(request))
  );
});
