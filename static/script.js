
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const safeText = (value) => String(value ?? "").trim();

  const panelNames = [
    "websites",
    "centres",
    "tools",
    "images",
    "news",
    "notifications",
    "vault"
  ];

  const panels = Object.fromEntries(
    panelNames.map(name => [name, $(name + "Panel")])
  );

  let allWebsites = [];
  let governmentCentres = [];
  let latestNews = [];
  let alertsLoaded = false;
  let newsLoaded = false;
  let currentResults = [];
  let currentQuery = "";
  let currentResultTab = "all";
  let selectedWebsiteCategory = "all";
  let selectedCentreCategory = "all";

  const builtInWebsites = [
    ["Instagram", "https://www.instagram.com/", "social", "फोटो और Reels"],
    ["Facebook", "https://www.facebook.com/", "social", "सोशल मीडिया"],
    ["YouTube", "https://www.youtube.com/", "social", "वीडियो और चैनल"],
    ["WhatsApp", "https://www.whatsapp.com/", "social", "मैसेज और कॉल"],
    ["Telegram", "https://web.telegram.org/", "social", "मैसेज और चैनल"],
    ["LinkedIn", "https://www.linkedin.com/", "social", "प्रोफेशनल नेटवर्क"],
    ["UIDAI Aadhaar", "https://uidai.gov.in/", "government", "आधार की आधिकारिक वेबसाइट"],
    ["DigiLocker", "https://www.digilocker.gov.in/", "government", "डिजिटल दस्तावेज़"],
    ["Rajasthan SSO", "https://sso.rajasthan.gov.in/", "government", "राजस्थान ऑनलाइन सेवाएँ"],
    ["Cyber Crime Portal", "https://cybercrime.gov.in/", "government", "साइबर शिकायत"],
    ["Indian Railways", "https://indianrailways.gov.in/", "jobs", "रेलवे"],
    ["IRCTC", "https://www.irctc.co.in/", "travel", "रेल टिकट"],
    ["RRB", "https://www.rrbcdg.gov.in/", "jobs", "रेलवे भर्ती"],
    ["SSC", "https://ssc.gov.in/", "jobs", "सरकारी भर्ती"],
    ["RPSC", "https://rpsc.rajasthan.gov.in/", "jobs", "राजस्थान भर्ती"],
    ["National Career Service", "https://www.ncs.gov.in/", "jobs", "नौकरी"],
    ["Scholarship Portal", "https://scholarships.gov.in/", "education", "छात्रवृत्ति"],
    ["NTA", "https://nta.ac.in/", "education", "परीक्षा"],
    ["SWAYAM", "https://swayam.gov.in/", "education", "ऑनलाइन पढ़ाई"],
    ["RBI", "https://www.rbi.org.in/", "finance", "रिजर्व बैंक"],
    ["SBI", "https://sbi.co.in/", "finance", "बैंकिंग"],
    ["Amazon India", "https://www.amazon.in/", "shopping", "ऑनलाइन खरीदारी"],
    ["Flipkart", "https://www.flipkart.com/", "shopping", "ऑनलाइन खरीदारी"],
    ["Google News", "https://news.google.com/", "news", "समाचार"],
    ["PIB India", "https://pib.gov.in/", "news", "सरकारी प्रेस रिलीज़"],
    ["GitHub", "https://github.com/", "technology", "कोड और प्रोजेक्ट"],
    ["Python", "https://www.python.org/", "technology", "Python programming"],
    ["MDN Web Docs", "https://developer.mozilla.org/", "technology", "वेब डेवलपमेंट"],
    ["Photopea", "https://www.photopea.com/", "technology", "फोटो एडिटिंग"],
    ["Canva", "https://www.canva.com/", "technology", "पोस्टर डिजाइन"],
    ["Pexels", "https://www.pexels.com/", "technology", "फोटो और वीडियो"],
    ["Google Maps", "https://maps.google.com/", "travel", "मैप और रास्ते"],
    ["RSRTC", "https://rsrtconline.rajasthan.gov.in/", "travel", "राजस्थान रोडवेज"],
    ["Ayushman Bharat", "https://pmjay.gov.in/", "health", "स्वास्थ्य योजना"],
    ["ABHA", "https://abha.abdm.gov.in/", "health", "स्वास्थ्य खाता"]
  ].map(([name, url, category, description]) => ({
    name, url, category, description
  }));

  const tools = [
    {
      name: "Photopea",
      url: "https://www.photopea.com/",
      description: "फोटो एडिटिंग"
    },
    {
      name: "Canva",
      url: "https://www.canva.com/",
      description: "पोस्टर और डिजाइन"
    },
    {
      name: "Pexels",
      url: "https://www.pexels.com/",
      description: "फोटो और वीडियो"
    },
    {
      name: "Pixabay",
      url: "https://pixabay.com/",
      description: "चित्र और फोटो"
    },
    {
      name: "freeCodeCamp",
      url: "https://www.freecodecamp.org/",
      description: "मुफ्त कोडिंग"
    },
    {
      name: "CodePen",
      url: "https://codepen.io/",
      description: "HTML, CSS और JavaScript"
    },
    {
      name: "Stack Overflow",
      url: "https://stackoverflow.com/",
      description: "प्रोग्रामिंग सवाल-जवाब"
    },
    {
      name: "Google Translate",
      url: "https://translate.google.com/",
      description: "भाषा अनुवाद"
    }
  ];

  function validUrl(value) {
    try {
      const url = new URL(value);
      return url.protocol === "https:" || url.protocol === "http:";
    } catch {
      return false;
    }
  }

  function normalizeSite(item) {
    if (!item || typeof item !== "object") return null;

    const name = safeText(item.name || item.title);
    const url = safeText(item.url || item.link);

    if (!name || !validUrl(url)) return null;

    return {
      name,
      url,
      category: safeText(item.category || "general").toLowerCase(),
      description: safeText(
        item.description || item.category || "वेबसाइट खोलें"
      )
    };
  }

  function createElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function makeLogo(url) {
    const image = document.createElement("img");
    image.className = "site-logo";
    image.alt = "";
    image.loading = "lazy";
    image.referrerPolicy = "no-referrer";

    try {
      const host = new URL(url).hostname;
      image.src =
        "https://www.google.com/s2/favicons?domain=" +
        encodeURIComponent(host) +
        "&sz=128";

      image.addEventListener("error", () => {
        image.hidden = true;
      }, { once: true });
    } catch {
      image.hidden = true;
    }

    return image;
  }

  function renderCards(container, items, options = {}) {
    if (!container) return;

    container.replaceChildren();
    let shown = 0;

    (items || []).forEach(raw => {
      const item = normalizeSite(raw);
      if (!item) return;

      const card = createElement(
        "a",
        options.resultCard ? "result-card" : "directory-card"
      );

      card.href = item.url;
      card.target = "_blank";
      card.rel = "noopener noreferrer";

      if (options.logo) {
        card.appendChild(makeLogo(item.url));
      }

      const copy = createElement("span", "card-copy");
      const title = createElement("strong", "", item.name);
      const description = createElement("small", "", item.description);

      copy.append(title, description);
      card.appendChild(copy);
      container.appendChild(card);
      shown++;
    });

    if (!shown) {
      container.appendChild(
        createElement(
          "p",
          "empty",
          options.empty || "कोई परिणाम नहीं मिला।"
        )
      );
    }
  }

  async function getJson(url) {
    const response = await fetch(url, {
      headers: { Accept: "application/json" }
    });

    if (!response.ok) {
      throw new Error("HTTP " + response.status);
    }

    return response.json();
  }

  // PAGE NAVIGATION

  function showView(name) {
    const home = $("homePanel");
    const results = $("searchResults");

    if (home) home.hidden = name !== "home";
    if (results) results.hidden = true;

    panelNames.forEach(key => {
      if (panels[key]) {
        panels[key].hidden = key !== name;
      }
    });

    document.body.classList.toggle(
      "has-searched",
      name !== "home"
    );

    document.querySelectorAll("[data-view]").forEach(link => {
      link.classList.toggle(
        "active",
        link.dataset.view === name
      );
    });

    if (name === "websites" && !allWebsites.length) {
      loadWebsites();
    }

    if (name === "centres" && !governmentCentres.length) {
      loadGovernmentCentres();
    }

    if (name === "tools") renderTools();
    if (name === "news" && !newsLoaded) loadNews();
    if (name === "home" && !alertsLoaded) loadAlerts();

    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  document.querySelectorAll("[data-view]").forEach(link => {
    link.addEventListener("click", event => {
      event.preventDefault();
      const view = link.dataset.view;
      showView(view);
      history.replaceState(null, "", "#" + view);
    });
  });

  // WEBSITE DIRECTORY

  async function loadWebsites() {
    const status = $("websiteStatus");
    if (status) status.textContent = "वेबसाइटें लोड हो रही हैं...";

    try {
      const data = await getJson("/api/services");

      const combined = [
        ...builtInWebsites,
        ...(Array.isArray(data.results) ? data.results : [])
      ].map(normalizeSite).filter(Boolean);

      const seen = new Set();

      allWebsites = combined.filter(item => {
        const key = item.url.replace(/\/+$/, "").toLowerCase();
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });

      renderWebsites();

      if (status) {
        status.textContent = allWebsites.length + " वेबसाइटें उपलब्ध हैं।";
      }
    } catch (error) {
      console.error("Website load failed:", error);
      allWebsites = builtInWebsites;
      renderWebsites();

      if (status) {
        status.textContent = "स्थानीय वेबसाइट सूची दिखाई जा रही है।";
      }
    }
  }

  function renderWebsites() {
    const filter = $("websiteFilter");
    const query = filter ? filter.value.trim().toLowerCase() : "";

    const items = allWebsites.filter(site => {
      const text = [
        site.name, site.url, site.category, site.description
      ].join(" ").toLowerCase();

      const categoryMatch =
        selectedWebsiteCategory === "all" ||
        site.category === selectedWebsiteCategory ||
        (
          selectedWebsiteCategory === "government" &&
          ["documents", "legal", "rajasthan"].includes(site.category)
        );

      return categoryMatch && (!query || text.includes(query));
    });

    renderCards($("websiteList"), items, {
      logo: true,
      empty: "कोई वेबसाइट नहीं मिली।"
    });
  }

  if ($("websiteFilter")) {
    $("websiteFilter").addEventListener("input", renderWebsites);
  }

  if ($("websiteCategories")) {
    $("websiteCategories").addEventListener("click", event => {
      const button = event.target.closest("[data-category]");
      if (!button) return;

      selectedWebsiteCategory = button.dataset.category;

      $("websiteCategories")
        .querySelectorAll("[data-category]")
        .forEach(item => {
          item.classList.toggle("active", item === button);
        });

      renderWebsites();
    });
  }

  // GOVERNMENT CENTRES

  async function loadGovernmentCentres() {
    const status = $("centreStatus");
    const list = $("centreList");

    if (status) status.textContent = "सरकारी केंद्र लोड हो रहे हैं...";
    if (list) list.replaceChildren();

    try {
      const data = await getJson("/api/future/centres");

      if (!data.success || !Array.isArray(data.categories)) {
        throw new Error("Invalid centres response");
      }

      governmentCentres = data.categories;
      renderGovernmentCentres();

      if (status) {
        status.textContent =
          (data.total_links || 0) +
          " आधिकारिक लिंक उपलब्ध हैं।";
      }
    } catch (error) {
      console.error("Government centres failed:", error);

      if (status) {
        status.textContent =
          "सरकारी केंद्र लोड नहीं हुए। API जाँचें।";
      }
    }
  }

  function renderGovernmentCentres() {
    const container = $("centreList");
    if (!container) return;

    const filter = $("centreFilter");
    const query = filter ? filter.value.trim().toLowerCase() : "";

    container.replaceChildren();
    let shown = 0;

    const groups = governmentCentres.filter(centre =>
      selectedCentreCategory === "all" ||
      centre.id === selectedCentreCategory
    );

    groups.forEach(centre => {
      const items = (centre.items || []).filter(item => {
        const text = [
          centre.name,
          centre.description,
          item.name,
          item.description,
          item.source,
          item.url
        ].join(" ").toLowerCase();

        return !query || text.includes(query);
      });

      if (!items.length) return;

      const group = createElement("section", "centre-group");
      group.appendChild(createElement("h3", "", centre.name));

      group.appendChild(
        createElement("p", "panel-status", centre.description || "")
      );

      const grid = createElement("div", "directory-grid");

      items.forEach(item => {
        if (!validUrl(item.url)) return;

        const card = createElement("a", "directory-card");
        card.href = item.url;
        card.target = "_blank";
        card.rel = "noopener noreferrer";

        const copy = createElement("span", "card-copy");
        copy.appendChild(
          createElement("strong", "", item.name || "सरकारी सेवा")
        );
        copy.appendChild(
          createElement(
            "small",
            "",
            item.description || "आधिकारिक पोर्टल खोलें"
          )
        );

        if (item.source) {
          copy.appendChild(
            createElement("small", "centre-source", "स्रोत: " + item.source)
          );
        }

        card.appendChild(copy);
        grid.appendChild(card);
        shown++;
      });

      group.appendChild(grid);
      container.appendChild(group);
    });

    if (!shown) {
      container.appendChild(
        createElement("p", "empty", "इस खोज में कोई सरकारी लिंक नहीं मिला।")
      );
    }
  }

  if ($("centreFilter")) {
    $("centreFilter").addEventListener("input", renderGovernmentCentres);
  }

  if ($("centreCategories")) {
    $("centreCategories").addEventListener("click", event => {
      const button = event.target.closest("[data-centre-category]");
      if (!button) return;

      selectedCentreCategory = button.dataset.centreCategory;

      $("centreCategories")
        .querySelectorAll("[data-centre-category]")
        .forEach(item => {
          item.classList.toggle("active", item === button);
        });

      renderGovernmentCentres();
    });
  }

  window.openGovernmentCentre = function(category) {
    const allowed = ["schemes", "documents", "scholarships", "exams", "skills"];
    if (!allowed.includes(category)) return;

    showView("centres");
    selectedCentreCategory = category;

    if ($("centreFilter")) $("centreFilter").value = "";

    if ($("centreCategories")) {
      $("centreCategories")
        .querySelectorAll("[data-centre-category]")
        .forEach(button => {
          button.classList.toggle(
            "active",
            button.dataset.centreCategory === category
          );
        });
    }

    renderGovernmentCentres();
    history.replaceState(null, "", "#centres");
  };

  // TOOLS

  function renderTools() {
    const filter = $("toolFilter");
    const query = filter ? filter.value.trim().toLowerCase() : "";

    const filtered = tools.filter(item =>
      (item.name + " " + item.description).toLowerCase().includes(query)
    );

    renderCards($("toolList"), filtered, { logo: true });
  }

  if ($("toolFilter")) {
    $("toolFilter").addEventListener("input", renderTools);
  }

  // IMAGE SEARCH

  async function searchImages(query) {
    const status = $("imageStatus");
    const container = $("imageResults");

    if (!container) return;

    if (status) status.textContent = "तस्वीरें खोजी जा रही हैं...";
    container.replaceChildren();

    try {
      const data = await getJson(
        "/api/images?q=" + encodeURIComponent(query)
      );

      const items = Array.isArray(data.results) ? data.results : [];
      let shown = 0;

      items.forEach(item => {
        const src = item.image_url || item.image || item.src || item.thumbnail;
        if (!validUrl(src)) return;

        const card = createElement("a", "directory-card");
        card.href = validUrl(item.page_url) ? item.page_url : src;
        card.target = "_blank";
        card.rel = "noopener noreferrer";
        card.style.display = "block";

        const img = document.createElement("img");
        img.src = src;
        img.alt = safeText(item.alt || item.title || query);
        img.loading = "lazy";

        img.addEventListener("error", () => card.remove(), { once: true });

        const caption = createElement(
          "small",
          "",
          safeText(item.title || query)
        );

        card.append(img, caption);
        container.appendChild(card);
        shown++;
      });

      if (status) {
        status.textContent = shown
          ? shown + " तस्वीरें मिलीं। स्रोत और लाइसेंस की शर्तें देखें।"
          : "कोई तस्वीर नहीं मिली।";
      }
    } catch (error) {
      console.error("Image search failed:", error);

      if (status) {
        status.textContent = "Image API उपलब्ध नहीं है। बाद में कोशिश करें।";
      }
    }
  }

  if ($("imageSearchForm")) {
    $("imageSearchForm").addEventListener("submit", event => {
      event.preventDefault();
      const query = $("imageQuery")?.value.trim();
      if (query) searchImages(query);
    });
  }

  if ($("imageCategories")) {
    $("imageCategories").addEventListener("click", event => {
      const button = event.target.closest("[data-image-query]");
      if (!button) return;

      if ($("imageQuery")) {
        $("imageQuery").value = button.dataset.imageQuery;
      }

      searchImages(button.dataset.imageQuery);
    });
  }

  // NEWS

  async function loadNews() {
    const status = $("newsStatus");
    if (status) status.textContent = "नई खबरें लोड हो रही हैं...";

    try {
      const data = await getJson("/api/news?limit=15");
      latestNews = Array.isArray(data.results) ? data.results : [];

      const items = latestNews.map(item => ({
        name: item.title || item.name || "समाचार",
        url: item.url || item.link,
        category: "news",
        description: [
          item.source,
          item.published,
          item.description
        ].filter(Boolean).join(" • ")
      }));

      renderCards($("newsList"), items, {
        empty: "अभी खबरें उपलब्ध नहीं हैं।"
      });

      if (status) status.textContent = latestNews.length + " खबरें मिलीं।";
      newsLoaded = true;
    } catch (error) {
      console.error("News load failed:", error);
      if (status) status.textContent = "खबरें लोड नहीं हुईं।";
    }
  }

  // BREAKING NEWS / ISHWAR ALERT

  async function loadAlerts() {
    const status = $("alertStatus");
    if (status) status.textContent = "ताज़ा अपडेट लोड हो रहे हैं...";

    try {
      const data = await getJson("/api/news?limit=5&refresh=1");
      const items = Array.isArray(data.results) ? data.results : [];

      const alerts = items.map(item => ({
        name: item.title || item.name || "नई खबर",
        url: item.url || item.link,
        category: "alert",
        description: [
          item.source,
          item.published,
          item.description
        ].filter(Boolean).join(" • ") || "ताज़ा समाचार अपडेट"
      }));

      renderCards($("alertList"), alerts, {
        empty: "अभी कोई नया अपडेट उपलब्ध नहीं है।"
      });

      if (status) {
        status.textContent = alerts.length
          ? alerts.length + " ताज़ा अपडेट उपलब्ध हैं।"
          : "अभी कोई नया अपडेट उपलब्ध नहीं है।";
      }

      alertsLoaded = true;
    } catch (error) {
      console.error("Alert load failed:", error);
      if (status) status.textContent = "अलर्ट लोड नहीं हुए।";
    }
  }

  if ($("refreshAlerts")) {
    $("refreshAlerts").addEventListener("click", loadAlerts);
  }

  if ($("refreshNews")) {
    $("refreshNews").addEventListener("click", loadNews);
  }

  // MAIN SEARCH

  function renderSearchResults() {
    const filtered = currentResults.filter(item => {
      const category = safeText(
        item.result_type || item.category || "websites"
      ).toLowerCase();

      if (currentResultTab === "all") return true;

      if (currentResultTab === "websites") {
        return ["website", "websites", "web", "general"].includes(category);
      }

      return category.includes(currentResultTab);
    });

    renderCards($("resultsList"), filtered, {
      logo: true,
      resultCard: true,
      empty: "इस श्रेणी में कोई परिणाम नहीं मिला।"
    });

    const status = $("resultsStatus");
    if (status) {
      status.textContent = filtered.length
        ? filtered.length + " परिणाम मिले।"
        : "कोई परिणाम नहीं मिला।";
    }
  }

  async function performSearch(query) {
    query = safeText(query);
    if (!query) return;

    currentQuery = query;
    currentResultTab = "all";

    showView("home");

    document.body.classList.add("has-searched");

    const results = $("searchResults");
    if (results) results.hidden = false;

    if ($("resultsHeading")) {
      $("resultsHeading").textContent = "“" + query + "” के परिणाम";
    }

    if ($("resultsStatus")) {
      $("resultsStatus").textContent = "खोज रहे हैं...";
    }

    if ($("resultsList")) {
      $("resultsList").replaceChildren();
    }

    try {
      const data = await getJson(
        "/api/search?q=" + encodeURIComponent(query) + "&limit=50"
      );

      currentResults = Array.isArray(data.results) ? data.results : [];
      renderSearchResults();
    } catch (error) {
      console.error("Search failed:", error);

      if ($("resultsStatus")) {
        $("resultsStatus").textContent =
          "सर्च सेवा उपलब्ध नहीं है। बाद में कोशिश करें।";
      }
    }

    if (results) {
      results.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  if ($("searchForm")) {
    $("searchForm").addEventListener("submit", event => {
      event.preventDefault();
      const query = $("searchInput")?.value.trim();
      if (query) performSearch(query);
    });
  }

  // RESULT CATEGORY TABS

  document.querySelectorAll("[data-result-tab]").forEach(button => {
    button.addEventListener("click", () => {
      currentResultTab = button.dataset.resultTab || "all";

      document.querySelectorAll("[data-result-tab]").forEach(item => {
        item.classList.toggle("active", item === button);
      });

      renderSearchResults();
    });
  });

  // NOTIFICATIONS
  // Push subscription का काम notifications.js संभालता है।

  if ($("notificationButton")) {
    $("notificationButton").addEventListener("click", () => {
      showView("notifications");
    });
  }

  async function checkNewsNotification() {
    const status = $("notificationStatus");

    if (!("Notification" in window) ||
        Notification.permission !== "granted") {
      if (status) status.textContent = "पहले Notification चालू करें।";
      return;
    }

    try {
      const data = await getJson("/api/news?limit=5&refresh=1");
      const news = Array.isArray(data.results) ? data.results : [];

      if (!news.length) {
        if (status) status.textContent = "अभी नई खबरें उपलब्ध नहीं हैं।";
        return;
      }

      if (!("serviceWorker" in navigator)) {
        throw new Error("Service Worker unavailable");
      }

      const registration = await navigator.serviceWorker.ready;

      await registration.showNotification(
        "Ishwar Search — News Update",
        {
          body: safeText(news[0].title || "नई खबर उपलब्ध है।").slice(0, 180),
          icon: "/static/logo.png",
          badge: "/static/logo.png",
          tag: "ishwar-search-news-test",
          data: {
            url: news[0].url || news[0].link || "/"
          }
        }
      );

      if (status) {
        status.textContent = "टेस्ट नोटिफिकेशन दिखाया गया।";
      }
    } catch (error) {
      console.error("Notification test failed:", error);
      if (status) status.textContent = "टेस्ट नोटिफिकेशन नहीं दिखा।";
    }
  }

  if ($("checkNewsNotification")) {
    $("checkNewsNotification").addEventListener(
      "click",
      checkNewsNotification
    );
  }

  // THEME

  if ($("themeButton")) {
    const savedTheme = localStorage.getItem("ishwar-theme");

    if (savedTheme === "light") {
      document.body.classList.add("light-mode");
    }

    $("themeButton").addEventListener("click", () => {
      const light = document.body.classList.toggle("light-mode");

      localStorage.setItem(
        "ishwar-theme",
        light ? "light" : "default"
      );

      $("themeButton").textContent = light ? "☀" : "☾";
    });
  }

  // FOOTER YEAR

  if ($("year")) {
    $("year").textContent = new Date().getFullYear();
  }

  // INITIAL PAGE

  showView("home");

})();
