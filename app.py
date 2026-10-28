# ============================================================
# Ishwar Search
# Owner: Ishwar Ghanchi
# Version: 5.0.0
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
APP_VERSION = "5.0.0"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ishwar-search")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICES_FILE = os.path.join(BASE_DIR, "service.json")

HTTP_TIMEOUT = 8
MAX_NEWS_ITEMS = 20
NEWS_CACHE_SECONDS = 300
IMAGE_CACHE_SECONDS = 600
PLACE_CACHE_SECONDS = 600

# Wikimedia Commons supplies openly licensed media.
# Place search uses OpenStreetMap Nominatim under its usage policy.
USER_AGENT = (
    "IshwarSearch/5.0 "
    "(https://ishwar-search.onrender.com; public search application)"
)

# ------------------------------------------------------------
# HTTP and text helpers
# ------------------------------------------------------------

def fetch_url(url, timeout=HTTP_TIMEOUT):
    """Fetch HTTP/HTTPS text using an identifiable User-Agent."""
    parsed = urllib.parse.urlparse(url)

    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Invalid URL")

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "application/json, application/xml, text/xml, "
                "text/plain, */*"
            ),
        },
    )

    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


def clean_text(value):
    if value is None:
        return ""

    value = html.unescape(str(value))
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_text(value):
    value = clean_text(value).casefold().replace("&", " and ")
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def safe_url(value):
    if not value:
        return ""

    try:
        parsed = urllib.parse.urlparse(str(value).strip())
    except ValueError:
        return ""

    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""

    return str(value).strip()


def json_error(message, status=400):
    return jsonify({"success": False, "error": message}), status


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def bounded_limit(value, default=20, maximum=50):
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = default

    return max(1, min(value, maximum))


# ------------------------------------------------------------
# Small in-memory cache
# ------------------------------------------------------------

_cache = {}
_cache_lock = threading.Lock()


def cache_get(key, max_age):
    with _cache_lock:
        entry = _cache.get(key)

        if not entry:
            return None

        created, value = entry

        if time.time() - created > max_age:
            _cache.pop(key, None)
            return None

        return value


def cache_set(key, value):
    with _cache_lock:
        _cache[key] = (time.time(), value)

        # Keep memory use bounded.
        if len(_cache) > 300:
            oldest = sorted(
                _cache,
                key=lambda item: _cache[item][0]
            )[:100]

            for old_key in oldest:
                _cache.pop(old_key, None)


# ------------------------------------------------------------
# Local service directory: service.json
# ------------------------------------------------------------

def load_services():
    if not os.path.isfile(SERVICES_FILE):
        logger.warning("service.json missing: %s", SERVICES_FILE)
        return []

    try:
        with open(SERVICES_FILE, "r", encoding="utf-8") as file:
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
        logger.exception("service.json read failed: %s", exc)
        return []


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
    "hospital": ["अस्पताल", "clinic", "चिकित्सालय"],
    "police": ["पुलिस", "थाना", "police station"],
    "hotel": ["होटल", "stay", "accommodation"],
    "school": ["स्कूल", "विद्यालय"],
    "restaurant": ["रेस्टोरेंट", "खाना", "food"],
    "photo": ["image", "images", "फोटो", "तस्वीर"],
    "video": ["वीडियो", "clips"],
}


def expand_search_words(query):
    words = normalize_text(query).split()
    expanded = list(words)

    for word in words:
        for synonym in SEARCH_SYNONYMS.get(word, []):
            normalized = normalize_text(synonym)
            if normalized and normalized not in expanded:
                expanded.append(normalized)

    return expanded


def search_services(query, limit=30):
    query = normalize_text(query)

    if not query:
        return []

    matches = []
    query_words = expand_search_words(query)

    for service in load_services():
        name = normalize_text(service["name"])
        description = normalize_text(service["description"])
        category = normalize_text(service["category"])
        keywords = normalize_text(service["keywords"])
        searchable = " ".join([name, description, category, keywords])

        score = 8 if query in searchable else 0

        for word in query_words:
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

        if score:
            matches.append((score, service))

    matches.sort(key=lambda pair: (-pair[0], pair[1]["name"].casefold()))
    return [
        service for _, service in matches[:bounded_limit(limit, 30, 100)]
    ]


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
    for child in list(element):
        if child.tag.split("}")[-1].lower() in names:
            return "".join(child.itertext()).strip()
    return ""


