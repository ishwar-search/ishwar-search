# ============================================================
# ISHWAR SEARCH 5.2.0
# Owner: Ishwar Ghanchi
# Professional Search & Services Platform
# ============================================================

import os
import re
import json
import html
import time
import hmac
import logging
import threading
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from pathlib import Path
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template, send_from_directory

# ------------------------------------------------------------
# APP CONFIGURATION
# ------------------------------------------------------------

app = Flask(__name__)

APP_NAME = "Ishwar Search"
OWNER_NAME = "Ishwar Ghanchi"
APP_VERSION = "5.3.0"

BASE_DIR = Path(__file__).resolve().parent
SERVICES_FILE = BASE_DIR / "service.json"

# Render Persistent Disk के लिए /var/data सेट कर सकते हैं।
DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE_DIR)))
DATA_DIR.mkdir(parents=True, exist_ok=True)

PUSH_DATA_FILE = DATA_DIR / "push_subscriptions.json"

HTTP_TIMEOUT = 8
MAX_NEWS_ITEMS = 20

NEWS_CACHE_SECONDS = 300
IMAGE_CACHE_SECONDS = 600
PLACE_CACHE_SECONDS = 600

app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ishwar-search")

USER_AGENT = (
    "IshwarSearch/5.2 "
    "(https://ishwar-search.onrender.com; public search application)"
)

# ------------------------------------------------------------
# HTTP HELPERS
# ------------------------------------------------------------

