# ============================================================
# Ishwar Search
# Owner: Ishwar Ghanchi
# Version: 3.0.0
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
APP_VERSION = "3.0.0"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ishwar-search")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICES_FILE = os.path.join(BASE_DIR, "service.json")

HTTP_TIMEOUT = 8
MAX_NEWS_ITEMS = 20

# ------------------------------------------------------------
# HTTP helper
# ------------------------------------------------------------

def fetch_url(url, timeout=HTTP_TIMEOUT):
    """Fetch a URL and return its response text."""
    request_obj = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
            ),
            "Accept": "*/*",
        },
    )

    with urllib.request.urlopen(
        request_obj, timeout=timeout
    ) as response:
        data = response.read()

        charset = response.headers.get_content_charset() or "utf-8"
        return data.decode(charset, errors="replace")


def clean_text(value):
    """Remove HTML markup and normalize text."""
    if not value:
        return ""

    value = html.unescape(str(value))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def safe_url(value):
    """Allow only HTTP and HTTPS links."""
    if not value:
        return ""

    value = str(value).strip()
    parsed = urllib.parse.urlparse(value)

    if parsed.scheme not in ("http", "https"):
        return ""

    if not parsed.netloc:
        return ""

    return value


def json_error(message, status=400):
    return jsonify({
        "success": False,
        "error": message
    }), status


# ------------------------------------------------------------
# Service links
# ------------------------------------------------------------

def load_services():
    """
    Read service links from service.json.
    Accepts either a list or an object containing 'services'.
    """
    if not os.path.exists(SERVICES_FILE):
        logger.warning("service.json was not found.")
        return []

    try:
        with open(
            SERVICES_FILE, "r", encoding="utf-8"
        ) as file:
            data = json.load(file)

        if isinstance(data, dict):
            data = data.get("services", [])

        if not isinstance(data, list):
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

            url = safe_url(
                item.get("url")
                or item.get("link")
            )

            if not name or not url:
                continue

            services.append({
                "name": name,
                "url": url,
                "description": clean_text(
                    item.get("description", "")
                ),
                "category": clean_text(
                    item.get("category", "General")
                ),
                "keywords": clean_text(
                    item.get("keywords", "")
                ),
            })

        return services

    except (OSError, json.JSONDecodeError) as exc:
        logger.exception("Could not load service.json: %s", exc)
        return []


def search_services(query, limit=30):
    """Search the local service directory."""
    query = clean_text(query).lower()

    if not query:
        return []

    words = query.split()
    matches = []

    for service in load_services():
        searchable = " ".join([
            service.get("name", ""),
            service.get("description", ""),
            service.get("category", ""),
            service.get("keywords", ""),
        ]).lower()

        score = sum(
            1 for word in words if word in searchable
        )

        if score:
            matches.append((score, service))

    matches.sort(
        key=lambda item: (
            item[0],
            item[1].get("name", "").lower()
        ),
        reverse=True
    )

    return [
        item[1] for item in matches[:limit]
    ]


# ------------------------------------------------------------
# News feeds
# ------------------------------------------------------------

NEWS_FEEDS = [
    {
        "name": "Google News Hindi",
        "url": (
            "https://news.google.com/rss"
            "?hl=hi&gl=IN&ceid=IN:hi"
        ),
    },
    {
        "name": "Google News India",
        "url": (
            "https://news.google.com/rss"
            "?hl=en-IN&gl=IN&ceid=IN:en"
        ),
    },
    {
        "name": "BBC Hindi",
        "url": "https://feeds.bbci.co.uk/hindi/rss.xml",
    },
]

_news_cache = []
_news_cache_time = 0
_news_lock = threading.Lock()
NEWS_CACHE_SECONDS = 300


def get_xml_text(element, names):
    """Find an XML child by local tag name."""
    for child in list(element):
        local_name = child.tag.split("}")[-1].lower()

        if local_name in names:
            return "".join(child.itertext()).strip()

    return ""


def extract_news_items(xml_text, source_name):
    """Read RSS items and Atom entries."""
    root = ET.fromstring(xml_text)
    results = []

    for node in root.iter():
        tag = node.tag.split("}")[-1].lower()

        if tag not in ("item", "entry"):
            continue

        title = get_xml_text(node, {"title"})
        description = get_xml_text(
            node, {"description", "summary", "content"}
        )
        published = get_xml_text(
            node,
            {"pubdate", "published", "updated", "date"}
        )

        link = get_xml_text(node, {"link"})

        # Atom feeds may store the URL in a link attribute.
        if not link:
            for child in list(node):
                if child.tag.split("}")[-1].lower() == "link":
                    rel = child.attrib.get("rel", "alternate")

                    if rel == "alternate":
                        link = child.attrib.get("href", "")
                        if link:
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
# News loading and search
# ------------------------------------------------------------

