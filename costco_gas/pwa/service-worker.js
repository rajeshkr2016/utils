// Network-first service worker. Online visits always see the latest deploy;
// the cache is the offline fallback only.

const CACHE = "costco-gas-shell-v2";
const SHELL = [
  "./",
  "index.html",
  "app.js",
  "style.css",
  "manifest.webmanifest",
  "icon.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)));
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET") return;
  if (url.origin !== self.location.origin) return;

  event.respondWith((async () => {
    try {
      // cache: "no-cache" still uses HTTP cache but revalidates with the
      // origin (ETag / Last-Modified), so unchanged assets come back as 304.
      const fresh = await fetch(event.request, { cache: "no-cache" });
      if (fresh && fresh.status === 200) {
        const copy = fresh.clone();
        caches.open(CACHE).then((c) => c.put(event.request, copy));
      }
      return fresh;
    } catch {
      const cached = await caches.match(event.request);
      if (cached) return cached;
      throw new Error("Network failed and no cache available");
    }
  })());
});