def fetch_url(url, timeout=HTTP_TIMEOUT):
    parsed = urllib.parse.urlparse(url)

    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Invalid URL")

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json, application/xml, text/xml, */*"
        }
    )

    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read()

        if len(raw) > 5 * 1024 * 1024:
            raise ValueError("Response too large")

        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


# ------------------------------------------------------------
# TEXT HELPERS
# ------------------------------------------------------------

def clean_text(value):
    if value is None:
        return ""

    value = html.unescape(str(value))
    value = re.sub(r"<[^>]*>", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_text(value):
    value = clean_text(value).casefold()
    value = value.replace("&", " and ")
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)

    return re.sub(r"\s+", " ", value).strip()


def safe_url(value):
    if not value:
        return ""

    try:
        value = str(value).strip()
        parsed = urllib.parse.urlparse(value)

        if parsed.scheme not in ("http", "https"):
            return ""

        if not parsed.hostname:
            return ""

        if parsed.username or parsed.password:
            return ""

        return value

    except (ValueError, TypeError):
        return ""


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def json_error(message, status=400):
    return jsonify({
        "success": False,
        "error": message
    }), status


def bounded_limit(value, default=20, maximum=50):
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = default

    return max(1, min(value, maximum))


def get_request_query():
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}

        if not isinstance(payload, dict):
            return "", 30

        return (
            clean_text(payload.get("q") or payload.get("query") or ""),
            payload.get("limit", 30)
        )

    return (
        clean_text(request.args.get("q", "")),
        request.args.get("limit", 30)
    )


# ------------------------------------------------------------
# MEMORY CACHE
# ------------------------------------------------------------

_cache = {}
_cache_lock = threading.Lock()


def cache_get(key, max_age):
    with _cache_lock:
        entry = _cache.get(key)

        if entry is None:
            return None

        created, value = entry

        if time.time() - created > max_age:
            _cache.pop(key, None)
            return None

        return value


def cache_set(key, value):
    with _cache_lock:
        _cache[key] = (time.time(), value)

        if len(_cache) > 300:
            oldest = sorted(
                _cache,
                key=lambda item: _cache[item][0]
            )[:100]

            for old_key in oldest:
                _cache.pop(old_key, None)


# ------------------------------------------------------------
# SERVICE DIRECTORY
# ------------------------------------------------------------

def load_services():
    if not SERVICES_FILE.is_file():
        logger.warning("service.json not found")
        return []

    try:
        with SERVICES_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, dict):
            data = data.get("services", [])

        if not isinstance(data, list):
            return []

        services = []
        seen = set()

        for item in data:
            if not isinstance(item, dict):
                continue

            name = clean_text(
                item.get("name")
                or item.get("title")
                or item.get("label")
            )

            url = safe_url(
                item.get("url") or item.get("link")
            )

            if not name or not url:
                continue

            keywords = item.get("keywords", "")

            if isinstance(keywords, list):
                keywords = " ".join(map(str, keywords))

            key = url.rstrip("/").casefold()

            if key in seen:
                continue

            seen.add(key)

            services.append({
                "name": name,
                "title": name,
                "url": url,
                "link": url,
                "description": clean_text(
                    item.get("description", "")
                ),
                "category": clean_text(
                    item.get("category", "general")
                ).casefold(),
                "keywords": clean_text(keywords)
            })

        return services

    except (OSError, json.JSONDecodeError):
        logger.exception("Service directory loading failed")
        return []


# ------------------------------------------------------------
# SEARCH SYNONYMS
# ------------------------------------------------------------

SEARCH_SYNONYMS = {
    "railway": ["rrb", "rail", "रेलवे", "रेल", "ट्रेन"],
    "rrb": ["railway", "रेलवे"],
    "job": ["jobs", "recruitment", "vacancy", "नौकरी", "भर्ती"],
    "jobs": ["job", "recruitment", "vacancy", "नौकरी", "भर्ती"],
    "recruitment": ["job", "jobs", "vacancy", "भर्ती"],
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
    "police": ["पुलिस", "थाना"],
    "hotel": ["होटल", "stay", "accommodation"],
    "school": ["स्कूल", "विद्यालय"],
    "restaurant": ["रेस्टोरेंट", "खाना", "food"],
    "photo": ["image", "images", "फोटो", "तस्वीर"],
    "image": ["photo", "photos", "फोटो", "तस्वीर"],
    "video": ["वीडियो", "clips"]
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


# ------------------------------------------------------------
# SMART LOCAL SEARCH
# ------------------------------------------------------------

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

        searchable = " ".join([
            name,
            description,
            category,
            keywords
        ])

        score = 0

        if query == name:
            score += 100

        elif query in name:
            score += 50

        if query in keywords:
            score += 25

        if query in category:
            score += 15

        if query in description:
            score += 10

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
            result = dict(service)
            result["score"] = score
            matches.append(result)

    matches.sort(
        key=lambda item: (
            -item["score"],
            item["name"].casefold()
        )
    )

    return matches[:bounded_limit(limit, 30, 100)]

# ============================================================
# NEWS SYSTEM
# ============================================================

NEWS_FEEDS = [
    {
        "name": "Google News Hindi",
        "url": "https://news.google.com/rss?hl=hi&gl=IN&ceid=IN:hi"
    },
    {
        "name": "Google News India",
        "url": "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en"
    },
    {
        "name": "BBC Hindi",
        "url": "https://feeds.bbci.co.uk/hindi/rss.xml"
    }
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
            get_xml_text(
                node,
                {"description", "summary", "content", "encoded"}
            )
        )

        published = clean_text(
            get_xml_text(
                node,
                {"pubdate", "published", "updated", "date"}
            )
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
                "name": title,
                "description": description[:1000],
                "url": link,
                "link": link,
                "source": source_name,
                "published": published
            })

    return results


def fetch_news(query="", force_refresh=False):
    global _news_cache, _news_cache_time

    now = time.time()

    with _news_lock:
        valid = (
            bool(_news_cache)
            and now - _news_cache_time < NEWS_CACHE_SECONDS
        )

        if valid and not force_refresh:
            all_news = list(_news_cache)

        else:
            all_news = []

            for feed in NEWS_FEEDS:
                try:
                    xml_text = fetch_url(feed["url"], timeout=7)

                    all_news.extend(
                        extract_news_items(xml_text, feed["name"])
                    )

                except Exception as exc:
                    logger.warning(
                        "News feed failed (%s): %s",
                        feed["name"],
                        exc
                    )

            unique = []
            seen = set()

            for item in all_news:
                key = item["url"].rstrip("/").casefold()

                if key in seen:
                    continue

                seen.add(key)
                unique.append(item)

            all_news = unique
            _news_cache = list(unique)
            _news_cache_time = now

    words = normalize_text(query).split()

    if words:
        filtered = []

        for item in all_news:
            searchable = normalize_text(
                item["title"] + " "
                + item["description"] + " "
                + item["source"]
            )

            if all(word in searchable for word in words):
                filtered.append(item)

        return filtered[:MAX_NEWS_ITEMS]

    return all_news[:MAX_NEWS_ITEMS]


# ============================================================
# WEATHER SYSTEM - OPEN METEO
# ============================================================

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
        "countryCode": "IN"
    })

    try:
        data = json.loads(fetch_url(
            "https://geocoding-api.open-meteo.com/v1/search?"
            + params,
            timeout=7
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
            (
                item for item in candidates
                if item.get("name", "").casefold()
                == place.casefold()
            ),
            candidates[0]
        )

        cache_set(key, exact)
        return exact

    except Exception as exc:
        logger.warning("Geocoding failed: %s", exc)
        return None


def weather_description(code):
    descriptions = {
        0: "साफ आसमान",
        1: "मुख्यतः साफ",
        2: "कुछ बादल",
        3: "बादल छाए हुए",
        45: "कोहरा",
        48: "जमा हुआ कोहरा",
        51: "हल्की बूंदाबांदी",
        53: "बूंदाबांदी",
        55: "तेज बूंदाबांदी",
        61: "हल्की बारिश",
        63: "बारिश",
        65: "तेज बारिश",
        71: "हल्की बर्फबारी",
        73: "बर्फबारी",
        75: "तेज बर्फबारी",
        80: "बारिश की बौछारें",
        81: "तेज बारिश की बौछारें",
        82: "बहुत तेज बौछारें",
        95: "आंधी-तूफान",
        96: "ओलों के साथ तूफान",
        99: "तेज तूफान और ओले"
    }

    try:
        return descriptions.get(
            int(code),
            "मौसम की जानकारी उपलब्ध"
        )
    except (ValueError, TypeError):
        return "मौसम की जानकारी उपलब्ध"
        def get_weather(place):
    location = get_location_details(place)

    if not location:
        return {
            "success": False,
            "error": "इस जगह का मौसम नहीं मिला।"
        }

    params = urllib.parse.urlencode({
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "current": (
            "temperature_2m,relative_humidity_2m,"
            "apparent_temperature,is_day,precipitation,"
            "weather_code,wind_speed_10m"
        ),
        "timezone": "auto"
    })

    try:
        data = json.loads(fetch_url(
            "https://api.open-meteo.com/v1/forecast?"
            + params,
            timeout=7
        ))

        current = data.get("current", {})

        if "temperature_2m" not in current:
            return {
                "success": False,
                "error": "मौसम डेटा उपलब्ध नहीं है।"
            }

        code = current.get("weather_code")
        temperature = current.get("temperature_2m")
        condition = weather_description(code)

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
            "temperature": temperature,
            "temp": temperature,
            "description": condition,
            "condition": condition,
            "feels_like": current.get("apparent_temperature"),
            "apparent_temperature": current.get("apparent_temperature"),
            "humidity": current.get("relative_humidity_2m"),
            "wind_speed": current.get("wind_speed_10m"),
            "precipitation": current.get("precipitation"),
            "weather_code": code,
            "is_day": current.get("is_day"),
            "current": current,
            "units": data.get("current_units", {}),
            "time": current.get("time"),
            "updated_at": current.get("time"),
            "timezone": data.get("timezone", ""),
            "source": "Open-Meteo"
        }

    except Exception as exc:
        logger.warning("Weather request failed: %s", exc)

        return {
            "success": False,
            "error": "मौसम सर्वर से संपर्क नहीं हो पाया।"
        }


# ============================================================
# IMAGE SEARCH - WIKIMEDIA COMMONS
# ============================================================

def search_images(query, limit=12):
    query = clean_text(query)

    if not query:
        return []

    limit = bounded_limit(limit, 12, 30)

    key = (
        "images:"
        + normalize_text(query)
        + ":"
        + str(limit)
    )

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
        "format": "json"
    })

    endpoint = (
        "https://commons.wikimedia.org/w/api.php?"
        + params
    )

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

            image_url = safe_url(
                info.get("thumburl") or info.get("url")
            )

            page_url = safe_url(info.get("descriptionurl"))

            if not image_url or not page_url:
                continue

            def meta_value(name):
                item = metadata.get(name, {})

                if isinstance(item, dict):
                    return clean_text(item.get("value", ""))

                return ""

            title = clean_text(
                page.get("title", "").replace("File:", "")
            )

            artist = meta_value("Artist")

            license_name = (
                meta_value("LicenseShortName")
                or "लाइसेंस विवरण स्रोत पेज पर देखें"
            )

            results.append({
                "title": title,
                "alt": title,
                "image": image_url,
                "src": image_url,
                "image_url": image_url,
                "url": page_url,
                "page_url": page_url,
                "source": "Wikimedia Commons",
                "license": license_name,
                "artist": artist,
                "credit": meta_value("Credit"),
                "attribution_required": True
            })

        cache_set(key, results)
        return results

    except Exception as exc:
        logger.warning("Image search failed: %s", exc)
        return []


# ============================================================
# VIDEO SEARCH LINKS
# ============================================================

def search_videos(query, limit=10):
    query = clean_text(query)

    if not query:
        return []

    encoded = urllib.parse.quote_plus(query)

    results = [
        {
            "title": "YouTube पर " + query + " खोजें",
            "url": (
                "https://www.youtube.com/results?search_query="
                + encoded
            ),
            "source": "YouTube",
            "type": "search_link"
        },
        {
            "title": "Bing Videos पर " + query + " खोजें",
            "url": (
                "https://www.bing.com/videos/search?q="
                + encoded
            ),
            "source": "Bing Videos",
            "type": "search_link"
        }
    ]

    return results[:bounded_limit(limit, 10, 10)]


# ============================================================
# PLACES SEARCH - OPENSTREETMAP
# ============================================================

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

        wait = 1.05 - (time.time() - _last_place_request)

        if wait > 0:
            time.sleep(wait)

        params = urllib.parse.urlencode({
            "q": query,
            "format": "jsonv2",
            "limit": limit,
            "addressdetails": 1,
            "countrycodes": "in"
        })

        endpoint = (
            "https://nominatim.openstreetmap.org/search?"
            + params
        )

        _last_place_request = time.time()

        try:
            data = json.loads(
                fetch_url(endpoint, timeout=8)
            )

            results = []

            for item in data if isinstance(data, list) else []:
                lat = item.get("lat")
                lon = item.get("lon")

                if not lat or not lon:
                    continue

                osm_type = str(item.get("osm_type", ""))
                osm_id = str(item.get("osm_id", ""))

                results.append({
                    "name": clean_text(
                        item.get("name")
                        or item.get("display_name", "")
                    ),
                    "address": clean_text(
                        item.get("display_name", "")
                    ),
                    "category": clean_text(
                        item.get("category", "")
                    ),
                    "type": clean_text(
                        item.get("type", "")
                    ),
                    "latitude": lat,
                    "longitude": lon,
                    "map_url": (
                        "https://www.openstreetmap.org/"
                        + urllib.parse.quote(osm_type)
                        + "/"
                        + urllib.parse.quote(osm_id)
                    ),
                    "directions_url": (
                        "https://www.openstreetmap.org/directions?to="
                        + urllib.parse.quote(str(lat) + "," + str(lon))
                    ),
                    "source": "© OpenStreetMap contributors"
                })

            _place_cache[key] = (time.time(), results)

            return results

        except Exception as exc:
            logger.warning("Place search failed: %s", exc)
            return []


# ============================================================
# MARKET RATE SOURCE LINKS
# ============================================================

RATE_SOURCES = {
    "gold": {
        "title": "सोना",
        "description": "सोने का भाव स्रोत वेबसाइट पर देखें।",
        "url": "https://www.goodreturns.in/gold-rates/"
    },
    "silver": {
        "title": "चाँदी",
        "description": "चाँदी का भाव स्रोत वेबसाइट पर देखें।",
        "url": "https://www.goodreturns.in/silver-rates/"
    },
    "stock_market": {
        "title": "शेयर बाजार",
        "description": "शेयर बाजार के लिए NSE वेबसाइट देखें।",
        "url": "https://www.nseindia.com/"
    },
    "mandi": {
        "title": "मंडी भाव",
        "description": "कृषि मंडी के भाव के लिए Agmarknet देखें।",
        "url": "https://agmarknet.gov.in/"
    }
}


def get_rates(place="Rajasthan"):
    place = clean_text(place) or "Rajasthan"

    rates = {}

    for key, source in RATE_SOURCES.items():
        rates[key] = {
            "title": source["title"],
            "value": "स्रोत पर देखें",
            "unit": "",
            "description": source["description"],
            "source": source["url"],
            "updated_at": None,
            "is_live_value": False
        }

    return {
        "success": True,
        "place": place,
        "updated_at": utc_now(),
        "live_prices_available": False,
        "rates": rates,
        "message": (
            "वास्तविक कीमतों का सीधा डेटा कनेक्शन अभी उपलब्ध नहीं है।"
        )
    }


# ============================================================
# MAIN PAGE
# ============================================================

@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")


@app.route("/sw.js", methods=["GET"])
def service_worker():
    """Serve the worker at the site root so it can control the whole site."""
    response = app.make_response(
        send_from_directory(app.static_folder, "sw.js", mimetype="application/javascript")
    )
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health", methods=["GET"])
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "success": True,
        "app": APP_NAME,
        "owner": OWNER_NAME,
        "version": APP_VERSION,
        "status": "running",
        "services_count": len(load_services()),
        "time": utc_now()
    })


# ============================================================
# ABOUT API
# ============================================================

@app.route("/api/about", methods=["GET"])
def about():
    return jsonify({
        "success": True,
        "name": APP_NAME,
        "owner": OWNER_NAME,
        "version": APP_VERSION,
        "features": [
            "Hindi and English service search",
            "Website directory",
            "RSS news updates",
            "Open-Meteo weather",
            "Wikimedia Commons image search",
            "Video search links",
            "OpenStreetMap place search",
            "Market-rate source links",
            "Push notification API",
            "Root-scope Service Worker endpoint",
            "Push subscription status diagnostics"
        ],
        "services_count": len(load_services())
    })


# ============================================================
# MAIN SEARCH API
# ============================================================

@app.route("/api/search", methods=["GET", "POST"])
def api_search():
    query, limit = get_request_query()

    if len(query) > 250:
        return json_error(
            "खोज का शब्द 250 अक्षरों से छोटा रखें।"
        )

    limit = bounded_limit(limit, 30, 100)

    if not query:
        return jsonify({
            "success": True,
            "query": "",
            "count": 0,
            "results": [],
            "message": "खोजने के लिए कुछ लिखें।"
        })

    results = search_services(query, limit)

    return jsonify({
        "success": True,
        "query": query,
        "count": len(results),
        "results": results,
        "message": (
            "" if results else "कोई स्थानीय लिंक नहीं मिला।"
        )
    })


@app.route("/api/search-services", methods=["GET"])
def api_search_services():
    return api_search()


# ============================================================
# WEBSITE DIRECTORY API
# ============================================================

@app.route("/api/services", methods=["GET"])
def api_services():
    query = clean_text(request.args.get("q", ""))
    category = normalize_text(
        request.args.get("category", "")
    )

    if len(query) > 250:
        return json_error("खोज का शब्द बहुत लंबा है।")

    services = load_services()

    if query:
        services = search_services(query, 100)

    if category and category != "all":
        services = [
            item for item in services
            if normalize_text(item.get("category", "")) == category
        ]

    return jsonify({
        "success": True,
        "count": len(services),
        "results": services[:100],
        "services": services[:100]
    })


# ============================================================
# IMAGE SEARCH API
# ============================================================

@app.route("/api/images/search", methods=["GET"])
@app.route("/api/images", methods=["GET"])
def api_images_search():
    query = clean_text(request.args.get("q", ""))

    if not query:
        return json_error("फोटो खोजने के लिए कोई विषय लिखें।")

    if len(query) > 150:
        return json_error("फोटो खोज का शब्द बहुत लंबा है।")

    limit = bounded_limit(
        request.args.get("limit", 12),
        12,
        30
    )

    results = search_images(query, limit)

    return jsonify({
        "success": True,
        "query": query,
        "count": len(results),
        "results": results,
        "source": "Wikimedia Commons",
        "message": (
            "" if results
            else "अभी फोटो परिणाम नहीं मिले। दूसरा शब्द लिखकर देखें।"
        )
    })


# ============================================================
# VIDEO SEARCH API
# ============================================================

@app.route("/api/videos", methods=["GET"])
def api_videos():
    query = clean_text(request.args.get("q", ""))

    if not query:
        return json_error("वीडियो खोजने के लिए कोई विषय लिखें।")

    if len(query) > 150:
        return json_error("वीडियो खोज का शब्द बहुत लंबा है।")

    results = search_videos(query)

    return jsonify({
        "success": True,
        "query": query,
        "count": len(results),
        "results": results,
        "message": "ये वीडियो खोज के लिंक हैं, वास्तविक वीडियो सूची नहीं।"
    })


# ============================================================
# PLACES API
# ============================================================

@app.route("/api/places", methods=["GET"])
def api_places():
    query = clean_text(request.args.get("q", ""))

    if not query:
        return json_error(
            "जगह, होटल, अस्पताल या पुलिस स्टेशन का नाम लिखें।"
        )

    if len(query) > 150:
        return json_error("जगह की खोज का शब्द बहुत लंबा है।")

    limit = bounded_limit(
        request.args.get("limit", 10),
        10,
        10
    )

    results = search_places(query, limit)

    return jsonify({
        "success": True,
        "query": query,
        "count": len(results),
        "results": results,
        "source": "OpenStreetMap contributors",
        "attribution": "© OpenStreetMap contributors",
        "message": (
            "" if results
            else "जगह के परिणाम नहीं मिले या सेवा उपलब्ध नहीं है।"
        )
    })


# ============================================================
# COMBINED SEARCH API
# ============================================================

@app.route("/api/search-all", methods=["GET"])
def api_search_all():
    query = clean_text(request.args.get("q", ""))

    if not query:
        return json_error("खोजने के लिए कोई विषय लिखें।")

    if len(query) > 150:
        return json_error("खोज का शब्द बहुत लंबा है।")

    encoded = urllib.parse.quote(query)

    return jsonify({
        "success": True,
        "query": query,
        "services": search_services(query, 20),
        "images_api": "/api/images/search?q=" + encoded,
        "videos_api": "/api/videos?q=" + encoded,
        "places_api": "/api/places?q=" + encoded,
        "news_api": "/api/news?q=" + encoded,
        "weather_api": "/api/weather?place=" + encoded,
            "news_api": "/api/news?q=" + encoded,
        "weather_api": "/api/weather?place=" + encoded,
        "rates_api": "/api/rates"
    })


# ============================================================
# NEWS API
# ============================================================

@app.route("/api/news", methods=["GET"])
def api_news():
    query = clean_text(request.args.get("q", ""))

    if len(query) > 150:
        return json_error("खबर खोजने का शब्द बहुत लंबा है।")

    limit = bounded_limit(
        request.args.get("limit", 15),
        15,
        MAX_NEWS_ITEMS
    )

    force_refresh = (
        request.args.get("refresh", "").lower()
        in ("1", "true", "yes")
    )

    results = fetch_news(query, force_refresh)

    return jsonify({
        "success": True,
        "query": query,
        "count": min(len(results), limit),
        "results": results[:limit],
        "updated_at": utc_now(),
        "source": "RSS feeds"
    })


# ============================================================
# WEATHER API
# ============================================================

@app.route("/api/weather", methods=["GET"])
def api_weather():
    place = clean_text(
        request.args.get("place")
        or request.args.get("q")
        or ""
    )

    if not place:
        return json_error("कृपया शहर या जगह का नाम लिखें।")

    if len(place) > 100:
        return json_error("जगह का नाम बहुत लंबा है।")

    result = get_weather(place)

    if not result.get("success"):
        return jsonify(result), 404

    return jsonify(result)


# ============================================================
# MARKET RATES API
# ============================================================

@app.route("/api/rates", methods=["GET"])
def api_rates():
    place = clean_text(
        request.args.get("place", "Rajasthan")
    )

    return jsonify(get_rates(place))


# ============================================================
# EDUCATION AND IMPORTANT LINKS
# ============================================================

@app.route("/api/education", methods=["GET"])
def api_education():
    results = [
        {
            "name": "National Scholarship Portal",
            "url": "https://scholarships.gov.in/",
            "category": "scholarship"
        },
        {
            "name": "DigiLocker",
            "url": "https://www.digilocker.gov.in/",
            "category": "documents"
        },
        {
            "name": "National Career Service",
            "url": "https://www.ncs.gov.in/",
            "category": "jobs"
        },
        {
            "name": "Skill India Digital",
            "url": "https://www.skillindiadigital.gov.in/",
            "category": "skills"
        },
        {
            "name": "Railway Recruitment Board",
            "url": "https://www.rrbapply.gov.in/",
            "category": "railway"
        },
        {
            "name": "Union Public Service Commission",
            "url": "https://upsc.gov.in/",
            "category": "government jobs"
        },
        {
            "name": "Rajasthan Public Service Commission",
            "url": "https://rpsc.rajasthan.gov.in/",
            "category": "rajasthan jobs"
        },
        {
            "name": "Rajasthan Staff Selection Board",
            "url": "https://rssb.rajasthan.gov.in/",
            "category": "rajasthan jobs"
        }
    ]

    return jsonify({
        "success": True,
        "count": len(results),
        "results": results
    })


# ============================================================
# NOTIFICATION CONFIGURATION
# ============================================================

def get_vapid_settings():
    return {
        "public_key": os.environ.get(
            "VAPID_PUBLIC_KEY", ""
        ).strip(),
        "private_key": os.environ.get(
            "VAPID_PRIVATE_KEY", ""
        ).strip(),
        "subject": os.environ.get(
            "VAPID_SUBJECT",
            "mailto:admin@example.com"
        ).strip()
    }


def push_configuration():
    settings = get_vapid_settings()

    try:
        import pywebpush
        package_available = True
    except ImportError:
        package_available = False

    return {
        "public_key_configured": bool(settings["public_key"]),
        "private_key_configured": bool(settings["private_key"]),
        "subject_configured": bool(settings["subject"]),
        "pywebpush_available": package_available,
        "configured": bool(
            settings["public_key"]
            and settings["private_key"]
            and settings["subject"]
            and package_available
        )
    }


# ============================================================
# SUBSCRIPTION STORAGE
# ============================================================

_subscription_lock = threading.RLock()


def load_subscriptions():
    with _subscription_lock:
        if not PUSH_DATA_FILE.is_file():
            return []

        try:
            with PUSH_DATA_FILE.open(
                "r",
                encoding="utf-8"
            ) as file:
                data = json.load(file)

            if not isinstance(data, list):
                return []

            valid = []

            for item in data:
                if not isinstance(item, dict):
                    continue

                endpoint = safe_url(item.get("endpoint"))
                keys = item.get("keys", {})

                if not endpoint or not isinstance(keys, dict):
                    continue

                if not keys.get("p256dh") or not keys.get("auth"):
                    continue

                item["endpoint"] = endpoint
                valid.append(item)

            return valid

        except (OSError, json.JSONDecodeError):
            logger.exception(
                "Subscription file could not be read"
            )
            return []


def save_subscriptions(subscriptions):
    with _subscription_lock:
        temp_file = PUSH_DATA_FILE.with_suffix(".tmp")

        try:
            DATA_DIR.mkdir(
                parents=True,
                exist_ok=True
            )

            with temp_file.open(
                "w",
                encoding="utf-8"
            ) as file:
                json.dump(
                    subscriptions,
                    file,
                    ensure_ascii=False,
                    indent=2
                )

                file.flush()
                os.fsync(file.fileno())

            os.replace(
                temp_file,
                PUSH_DATA_FILE
            )

            return True

        except OSError:
            logger.exception(
                "Subscription file could not be saved"
            )

            try:
                if temp_file.exists():
                    temp_file.unlink()
            except OSError:
                pass

            return False


def notification_admin_authorized():
    expected = os.environ.get(
        "NOTIFICATION_ADMIN_TOKEN",
        ""
    ).strip()

    if not expected:
        return False

    supplied = (
        request.headers.get("X-Admin-Token", "")
        or request.args.get("token", "")
    )

    return bool(supplied) and hmac.compare_digest(
        supplied,
        expected
    )


# ============================================================
# NOTIFICATION STATUS API
# ============================================================

@app.route(
    "/api/notifications/status",
    methods=["GET"]
)
def notification_status():
    config = push_configuration()
    subscriptions = load_subscriptions()

    return jsonify({
        "success": True,
        "version": APP_VERSION,
        "push_configured": config["configured"],
        "configuration": config,
        "subscription_count": len(subscriptions),
        "time": utc_now()
    })


# ============================================================
# NOTIFICATION PUBLIC KEY API
# ============================================================

@app.route(
    "/api/notifications/public-key",
    methods=["GET"]
)
def notification_public_key():
    settings = get_vapid_settings()

    if not settings["public_key"]:
        return json_error(
            "Notifications की public key अभी सेट नहीं है।",
            503
        )

    return jsonify({
        "success": True,
        "publicKey": settings["public_key"]
    })


# ============================================================
# NOTIFICATION SUBSCRIBE API
# ============================================================

@app.route(
    "/api/notifications/subscribe",
    methods=["POST"]
)
def notification_subscribe():
    settings = get_vapid_settings()

    if not settings["public_key"]:
        return json_error(
            "Push notification configuration उपलब्ध नहीं है।",
            503
        )

    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return json_error("गलत subscription data।")

    endpoint = safe_url(
        payload.get("endpoint")
    )

    keys = payload.get("keys", {})

    if not endpoint or not isinstance(keys, dict):
        return json_error(
            "Subscription details अधूरी हैं।"
        )

    p256dh = clean_text(keys.get("p256dh"))
    auth = clean_text(keys.get("auth"))

    if not p256dh or not auth:
        return json_error(
            "Subscription keys उपलब्ध नहीं हैं।"
        )

    subscription = {
        "endpoint": endpoint,
        "expirationTime": payload.get("expirationTime"),
        "keys": {
            "p256dh": p256dh,
            "auth": auth
        },
        "created_at": utc_now()
    }

    with _subscription_lock:
        subscriptions = load_subscriptions()

        subscriptions = [
            item for item in subscriptions
            if item.get("endpoint") != endpoint
        ]

        if len(subscriptions) >= 10000:
            return json_error(
                "अभी subscription की अधिकतम सीमा पूरी हो गई है।",
                429
            )

        subscriptions.append(subscription)

        if not save_subscriptions(subscriptions):
            return json_error(
                "Subscription सेव नहीं हो सका।",
                500
            )

    return jsonify({
        "success": True,
        "message": "Notifications subscription सेव हो गया।",
        "subscription_count": len(subscriptions)
    })


# ============================================================
# NOTIFICATION UNSUBSCRIBE API
# ============================================================

@app.route(
    "/api/notifications/unsubscribe",
    methods=["POST"]
)
def notification_unsubscribe():
    payload = request.get_json(silent=True) or {}

    if not isinstance(payload, dict):
        return json_error("गलत अनुरोध।")

    endpoint = safe_url(
        payload.get("endpoint")
    )

    if not endpoint:
        return json_error(
            "Subscription endpoint नहीं मिला।"
        )

    with _subscription_lock:
        subscriptions = load_subscriptions()

        updated = [
            item for item in subscriptions
            if item.get("endpoint") != endpoint
        ]

        if not save_subscriptions(updated):
            return json_error(
                "Subscription हटाया नहीं जा सका।",
                500
            )

    return jsonify({
        "success": True,
        "message": "Subscription हटा दिया गया।",
        "subscription_count": len(updated)
    })


# ============================================================
# NOTIFICATION SEND API
# ============================================================

@app.route(
    "/api/notifications/send",
    methods=["POST"]
)
def notification_send():
    if not notification_admin_authorized():
        return json_error(
            "Admin authorization जरूरी है।",
            403
        )

    config = push_configuration()

    if not config["configured"]:
        return json_error(
            "Push notification configuration पूरी नहीं है।",
            503
        )

    payload = request.get_json(silent=True) or {}

    if not isinstance(payload, dict):
        return json_error(
            "गलत notification data।"
        )

    title = clean_text(
        payload.get("title") or APP_NAME
    )

    body = clean_text(
        payload.get("body") or "नई जानकारी उपलब्ध है।"
    )

    target_url = payload.get("url") or "/"

    if target_url != "/":
        target_url = safe_url(target_url)

        if not target_url:
            return json_error(
                "Notification का URL सही नहीं है।"
            )

        parsed_target = urllib.parse.urlparse(target_url)
        parsed_base = urllib.parse.urlparse(request.host_url)

        if parsed_target.netloc != parsed_base.netloc:
            return json_error(
                "Notification URL इसी वेबसाइट का होना चाहिए।"
            )

    if len(title) > 100:
        title = title[:100]

    if len(body) > 300:
        body = body[:300]

    settings = get_vapid_settings()

    try:
        from pywebpush import (
            webpush,
            WebPushException
        )
    except ImportError:
        return json_error(
            "pywebpush package उपलब्ध नहीं है।",
            503
        )

    subscriptions = load_subscriptions()

    sent = 0
    failed = 0
    expired = set()
    attempted = len(subscriptions)

    notification_data = json.dumps({
        "title": title,
        "body": body,
        "url": target_url,
        "icon": "/static/logo.png",
        "badge": "/static/logo.png"
    }, ensure_ascii=False)

    for subscription in subscriptions:
        try:
            webpush(
                subscription_info=subscription,
                data=notification_data,
                vapid_private_key=settings["private_key"],
                vapid_claims={
                    "sub": settings["subject"]
                },
                timeout=10
            )

            sent += 1

        except WebPushException as exc:
            failed += 1

            response = getattr(
                exc,
                "response",
                None
            )

            status_code = getattr(
                response,
                "status_code",
                None
            )

            if status_code in (404, 410):
                expired.add(
                    subscription.get("endpoint")
                )

            logger.warning(
                "Push notification failed: %s",
                status_code or str(exc)
            )

        except Exception:
            failed += 1
            logger.exception(
                "Unexpected push notification error"
            )

    if expired:
        remaining = [
            item for item in subscriptions
            if item.get("endpoint") not in expired
        ]

        save_subscriptions(remaining)

    return jsonify({
        "success": True,
        "attempted": attempted,
        "sent": sent,
        "failed": failed,
        "expired_removed": len(expired),
        "message": "Notification sending process पूरा हुआ।"
    })


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def page_not_found(error):
    if request.path.startswith("/api/"):
        return json_error(
            "यह API endpoint उपलब्ध नहीं है।",
            404
        )

    return jsonify({
        "success": False,
        "error": "यह पेज नहीं मिला।"
    }), 404


@app.errorhandler(413)
def request_too_large(error):
    return json_error(
        "भेजा गया डेटा बहुत बड़ा है।",
        413
    )


@app.errorhandler(500)
def internal_server_error(error):
    logger.exception(
        "Internal server error"
    )

    if request.path.startswith("/api/"):
        return json_error(
            "Server पर समस्या आई है। कृपया बाद में प्रयास करें।",
            500
        )

    return jsonify({
        "success": False,
        "error": "Server पर समस्या आई है।"
    }), 500


# ============================================================
# APPLICATION START
# ============================================================

if __name__ == "__main__":
    port = int(
        os.environ.get("PORT", 5000)
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
