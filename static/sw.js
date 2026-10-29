
"use strict";

const CACHE_NAME = "ishwar-search-static-v1";

self.addEventListener("install", event => {
  self.skipWaiting();
});

self.addEventListener("activate", event => {
  event.waitUntil(
    (async () => {
      const cacheNames = await caches.keys();

      await Promise.all(
        cacheNames
          .filter(name =>
            name.startsWith("ishwar-search-") &&
            name !== CACHE_NAME
          )
          .map(name => caches.delete(name))
      );

      await self.clients.claim();
    })()
  );
});

// Notifications sent by a future push backend can be displayed here.
self.addEventListener("push", event => {
  let data = {
    title: "Ishwar Search",
    body: "नई जानकारी उपलब्ध है।",
    url: "/"
  };

  if (event.data) {
    try {
      data = {
        ...data,
        ...event.data.json()
      };
    } catch {
      data.body = event.data.text();
    }
  }

  const title = String(data.title || "Ishwar Search");
  const body = String(data.body || "नई जानकारी उपलब्ध है।");

  let targetUrl = "/";

  try {
    const candidate = new URL(data.url || "/", self.location.origin);

    // Only open same-origin links from push data.
    if (candidate.origin === self.location.origin) {
      targetUrl = candidate.pathname + candidate.search + candidate.hash;
    }
  } catch {
    targetUrl = "/";
  }

  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon: "/static/logo.png",
      badge: "/static/logo.png",
      tag: "ishwar-search-news",
      data: {
        url: targetUrl
      }
    })
  );
});

self.addEventListener("notificationclick", event => {
  event.notification.close();

  const targetUrl = new URL(
    event.notification.data?.url || "/",
    self.location.origin
  ).href;

  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({
        type: "window",
        includeUncontrolled: true
      });

      for (const client of windows) {
        if (client.url.startsWith(self.location.origin) && "focus" in client) {
          await client.focus();

          if ("navigate" in client) {
            await client.navigate(targetUrl);
          }

          return;
        }
      }

      await self.clients.openWindow(targetUrl);
    })()
  );
});

"use strict";

self.addEventListener("install", event => {
  self.skipWaiting();
});

self.addEventListener("activate", event => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", event => {
  let data = {};

  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = {
      title: "Ishwar Search",
      body: event.data ? event.data.text() : "नई सूचना उपलब्ध है।"
    };
  }

  const title = String(data.title || "Ishwar Search").slice(0, 100);
  const body = String(data.body || "नई सूचना उपलब्ध है।").slice(0, 300);

  const targetUrl = (() => {
    try {
      const candidate = new URL(data.url || "/", self.location.origin);
      return candidate.origin === self.location.origin
        ? candidate.href
        : self.location.origin + "/";
    } catch {
      return self.location.origin + "/";
    }
  })();

  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon: "/static/logo.png",
      badge: "/static/logo.png",
      tag: String(data.tag || "ishwar-search"),
      data: { url: targetUrl },
      renotify: false
    })
  );
});

self.addEventListener("notificationclick", event => {
  event.notification.close();

  const targetUrl =
    event.notification.data?.url || self.location.origin + "/";

  event.waitUntil(
    self.clients.matchAll({
      type: "window",
      includeUncontrolled: true
    }).then(clientList => {
      for (const client of clientList) {
        if (client.url.startsWith(self.location.origin) && "focus" in client) {
          client.navigate(targetUrl);
          return client.focus();
        }
      }

      return self.clients.openWindow(targetUrl);
    })
  );
});


