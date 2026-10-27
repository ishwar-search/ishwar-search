
# ============================================================
# Ishwar Search
# Owner: Ishwar Ghanchi
# Version: 4.0.0
# ============================================================

import os
import re
import json
import html
import time
import logging
import threading
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

APP_NAME = "Ishwar Search"
OWNER_NAME = "Ishwar Ghanchi"
APP_VERSION = "4.0.0"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ishwar-search")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICES_FILE = os.path.join(BASE_DIR, "service.json")

HTTP_TIMEOUT = 8
MAX_NEWS_ITEMS = 20
NEWS_CACHE_SECONDS = 300

# ------------------------------------------------------------
# HTTP and text helpers
# ------------------------------------------------------------

def fetch_url(url, timeout=HTTP_TIMEOUT):
    """Fetch an HTTP/HTTPS URL and return decoded text."""
    parsed = urllib.parse.urlparse(url)

    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Invalid URL")

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "IshwarSearch/4.0 (public information service)",
            "Accept": "application/json, application/xml, text/xml, text/plain, */*",
        },
    )

    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


def clean_text(value):
    """Remove HTML markup and normalize whitespace."""
    if value is None:
        return ""

    value = html.unescape(str(value))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_text(value):
    """Normalize search text while preserving Hindi and English letters."""
    value = clean_text(value).casefold()
    value = value.replace("&", " and ")
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def safe_url(value):
    """Allow only valid HTTP and HTTPS links."""
    if not value:
        return ""

    value = str(value).strip()

    try:
        parsed = urllib.parse.urlparse(value)
    except ValueError:
        return ""

    if parsed.scheme not in ("http", "https"):
        return ""

    if not parsed.netloc:
        return ""

    return value


def json_error(message, status=400):
    return jsonify({
        "success": False,
        "error": message,
    }), status


def utc_now():
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------
# Service directory
# ------------------------------------------------------------

def load_services():
    """
    Read service.json.
    Supports either a list or {"services": [...]}.
    """
    if not os.path.isfile(SERVICES_FILE):
        logger.warning("service.json was not found at %s", SERVICES_FILE)
        return []

    try:
        with open(SERVICES_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, dict):
            data = data.get("services", [])

        if not isinstance(data, list):
            logger.warning("service.json must contain a list of services")
            return []

        services = []

        for item in data:
            if not isinstance(item, dict):
                continue

            name = clean_text(
                item.get("name")
                or item.get("title")
                or item.get("label")
            )

            url = safe_url(item.get("url") or item.get("link"))

            if not name or not url:
                continue

            keywords = item.get("keywords", "")
            if isinstance(keywords, list):
                keywords = " ".join(map(str, keywords))

            services.append({
                "name": name,
                "title": name,
                "url": url,
                "description": clean_text(item.get("description", "")),
                "category": clean_text(item.get("category", "General")),
                "keywords": clean_text(keywords),
            })

        return services

    except (OSError, json.JSONDecodeError) as exc:
        logger.exception("Could not read service.json: %s", exc)
        return []


# Common synonyms help users search with different wording.
SEARCH_SYNONYMS = {
    "railway": ["rrb", "rail", "रेलवे", "रेल", "ट्रेन"],
    "rrb": ["railway", "रेलवे"],
    "job": ["jobs", "recruitment", "vacancy", "नौकरी", "भर्ती"],
    "jobs": ["job", "recruitment", "vacancy", "नौकरी", "भर्ती"],
    "recruitment": ["job", "jobs", "vacancy", "भर्ती", "नौकरी"],
    "scholarship": ["छात्रवृत्ति", "स्कॉलरशिप", "छात्र"],
    "aadhaar": ["aadhar", "आधार", "uidai"],
    "aadhar": ["aadhaar", "आधार", "uidai"],
    "weather": ["मौसम", "तापमान"],
    "gold": ["सोना", "gold rate"],
    "silver": ["चांदी", "चाँदी", "silver rate"],
    "mandi": ["मंडी", "कृषि मंडी", "agmarknet"],
    "share": ["stock", "stocks", "शेयर", "शेयर बाजार"],
    "stock": ["share", "stocks", "शेयर बाजार"],
    "news": ["खबर", "समाचार", "ताजा खबर"],
    "cyber": ["cybercrime", "साइबर", "फ्रॉड", "fraud"],
}


def expand_search_words(query):
    """Expand common search terms without requiring external search engines."""
    words = normalize_text(query).split()
    expanded = list(words)

    for word in words:
        for synonym in SEARCH_SYNONYMS.get(word, []):
            normalized = normalize_text(synonym)
            if normalized and normalized not in expanded:
                expanded.append(normalized)

    return expanded


