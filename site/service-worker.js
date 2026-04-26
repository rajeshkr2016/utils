// Tombstone service worker.
//
// The old PWA registered a service worker at /utils/service-worker.js when the
// gas app lived at /utils/. We've since restructured to /utils/costco-gas/, so
// returning visitors still have the old SW intercepting /utils/ requests with
// stale cached content. This file replaces the old SW: it installs, then
// immediately wipes its caches, unregisters itself, and reloads any windows
// that are still under its control so they fetch the new landing page.

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.map((k) => caches.delete(k)));
    await self.registration.unregister();
    const clients = await self.clients.matchAll({ type: "window" });
    for (const client of clients) {
      try { client.navigate(client.url); } catch {}
    }
  })());
});
