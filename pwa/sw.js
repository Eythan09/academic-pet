// Оболочка приложения кэшируется для офлайна. deadlines.json не кэшируем: приложение хранит его само.
// При изменении app.js/style.css подними ?v= здесь и в index.html, и версию CACHE.
const CACHE = "erudax-v5";
const SHELL = ["./", "index.html", "style.css?v=4", "config.js?v=4", "pet.js?v=4", "app.js?v=4",
  "fonts/pixelify-sans-cyrillic.woff2", "fonts/pixelify-sans-latin.woff2",
  "manifest.webmanifest", "icon.svg", "icon-192.png", "icon-512.png",
  "notify/happy.png", "notify/worried.png", "notify/panic.png", "notify/sad.png", "notify/done.png", "notify/badge.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.endsWith("/deadlines.json")) return; // всегда из сети
  // Сначала сеть (чтобы обновления доходили), при офлайне — кэш
  e.respondWith(
    fetch(e.request, { cache: "no-cache" })
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copy));
        return res;
      })
      .catch(() => caches.match(e.request).then((r) => r || caches.match("index.html")))
  );
});

// ---------- Web Push ----------

self.addEventListener("push", (e) => {
  let data = {};
  try { data = e.data ? e.data.json() : {}; } catch { data = { body: e.data && e.data.text() }; }
  // Картинка под настроение (Android/Chrome). iOS всегда показывает иконку приложения.
  const mood = ["happy", "worried", "panic", "sad", "done"].includes(data.mood) ? data.mood : "happy";
  e.waitUntil(self.registration.showNotification(data.title || "Erudax", {
    body: data.body || "",
    tag: data.tag,
    renotify: !!(data.renotify && data.tag), // повторное «срочно» снова звенит, а не тихо заменяет прошлое
    icon: `notify/${mood}.png`,
    badge: "notify/badge.png",
    data: { url: self.registration.scope },
  }));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const target = (e.notification.data && e.notification.data.url) || self.registration.scope;
  e.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((wins) => {
      const open = wins.find((w) => w.url.startsWith(self.registration.scope));
      return open ? open.focus() : self.clients.openWindow(target);
    })
  );
});