def extract_news_items(xml_text, source_name):
    root = ET.fromstring(xml_text)
    results = []

    for node in root.iter():
        if node.tag.split("}")[-1].lower() not in ("item", "entry"):
            continue

        title = clean_text(get_xml_text(node, {"title"}))
        description = clean_text(
            get_xml_text(node, {"description", "summary", "content", "encoded"})
        )
        published = clean_text(
            get_xml_text(node, {"pubdate", "published", "updated", "date"})
        )
        link = safe_url(get_xml_text(node, {"link"}))

        if not link:
            for child in list(node):
                if child.tag.split("}")[-1].lower() == "link":
                    if child.attrib.get("rel", "alternate") == "alternate":
                        link = safe_url(child.attrib.get("href", ""))
                        if link:
                            break

        if title and link:
            results.append({
                "title": title,
                "description": description,
                "url": link,
                "source": source_name,
                "published": published,
            })

    return results
    # ------------------------------------------------------------
# News loading and caching
# ------------------------------------------------------------

def fetch_news(query="", force_refresh=False):
    global _news_cache, _news_cache_time

    now = time.time()

    with _news_lock:
        valid = bool(_news_cache) and now - _news_cache_time < NEWS_CACHE_SECONDS

        if valid and not force_refresh:
            all_news = list(_news_cache)
        else:
            all_news = []

            for feed in NEWS_FEEDS:
                try:
                    xml_text = fetch_url(feed["url"], timeout=6)
                    all_news.extend(extract_news_items(xml_text, feed["name"]))
                except Exception as exc:
                    logger.warning("News feed failed (%s): %s", feed["name"], exc)

            unique = []
            seen = set()

            for item in all_news:
                if item["url"] not in seen:
                    seen.add(item["url"])
                    unique.append(item)

            all_news = unique
            _news_cache = list(unique)
            _news_cache_time = now

    words = normalize_text(query).split()

    if words:
        filtered = []
        for item in all_news:
            searchable = normalize_text(
                item["title"] + " " + item["description"] + " " + item["source"]
            )
            if all(word in searchable for word in words):
                filtered.append(item)
        return filtered[:MAX_NEWS_ITEMS]

    return all_news[:MAX_NEWS_ITEMS]


# ------------------------------------------------------------
# Weather: Open-Meteo
# ------------------------------------------------------------

def get_location_details(place):
    place = clean_text(place)
    if not place:
        return None

    key = "geocode:" + normalize_text(place)
    cached = cache_get(key, 3600)
    if cached is not None:
        return cached

    params = urllib.parse.urlencode({
        "name": place,
        "count": 10,
        "language": "en",
        "format": "json",
        "countryCode": "IN",
    })

    try:
        data = json.loads(fetch_url(
            "https://geocoding-api.open-meteo.com/v1/search?" + params,
            timeout=7,
        ))
        results = data.get("results", [])
        if not results:
            cache_set(key, None)
            return None

        candidates = [
            item for item in results
            if item.get("country_code") == "IN"
        ] or results

        exact = next(
            (item for item in candidates
             if item.get("name", "").casefold() == place.casefold()),
            candidates[0],
        )
        cache_set(key, exact)
        return exact

    except Exception as exc:
        logger.warning("Geocoding failed: %s", exc)
        return None