def search_services(query, limit=30):
    """Search local service links with partial and phrase matching."""
    query = normalize_text(query)

    if not query:
        return []

    services = load_services()
    query_words = expand_search_words(query)
    matches = []

    for service in services:
        name = normalize_text(service.get("name", ""))
        description = normalize_text(service.get("description", ""))
        category = normalize_text(service.get("category", ""))
        keywords = normalize_text(service.get("keywords", ""))

        searchable = " ".join([name, description, category, keywords])

        score = 0

        # Full phrase match gets a higher score.
        if query and query in searchable:
            score += 8

        for word in query_words:
            if not word:
                continue

            if word in name:
                score += 5
            elif word in keywords:
                score += 4
            elif word in category:
                score += 3
            elif word in description:
                score += 2
            elif word in searchable:
                score += 1

        if score > 0:
            matches.append((score, service))

    matches.sort(
        key=lambda item: (-item[0], item[1]["name"].casefold())
    )

    return [service for _, service in matches[:max(1, min(limit, 100))]]


# ------------------------------------------------------------
# News feeds
# ------------------------------------------------------------

NEWS_FEEDS = [
    {
        "name": "Google News Hindi",
        "url": "https://news.google.com/rss?hl=hi&gl=IN&ceid=IN:hi",
    },
    {
        "name": "Google News India",
        "url": "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en",
    },
    {
        "name": "BBC Hindi",
        "url": "https://feeds.bbci.co.uk/hindi/rss.xml",
    },
]

_news_cache = []
_news_cache_time = 0
_news_lock = threading.Lock()


def get_xml_text(element, names):
    """Find a direct XML child by local tag name."""
    for child in list(element):
        local_name = child.tag.split("}")[-1].lower()

        if local_name in names:
            return "".join(child.itertext()).strip()

    return ""


def extract_news_items(xml_text, source_name):
    """Parse RSS items and Atom entries."""
    root = ET.fromstring(xml_text)
    results = []

    for node in root.iter():
        tag = node.tag.split("}")[-1].lower()

        if tag not in ("item", "entry"):
            continue

        title = get_xml_text(node, {"title"})
        description = get_xml_text(
            node, {"description", "summary", "content", "encoded"}
        )
        published = get_xml_text(
            node, {"pubdate", "published", "updated", "date"}
        )

        link = get_xml_text(node, {"link"})

        # Atom feeds often store URLs in a link attribute.
        if not link:
            for child in list(node):
                if child.tag.split("}")[-1].lower() == "link":
                    rel = child.attrib.get("rel", "alternate")
                    href = child.attrib.get("href", "")

                    if rel == "alternate" and href:
                        link = href
                        break

        link = safe_url(link)
        title = clean_text(title)
        description = clean_text(description)

        if not title or not link:
            continue

        results.append({
            "title": title,
            "description": description,
            "url": link,
            "source": source_name,
            "published": clean_text(published),
        })

    return results

# ------------------------------------------------------------
# News loading, caching and search
# ------------------------------------------------------------

def fetch_news(query="", force_refresh=False):
    global _news_cache, _news_cache_time

    now = time.time()

    with _news_lock:
        cache_is_valid = (
            bool(_news_cache)
            and now - _news_cache_time < NEWS_CACHE_SECONDS
        )

        if cache_is_valid and not force_refresh:
            all_news = list(_news_cache)
        else:
            all_news = []

            for feed in NEWS_FEEDS:
                try:
                    xml_text = fetch_url(feed["url"], timeout=6)
                    all_news.extend(
                        extract_news_items(xml_text, feed["name"])
                    )
                except Exception as exc:
                    logger.warning(
                        "News feed failed (%s): %s",
                        feed["name"], exc
                    )

            unique = []
            seen_urls = set()

            for item in all_news:
                url = item.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique.append(item)

            all_news = unique
            _news_cache = list(all_news)
            _news_cache_time = now

    query_words = normalize_text(query).split()

    if query_words:
        filtered = []

        for item in all_news:
            searchable = normalize_text(" ".join([
                item.get("title", ""),
                item.get("description", ""),
                item.get("source", ""),
            ]))

            if all(word in searchable for word in query_words):
                filtered.append(item)

        return filtered[:MAX_NEWS_ITEMS]

    return all_news[:MAX_NEWS_ITEMS]


# ------------------------------------------------------------
# Weather: Open-Meteo free endpoints
# ------------------------------------------------------------

