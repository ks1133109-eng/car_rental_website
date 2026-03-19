// DriveX Service Worker v1.2
// FIX: Clone response BEFORE consuming body (fixes "body already used" TypeError)
// NOTE: Only caches same-origin assets to comply with Flask-Talisman CSP.

const STATIC_CACHE  = 'drivex-static-v2';
const DYNAMIC_CACHE = 'drivex-dynamic-v2';

const PRECACHE_URLS = [
  "/",
  "/fleet",
  "/static/style.css",
  "/static/manifest.json",
  "/static/icons/icon-192.svg",
  "/static/icons/icon-512.svg",
];

// ---------------- INSTALL ----------------

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then(cache =>
      Promise.allSettled(
        PRECACHE_URLS.map(url =>
          cache.add(url).catch(err =>
            console.warn('[SW] Could not pre-cache:', url, err.message)
          )
        )
      )
    ).then(() => {
      console.log('[DriveX SW] v1.2 Installed');
      return self.skipWaiting();
    })
  );
});

// ---------------- ACTIVATE ----------------

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(k => k !== STATIC_CACHE && k !== DYNAMIC_CACHE)
          .map(k => {
            console.log('[DriveX SW] Deleting old cache:', k);
            return caches.delete(k);
          })
      )
    ).then(() => {
      console.log("[DriveX SW] Activated — old caches cleared");
      return self.clients.claim();
    })
  );
});

// ---------------- FETCH ----------------

self.addEventListener("fetch", event => {
  const request = event.request;
  const url = new URL(request.url);

  if (request.method !== 'GET') return;
  if (url.origin !== self.location.origin) return; // skip all cross-origin

  const BYPASS = ['/login','/logout','/register','/admin','/pay',
                  '/book','/kyc','/confirm','/apply-coupon','/create-order','/reset-db'];
  if (BYPASS.some(p => url.pathname.startsWith(p))) return;

  // ── Static assets: cache-first ──────────────────────────────
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(request).then(cached => {
        if (cached) return cached;
        return fetch(request).then(res => {
          if (res && res.ok) {
            // FIX: clone BEFORE returning so body isn't consumed yet
            const toCache = res.clone();
            caches.open(STATIC_CACHE).then(c => c.put(request, toCache));
          }
          return res;
        });
      })
    );
    return;
  }

  // ── Navigation: network-first, fallback to cache/offline ────
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).then(res => {
        if (res.ok) {
          // FIX: clone BEFORE returning
          const toCache = res.clone();
          caches.open(DYNAMIC_CACHE).then(c => c.put(request, toCache));
        }
        return res;
      }).catch(() =>
        caches.match(request)
          .then(c => c || caches.match('/'))
          .then(c => c || new Response(getOfflineHTML(),
            { headers: { 'Content-Type': 'text/html; charset=utf-8' } }))
      )
    );
    return;
  }

  // ── API / other: network-first, fallback to cache ───────────
  event.respondWith(
    fetch(request).then(res => {
      if (res && res.ok) {
        // FIX: clone BEFORE returning
        const toCache = res.clone();
        caches.open(DYNAMIC_CACHE).then(c => c.put(request, toCache));
      }
      return res;
    }).catch(() => caches.match(request))
  );
});

// ---------------- PUSH NOTIFICATIONS ----------------

self.addEventListener("push", event => {
  if (!event.data) return;

  let data = {};
  try {
    data = event.data.json();
  } catch {
    data = { title: "DriveX", body: event.data.text() };
  }

  event.waitUntil(
    self.registration.showNotification(data.title || "DriveX", {
      body: data.body || "You have a new update.",
      icon: "/static/icons/icon-192.svg",
      badge: "/static/icons/icon-192.svg",
      vibrate: [200, 100, 200],
      data: { url: data.url || "/" }
    })
  );
});

// ---------------- NOTIFICATION CLICK ----------------

self.addEventListener("notificationclick", event => {
  event.notification.close();
  event.waitUntil(
    clients.openWindow(event.notification.data.url || "/")
  );
});

// ---------------- OFFLINE PAGE ----------------

function getOfflineHTML() {
  return `
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DriveX — Offline</title>
<style>
*{ box-sizing:border-box; margin:0; padding:0; }
body{
  font-family:system-ui,sans-serif;
  background:#0f172a;
  color:white;
  min-height:100vh;
  display:flex;
  align-items:center;
  justify-content:center;
  text-align:center;
  padding:20px;
}
.card{ max-width:360px; width:100%; }
.bolt{
  width:72px; height:72px;
  background:#2563EB;
  border-radius:20px;
  display:flex; align-items:center; justify-content:center;
  font-size:2rem;
  margin:0 auto 24px;
  box-shadow:0 8px 32px rgba(37,99,235,.4);
}
h1{ font-size:1.8rem; font-weight:800; margin-bottom:10px; }
p{ color:#94a3b8; line-height:1.6; margin-bottom:28px; }
button{
  background:#2563EB; color:white; border:none;
  padding:14px 32px; border-radius:50px;
  font-size:1rem; font-weight:700; cursor:pointer;
}
</style>
</head>
<body>
<div class="card">
  <div class="bolt">⚡</div>
  <h1>You're Offline</h1>
  <p>DriveX needs an internet connection to show live car availability. Please check your connection.</p>
  <button onclick="location.reload()">Try Again</button>
</div>
</body>
</html>
`;
}