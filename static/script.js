(() => {
  "use strict";

  const $ = id => document.getElementById(id);

  const panelNames = [
    "websites",
    "tools",
    "images",
    "news",
    "notifications",
    "centres",
    "vault"
  ];

  const panels = Object.fromEntries(
    panelNames.map(name => [name, $(name + "Panel")])
  );

  let allWebsites = [];
  let selectedCategory = "all";
  let newsLoaded = false;
  let latestNews = [];
  let alertsLoaded = false;
  let governmentCentres = [];
  let selectedCentreCategory = "all";

  $("year").textContent = new Date().getFullYear();

  const builtInWebsites = [
    ["Instagram","https://www.instagram.com/","social","फोटो और Reels"],
    ["Facebook","https://www.facebook.com/","social","सोशल मीडिया"],
    ["YouTube","https://www.youtube.com/","social","वीडियो और चैनल"],
    ["WhatsApp","https://www.whatsapp.com/","social","मैसेज और कॉल"],
    ["Telegram","https://web.telegram.org/","social","मैसेज और चैनल"],
    ["LinkedIn","https://www.linkedin.com/","social","प्रोफेशनल नेटवर्क"],
    ["PAN Services","https://www.protean-tinpan.com/","government","PAN सेवाएँ"],
    ["UIDAI Aadhaar","https://uidai.gov.in/","government","आधार की आधिकारिक वेबसाइट"],
    ["DigiLocker","https://www.digilocker.gov.in/","government","डिजिटल दस्तावेज़"],
    ["Rajasthan SSO","https://sso.rajasthan.gov.in/","government","राजस्थान ऑनलाइन सेवाएँ"],
    ["Cyber Crime Portal","https://cybercrime.gov.in/","government","साइबर शिकायत"],
    ["National Consumer Helpline","https://consumerhelpline.gov.in/","government","उपभोक्ता शिकायत"],
    ["Indian Railways","https://indianrailways.gov.in/","jobs","रेलवे"],
    ["IRCTC","https://www.irctc.co.in/","travel","रेल टिकट"],
    ["RRB","https://www.rrbcdg.gov.in/","jobs","रेलवे भर्ती"],
    ["SSC","https://ssc.gov.in/","jobs","सरकारी भर्ती"],
    ["RPSC","https://rpsc.rajasthan.gov.in/","jobs","राजस्थान भर्ती"],
    ["National Career Service","https://www.ncs.gov.in/","jobs","नौकरी"],
    ["Scholarship Portal","https://scholarships.gov.in/","education","छात्रवृत्ति"],
    ["NTA","https://nta.ac.in/","education","परीक्षा"],
    ["SWAYAM","https://swayam.gov.in/","education","ऑनलाइन पढ़ाई"],
    ["RBI","https://www.rbi.org.in/","finance","रिजर्व बैंक"],
    ["SBI","https://sbi.co.in/","finance","बैंकिंग"],
    ["Amazon India","https://www.amazon.in/","shopping","ऑनलाइन खरीदारी"],
    ["Flipkart","https://www.flipkart.com/","shopping","ऑनलाइन खरीदारी"],
    ["Google News","https://news.google.com/","news","समाचार"],
    ["PIB India","https://pib.gov.in/","news","सरकारी प्रेस रिलीज़"],
    ["GitHub","https://github.com/","technology","कोड और प्रोजेक्ट"],
    ["Python","https://www.python.org/","technology","Python programming"],
    ["MDN Web Docs","https://developer.mozilla.org/","technology","वेब डेवलपमेंट"],
    ["Photopea","https://www.photopea.com/","technology","फोटो एडिटिंग"],
    ["Canva","https://www.canva.com/","technology","पोस्टर डिजाइन"],
    ["Pexels","https://www.pexels.com/","technology","फोटो और वीडियो"],
    ["Google Maps","https://maps.google.com/","travel","मैप और रास्ते"],
    ["RSRTC","https://rsrtconline.rajasthan.gov.in/","travel","राजस्थान रोडवेज"],
    ["Ayushman Bharat","https://pmjay.gov.in/","health","स्वास्थ्य योजना"],
    ["ABHA","https://abha.abdm.gov.in/","health","स्वास्थ्य खाता"]
  ].map(([name,url,category,description]) => ({
    name,url,category,description
  }));

  const tools = [
    {
      name:"Photopea",
      url:"https://www.photopea.com/",
      category:"technology",
      description:"फोटो एडिटिंग"
    },
    {
      name:"Canva",
      url:"https://www.canva.com/",
      category:"technology",
      description:"पोस्टर और डिजाइन"
    },
    {
      name:"Pexels",
      url:"https://www.pexels.com/",
      category:"technology",
      description:"फोटो और वीडियो"
    },
    {
      name:"Pixabay",
      url:"https://pixabay.com/",
      category:"technology",
      description:"चित्र और फोटो"
    },
    {
      name:"freeCodeCamp",
      url:"https://www.freecodecamp.org/",
      category:"education",
      description:"मुफ्त कोडिंग"
    },
    {
      name:"CodePen",
      url:"https://codepen.io/",
      category:"technology",
      description:"HTML, CSS और JavaScript"
    },
    {
      name:"Stack Overflow",
      url:"https://stackoverflow.com/",
      category:"technology",
      description:"प्रोग्रामिंग सवाल-जवाब"
    },
    {
      name:"Google Translate",
      url:"https://translate.google.com/",
      category:"technology",
      description:"भाषा अनुवाद"
    }
  ];

  function validUrl(value) {
    try {
      const url = new URL(value);
      return url.protocol === "https:" ||
             url.protocol === "http:";
    } catch {
      return false;
    }
  }

  function normalizeSite(item) {
    const name = String(
      item.name || item.title || ""
    ).trim();

    const url = String(
      item.url || item.link || ""
    ).trim();

    if (!name || !validUrl(url)) return null;

    return {
      name,
      url,
      category: String(
        item.category || "general"
      ).toLowerCase(),
      description: String(
        item.description ||
        item.category ||
        "वेबसाइट खोलें"
      )
    };
  }

  function logoFor(url) {
    const img = document.createElement("img");

    img.className = "site-logo";
    img.alt = "";
    img.loading = "lazy";
    img.referrerPolicy = "no-referrer";

    try {
      const host = new URL(url).hostname;

      img.src =
        "https://www.google.com/s2/favicons?domain=" +
        encodeURIComponent(host) +
        "&sz=128";

      img.addEventListener("error", () => {
        img.hidden = true;
      }, {once:true});

    } catch {
      img.hidden = true;
    }

    return img;
  }

  function renderCards(container,items,options={}) {
    container.replaceChildren();

    let shown = 0;

    items.forEach(raw => {
      const item = normalizeSite(raw);

      if (!item) return;

      shown++;

      const card = document.createElement("a");

      card.className = options.resultCard
        ? "result-card"
        : "directory-card";

      card.href = item.url;
      card.target = "_blank";
      card.rel = "noopener noreferrer";

      if (options.logo) {
        card.appendChild(logoFor(item.url));
      }

      const copy = document.createElement("span");
      copy.className = "card-copy";

      const title = document.createElement("strong");
      title.textContent = item.name;

      const description = document.createElement("small");
      description.textContent = item.description;

      copy.append(title,description);
      card.appendChild(copy);

      container.appendChild(card);
    });

    if (!shown) {
      const empty = document.createElement("p");

      empty.className = "empty";
      empty.textContent =
        options.empty || "कोई परिणाम नहीं मिला।";

      container.appendChild(empty);
    }
  }

  function showView(name) {
    $("homePanel").hidden = name !== "home";
    $("searchResults").hidden = true;

    panelNames.forEach(key => {
      panels[key].hidden = key !== name;
    });

    document.querySelectorAll("[data-view]").forEach(link => {
      link.classList.toggle(
        "active",
        link.dataset.view === name
      );
    });

    if (name === "websites" && !allWebsites.length) {
      loadWebsites();
    }

    if (name === "home" && !alertsLoaded) {
      loadAlerts();
    }

    if (name === "tools") {
      renderTools();
    }

    if (name === "news" && !newsLoaded) {
      loadNews();
    }

    if (name === "centres" && !governmentCentres.length) {
      loadGovernmentCentres();
    }

    window.scrollTo({
      top:0,
      behavior:"smooth"
    });
  }

  document.querySelectorAll("[data-view]").forEach(link => {
    link.addEventListener("click",event => {
      event.preventDefault();

      showView(link.dataset.view);

      history.replaceState(
        null,
        "",
        "#" + link.dataset.view
      );
    });
  });

  async function loadWebsites() {
    $("websiteStatus").textContent =
      "वेबसाइटें लोड हो रही हैं...";

    try {
      const response = await fetch("/api/services");

      if (!response.ok) {
        throw new Error("HTTP " + response.status);
      }

      const data = await response.json();

      const combined = [
        ...builtInWebsites,
        ...(Array.isArray(data.results)
          ? data.results
          : [])
      ].map(normalizeSite).filter(Boolean);

      const seen = new Set();

      allWebsites = combined.filter(item => {
        const key = item.url
          .replace(/\/+$/,"")
          .toLowerCase();

        if (seen.has(key)) return false;

        seen.add(key);
        return true;
      });

      renderWebsites();

      $("websiteStatus").textContent =
        allWebsites.length +
        " वेबसाइटें उपलब्ध हैं।";

    } catch(error) {
      console.error(error);

      allWebsites = builtInWebsites;

      renderWebsites();

      $("websiteStatus").textContent =
        "स्थानीय वेबसाइट सूची दिखाई जा रही है।";
    }
  }

  function renderWebsites() {
    const query = $("websiteFilter")
      .value.trim().toLowerCase();

    const items = allWebsites.filter(site => {
      const text = (
        site.name + " " +
        site.url + " " +
        site.category + " " +
        site.description
      ).toLowerCase();

      const categoryMatch =
        selectedCategory === "all" ||
        site.category === selectedCategory ||
        (
          selectedCategory === "government" &&
          ["documents","legal","rajasthan"]
            .includes(site.category)
        );

      return categoryMatch &&
        (!query || text.includes(query));
    });

    renderCards($("websiteList"),items,{
      logo:true,
      empty:"कोई वेबसाइट नहीं मिली।"
    });
  }

  $("websiteFilter").addEventListener(
    "input",
    renderWebsites
  );

  $("websiteCategories").addEventListener(
    "click",
    event => {
      const button = event.target.closest(
        "[data-category]"
      );

      if (!button) return;

      selectedCategory = button.dataset.category;

      $("websiteCategories")
        .querySelectorAll("[data-category]")
        .forEach(item => {
          item.classList.toggle(
            "active",
            item === button
          );
        });

      renderWebsites();
    }
  );
    // GOVERNMENT INFORMATION CENTRE

  async function loadGovernmentCentres() {
    $("centreStatus").textContent =
      "सरकारी केंद्र लोड हो रहे हैं...";

    $("centreList").replaceChildren();

    try {
      const response = await fetch("/api/future/centres");

      if (!response.ok) {
        throw new Error("HTTP " + response.status);
      }

      const data = await response.json();

      if (!data.success || !Array.isArray(data.categories)) {
        throw new Error("Invalid Government Centres response");
      }

      governmentCentres = data.categories;

      renderGovernmentCentres();

      $("centreStatus").textContent =
        (data.total_links || 0) +
        " आधिकारिक लिंक " +
        governmentCentres.length +
        " केंद्रों में उपलब्ध हैं।";

    } catch (error) {
      console.error(
        "Government Centres load failed:",
        error
      );

      $("centreStatus").textContent =
        "सरकारी केंद्र लोड नहीं हुए। कृपया API /api/future/centres जाँचें।";
    }
  }

  function renderGovernmentCentres() {
    const query = $("centreFilter")
      .value.trim().toLowerCase();

    const container = $("centreList");

    container.replaceChildren();

    const centres = governmentCentres.filter(centre =>
      selectedCentreCategory === "all" ||
      centre.id === selectedCentreCategory
    );

    let shown = 0;

    centres.forEach(centre => {
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

      const group = document.createElement("section");
      group.className = "centre-group";

      const heading = document.createElement("h3");
      heading.textContent = centre.name;

      const summary = document.createElement("p");
      summary.className = "panel-status";
      summary.textContent = centre.description || "";

      group.append(heading,summary);

      const grid = document.createElement("div");
      grid.className = "directory-grid";

      items.forEach(item => {
        if (!validUrl(item.url)) return;

        const card = document.createElement("a");

        card.className = "directory-card";
        card.href = item.url;
        card.target = "_blank";
        card.rel = "noopener noreferrer";

        const copy = document.createElement("span");
        copy.className = "card-copy";

        const title = document.createElement("strong");
        title.textContent = item.name || "सरकारी सेवा";

        const description = document.createElement("small");
        description.textContent =
          item.description || "आधिकारिक पोर्टल खोलें";

        const source = document.createElement("span");
        source.className = "centre-source";

        source.textContent = item.source
          ? "स्रोत: " + item.source
          : "";

        copy.append(title,description,source);
        card.appendChild(copy);
        grid.appendChild(card);

        shown++;
      });

      group.appendChild(grid);
      container.appendChild(group);
    });

    if (!shown) {
      const empty = document.createElement("p");

      empty.className = "empty";
      empty.textContent =
        "इस खोज में कोई सरकारी लिंक नहीं मिला।";

      container.appendChild(empty);
    }
  }

  window.openGovernmentCentre = function(category) {
    const allowed = [
      "schemes",
      "documents",
      "scholarships",
      "exams",
      "skills"
    ];

    if (!allowed.includes(category)) return;

    showView("centres");

    selectedCentreCategory = category;
    $("centreFilter").value = "";

    $("centreCategories")
      .querySelectorAll("[data-centre-category]")
      .forEach(button => {
        button.classList.toggle(
          "active",
          button.dataset.centreCategory === category
        );
      });

    if (governmentCentres.length) {
      renderGovernmentCentres();
    }

    history.replaceState(null,"","#centres");
  };

  $("centreFilter").addEventListener(
    "input",
    renderGovernmentCentres
  );

  $("centreCategories").addEventListener(
    "click",
    event => {
      const button = event.target.closest(
        "[data-centre-category]"
      );

      if (!button) return;

      selectedCentreCategory = button.dataset.centreCategory;

      $("centreCategories")
        .querySelectorAll("[data-centre-category]")
        .forEach(item => {
          item.classList.toggle(
            "active",
            item === button
          );
        });

      renderGovernmentCentres();
    }
  );

  // TOOLS

  function renderTools() {
    const query = $("toolFilter")
      .value.trim().toLowerCase();

    renderCards(
      $("toolList"),
      tools.filter(item =>
        (
          item.name + " " +
          item.description
        ).toLowerCase().includes(query)
      ),
      {logo:true}
    );
  }

  $("toolFilter").addEventListener(
    "input",
    renderTools
  );

  // IMAGE SEARCH

  async function searchImages(query) {
    $("imageStatus").textContent =
      "तस्वीरें खोजी जा रही हैं...";

    $("imageResults").replaceChildren();

    try {
      const response = await fetch(
        "/api/images?q=" + encodeURIComponent(query)
      );

      if (!response.ok) {
        throw new Error("HTTP " + response.status);
      }

      const data = await response.json();

      const items = Array.isArray(data.results)
        ? data.results
        : [];

      const container = $("imageResults");

      container.style.gridTemplateColumns =
        "repeat(auto-fit,minmax(180px,1fr))";

      items.forEach(item => {
        const src =
          item.image_url ||
          item.image ||
          item.src ||
          item.thumbnail;

        if (!validUrl(src)) return;

        const card = document.createElement("a");

        card.className = "directory-card";

        card.href = validUrl(item.page_url)
          ? item.page_url
          : src;

        card.target = "_blank";
        card.rel = "noopener noreferrer";
        card.style.display = "block";

        const img = document.createElement("img");

        img.src = src;
        img.alt = String(
          item.alt || item.title || query
        );

        img.loading = "lazy";
        img.style.width = "100%";
        img.style.height = "190px";
        img.style.objectFit = "cover";
        img.style.borderRadius = "8px";

        const caption = document.createElement("small");
        caption.textContent = String(item.title || query);

        img.addEventListener("error",() => {
          card.remove();
        },{once:true});

        card.append(img,caption);
        container.appendChild(card);
      });

      $("imageStatus").textContent = items.length
        ? items.length +
          " तस्वीरें मिलीं। स्रोत और लाइसेंस की शर्तें देखें।"
        : "कोई तस्वीर नहीं मिली।";

    } catch(error) {
      console.error(error);

      $("imageStatus").textContent =
        "Image API उपलब्ध नहीं है। app.py का अगला अपडेट जरूरी हो सकता है।";
    }
  }

  $("imageSearchForm").addEventListener(
    "submit",
    event => {
      event.preventDefault();

      const query = $("imageQuery").value.trim();

      if (query) {
        searchImages(query);
      }
    }
  );

  $("imageCategories").addEventListener(
    "click",
    event => {
      const button = event.target.closest(
        "[data-image-query]"
      );

      if (!button) return;

      $("imageQuery").value = button.dataset.imageQuery;

      searchImages(button.dataset.imageQuery);
    }
  );

  // NEWS

  async function loadNews() {
    $("newsStatus").textContent =
      "नई खबरें लोड हो रही हैं...";

    $("newsList").replaceChildren();

    try {
      const response = await fetch("/api/news?limit=15");

      if (!response.ok) {
        throw new Error("HTTP " + response.status);
      }

      const data = await response.json();

      latestNews = Array.isArray(data.results)
        ? data.results
        : [];

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

      renderCards($("newsList"),items,{
        empty:"अभी खबरें उपलब्ध नहीं हैं।"
      });

      $("newsStatus").textContent =
        latestNews.length + " खबरें मिलीं।";

      newsLoaded = true;

    } catch(error) {
      console.error(error);

      $("newsStatus").textContent =
        "खबरें लोड नहीं हुईं। app.py का news endpoint जाँचें।";
    }
  }

  // ISHWAR ALERT

  async function loadAlerts() {
    $("alertStatus").textContent =
      "Ishwar Alert के लिए ताज़ा अपडेट लोड हो रहे हैं...";

    $("alertList").replaceChildren();

    try {
      const response = await fetch(
        "/api/news?limit=5&refresh=1"
      );

      if (!response.ok) {
        throw new Error("HTTP " + response.status);
      }

      const data = await response.json();

      const items = Array.isArray(data.results)
        ? data.results
        : [];

      const alerts = items.map(item => ({
        name: item.title || item.name || "नई खबर",
        url: item.url || item.link,
        category: "alert",
        description: [
          item.source,
          item.published,
          item.description
        ].filter(Boolean).join(" • ") ||
          "ताज़ा समाचार अपडेट"
      }));

      renderCards($("alertList"),alerts,{
        empty:"अभी कोई नया अपडेट उपलब्ध नहीं है।"
      });

      $("alertStatus").textContent = alerts.length
        ? alerts.length +
          " ताज़ा अपडेट उपलब्ध हैं। खबर खोलकर स्रोत और तारीख जाँचें।"
        : "अभी कोई नया अपडेट उपलब्ध नहीं है।";

      alertsLoaded = true;

    } catch (error) {
      console.error(
        "Ishwar Alert load failed:",
        error
      );

      $("alertStatus").textContent =
        "अलर्ट लोड नहीं हुए। कृपया थोड़ी देर बाद फिर कोशिश करें।";
    }
  }

  $("refreshAlerts").addEventListener(
    "click",
    loadAlerts
  );

  $("refreshNews").addEventListener(
    "click",
    loadNews
  );
    // ISHWAR ALERT

  async function loadAlerts() {
    $("alertStatus").textContent =
      "Ishwar Alert के लिए ताज़ा अपडेट लोड हो रहे हैं...";

    $("alertList").replaceChildren();

    try {
      const response = await fetch(
        "/api/news?limit=5&refresh=1"
      );

      if (!response.ok) {
        throw new Error("HTTP " + response.status);
      }

      const data = await response.json();

      const items = Array.isArray(data.results)
        ? data.results
        : [];

      const alerts = items.map(item => ({
        name: item.title || item.name || "नई खबर",
        url: item.url || item.link,
        category: "alert",
        description: [
          item.source,
          item.published,
          item.description
        ].filter(Boolean).join(" • ") ||
          "ताज़ा समाचार अपडेट"
      }));

      renderCards($("alertList"),alerts,{
        empty:"अभी कोई नया अपडेट उपलब्ध नहीं है।"
      });

      $("alertStatus").textContent = alerts.length
        ? alerts.length +
          " ताज़ा अपडेट उपलब्ध हैं। खबर खोलकर स्रोत और तारीख जाँचें।"
        : "अभी कोई नया अपडेट उपलब्ध नहीं है।";

      alertsLoaded = true;

    } catch (error) {
      console.error(
        "Ishwar Alert load failed:",
        error
      );

      $("alertStatus").textContent =
        "अलर्ट लोड नहीं हुए। कृपया थोड़ी देर बाद फिर कोशिश करें।";
    }
  }

  $("refreshAlerts").addEventListener(
    "click",
    loadAlerts
  );

  $("refreshNews").addEventListener(
    "click",
    loadNews
  );

  // MAIN SEARCH

  async function performSearch(query) {
    showView("home");

    $("searchResults").hidden = false;

    $("resultsHeading").textContent =
      "“" + query + "” के परिणाम";

    $("resultsStatus").textContent = "खोज रहे हैं...";

    $("resultsList").replaceChildren();

    try {
      const response = await fetch(
        "/api/search?q=" +
        encodeURIComponent(query) +
        "&limit=30"
      );

      if (!response.ok) {
        throw new Error("HTTP " + response.status);
      }

      const data = await response.json();

      const results = Array.isArray(data.results)
        ? data.results
        : [];

      renderCards($("resultsList"),results,{
        logo:true,
        resultCard:true
      });

      $("resultsStatus").textContent = results.length
        ? results.length +
          " परिणाम मिले। कार्ड पर क्लिक करके वेबसाइट खोलें।"
        : "कोई परिणाम नहीं मिला। Websites सेक्शन भी देखें।";

    } catch(error) {
      console.error(error);

      $("resultsStatus").textContent =
        "सर्च सेवा उपलब्ध नहीं है। बाद में कोशिश करें।";
    }

    $("searchResults").scrollIntoView({
      behavior:"smooth",
      block:"start"
    });
  }

  $("searchForm").addEventListener(
    "submit",
    event => {
      event.preventDefault();

      const query = $("searchInput").value.trim();

      if (query) {
        performSearch(query);
      }
    }
  );

  // NEWS NOTIFICATIONS
  // Push subscription notifications.js संभालता है।

  $("notificationButton").addEventListener(
    "click",
    () => {
      showView("notifications");
    }
  );

  async function checkNewsNotification() {
    if (
      !("Notification" in window) ||
      Notification.permission !== "granted"
    ) {
      $("notificationStatus").textContent =
        "पहले Notification चालू करें।";

      return;
    }

    try {
      const response = await fetch(
        "/api/news?limit=5&refresh=1"
      );

      if (!response.ok) {
        throw new Error(
          "News API " + response.status
        );
      }

      const data = await response.json();

      const news = Array.isArray(data.results)
        ? data.results
        : [];

      if (!news.length) {
        $("notificationStatus").textContent =
          "अभी नई खबरें उपलब्ध नहीं हैं।";

        return;
      }

      const registration =
        await navigator.serviceWorker.ready;

      await registration.showNotification(
        "Ishwar Search — News Update",
        {
          body: String(
            news[0].title || "नई खबर उपलब्ध है।"
          ).slice(0,180),

          icon: "/static/logo.png",
          badge: "/static/logo.png",

          tag: "ishwar-search-manual-news-test",

          data: {
            url: news[0].url ||
                 news[0].link ||
                 "/"
          }
        }
      );

      $("notificationStatus").textContent =
        "ताज़ा खबर का टेस्ट नोटिफिकेशन दिखाया गया।";

      latestNews = news;

    } catch (error) {
      console.error(
        "News notification test failed:",
        error
      );

      $("notificationStatus").textContent =
        "खबर जाँच नहीं पाए। News API या Service Worker जाँचें।";
    }
  }

  $("checkNewsNotification").addEventListener(
    "click",
    checkNewsNotification
  );

  // THEME

  $("themeButton").addEventListener(
    "click",
    () => {
      const light =
        document.body.classList.toggle("light-mode");

      $("themeButton").textContent =
        light ? "☀" : "☾";
    }
  );

  // INITIAL PAGE

  showView("home");

})();
