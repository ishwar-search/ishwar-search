"use strict";

const CACHE_NAME = "ishwar-search-static-v2";

// Install Service Worker
self.addEventListener("install", event => {
  event.waitUntil(self.skipWaiting());
});

// Activate Service Worker
self.addEventListener("activate", event => {
  event.waitUntil(self.clients.claim());
});

// Receive Push Notification
self.addEventListener("push", event => {
  let data = {};

  try {
    data = event.data ? event.data.json() : {};
  } catch (error) {
    data = {
      title: "Ishwar Search",
      body: event.data ? event.data.text() : "नई सूचना उपलब्ध है।"
    };
  }

  const title = String(data.title || "Ishwar Search").slice(0, 100);
  const body = String(data.body || "नई जानकारी उपलब्ध है।").slice(0, 300);

  let targetUrl = "/";

  try {
    const url = new URL(data.url || "/", self.location.origin);

    // केवल अपनी वेबसाइट के लिंक खोलें
    if (url.origin === self.location.origin) {
      targetUrl = url.pathname + url.search + url.hash;
    }
  } catch (error) {
    targetUrl = "/";
  }

  const options = {
    body: body,
    icon: "/static/logo.png",
    badge: "/static/logo.png",
    tag: String(data.tag || "ishwar-search-news").slice(0, 100),
    renotify: false,
    data: {
      url: targetUrl
    }
  };

  event.waitUntil(
    self.registration.showNotification(title, options)
  );
});

// Notification पर क्लिक करने पर वेबसाइट खोलें
self.addEventListener("notificationclick", event => {
  event.notification.close();

  let targetUrl = self.location.origin + "/";

  try {
    const url = new URL(
      event.notification.data?.url || "/",
      self.location.origin
    );

    if (url.origin === self.location.origin) {
      targetUrl = url.href;
    }
  } catch (error) {
    targetUrl = self.location.origin + "/";
  }

  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({
        type: "window",
        includeUncontrolled: true
      });

      for (const client of windows) {
        if (
          client.url.startsWith(self.location.origin) &&
          "focus" in client
        ) {
          if ("navigate" in client) {
            await client.navigate(targetUrl);
          }

          await client.focus();
          return;
        }
      }

      await self.clients.openWindow(targetUrl);
    })()
  );
});
