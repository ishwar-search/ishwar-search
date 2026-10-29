
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

"use strict";

(() => {
  const button = document.getElementById("enableNotifications");
  const status = document.getElementById("notificationStatus");

  if (!button || !status) return;

  const setStatus = message => {
    status.textContent = message;
  };

  function urlBase64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding)
      .replace(/-/g, "+")
      .replace(/_/g, "/");

    const raw = atob(base64);
    return Uint8Array.from(raw, char => char.charCodeAt(0));
  }

  async function enableNotifications() {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      setStatus("इस ब्राउज़र में Push Notification समर्थित नहीं है।");
      return;
    }

    if (!window.isSecureContext) {
      setStatus("Push Notification के लिए HTTPS वेबसाइट खोलें।");
      return;
    }

    if (!("Notification" in window)) {
      setStatus("इस ब्राउज़र में Notification उपलब्ध नहीं है।");
      return;
    }

    button.disabled = true;
    setStatus("Notification सेवा तैयार हो रही है...");

    try {
      const keyResponse = await fetch("/api/notifications/public-key");
      const keyData = await keyResponse.json();

      if (!keyResponse.ok || !keyData.publicKey) {
        throw new Error(keyData.error || "Push public key सेट नहीं है।");
      }

      let permission = Notification.permission;

      if (permission === "default") {
        permission = await Notification.requestPermission();
      }

      if (permission !== "granted") {
        setStatus("Notification की अनुमति नहीं मिली। Browser settings में अनुमति दें।");
        return;
      }

      const registration = await navigator.serviceWorker.register("/static/sw.js");
      await navigator.serviceWorker.ready;

      let subscription = await registration.pushManager.getSubscription();

      if (!subscription) {
        subscription = await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(keyData.publicKey)
        });
      }

      const response = await fetch("/api/notifications/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(subscription)
      });

      const result = await response.json();

      if (!response.ok || !result.success) {
        throw new Error(result.error || "Subscription सेव नहीं हो पाया।");
      }

      setStatus("✅ Ishwar Search की Push Notification चालू हो गई!");
      button.textContent = "🔔 Notifications चालू हैं";

    } catch (error) {
      console.error("Notification setup failed:", error);
      setStatus("Notification चालू नहीं हुई: " + error.message);
    } finally {
      button.disabled = false;
    }
  }

  button.addEventListener("click", enableNotifications);

  if ("Notification" in window && Notification.permission === "granted") {
    setStatus("आपके ब्राउज़र में Notification की अनुमति पहले से है।");
  } else {
    setStatus("ताज़ा खबरें और जरूरी अलर्ट पाने के लिए Notification चालू करें।");
  }
})();