def get_weather(place):
    location = get_location_details(place)

    if not location:
        return {"success": False, "error": "इस जगह का मौसम नहीं मिला।"}

    params = urllib.parse.urlencode({
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "current": (
            "temperature_2m,relative_humidity_2m,apparent_temperature,"
            "is_day,precipitation,weather_code,wind_speed_10m"
        ),
        "timezone": "auto",
    })

    try:
        data = json.loads(fetch_url(
            "https://api.open-meteo.com/v1/forecast?" + params,
            timeout=7,
        ))
        current = data.get("current", {})

        if "temperature_2m" not in current:
            return {"success": False, "error": "मौसम डेटा उपलब्ध नहीं है।"}

        return {
            "success": True,
            "place": location.get("name", place),
            "city": location.get("name", place),
            "region": location.get("admin2") or location.get("admin1") or "",
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
            "timezone": data.get("timezone", ""),
            "source": "Open-Meteo",
        }

    except Exception as exc:
        logger.warning("Weather request failed: %s", exc)
        return {"success": False, "error": "मौसम सर्वर से संपर्क नहीं हो पाया।"}


# ------------------------------------------------------------
# Image search: Wikimedia Commons API
# ------------------------------------------------------------

def search_images(query, limit=12):
    query = clean_text(query)
    if not query:
        return []

    limit = bounded_limit(limit, 12, 30)
    key = "images:" + normalize_text(query) + ":" + str(limit)
    cached = cache_get(key, IMAGE_CACHE_SECONDS)

    if cached is not None:
        return cached

    params = urllib.parse.urlencode({
        "action": "query",
        "generator": "search",
        "gsrsearch": "filetype:bitmap " + query,
        "gsrnamespace": 6,
        "gsrlimit": limit,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": 500,
        "format": "json",
        "origin": "*",
    })

    endpoint = "https://commons.wikimedia.org/w/api.php?" + params

    try:
        data = json.loads(fetch_url(endpoint, timeout=8))
        pages = data.get("query", {}).get("pages", {})
        results = []

        for page in pages.values():
            info_list = page.get("imageinfo", [])
            if not info_list:
                continue

            info = info_list[0]
            metadata = info.get("extmetadata", {})

            image_url = safe_url(info.get("thumburl") or info.get("url"))
            page_url = safe_url(info.get("descriptionurl"))

            if not image_url or not page_url:
                continue

            def meta_value(name):
                item = metadata.get(name, {})
                return clean_text(item.get("value", "")) if isinstance(item, dict) else ""

            results.append({
                "title": clean_text(page.get("title", "").replace("File:", "")),
                "image_url": image_url,
                "url": page_url,
                "source": "Wikimedia Commons",
                "license": meta_value("LicenseShortName") or "लाइसेंस पेज पर देखें",
                "artist": meta_value("Artist"),
                "credit": meta_value("Credit"),
                "attribution_required": True,
            })

        cache_set(key, results)
        return results

    except Exception as exc:
        logger.warning("Image search failed: %s", exc)
        return []


# ------------------------------------------------------------
# Video search links
# This creates a search link, not an invented video feed.
# ------------------------------------------------------------

def search_videos(query, limit=10):
    query = clean_text(query)
    if not query:
        return []

    encoded = urllib.parse.quote_plus(query)

    return [
        {
            "title": "YouTube पर " + query + " खोजें",
            "url": "https://www.youtube.com/results?search_query=" + encoded,
            "source": "YouTube",
            "type": "search_link",
        },
        {
            "title": "Bing Videos पर " + query + " खोजें",
            "url": "https://www.bing.com/videos/search?q=" + encoded,
            "source": "Bing Videos",
            "type": "search_link",
        },
    ][:bounded_limit(limit, 10, 10)]


# ------------------------------------------------------------
# Places search: OpenStreetMap Nominatim
# Respect usage limits and cache results.
# ------------------------------------------------------------

_place_cache = {}
_place_lock = threading.Lock()
_last_place_request = 0.0


