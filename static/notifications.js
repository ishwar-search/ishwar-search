"use strict";

(() => {
  const button = document.getElementById("enableNotifications");
  const status = document.getElementById("notificationStatus");

  const STORAGE_KEY = "ishwar-search-notification-preference";

  function setStatus(message) {
    if (status) {
      status.textContent = message;
    }
  }

  function savePreference(value) {
    try {
      localStorage.setItem(STORAGE_KEY, value);
    } catch (error) {
      console.warn("Notification preference save failed:", error);
    }
  }

  function urlBase64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - base64String.length % 4) % 4);

    const base64 = (base64String + padding)
      .replace(/-/g, "+")
      .replace(/_/g, "/");

    const rawData = window.atob(base64);

    return Uint8Array.from(
      rawData,
      character => character.charCodeAt(0)
    );
  }

  async function fetchJSON(url, options = {}) {
    const response = await fetch(url, options);

    let data = {};

    try {
      data = await response.json();
    } catch (error) {
      throw new Error("Server से सही जवाब नहीं मिला।");
    }

    if (!response.ok) {
      throw new Error(
        data.error || data.message || "Server request असफल हुई।"
      );
    }

    return data;
  }

  async function registerServiceWorker() {
    if (!("serviceWorker" in navigator)) {
      throw new Error("इस ब्राउज़र में Service Worker उपलब्ध नहीं है।");
    }

    const registration = await navigator.serviceWorker.register(
      "/static/sw.js",
      { scope: "/" }
    );

    await navigator.serviceWorker.ready;

    return registration;
  }

  async function enableNotifications() {
    if (!("Notification" in window)) {
      throw new Error("यह ब्राउज़र Notification सपोर्ट नहीं करता।");
    }

    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      throw new Error("इस ब्राउज़र में Push Notification उपलब्ध नहीं है।");
    }

    if (!window.isSecureContext) {
      throw new Error("Notification के लिए HTTPS वेबसाइट खोलें।");
    }

    // पहले Server से VAPID Public Key लें
    const keyData = await fetchJSON(
      "/api/notifications/public-key"
    );

    if (!keyData.publicKey) {
      throw new Error("Push Public Key अभी सेट नहीं है।");
    }

    // Browser से अनुमति लें
    let permission = Notification.permission;

    if (permission === "default") {
      permission = await Notification.requestPermission();
    }

    if (permission !== "granted") {
      savePreference("denied");
      throw new Error("Notification की अनुमति नहीं मिली।");
    }

    // Service Worker तैयार करें
    const registration = await registerServiceWorker();

    // पहले से मौजूद Push Subscription देखें
    let subscription =
      await registration.pushManager.getSubscription();

    // Subscription मौजूद नहीं है तो नया बनाएं
    if (!subscription) {
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(
          keyData.publicKey
        )
      });
    }

    // Subscription Backend पर सेव करें
    const result = await fetchJSON(
      "/api/notifications/subscribe",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(subscription)
      }
    );

    if (result.success !== true) {
      throw new Error(
        result.error || "Subscription सेव नहीं हो पाया।"
      );
    }

    savePreference("enabled");

    return {
      enabled: true,
      permission: permission,
      subscription: true
    };
  }

  async function showTestNotification() {
    if (
      !("Notification" in window) ||
      Notification.permission !== "granted"
    ) {
      throw new Error("पहले Notification की अनुमति दें।");
    }

    const registration = await registerServiceWorker();

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
    const supported =
      "Notification" in window &&
      "serviceWorker" in navigator &&
      "PushManager" in window;

    let serviceWorkerReady = false;
    let subscribed = false;

    if (supported) {
      try {
        const registration = await registerServiceWorker();

        serviceWorkerReady = true;

        const subscription =
          await registration.pushManager.getSubscription();

        subscribed = Boolean(subscription);
      } catch (error) {
        console.warn("Notification status:", error);
      }
    }

    let preference = null;

    try {
      preference = localStorage.getItem(STORAGE_KEY);
    } catch (error) {
      // Storage unavailable
    }

    return {
      supported: supported,
      permission: "Notification" in window
        ? Notification.permission
        : "unsupported",
      serviceWorkerReady: serviceWorkerReady,
      subscribed: subscribed,
      preference: preference
    };
  }

  // Public functions
  window.IshwarNotifications = {
    enable: enableNotifications,
    test: showTestNotification,
    status: getStatus
  };

  // Enable button
  if (button) {
    button.addEventListener("click", async () => {
      button.disabled = true;
      setStatus("Notification सेवा तैयार हो रही है...");

      try {
        await enableNotifications();

        button.textContent = "🔔 Notifications चालू हैं";

        setStatus(
          "✅ Ishwar Search की Push Notification चालू हो गई!"
        );
      } catch (error) {
        console.error("Notification setup error:", error);

        setStatus(
          "Notification चालू नहीं हुई: " + error.message
        );
      } finally {
        button.disabled = false;
      }
    });
  }

  // शुरुआती स्थिति दिखाएं
  (async () => {
    if (!status) return;

    try {
      const current = await getStatus();

      if (!current.supported) {
        setStatus(
          "इस ब्राउज़र में Push Notification उपलब्ध नहीं है।"
        );
      } else if (current.subscribed) {
        setStatus(
          "आपकी Push Notification पहले से चालू है।"
        );

        if (button) {
          button.textContent = "🔔 Notifications चालू हैं";
        }
      } else if (current.permission === "granted") {
        setStatus(
          "Notification की अनुमति मिल चुकी है। Push चालू करने के लिए बटन दबाएं।"
        );
      } else {
        setStatus(
          "ताज़ा खबरें और जरूरी अलर्ट पाने के लिए Notification चालू करें।"
        );
      }
    } catch (error) {
      setStatus("Notification स्थिति जाँच नहीं हो सकी।");
    }
  })();
})();
