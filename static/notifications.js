
"use strict";

(() => {
  const SUPPORTS_NOTIFICATIONS = "Notification" in window;
  const SUPPORTS_SERVICE_WORKER = "serviceWorker" in navigator;
  const SUPPORTS_PUSH = "PushManager" in window;

  const STORAGE_KEY = "ishwar-search-notification-preference";

  function getPreference() {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch {
      return null;
    }
  }

  function setPreference(value) {
    try {
      localStorage.setItem(STORAGE_KEY, value);
    } catch {
      // Storage may be unavailable in private browsing.
    }
  }

  async function registerServiceWorker() {
    if (!SUPPORTS_SERVICE_WORKER) {
      throw new Error("इस ब्राउज़र में Service Worker उपलब्ध नहीं है।");
    }

    return navigator.serviceWorker.register("/static/sw.js", {
      scope: "/"
    });
  }

  async function enableNotifications() {
    if (!SUPPORTS_NOTIFICATIONS) {
      throw new Error("यह ब्राउज़र Notifications सपोर्ट नहीं करता।");
    }

    if (!window.isSecureContext) {
      throw new Error("Notifications के लिए HTTPS वेबसाइट खोलें।");
    }

    const permission = await Notification.requestPermission();

    if (permission !== "granted") {
      setPreference("denied");
      throw new Error("Notification permission नहीं मिली।");
    }

    const registration = await registerServiceWorker();

    setPreference("enabled");

    return {
      enabled: true,
      permission,
      pushSupported: SUPPORTS_PUSH,
      serviceWorkerReady: Boolean(registration.active || registration.installing)
    };
  }

  async function showTestNotification() {
    if (!SUPPORTS_NOTIFICATIONS || Notification.permission !== "granted") {
      throw new Error("पहले Notifications चालू करें।");
    }

    const registration = await registerServiceWorker();

    await navigator.serviceWorker.ready;

    await registration.showNotification("Ishwar Search", {
      body: "Notification test सफल रहा! 🔔",
      icon: "/static/logo.png",
      badge: "/static/logo.png",
      tag: "ishwar-search-test",
      data: {
        url: "/"
      }
    });

    return true;
  }

  async function getStatus() {
    let serviceWorkerReady = false;

    if (SUPPORTS_SERVICE_WORKER) {
      try {
        await registerServiceWorker();
        await navigator.serviceWorker.ready;
        serviceWorkerReady = true;
      } catch (error) {
        console.warn("Service Worker:", error);
      }
    }

    return {
      supported: SUPPORTS_NOTIFICATIONS,
      pushSupported: SUPPORTS_PUSH,
      permission: SUPPORTS_NOTIFICATIONS
        ? Notification.permission
        : "unsupported",
      preference: getPreference(),
      serviceWorkerReady
    };
  }

  window.IshwarNotifications = {
    enable: enableNotifications,
    test: showTestNotification,
    status: getStatus
  };
})();