def search_places(query, limit=10):
    global _last_place_request

    query = clean_text(query)
    if not query:
        return []

    limit = bounded_limit(limit, 10, 10)
    key = normalize_text(query) + ":" + str(limit)

    with _place_lock:
        cached = _place_cache.get(key)
        if cached and time.time() - cached[0] < PLACE_CACHE_SECONDS:
            return cached[1]

        # Public Nominatim server limit: at most one request per second.
        wait = 1.05 - (time.time() - _last_place_request)
        if wait > 0:
            time.sleep(wait)

        params = urllib.parse.urlencode({
            "q": query,
            "format": "jsonv2",
            "limit": limit,
            "addressdetails": 1,
            "countrycodes": "in",
        })

        endpoint = "https://nominatim.openstreetmap.org/search?" + params
        _last_place_request = time.time()

        try:
            data = json.loads(fetch_url(endpoint, timeout=8))
            results = []

            for item in data if isinstance(data, list) else []:
                lat = item.get("lat")
                lon = item.get("lon")
                osm_type = item.get("osm_type", "")
                osm_id = item.get("osm_id", "")

                if not lat or not lon:
                    continue

                results.append({
                    "name": clean_text(item.get("name") or item.get("display_name", "")),
                    "address": clean_text(item.get("display_name", "")),
                    "category": clean_text(item.get("category", "")),
                    "type": clean_text(item.get("type", "")),
                    "latitude": lat,
                    "longitude": lon,
                    "map_url": (
                        "https://www.openstreetmap.org/"
                        + urllib.parse.quote(osm_type) + "/" + str(osm_id)
                    ),
                    "directions_url": (
                        "https://www.openstreetmap.org/directions?to="
                        + urllib.parse.quote(str(lat) + "," + str(lon))
                    ),
                    "source": "© OpenStreetMap contributors",
                })

            _place_cache[key] = (time.time(), results)
            return results

        except Exception as exc:
            logger.warning("Place search failed: %s", exc)
            return []
            # ------------------------------------------------------------
# Rate source directory (not actual live prices)
# ------------------------------------------------------------

RATE_SOURCES = {
    "gold": {
        "title": "सोना",
        "description": "सोने का भाव स्रोत वेबसाइट पर देखें।",
        "url": "https://www.goodreturns.in/gold-rates/",
    },
    "silver": {
        "title": "चाँदी",
        "description": "चाँदी का भाव स्रोत वेबसाइट पर देखें।",
        "url": "https://www.goodreturns.in/silver-rates/",
    },
    "stock_market": {
        "title": "शेयर बाजार",
        "description": "शेयर बाजार के लिए NSE वेबसाइट देखें।",
        "url": "https://www.nseindia.com/",
    },
    "mandi": {
        "title": "मंडी भाव",
        "description": "कृषि मंडी के उपलब्ध भाव देखें।",
        "url": "https://agmarknet.gov.in/",
    },
}


def get_rates(place="Rajasthan"):
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

    return {
        "success": True,
        "place": place,
        "updated_at": utc_now(),
        "live_prices_available": False,
        "rates": rates,
        "message": "वास्तविक कीमतों का सीधा डेटा कनेक्शन अभी उपलब्ध नहीं है।",
    }


# ------------------------------------------------------------
# Main pages and health
# ------------------------------------------------------------

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/health")
@app.route("/api/health")
def health():
    return jsonify({
        "success": True,
        "app": APP_NAME,
        "owner": OWNER_NAME,
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
            "Hindi and English local service search",
            "RSS news updates",
            "Open-Meteo weather",
            "Wikimedia Commons image search",
            "Video search links",
            "OpenStreetMap place search",
            "Market rate source links",
        ],
    })


# ------------------------------------------------------------
# Main search APIs
# ------------------------------------------------------------

@app.route("/api/search")
def api_search():
    query = clean_text(request.args.get("q", ""))
    limit = bounded_limit(request.args.get("limit", 30), 30, 100)

    if not query:
        return jsonify({
            "success": True,
            "query": "",
            "count": 0,
            "results": [],
            "message": "खोजने के लिए कुछ लिखें।",
        })

    results = search_services(query, limit)

    return jsonify({
        "success": True,
        "query": query,
        "count": len(results),
        "results": results,
        "message": "" if results else "कोई स्थानीय लिंक नहीं मिला।",
    })


@app.route("/api/services")
def api_services():
    query = clean_text(request.args.get("q", ""))
    services = search_services(query) if query else load_services()[:100]

    return jsonify({
        "success": True,
        "count": len(services),
        "services": services,
    })


@app.route("/api/search-services")
def api_search_services():
    return api_search()


# ------------------------------------------------------------
# Image, video and place search APIs
# ------------------------------------------------------------

