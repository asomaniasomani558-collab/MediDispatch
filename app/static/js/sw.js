/* MediDispatch GH - civilian PWA service worker (scope /civilian/).
 *
 * Caches the app shell so the page, first-aid steps and the Call 112 button
 * load with no network. API calls are never cached (they carry personal data
 * and must be live); the page queues reports itself while offline.
 */
"use strict";

var CACHE = "md-civilian-v1";
var SHELL = [
  "/civilian/",
  "/static/css/core.css",
  "/static/css/civilian.css",
  "/static/js/app.js",
  "/static/js/gps.js",
  "/static/js/camera.js",
  "/static/js/civilian.js",
  "/static/img/mark-red.png",
  "/static/img/favicon-32.png",
  "/static/img/icon-192.png",
  "/static/fonts/atkinson-hyperlegible-latin-400-normal.woff2",
  "/static/fonts/atkinson-hyperlegible-latin-700-normal.woff2",
  "/static/fonts/barlow-condensed-latin-600-normal.woff2",
  "/static/fonts/barlow-condensed-latin-700-normal.woff2",
];

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(CACHE).then(function (cache) { return cache.addAll(SHELL); }).then(function () {
      return self.skipWaiting();
    })
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (k) { return k !== CACHE; }).map(function (k) {
        return caches.delete(k);
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function (event) {
  var req = event.request;
  if (req.method !== "GET") return;
  var url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.indexOf("/civilian/api/") === 0) return; // always live

  // Page: network first (fresh CSRF token), fall back to cached shell.
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req).then(function (res) {
        var copy = res.clone();
        caches.open(CACHE).then(function (c) { c.put("/civilian/", copy); });
        return res;
      }).catch(function () { return caches.match("/civilian/"); })
    );
    return;
  }

  // Static assets: cache first.
  if (url.pathname.indexOf("/static/") === 0) {
    event.respondWith(
      caches.match(req).then(function (hit) {
        return hit || fetch(req).then(function (res) {
          var copy = res.clone();
          caches.open(CACHE).then(function (c) { c.put(req, copy); });
          return res;
        });
      })
    );
  }
});