def get_location_details(place):
    """Find a location, preferring an exact Indian place name."""
    place = clean_text(place)

    if not place:
        return None

    params = urllib.parse.urlencode({
        "name": place,
        "count": 10,
        "language": "en",
        "format": "json",
        "countryCode": "IN",
    })

    url = "https://geocoding-api.open-meteo.com/v1/search?" + params

    try:
        response = json.loads(fetch_url(url, timeout=7))
        results = response.get("results", [])

        if not results:
            return None

        india_results = [
            item for item in results
            if item.get("country_code") == "IN"
        ]
        candidates = india_results or results
        place_lower = place.casefold()

        for item in candidates:
            if item.get("name", "").casefold() == place_lower:
                return item

        return candidates[0]

    except Exception as exc:
        logger.warning("Geocoding failed: %s", exc)
        return None


def get_weather(place):
    location = get_location_details(place)

    if not location:
        return {
            "success": False,
            "error": "इस जगह का मौसम नहीं मिला। शहर का नाम जाँचें।",
        }

    params = urllib.parse.urlencode({
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "current": (
            "temperature_2m,"
            "relative_humidity_2m,"
            "apparent_temperature,"
            "is_day,"
            "precipitation,"
            "weather_code,"
            "wind_speed_10m"
        ),
        "timezone": "auto",
    })

    url = "https://api.open-meteo.com/v1/forecast?" + params

    try:
        response = json.loads(fetch_url(url, timeout=7))
        current = response.get("current", {})

        if "temperature_2m" not in current:
            return {
                "success": False,
                "error": "मौसम की जानकारी अभी उपलब्ध नहीं है।",
            }

        return {
            "success": True,
            "place": location.get("name", place),
            "city": location.get("name", place),
            "region": (
                location.get("admin2")
                or location.get("admin1")
                or ""
            ),
            "country": location.get("country", ""),
            "latitude": location.get("latitude"),
            "longitude": location.get("longitude"),
            "temperature": current.get("temperature_2m"),
            "feels_like": current.get("apparent_temperature"),
            "humidity": current.get("relative_humidity_2m"),
            "wind_speed": current.get("wind_speed_10m"),
            "precipitation": current.get("precipitation"),
            "weather_code": current.get("weather_code"),
            "is_day": current.get("is_day"),
            "time": current.get("time"),
            "timezone": response.get("timezone", ""),
            "source": "Open-Meteo",
        }

    except Exception as exc:
        logger.warning("Weather request failed: %s", exc)
        return {
            "success": False,
            "error": "मौसम सर्वर से संपर्क नहीं हो पाया। बाद में प्रयास करें।",
        }


# ------------------------------------------------------------
# Live Rates: honest source directory
# ------------------------------------------------------------

RATE_SOURCES = {
    "gold": {
        "title": "सोना",
        "description": "ताज़ा सोने का भाव स्रोत वेबसाइट पर देखें।",
        "url": "https://www.goodreturns.in/gold-rates/",
    },
    "silver": {
        "title": "चाँदी",
        "description": "ताज़ा चाँदी का भाव स्रोत वेबसाइट पर देखें।",
        "url": "https://www.goodreturns.in/silver-rates/",
    },
    "stock_market": {
        "title": "शेयर बाजार",
        "description": "शेयर बाजार और इंडेक्स के लिए NSE वेबसाइट देखें।",
        "url": "https://www.nseindia.com/",
    },
    "mandi": {
        "title": "मंडी भाव",
        "description": "कृषि मंडी के उपलब्ध भाव AGMARKNET पर देखें।",
        "url": "https://agmarknet.gov.in/",
    },
}


def get_rates(place="Rajasthan"):
    """
    Return verified source links, not invented prices.

    A real price is returned only when a trusted, configured data
    provider is integrated. No paid API is called here.
    """
    place = clean_text(place) or "Rajasthan"

    rates = {}

    for key, source in RATE_SOURCES.items():
        rates[key] = {
            "value": "स्रोत पर देखें",
            "unit": "",
            "description": source["description"],
            "source": source["url"],
            "updated_at": None,
            "is_live_value": False,
        }

    # State/area selection is included for a future verified mandi API.
    return {
        "success": True,
        "place": place,
        "updated_at": utc_now(),
        "live_prices_available": False,
        "rates": rates,
        "message": (
            "यहाँ सत्यापित स्रोत लिंक दिए गए हैं। "
            "अभी वास्तविक कीमतों का सीधा डेटा कनेक्शन नहीं है।"
        ),
    }


# ------------------------------------------------------------
# Main pages
# ------------------------------------------------------------

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/health")
def health():
    return jsonify({
        "success": True,
        "app": APP_NAME,
        "version": APP_VERSION,
        "status": "running",
        "time": utc_now(),
    })