@app.route("/api/images")
def api_images():
    query = clean_text(request.args.get("q", ""))
    if not query:
        return json_error("फोटो खोजने के लिए कोई विषय लिखें।")

    results = search_images(query, request.args.get("limit", 12))

    return jsonify({
        "success": True,
        "query": query,
        "count": len(results),
        "results": results,
        "source": "Wikimedia Commons",
        "message": "" if results else "अभी फोटो परिणाम उपलब्ध नहीं हैं।",
    })


@app.route("/api/videos")
def api_videos():
    query = clean_text(request.args.get("q", ""))
    if not query:
        return json_error("वीडियो खोजने के लिए कोई विषय लिखें।")

    results = search_videos(query)

    return jsonify({
        "success": True,
        "query": query,
        "count": len(results),
        "results": results,
        "message": (
            "ये वीडियो खोज के लिंक हैं, वास्तविक वीडियो सूची नहीं।"
        ),
    })


@app.route("/api/places")
def api_places():
    query = clean_text(request.args.get("q", ""))
    if not query:
        return json_error("जगह, होटल, अस्पताल या पुलिस स्टेशन का नाम लिखें।")

    results = search_places(query, request.args.get("limit", 10))

    return jsonify({
        "success": True,
        "query": query,
        "count": len(results),
        "results": results,
        "source": "OpenStreetMap contributors",
        "attribution": "© OpenStreetMap contributors",
        "message": "" if results else "जगह के परिणाम नहीं मिले या सेवा उपलब्ध नहीं है।",
    })


# ------------------------------------------------------------
# Combined search API
# Returns local services and links to other search categories.
# ------------------------------------------------------------

@app.route("/api/search-all")
def api_search_all():
    query = clean_text(request.args.get("q", ""))

    if not query:
        return json_error("खोजने के लिए कोई विषय लिखें।")

    services = search_services(query, 20)

    return jsonify({
        "success": True,
        "query": query,
        "services": services,
        "images_api": "/api/images?q=" + urllib.parse.quote(query),
        "videos_api": "/api/videos?q=" + urllib.parse.quote(query),
        "places_api": "/api/places?q=" + urllib.parse.quote(query),
        "news_api": "/api/news?q=" + urllib.parse.quote(query),
        "weather_api": "/api/weather?place=" + urllib.parse.quote(query),
        "message": (
            "फोटो, वीडियो, जगहों और न्यूज़ के लिए संबंधित API खोलें।"
        ),
    })


# ------------------------------------------------------------
# News APIs
# ------------------------------------------------------------

@app.route("/api/news")
def api_news():
    query = clean_text(request.args.get("q", ""))
    refresh = request.args.get("refresh", "").casefold()
    force_refresh = refresh in ("1", "true", "yes")

    news = fetch_news(query, force_refresh)

    return jsonify({
        "success": True,
        "count": len(news),
        "query": query,
        "updated_at": utc_now(),
        "news": news,
        "message": "" if news else "कोई खबर नहीं मिली।",
    })


@app.route("/api/latest-news")
def api_latest_news():
    return api_news()


# ------------------------------------------------------------
# Weather APIs
# ------------------------------------------------------------

@app.route("/api/weather")
def api_weather():
    place = clean_text(
        request.args.get("place", "") or request.args.get("q", "")
    )

    if not place:
        return json_error("शहर या गाँव का नाम लिखें।")

    result = get_weather(place)

    if not result.get("success"):
        return jsonify(result), 502

    return jsonify(result)


@app.route("/api/current-weather")
def api_current_weather():
    return api_weather()


# ------------------------------------------------------------
# Rate API
# ------------------------------------------------------------

@app.route("/api/rates")
def api_rates():
    place = clean_text(request.args.get("place", "Rajasthan"))
    return jsonify(get_rates(place))


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
        "<h1>Ishwar Search</h1><p>यह पेज नहीं मिला।</p>"
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
            "error": "सर्वर में समस्या आई। बाद में प्रयास करें।",
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
@app.route("/education", methods=["GET"])
def education():
    return render_template("education.html")
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
    )
