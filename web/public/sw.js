// KAFRIADA NET service worker. Deliberately small: it keeps two pages and shows
// one when a navigation cannot get an answer. /offline when the phone itself has
// no connection; /offline/server when it is online but the site did not answer.
// Try again on either goes back to the page that failed. It caches nothing
// personal and never serves a stale account page; everything else goes straight
// to the network as if this file did not exist.
const CACHE = "kaf-offline-v3";
const OFFLINE = "/offline";
const SERVER = "/offline/server";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) =>
      cache.addAll([new Request(OFFLINE, { cache: "reload" }), new Request(SERVER, { cache: "reload" })]),
    ),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))),
  );
  self.clients.claim();
});

async function fallback(request) {
  const page = await caches.match(self.navigator.onLine === false ? OFFLINE : SERVER);
  if (!page) return Response.error();
  const url = new URL(request.url);
  const back = url.origin === self.location.origin ? url.pathname + url.search : "/";
  const html = (await page.text()).replace(
    /href="[^"]*"([^>]*data-retry="")/g,
    (_, retry) => `href="${back.replace(/[&"<>]/g, (c) => `&#${c.charCodeAt(0)};`)}"${retry}`,
  );
  return new Response(html, { status: 503, headers: { "content-type": "text/html; charset=utf-8" } });
}

self.addEventListener("fetch", (event) => {
  if (event.request.mode !== "navigate") return;
  event.respondWith(fetch(event.request).catch(() => fallback(event.request)));
});