def fetch_news(query="", force_refresh=False):
    global _news_cache, _news_cache_time

    now = time.time()

    with _news_lock:
        cache_is_valid = (
            _news_cache
            and now - _news_cache_time < NEWS_CACHE_SECONDS
        )

        if cache_is_valid and not force_refresh:
            all_news = list(_news_cache)
        else:
            all_news = []

            for feed in NEWS_FEEDS:
                try:
                    xml_text = fetch_url(
                        feed["url"], timeout=6
                    )

                    items = extract_news_items(
                        xml_text, feed["name"]
                    )

                    all_news.extend(items)

                except Exception as exc:
                    # One failed feed must not stop other feeds.
                    logger.warning(
                        "News feed failed (%s): %s",
                        feed["name"], exc
                    )

            # Remove duplicate article URLs.
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

    query = clean_text(query).lower()

    if query:
        words = query.split()

        filtered = []

        for item in all_news:
            text = " ".join([
                item.get("title", ""),
                item.get("description", ""),
                item.get("source", ""),
            ]).lower()

            if all(word in text for word in words):
                filtered.append(item)

        return filtered[:MAX_NEWS_ITEMS]

    return all_news[:MAX_NEWS_ITEMS]


# ------------------------------------------------------------
# Weather
# ------------------------------------------------------------

def get_location_details(place):
    """
    Find a place using Open-Meteo geocoding.
    Prefer results located in India.
    """
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

    url = (
        "https://geocoding-api.open-meteo.com/v1/search?"
        + params
    )

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
        place_lower = place.lower()

        # Prefer an exact name match.
        for item in candidates:
            if item.get("name", "").lower() == place_lower:
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
            "error": "इस जगह का मौसम नहीं मिला। नाम जाँचकर दोबारा प्रयास करें।"
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

    url = (
        "https://api.open-meteo.com/v1/forecast?"
        + params
    )

    try:
        response = json.loads(fetch_url(url, timeout=7))
        current = response.get("current", {})

        if not current:
            return {
                "success": False,
                "error": "मौसम की जानकारी अभी उपलब्ध नहीं है।"
            }

        return {
            "success": True,
            "place": location.get("name", place),
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
        }

    except Exception as exc:
        logger.warning("Weather request failed: %s", exc)

        return {
            "success": False,
            "error": "मौसम सर्वर से संपर्क नहीं हो पाया। थोड़ी देर बाद प्रयास करें।"
        }


# ------------------------------------------------------------
# Main pages
# ------------------------------------------------------------

@app.route("/")
def home():
    try:
        return render_template("index.html")
    except Exception:
        return (
            "<h1>Ishwar Search</h1>"
            "<p>Owner: Ishwar Ghanchi</p>"
            "<p>templates/index.html फ़ाइल नहीं मिली।</p>"
        )


@app.route("/health")
def health():
    return jsonify({
        "success": True,
        "app": APP_NAME,
        "version": APP_VERSION,
        "status": "running",
        "time": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/api/about")
def about():
    return jsonify({
        "success": True,
        "name": APP_NAME,
        "owner": OWNER_NAME,
        "version": APP_VERSION,
        "features": [
            "Search",
            "Service directory",
            "News",
            "Weather",
        ],
    })


# ------------------------------------------------------------
# Search API
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

    results = search_services(query)

    return jsonify({
        "success": True,
        "query": query,
        "count": len(results),
        "results": results,
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


# ------------------------------------------------------------
# News API
# ------------------------------------------------------------

@app.route("/api/news")
def api_news():
    query = clean_text(request.args.get("q", ""))

    refresh = request.args.get("refresh", "").lower()
    force_refresh = refresh in ("1", "true", "yes")

    news = fetch_news(
        query=query,
        force_refresh=force_refresh,
    )

    return jsonify({
        "success": True,
        "count": len(news),
        "query": query,
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "news": news,
        "message": (
            "कोई खबर नहीं मिली।"
            if not news else ""
        ),
    })


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
        return json_error(
            "शहर या गाँव का नाम लिखें।"
        )

    result = get_weather(place)

    if not result.get("success"):
        return jsonify(result), 502

    return jsonify(result)
    # ------------------------------------------------------------
# Optional compatibility endpoints
# ------------------------------------------------------------

@app.route("/api/search-services")
def api_search_services():
    """Alternative endpoint for older frontend code."""
    return api_search()


@app.route("/api/latest-news")
def api_latest_news():
    """Alternative endpoint for older frontend code."""
    return api_news()


@app.route("/api/current-weather")
def api_current_weather():
    """Alternative endpoint for older frontend code."""
    return api_weather()


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
        "<h1>404</h1>"
        "<p>यह पेज नहीं मिला।</p>"
        "<a href='/'>Ishwar Search पर वापस जाएँ</a>",
        404,
    )


@app.errorhandler(500)
def internal_server_error(error):
    logger.exception("Internal server error")

    if request.path.startswith("/api/"):
        return jsonify({
            "success": False,
            "error": "सर्वर में समस्या आई।",
        }), 500

    return (
        "<h1>500</h1>"
        "<p>सर्वर में समस्या आई। कृपया बाद में प्रयास करें।</p>",
        500,
    )


# ------------------------------------------------------------
# Run locally
# ------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
    )
