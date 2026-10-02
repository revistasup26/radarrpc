/* Radar RPC — Service Worker: shell offline + API con red-primero y caché de respaldo.
   Estrategia: el feed funciona aunque la red falle (último snapshot). */
"use strict";

const CACHE = "radar-rpc-v7";
const SHELL = [
  "./",
  "./index.html",
  "./css/style.css",
  "./js/app.js",
  "./widget.html",
  "./embed.js",
  "./manifest.webmanifest",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/icon.svg",
  "./icons/logo-rpc-original.png",
];

self.addEventListener("install", e => {
  self.skipWaiting();
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(SHELL))
  );
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;

  // Red primero siempre. Los documentos/HTML NUNCA se cachean (evita shells congelados);
  // el resto se guarda como respaldo offline.
  e.respondWith(
    fetch(req)
      .then(resp => {
        if (resp && resp.ok && req.destination !== "document") {
          const copy = resp.clone();
          caches.open(CACHE).then(c => c.put(req, copy));
        }
        return resp;
      })
      .catch(() => caches.match(req).then(hit => hit || Response.error()))
  );
});