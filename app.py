
# ============================================================
# Ishwar Search
# Owner: Ishwar Ghanchi
# Version: 5.1.0
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
APP_VERSION = "5.1.0"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ishwar-search")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICES_FILE = os.path.join(BASE_DIR, "service.json")

HTTP_TIMEOUT = 8
MAX_NEWS_ITEMS = 20
NEWS_CACHE_SECONDS = 300
IMAGE_CACHE_SECONDS = 600
PLACE_CACHE_SECONDS = 600

USER_AGENT = (
    "IshwarSearch/5.1 "
    "(https://ishwar-search.onrender.com; public search application)"
)


# ------------------------------------------------------------
# HTTP AND TEXT HELPERS
# ------------------------------------------------------------

def fetch_url(url, timeout=HTTP_TIMEOUT):
    """Fetch an HTTP/HTTPS URL."""
    parsed = urllib.parse.urlparse(url)

    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Invalid URL")

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json, application/xml, text/xml, */*",
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
# SMALL IN-MEMORY CACHE
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
# LOCAL SERVICE DIRECTORY: service.json
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
        seen_urls = set()

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

            url_key = url.rstrip("/").casefold()

            if url_key in seen_urls:
                continue

            seen_urls.add(url_key)

            services.append({
                "name": name,
                "title": name,
                "url": url,
                "link": url,
                "description": clean_text(item.get("description", "")),
                "category": clean_text(item.get("category", "general")).casefold(),
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
    "image": ["photo", "photos", "फोटो", "तस्वीर"],
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

        searchable = " ".join([
            name, description, category, keywords
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

        if score:
            result = dict(service)
            result["score"] = score
            matches.append(result)

    matches.sort(
        key=lambda item: (-item["score"], item["name"].casefold())
    )

    return matches[:bounded_limit(limit, 30, 100)]


# ------------------------------------------------------------
# NEWS FEEDS
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
                    rel = child.attrib.get("rel", "alternate")

                    if rel == "alternate":
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
                "published": published,
            })

    return results


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


# ------------------------------------------------------------
# WEATHER: OPEN-METEO
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
            (
                item for item in candidates
                if item.get("name", "").casefold() == place.casefold()
            ),
            candidates[0],
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
        99: "तेज तूफान और ओले",
    }

    try:
        return descriptions.get(int(code), "मौसम की जानकारी उपलब्ध")
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
            return {
                "success": False,
                "error": "मौसम डेटा उपलब्ध नहीं है।"
            }

        code = current.get("weather_code")
        condition = weather_description(code)
        temperature = current.get("temperature_2m")

        return {
            "success": True,
            "place": location.get("name", place),
            "city": location.get("name", place),
            "region": location.get("admin2") or location.get("admin1") or "",
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
            "source": "Open-Meteo",
        }

    except Exception as exc:
        logger.warning("Weather request failed: %s", exc)

        return {
            "success": False,
            "error": "मौसम सर्वर से संपर्क नहीं हो पाया।"
        }


# ------------------------------------------------------------
# IMAGE SEARCH: WIKIMEDIA COMMONS
# Results include image URLs and license information.
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
                "attribution_required": True,
            })

        cache_set(key, results)
        return results

    except Exception as exc:
        logger.warning("Image search failed: %s", exc)
        return []


# ------------------------------------------------------------
# VIDEO SEARCH LINKS
# These are search links, not a live video feed.
# ------------------------------------------------------------

def search_videos(query, limit=10):
    query = clean_text(query)

    if not query:
        return []

    encoded = urllib.parse.quote_plus(query)

    results = [
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
    ]

    return results[:bounded_limit(limit, 10, 10)]


# ------------------------------------------------------------
# PLACES SEARCH: OPENSTREETMAP NOMINATIM
# Uses caching and a minimum delay between requests.
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

        # Respect the public service's request rate.
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

        endpoint = (
            "https://nominatim.openstreetmap.org/search?" + params
        )

        _last_place_request = time.time()

        try:
            data = json.loads(fetch_url(endpoint, timeout=8))
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
                    "address": clean_text(item.get("display_name", "")),
                    "category": clean_text(item.get("category", "")),
                    "type": clean_text(item.get("type", "")),
                    "latitude": lat,
                    "longitude": lon,
                    "map_url": (
                        "https://www.openstreetmap.org/"
                        + urllib.parse.quote(osm_type)
                        + "/" + urllib.parse.quote(osm_id)
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
# RATE SOURCES
# These are source links, not verified live prices.
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
        "description": "कृषि मंडी के भाव के लिए Agmarknet देखें।",
        "url": "https://agmarknet.gov.in/",
    },
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
            "is_live_value": False,
        }

    return {
        "success": True,
        "place": place,
        "updated_at": utc_now(),
        "live_prices_available": False,
        "rates": rates,
        "message": (
            "वास्तविक कीमतों का सीधा डेटा कनेक्शन अभी उपलब्ध नहीं है।"
        ),
    }


# ------------------------------------------------------------
# MAIN PAGE AND HEALTH CHECK
# ------------------------------------------------------------

@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")


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
        "time": utc_now(),
    })


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
        ],
        "services_count": len(load_services()),
    })


# ------------------------------------------------------------
# MAIN SEARCH API
# ------------------------------------------------------------

@app.route("/api/search", methods=["GET", "POST"])
def api_search():
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        query = clean_text(payload.get("q") or payload.get("query") or "")
        limit = payload.get("limit", 30)
    else:
        query = clean_text(request.args.get("q", ""))
        limit = request.args.get("limit", 30)

    if len(query) > 250:
        return json_error("खोज का शब्द 250 अक्षरों से छोटा रखें।")

    limit = bounded_limit(limit, 30, 100)

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


@app.route("/api/search-services", methods=["GET"])
def api_search_services():
    return api_search()


# ------------------------------------------------------------
# WEBSITE DIRECTORY API
# Compatible with the new index.html website section.
# ------------------------------------------------------------

@app.route("/api/services", methods=["GET"])
def api_services():
    query = clean_text(request.args.get("q", ""))
    category = normalize_text(request.args.get("category", ""))

    services = load_services()

    if query:
        services = search_services(query, limit=100)

    if category and category != "all":
        services = [
            item for item in services
            if normalize_text(item.get("category", "")) == category
        ]

    return jsonify({
        "success": True,
        "count": len(services),
        "results": services[:100],
        "services": services[:100],
    })


# ------------------------------------------------------------
# IMAGE SEARCH API
# Supports the new frontend route /api/images/search.
# Wikimedia Commons results include source and license details.
# ------------------------------------------------------------

@app.route("/api/images/search", methods=["GET"])
def api_images_search():
    query = clean_text(request.args.get("q", ""))

    if not query:
        return json_error("फोटो खोजने के लिए कोई विषय लिखें।")

    if len(query) > 150:
        return json_error("फोटो खोज का शब्द 150 अक्षरों से छोटा रखें।")

    limit = bounded_limit(request.args.get("limit", 12), 12, 30)
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
        ),
    })


@app.route("/api/images", methods=["GET"])
def api_images():
    return api_images_search()


# ------------------------------------------------------------
# VIDEO SEARCH API
# Returns search links, not a live video feed.
# ------------------------------------------------------------

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
        "message": "ये वीडियो खोज के लिंक हैं, वास्तविक वीडियो सूची नहीं।",
    })


# ------------------------------------------------------------
# PLACES SEARCH API
# ------------------------------------------------------------

@app.route("/api/places", methods=["GET"])
def api_places():
    query = clean_text(request.args.get("q", ""))

    if not query:
        return json_error(
            "जगह, होटल, अस्पताल या पुलिस स्टेशन का नाम लिखें।"
        )

    if len(query) > 150:
        return json_error("जगह की खोज का शब्द बहुत लंबा है।")

    limit = bounded_limit(request.args.get("limit", 10), 10, 10)
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
        ),
    })


# ------------------------------------------------------------
# COMBINED SEARCH API
# ------------------------------------------------------------

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
        "message": "उपलब्ध खोज श्रेणियों के API लिंक तैयार हैं।",
    })


# ------------------------------------------------------------
# NEWS API
# ------------------------------------------------------------

@app.route("/api/news", methods=["GET"])
def api_news():
    query = clean_text(request.args.get("q", ""))
    refresh = request.args.get("refresh", "").casefold()
    force_refresh = refresh in ("1", "true", "yes")

    if len(query) > 150:
        return json_error("समाचार खोज का शब्द बहुत लंबा है।")

    news = fetch_news(query, force_refresh)
    limit = bounded_limit(request.args.get("limit", MAX_NEWS_ITEMS),
                          MAX_NEWS_ITEMS, MAX_NEWS_ITEMS)
    news = news[:limit]

    return jsonify({
        "success": True,
        "count": len(news),
        "query": query,
        "updated_at": utc_now(),
        "results": news,
        "news": news,
        "message": "" if news else "कोई खबर नहीं मिली।",
    })


@app.route("/api/latest-news", methods=["GET"])
def api_latest_news():
    return api_news()


# ------------------------------------------------------------
# WEATHER API
# ------------------------------------------------------------

@app.route("/api/weather", methods=["GET"])
def api_weather():
    place = clean_text(
        request.args.get("place", "")
        or request.args.get("city", "")
        or request.args.get("q", "")
    )

    if not place:
        return json_error("शहर या गाँव का नाम लिखें।")

    if len(place) > 100:
        return json_error("शहर का नाम बहुत लंबा है।")

    result = get_weather(place)

    if not result.get("success"):
        return jsonify(result), 502

    return jsonify(result)


@app.route("/api/current-weather", methods=["GET"])
def api_current_weather():
    return api_weather()


# ------------------------------------------------------------
# RATE SOURCES API
# Does not claim to return live market prices.
# ------------------------------------------------------------

@app.route("/api/rates", methods=["GET"])
def api_rates():
    place = clean_text(request.args.get("place", "Rajasthan"))
    return jsonify(get_rates(place))


# ------------------------------------------------------------
# OPTIONAL EDUCATION PAGE
# If education.html is not present, return a helpful response.
# ------------------------------------------------------------

@app.route("/education", methods=["GET"])
def education():
    try:
        return render_template("education.html")
    except Exception:
        return (
            "<!doctype html><html lang='hi'><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Ishwar Search - Education</title>"
            "<h1>Ishwar Search</h1>"
            "<p>Education पेज अभी तैयार नहीं है।</p>"
            "<a href='/'>होम पेज पर जाएँ</a></html>",
            200,
        )


# ------------------------------------------------------------
# ERROR HANDLERS
# ------------------------------------------------------------

@app.errorhandler(404)
def page_not_found(error):
    if request.path.startswith("/api/"):
        return jsonify({
            "success": False,
            "error": "यह API endpoint नहीं मिला।",
            "path": request.path,
        }), 404

    return (
        "<!doctype html><html lang='hi'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>404 | Ishwar Search</title>"
        "<h1>Ishwar Search</h1><p>यह पेज नहीं मिला।</p>"
        "<a href='/'>Ishwar Search पर वापस जाएँ</a></html>",
        404,
    )


@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({
        "success": False,
        "error": "इस अनुरोध का तरीका उपलब्ध नहीं है।",
    }), 405


@app.errorhandler(413)
def request_too_large(error):
    return jsonify({
        "success": False,
        "error": "अनुरोध बहुत बड़ा है।",
    }), 413


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
        "<!doctype html><html lang='hi'><meta charset='utf-8'>"
        "<title>500 | Ishwar Search</title>"
        "<h1>Ishwar Search</h1>"
        "<p>सर्वर में समस्या आई। कृपया बाद में प्रयास करें।</p>"
        "<a href='/'>होम पेज पर जाएँ</a></html>",
        500,
    )


# ------------------------------------------------------------
# SECURITY HEADERS
# ------------------------------------------------------------

@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"

    return response


# ------------------------------------------------------------
# RUN LOCALLY / RENDER
# ------------------------------------------------------------

# ------------------------------------------------------------
# PUSH NOTIFICATION SUBSCRIPTION API
# यह endpoint browser subscription को स्वीकार करता है।
# वास्तविक push notification के लिए Web Push configuration
# और subscription को सुरक्षित रूप से save करना जरूरी है।
# ------------------------------------------------------------

@app.route("/api/notifications/status", methods=["GET"])
def notification_status():
    return jsonify({
        "success": True,
        "app": APP_NAME,
        "notifications_available": True,
        "push_configured": False,
        "message": (
            "Notification API उपलब्ध है। "
            "वास्तविक push notification अभी configure करना बाकी है।"
        )
    })


@app.route("/api/notifications/subscribe", methods=["POST"])
def notification_subscribe():
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify({
            "success": False,
            "error": "सही JSON subscription भेजें।"
        }), 400

    subscription = payload.get("subscription")

    if not isinstance(subscription, dict):
        return jsonify({
            "success": False,
            "error": "Browser subscription नहीं मिला।"
        }), 400

    endpoint = subscription.get("endpoint")
    keys = subscription.get("keys")

    if (
        not isinstance(endpoint, str)
        or not endpoint.startswith("https://")
        or not isinstance(keys, dict)
        or not keys.get("p256dh")
        or not keys.get("auth")
    ):
        return jsonify({
            "success": False,
            "error": "Browser subscription का प्रारूप सही नहीं है।"
        }), 400

    # अभी subscription को save या इस्तेमाल नहीं किया जा रहा।
    # अगला चरण: इसे सुरक्षित database में save करना और
    # Web Push service से खबरों के notifications भेजना।

    return jsonify({
        "success": True,
        "saved": False,
        "push_configured": False,
        "message": (
            "Subscription प्राप्त हुआ, लेकिन अभी save नहीं हुआ। "
            "Push notification के लिए अगला चरण बाकी है।"
        )
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
    )
    
# ============================================================
# ISHWAR SEARCH PUSH NOTIFICATIONS
# Add this block BEFORE: if __name__ == "__main__":
# ============================================================

import base64
import json
from pathlib import Path
from flask import current_app

PUSH_DATA_FILE = os.path.join(BASE_DIR, "push_subscriptions.json")

PUSH_CATEGORIES = {
    "news",
    "jobs",
    "updates",
    "schemes",
    "fraud",
}


def load_push_subscriptions():
    try:
        with open(PUSH_DATA_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_push_subscriptions(items):
    temp_file = PUSH_DATA_FILE + ".tmp"

    with open(temp_file, "w", encoding="utf-8") as file:
        json.dump(items, file, ensure_ascii=False, indent=2)

    os.replace(temp_file, PUSH_DATA_FILE)


def get_vapid_public_key():
    return os.environ.get("VAPID_PUBLIC_KEY", "").strip()


@app.route("/api/notifications/public-key", methods=["GET"])
def notification_public_key():
    public_key = get_vapid_public_key()

    if not public_key:
        return jsonify({
            "success": False,
            "error": "Push Notification की public key अभी सेट नहीं है।"
        }), 503

    return jsonify({
        "success": True,
        "publicKey": public_key
    })


@app.route("/api/notifications/subscribe", methods=["POST"])
def notification_subscribe():
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return json_error("Subscription का JSON सही नहीं है।")

    endpoint = payload.get("endpoint")
    keys = payload.get("keys")

    if (
        not isinstance(endpoint, str)
        or not endpoint.startswith("https://")
        or not isinstance(keys, dict)
        or not isinstance(keys.get("p256dh"), str)
        or not isinstance(keys.get("auth"), str)
    ):
        return json_error("Push subscription अधूरा या गलत है।")

    subscriptions = load_push_subscriptions()

    new_item = {
        "endpoint": endpoint,
        "keys": {
            "p256dh": keys["p256dh"],
            "auth": keys["auth"]
        }
    }

    # एक ही endpoint को बार-बार सेव न करें
    subscriptions = [
        item for item in subscriptions
        if item.get("endpoint") != endpoint
    ]
    subscriptions.append(new_item)

    try:
        save_push_subscriptions(subscriptions)
    except OSError:
        logger.exception("Push subscription save failed")
        return jsonify({
            "success": False,
            "error": "Subscription सेव नहीं हो पाया।"
        }), 500

    return jsonify({
        "success": True,
        "message": "Push subscription सेव हो गया।"
    })


@app.route("/api/notifications/unsubscribe", methods=["POST"])
def notification_unsubscribe():
    payload = request.get_json(silent=True) or {}
    endpoint = payload.get("endpoint")

    if not isinstance(endpoint, str):
        return json_error("Subscription endpoint नहीं मिला।")

    subscriptions = load_push_subscriptions()
    remaining = [
        item for item in subscriptions
        if item.get("endpoint") != endpoint
    ]

    try:
        save_push_subscriptions(remaining)
    except OSError:
        logger.exception("Push unsubscribe save failed")
        return jsonify({
            "success": False,
            "error": "Subscription हटाया नहीं जा सका।"
        }), 500

    return jsonify({"success": True})


@app.route("/api/notifications/send", methods=["POST"])
def notification_send():
    # केवल secret admin token वाला अनुरोध notification भेज सकता है।
    admin_secret = os.environ.get("NOTIFICATION_ADMIN_TOKEN", "")
    supplied_token = request.headers.get("X-Admin-Token", "")

    if not admin_secret or not supplied_token:
        return jsonify({
            "success": False,
            "error": "Admin authorization सेट नहीं है।"
        }), 403

    import hmac
    if not hmac.compare_digest(supplied_token, admin_secret):
        return jsonify({
            "success": False,
            "error": "Admin authorization गलत है।"
        }), 403

    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return json_error("Notification का JSON सही नहीं है।")

    category = str(payload.get("category", "")).strip().lower()
    title = clean_text(payload.get("title", ""))
    body = clean_text(payload.get("body", ""))
    target_url = str(payload.get("url", "/")).strip()

    if category not in PUSH_CATEGORIES:
        return json_error("Category news, jobs, updates, schemes या fraud होनी चाहिए।")

    if not title or not body:
        return json_error("Title और body दोनों जरूरी हैं।")

    if len(title) > 100 or len(body) > 300:
        return json_error("Title 100 और body 300 अक्षरों तक रखें।")

    # Notifications केवल अपनी वेबसाइट के URLs खोलें।
    from urllib.parse import urlparse
    parsed = urlparse(target_url)

    if target_url.startswith("/") and not target_url.startswith("//"):
        safe_target_url = target_url
    elif parsed.scheme == "https" and parsed.netloc == request.host:
        safe_target_url = target_url
    else:
        return json_error("Notification URL अपनी वेबसाइट का relative path होना चाहिए।")

    private_key = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
    public_key = get_vapid_public_key()

    if not private_key or not public_key:
        return jsonify({
            "success": False,
            "error": "VAPID keys सेट नहीं हैं।"
        }), 503

    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        return jsonify({
            "success": False,
            "error": "pywebpush dependency इंस्टॉल नहीं है।"
        }), 503

    subscriptions = load_push_subscriptions()
    delivered = 0
    failed = 0
    expired_endpoints = set()

    message = {
        "title": title,
        "body": body,
        "url": safe_target_url,
        "tag": "ishwar-" + category
    }

    for subscription in subscriptions:
        try:
            webpush(
                subscription_info=subscription,
                data=json.dumps(message, ensure_ascii=False),
                vapid_private_key=private_key,
                vapid_claims={
                    "sub": os.environ.get(
                        "VAPID_SUBJECT",
                        "mailto:admin@example.com"
                    )
                },
                ttl=3600,
            )
            delivered += 1

        except WebPushException as exc:
            failed += 1

            response = getattr(exc, "response", None)
            status_code = getattr(response, "status_code", None)

            # 404/410 usually means the subscription has expired.
            if status_code in (404, 410):
                expired_endpoints.add(subscription.get("endpoint"))

            logger.warning("Push delivery failed: %s", exc)

        except Exception:
            failed += 1
            logger.exception("Unexpected Push delivery error")

    if expired_endpoints:
        subscriptions = [
            item for item in subscriptions
            if item.get("endpoint") not in expired_endpoints
        ]
        try:
            save_push_subscriptions(subscriptions)
        except OSError:
            logger.exception("Could not clean expired subscriptions")

    return jsonify({
        "success": True,
        "category": category,
        "attempted": len(subscriptions) + len(expired_endpoints),
        "sent": delivered,
        "failed": failed,
        "message": "Push भेजने का प्रयास पूरा हुआ।"
    })

    if __name__ == "__main__":