@app.route("/api/about")
def about():
    return jsonify({
        "success": True,
        "name": APP_NAME,
        "owner": OWNER_NAME,
        "version": APP_VERSION,
        "features": [
            "Service directory search",
            "RSS news updates",
            "Open-Meteo weather",
            "Market rate source links",
            "Shopping links in frontend",
        ],
    })


# ------------------------------------------------------------
# Search and services API
# ------------------------------------------------------------

@app.route("/api/search")
def api_search():
    query = clean_text(request.args.get("q", ""))

    if not query:
        return jsonify({
            "success": True,
            "query": "",
            "count": 0,
            "results": [],
            "message": "खोजने के लिए कुछ लिखें।",
        })

    limit = request.args.get("limit", "30")

    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 30

    limit = max(1, min(limit, 100))
    results = search_services(query, limit=limit)

    return jsonify({
        "success": True,
        "query": query,
        "count": len(results),
        "results": results,
        "message": "" if results else "कोई मिलान नहीं मिला।",
    })


@app.route("/api/services")
def api_services():
    query = clean_text(request.args.get("q", ""))

    if query:
        services = search_services(query)
    else:
        services = load_services()[:100]

    return jsonify({
        "success": True,
        "count": len(services),
        "services": services,
    })


@app.route("/api/search-services")
def api_search_services():
    """Compatibility endpoint for older frontend versions."""
    return api_search()


# ------------------------------------------------------------
# News API
# ------------------------------------------------------------

@app.route("/api/news")
def api_news():
    query = clean_text(request.args.get("q", ""))
    refresh = request.args.get("refresh", "").casefold()
    force_refresh = refresh in ("1", "true", "yes")

    news = fetch_news(query=query, force_refresh=force_refresh)

    return jsonify({
        "success": True,
        "count": len(news),
        "query": query,
        "updated_at": utc_now(),
        "news": news,
        "message": "कोई खबर नहीं मिली।" if not news else "",
    })


@app.route("/api/latest-news")
def api_latest_news():
    """Compatibility endpoint for older frontend versions."""
    return api_news()


# ------------------------------------------------------------
# Weather API
# ------------------------------------------------------------

@app.route("/api/weather")
def api_weather():
    place = clean_text(
        request.args.get("place", "")
        or request.args.get("q", "")
    )

    if not place:
        return json_error("शहर या गाँव का नाम लिखें।")

    result = get_weather(place)

    if not result.get("success"):
        return jsonify(result), 502

    return jsonify(result)


@app.route("/api/current-weather")
def api_current_weather():
    """Compatibility endpoint for older frontend versions."""
    return api_weather()


# ------------------------------------------------------------
# Rates API
# ------------------------------------------------------------

@app.route("/api/rates")
def api_rates():
    place = clean_text(
        request.args.get("place", "Rajasthan")
    ) or "Rajasthan"

    return jsonify(get_rates(place))

# ------------------------------------------------------------
# Additional compatibility endpoints
# ------------------------------------------------------------

@app.route("/api/health")
def api_health():
    """Alternative health-check endpoint."""
    return health()


# ------------------------------------------------------------
# Error handlers
# ------------------------------------------------------------

@app.errorhandler(404)
def page_not_found(error):
    if request.path.startswith("/api/"):
        return jsonify({
            "success": False,
            "error": "यह API endpoint नहीं मिला।",
        }), 404

    return (
        "<!DOCTYPE html><html lang='hi'><meta charset='utf-8'>"
        "<title>404 | Ishwar Search</title>"
        "<h1>Ishwar Search</h1>"
        "<p>यह पेज नहीं मिला।</p>"
        "<a href='/'>Ishwar Search पर वापस जाएँ</a>",
        404,
    )


@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({
        "success": False,
        "error": "इस अनुरोध का तरीका उपलब्ध नहीं है।",
    }), 405


@app.errorhandler(500)
def internal_server_error(error):
    logger.error(
        "Internal server error on %s",
        request.path,
        exc_info=True,
    )

    if request.path.startswith("/api/"):
        return jsonify({
            "success": False,
            "error": "सर्वर में समस्या आई। कृपया बाद में प्रयास करें।",
        }), 500

    return (
        "<!DOCTYPE html><html lang='hi'><meta charset='utf-8'>"
        "<title>500 | Ishwar Search</title>"
        "<h1>Ishwar Search</h1>"
        "<p>सर्वर में समस्या आई। कृपया बाद में प्रयास करें।</p>"
        "<a href='/'>होम पेज पर जाएँ</a>",
        500,
    )


# ------------------------------------------------------------
# Run locally / Render
# ------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
    )
